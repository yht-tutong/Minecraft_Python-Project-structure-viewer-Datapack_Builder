# gui.py
# PyQt5 图形界面：项目设置、文件树预览、依赖关系图、进度监控

import os
import sys
import json
import struct
import socket
import threading

from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QTextEdit, QProgressBar,
    QSplitter, QFileDialog, QMessageBox, QDialog, QFormLayout,
    QSpinBox, QDialogButtonBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor

# 导入项目内模块
from scanner import ProjectScanner
from datapack_generator import DatapackGenerator


# ------------------------------------------------------------------
# RCON 通信
# ------------------------------------------------------------------

class RconClient:
    """标准 RCON 协议客户端

    参考: https://wiki.vg/RCON
    数据包格式:
        Length (int32 LE) | Request ID (int32 LE) | Type (int32 LE) |
        Payload (null-terminated ASCII) | Padding (0x00)
    """

    TYPE_LOGIN = 3
    TYPE_COMMAND = 2
    TYPE_RESPONSE = 0

    def __init__(self, host: str = "127.0.0.1", port: int = 25575, password: str = ""):
        self.host = host
        self.port = port
        self.password = password
        self._sock: socket.socket | None = None
        self._request_id = 0

    def connect(self) -> bool:
        """建立 TCP 连接并登录 RCON"""
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(5)
            self._sock.connect((self.host, self.port))
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            self._sock = None
            raise ConnectionError(f"无法连接到 RCON 服务器 {self.host}:{self.port}") from e

        # 登录
        self._request_id = 0
        try:
            self._send_packet(self.TYPE_LOGIN, self.password)
            self._request_id += 1
            # 收到响应就表示登录成功（失败会关闭连接）
            _ = self._recv_packet()
            return True
        except Exception as e:
            self._sock.close()
            self._sock = None
            raise ConnectionError("RCON 登录失败，请检查密码") from e

    def send_command(self, command: str) -> str:
        """发送命令并返回响应"""
        if self._sock is None:
            raise ConnectionError("RCON 未连接")
        self._request_id += 1
        self._send_packet(self.TYPE_COMMAND, command)
        return self._recv_packet()

    def close(self):
        """关闭连接"""
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _send_packet(self, packet_type: int, payload: str):
        """发送 RCON 数据包"""
        payload_bytes = payload.encode("utf-8") + b"\x00"
        length = 10 + len(payload_bytes)  # 4(request_id) + 4(type) + payload + 2(padding)
        data = struct.pack("<iii", length, self._request_id, packet_type) + payload_bytes + b"\x00"
        self._sock.sendall(data)

    def _recv_packet(self) -> str:
        """接收 RCON 响应数据包"""
        # 读取长度
        raw = self._sock.recv(4)
        if len(raw) < 4:
            raise ConnectionError("RCON 连接已断开")
        length = struct.unpack("<i", raw)[0]
        # 读取剩余数据
        data = b""
        while len(data) < length:
            chunk = self._sock.recv(length - len(data))
            if not chunk:
                raise ConnectionError("RCON 连接已断开")
            data += chunk
        # 解析: request_id(4) + type(4) + payload(null-terminated) + padding(1)
        if len(data) < 10:
            return ""
        payload_bytes = data[8:-1]  # 跳过 request_id(4) + type(4)，去掉末尾 padding
        return payload_bytes.decode("utf-8", errors="replace")


# ------------------------------------------------------------------
# RCON 配置弹窗
# ------------------------------------------------------------------

class RconConfigDialog(QDialog):
    """RCON 连接参数配置对话框"""

    def __init__(self, parent=None, host="127.0.0.1", port=25575, password=""):
        super().__init__(parent)
        self.setWindowTitle("RCON 配置")
        self.setMinimumWidth(320)

        layout = QFormLayout(self)

        self.host_edit = QLineEdit(host)
        layout.addRow("主机:", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(port)
        layout.addRow("端口:", self.port_spin)

        self.password_edit = QLineEdit(password)
        self.password_edit.setEchoMode(QLineEdit.Password)
        layout.addRow("密码:", self.password_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

    def get_values(self):
        """返回 (host, port, password) 元组"""
        return (
            self.host_edit.text().strip(),
            self.port_spin.value(),
            self.password_edit.text(),
        )


# ------------------------------------------------------------------
# 工作线程
# ------------------------------------------------------------------

class ScanThread(QThread):
    """后台扫描线程，避免阻塞 UI"""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, source_path: str):
        super().__init__()
        self.source_path = source_path

    def run(self):
        try:
            scanner = ProjectScanner(self.source_path)
            result = scanner.scan(progress_callback=self._on_progress)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, percent: int, message: str):
        self.progress.emit(percent, message)


class GenerateThread(QThread):
    """后台生成线程，避免阻塞 UI"""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, scan_result: dict, output_path: str, datapack_name: str):
        super().__init__()
        self.scan_result = scan_result
        self.output_path = output_path
        self.datapack_name = datapack_name

    def run(self):
        try:
            generator = DatapackGenerator(
                self.scan_result, self.output_path, self.datapack_name
            )
            result_path = generator.generate(progress_callback=self._on_progress)
            self.finished.emit(result_path)
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, percent: int, message: str):
        self.progress.emit(percent, message)


# ------------------------------------------------------------------
# 主窗口
# ------------------------------------------------------------------

class ProjectViewerGUI(QMainWindow):
    """Minecraft 项目结构查看器 - 数据包生成器 主窗口"""

    # 文件类型 → 颜色映射
    FILE_COLORS = {
        ".py": QColor("#569CD6"),         # 蓝色
        ".mcfunction": QColor("#CE9178"), # 橙色
        ".json": QColor("#6A9955"),       # 绿色
        ".png": QColor("#C586C0"),        # 紫色
        ".jpg": QColor("#C586C0"),
        ".jpeg": QColor("#C586C0"),
        ".gif": QColor("#C586C0"),
        ".bmp": QColor("#C586C0"),
        ".svg": QColor("#C586C0"),
        ".webp": QColor("#C586C0"),
    }

    DIR_COLOR = QColor("#FFD700")  # 金色

    def __init__(self):
        super().__init__()
        self._scan_result: dict | None = None  # 最近一次扫描结果
        self._rcon_config = {"host": "127.0.0.1", "port": 25575, "password": ""}
        self._scan_thread: ScanThread | None = None
        self._generate_thread: GenerateThread | None = None

        # 自动运行相关
        self._auto_cycle_active = False
        self.auto_timer = QTimer()
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self._on_countdown_tick)
        self.remaining_seconds = 30

        self._init_ui()
        self._load_default_config()

        # 检查配置是否有效，无效则弹出首次配置引导
        if not self._is_config_valid():
            QTimer.singleShot(500, self._show_setup_dialog)

    # ------------------------------------------------------------------
    # UI 初始化
    # ------------------------------------------------------------------

    def _init_ui(self):
        """初始化全部界面组件"""
        self.setWindowTitle("Minecraft 项目结构查看器 - 数据包生成器")
        self.resize(1000, 700)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # ---- 设置面板 ----
        main_layout.addWidget(self._create_settings_panel())

        # ---- 主内容区（QSplitter） ----
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._create_file_tree_panel())
        splitter.addWidget(self._create_dependency_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter, 1)

        # ---- 底部进度区 ----
        main_layout.addLayout(self._create_progress_bar_area())

    def _create_settings_panel(self) -> QGroupBox:
        """创建设置面板"""
        group = QGroupBox("设置")
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        # 源项目路径
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("源项目路径:"))
        self.src_path_edit = QLineEdit()
        self.src_path_edit.setPlaceholderText("选择要扫描的 Python 项目目录...")
        row1.addWidget(self.src_path_edit, 1)
        btn_browse_src = QPushButton("浏览...")
        btn_browse_src.clicked.connect(self._browse_src_path)
        row1.addWidget(btn_browse_src)
        layout.addLayout(row1)

        # 输出路径
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("输出路径:"))
        self.out_path_edit = QLineEdit()
        self.out_path_edit.setPlaceholderText("选择 Minecraft 存档的 datapacks 目录...")
        row2.addWidget(self.out_path_edit, 1)
        btn_browse_out = QPushButton("浏览...")
        btn_browse_out.clicked.connect(self._browse_out_path)
        row2.addWidget(btn_browse_out)
        layout.addLayout(row2)

        # 数据包名称 + 生成按钮
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("数据包名:"))
        self.datapack_name_edit = QLineEdit("project-structure-viewer")
        row3.addWidget(self.datapack_name_edit, 1)
        self.btn_generate = QPushButton("生成数据包")
        self.btn_generate.clicked.connect(self.generate_datapack)
        row3.addWidget(self.btn_generate)
        layout.addLayout(row3)

        # 自动运行
        row_auto = QHBoxLayout()
        self.auto_run_checkbox = QCheckBox("自动运行")
        self.auto_run_checkbox.setToolTip("定时自动扫描并生成数据包")
        self.auto_run_checkbox.toggled.connect(self._on_auto_run_toggled)
        row_auto.addWidget(self.auto_run_checkbox)
        row_auto.addWidget(QLabel("间隔:"))
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(10, 300)
        self.interval_spinbox.setValue(30)
        self.interval_spinbox.setSuffix(" 秒")
        self.interval_spinbox.setToolTip("自动扫描间隔（10-300 秒）")
        row_auto.addWidget(self.interval_spinbox)
        self.countdown_label = QLabel("下次扫描: 30s")
        row_auto.addWidget(self.countdown_label)
        row_auto.addStretch()
        layout.addLayout(row_auto)

        # 自动 reload + RCON 配置
        row4 = QHBoxLayout()
        self.auto_reload_check = QCheckBox("自动 reload")
        self.auto_reload_check.setToolTip("生成完成后自动通过 RCON 发送 /reload 命令")
        row4.addWidget(self.auto_reload_check)
        row4.addStretch()
        btn_rcon = QPushButton("RCON 配置...")
        btn_rcon.clicked.connect(self._open_rcon_dialog)
        row4.addWidget(btn_rcon)
        layout.addLayout(row4)

        return group

    def _create_file_tree_panel(self) -> QWidget:
        """创建左侧文件树面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("文件树"))

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setAlternatingRowColors(True)
        self.file_tree.itemClicked.connect(self._on_file_tree_item_clicked)
        layout.addWidget(self.file_tree, 1)

        return panel

    def _create_dependency_panel(self) -> QWidget:
        """创建右侧依赖关系面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("依赖关系"))

        self.dep_text = QTextEdit()
        self.dep_text.setReadOnly(True)
        font = QFont("Consolas", 10)
        self.dep_text.setFont(font)
        layout.addWidget(self.dep_text, 1)

        return panel

    def _create_progress_bar_area(self) -> QHBoxLayout:
        """创建底部进度条区域"""
        layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar, 1)

        self.status_label = QLabel("就绪")
        self.status_label.setMinimumWidth(200)
        layout.addWidget(self.status_label)

        self.auto_status_label = QLabel("○ 已停止")
        self.auto_status_label.setStyleSheet("color: #888888;")
        layout.addWidget(self.auto_status_label)
        return layout

    # ------------------------------------------------------------------
    # 配置加载
    # ------------------------------------------------------------------

    def load_config(self, config_path: str):
        """从配置文件加载设置"""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            QMessageBox.warning(self, "配置加载失败", f"无法读取配置文件:\n{e}")
            return

        if "source_path" in config:
            self.src_path_edit.setText(config["source_path"])
        if "mc_saves_path" in config:
            self.out_path_edit.setText(config["mc_saves_path"])
        if "output_datapack_name" in config:
            self.datapack_name_edit.setText(config["output_datapack_name"])
        if "auto_run" in config:
            self.auto_run_checkbox.setChecked(config["auto_run"])
        if "interval_seconds" in config:
            self.interval_spinbox.setValue(config["interval_seconds"])
        if "rcon" in config:
            rcon = config["rcon"]
            self._rcon_config["host"] = rcon.get("host", "127.0.0.1")
            self._rcon_config["port"] = rcon.get("port", 25575)
            self._rcon_config["password"] = rcon.get("password", "")
            self.auto_reload_check.setChecked(rcon.get("enabled", False))

    def _load_default_config(self):
        """尝试加载默认的 config.json"""
        default_path = os.path.join(os.path.dirname(__file__), "config.json")
        if os.path.isfile(default_path):
            self.load_config(default_path)

    # ------------------------------------------------------------------
    # 浏览按钮
    # ------------------------------------------------------------------

    def _browse_src_path(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择源项目目录")
        if dir_path:
            self.src_path_edit.setText(dir_path)

    def _browse_out_path(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录 (datapacks)")
        if dir_path:
            self.out_path_edit.setText(dir_path)

    # ------------------------------------------------------------------
    # RCON 配置
    # ------------------------------------------------------------------

    def _open_rcon_dialog(self):
        dialog = RconConfigDialog(
            self,
            host=self._rcon_config["host"],
            port=self._rcon_config["port"],
            password=self._rcon_config["password"],
        )
        if dialog.exec_() == QDialog.Accepted:
            host, port, password = dialog.get_values()
            self._rcon_config["host"] = host
            self._rcon_config["port"] = port
            self._rcon_config["password"] = password

    # ------------------------------------------------------------------
    # 自动运行
    # ------------------------------------------------------------------

    def _on_auto_run_toggled(self, checked: bool):
        """自动运行复选框切换"""
        if checked:
            self._start_auto_run()
        else:
            self._stop_auto_run()

    def _start_auto_run(self):
        """启动自动运行定时器"""
        self.remaining_seconds = self.interval_spinbox.value()
        self._update_countdown_label()
        self.countdown_timer.start(1000)
        self.auto_status_label.setText("● 自动运行中")
        self.auto_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")

    def _stop_auto_run(self):
        """停止自动运行定时器"""
        self.countdown_timer.stop()
        self.auto_status_label.setText("○ 已停止")
        self.auto_status_label.setStyleSheet("color: #888888;")
        self._set_status(0, "自动运行已停止")

    def _update_countdown_label(self):
        """更新倒计时标签文字"""
        self.countdown_label.setText(f"下次扫描: {self.remaining_seconds}s")

    def _on_countdown_tick(self):
        """倒计时每秒触发"""
        self.remaining_seconds -= 1
        self._update_countdown_label()
        if self.remaining_seconds <= 0:
            if not self._auto_cycle_active:
                self.auto_run_cycle()
            else:
                # 上一次还没完成，跳过本次，重置倒计时
                self.remaining_seconds = self.interval_spinbox.value()
                self._update_countdown_label()

    def auto_run_cycle(self):
        """执行一次自动运行周期：扫描 → 生成 → reload"""
        src_path = self.src_path_edit.text().strip()
        if not src_path or not os.path.isdir(src_path):
            self._set_status(0, "源项目路径无效，跳过本次扫描")
            self._finish_auto_cycle()
            return
        self._auto_cycle_active = True
        self._set_status(0, "正在扫描...")
        self.scan_project()

    def _auto_generate(self):
        """自动运行模式下，扫描完成后自动触发生成"""
        out_path = self.out_path_edit.text().strip()
        datapack_name = self.datapack_name_edit.text().strip()
        if not out_path or not os.path.isdir(out_path) or not datapack_name:
            self._set_status(0, "生成参数无效，跳过")
            self._finish_auto_cycle()
            return

        self._set_status(0, "正在生成数据包...")
        self._generate_thread = GenerateThread(
            self._scan_result, out_path, datapack_name
        )
        self._generate_thread.progress.connect(self._set_status)
        self._generate_thread.finished.connect(self._on_generate_finished)
        self._generate_thread.error.connect(self._on_generate_error)
        self._generate_thread.start()

    def _auto_reload_for_cycle(self):
        """自动运行模式下的 reload"""
        self._set_status(100, "正在通过 RCON 发送 /reload...")

        def _do_reload():
            rcon = RconClient(
                host=self._rcon_config["host"],
                port=self._rcon_config["port"],
                password=self._rcon_config["password"],
            )
            try:
                rcon.connect()
                response = rcon.send_command("/reload")
                self._on_cycle_reload_result(response)
            except Exception as e:
                self._on_cycle_reload_result(f"错误: {e}")
            finally:
                rcon.close()

        t = threading.Thread(target=_do_reload, daemon=True)
        t.start()

    def _on_cycle_reload_result(self, result: str):
        """自动运行模式下 reload 结果回调（可能在子线程）"""
        def _update():
            if result.startswith("错误:"):
                self.status_label.setText(f"RCON 失败: {result}")
            self._finish_auto_cycle()
        QTimer.singleShot(0, _update)

    def _finish_auto_cycle(self):
        """完成一次自动运行周期，重置倒计时"""
        self._auto_cycle_active = False
        self.remaining_seconds = self.interval_spinbox.value()
        self._update_countdown_label()
        self._set_status(100, f"完成！下次扫描: {self.remaining_seconds}s")

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------

    def scan_project(self):
        """扫描项目并更新文件树"""
        src_path = self.src_path_edit.text().strip()
        if not src_path:
            QMessageBox.warning(self, "提示", "请先选择源项目路径")
            return
        if not os.path.isdir(src_path):
            QMessageBox.warning(self, "提示", f"源项目路径不存在:\n{src_path}")
            return

        self.btn_generate.setEnabled(False)
        self.file_tree.clear()
        self.dep_text.clear()
        self._set_status(0, "正在扫描文件...")

        self._scan_thread = ScanThread(src_path)
        self._scan_thread.progress.connect(self._set_status)
        self._scan_thread.finished.connect(self._on_scan_finished)
        self._scan_thread.error.connect(self._on_scan_error)
        self._scan_thread.start()

    def _on_scan_finished(self, result: dict):
        """扫描完成回调"""
        self._scan_result = result
        self._populate_file_tree(result.get("file_tree"))
        self._set_status(100, "扫描完成")
        self.btn_generate.setEnabled(True)
        # 自动运行模式下，扫描完成后自动触发生成
        if self._auto_cycle_active:
            self._auto_generate()

    def _on_scan_error(self, error_msg: str):
        """扫描出错回调"""
        self._set_status(0, f"扫描失败: {error_msg}")
        self.btn_generate.setEnabled(True)
        if self._auto_cycle_active:
            self.status_label.setText(f"扫描失败: {error_msg}")
            self._finish_auto_cycle()
        else:
            QMessageBox.critical(self, "扫描失败", error_msg)

    # ------------------------------------------------------------------
    # 文件树填充
    # ------------------------------------------------------------------

    def _populate_file_tree(self, file_tree: dict | None):
        """将文件树数据填充到 QTreeWidget"""
        self.file_tree.clear()
        if not file_tree:
            return

        root_name = file_tree.get("name", "")
        root_item = QTreeWidgetItem(self.file_tree, [root_name])
        root_item.setData(0, Qt.UserRole, file_tree)  # 存储原始数据
        root_item.setForeground(0, self.DIR_COLOR)

        for child in file_tree.get("children", []):
            self._add_tree_item(root_item, child)

        self.file_tree.expandAll()

    def _add_tree_item(self, parent: QTreeWidgetItem, node: dict):
        """递归添加文件树节点"""
        name = node.get("name", "")
        node_type = node.get("type", "file")

        item = QTreeWidgetItem(parent, [name])
        item.setData(0, Qt.UserRole, node)  # 存储原始数据

        if node_type == "directory":
            item.setForeground(0, self.DIR_COLOR)
            for child in node.get("children", []):
                self._add_tree_item(item, child)
        else:
            ext = node.get("ext", "").lower()
            color = self.FILE_COLORS.get(ext, QColor("white"))
            item.setForeground(0, color)

    # ------------------------------------------------------------------
    # 文件树点击 → 显示依赖关系
    # ------------------------------------------------------------------

    def _on_file_tree_item_clicked(self, item: QTreeWidgetItem, column: int):
        """点击文件树节点时，在右侧显示依赖关系"""
        node = item.data(0, Qt.UserRole)
        if node is None or node.get("type") != "file":
            self.dep_text.clear()
            return

        file_path = node.get("path", "")
        self._show_dependencies(file_path)

    def _show_dependencies(self, file_path: str):
        """在右侧面板显示指定文件的依赖关系"""
        if self._scan_result is None:
            self.dep_text.clear()
            return

        dependencies = self._scan_result.get("dependencies", {})
        function_calls = self._scan_result.get("function_calls", {})

        html_parts = []
        file_name = os.path.basename(file_path)

        # 标题
        html_parts.append(
            f'<h3 style="color:#FFD700;">📄 {file_name}</h3>'
        )

        ext = os.path.splitext(file_path)[1].lower()

        # Python import 依赖
        if ext == ".py" and file_path in dependencies:
            imports = dependencies[file_path]
            if imports:
                html_parts.append(
                    '<p style="color:#569CD6;"><b>→ imports:</b></p><ul>'
                )
                for imp in imports:
                    html_parts.append(
                        f'<li style="color:#569CD6;">{imp}</li>'
                    )
                html_parts.append('</ul>')
            else:
                html_parts.append(
                    '<p style="color:#888;">→ 无 import 依赖</p>'
                )

            # 被依赖（反向查找）
            reverse_deps = []
            for other_file, other_imports in dependencies.items():
                if other_file == file_path:
                    continue
                base = os.path.splitext(os.path.basename(file_path))[0]
                if base in other_imports:
                    reverse_deps.append(other_file)
            if reverse_deps:
                html_parts.append(
                    '<p style="color:#9CDCFE;"><b>← imported by:</b></p><ul>'
                )
                for dep in reverse_deps:
                    html_parts.append(
                        f'<li style="color:#9CDCFE;">{os.path.basename(dep)}</li>'
                    )
                html_parts.append('</ul>')

        # .mcfunction 调用关系
        if ext == ".mcfunction" and file_path in function_calls:
            calls = function_calls[file_path]
            if calls:
                html_parts.append(
                    '<p style="color:#CE9178;"><b>→ calls:</b></p><ul>'
                )
                for call in calls:
                    html_parts.append(
                        f'<li style="color:#CE9178;">{call}</li>'
                    )
                html_parts.append('</ul>')
            else:
                html_parts.append(
                    '<p style="color:#888;">→ 无 function 调用</p>'
                )

            # 被调用（反向查找）
            reverse_calls = []
            for other_file, other_calls in function_calls.items():
                if other_file == file_path:
                    continue
                # 检查 other_file 是否调用了该文件
                for call in other_calls:
                    # 将 file_path 转为 namespace:path 格式做简单匹配
                    file_base = os.path.splitext(os.path.basename(file_path))[0]
                    if file_base in call:
                        reverse_calls.append(other_file)
                        break
            if reverse_calls:
                html_parts.append(
                    '<p style="color:#C586C0;"><b>← called by:</b></p><ul>'
                )
                for dep in reverse_calls:
                    html_parts.append(
                        f'<li style="color:#C586C0;">{os.path.basename(dep)}</li>'
                    )
                html_parts.append('</ul>')

        if not html_parts:
            html_parts.append(
                '<p style="color:#888;">没有依赖关系信息</p>'
            )

        self.dep_text.setHtml("".join(html_parts))

    # ------------------------------------------------------------------
    # 生成数据包
    # ------------------------------------------------------------------

    def generate_datapack(self):
        """生成数据包：先扫描（如需要），再生成"""
        # 保存当前配置到 config.json
        self._save_config()

        out_path = self.out_path_edit.text().strip()
        if not out_path:
            QMessageBox.warning(self, "提示", "请先选择输出路径")
            return
        if not os.path.isdir(out_path):
            QMessageBox.warning(self, "提示", f"输出路径不存在:\n{out_path}")
            return

        datapack_name = self.datapack_name_edit.text().strip()
        if not datapack_name:
            QMessageBox.warning(self, "提示", "请输入数据包名称")
            return

        # 如果还没扫描过，先扫描
        if self._scan_result is None:
            src_path = self.src_path_edit.text().strip()
            if not src_path or not os.path.isdir(src_path):
                QMessageBox.warning(self, "提示", "请先选择源项目路径并扫描")
                return
            # 同步扫描（简单场景）
            self._set_status(0, "正在扫描文件...")
            try:
                scanner = ProjectScanner(src_path)
                self._scan_result = scanner.scan(
                    progress_callback=lambda p, m: self._set_status(p, m)
                )
                self._populate_file_tree(self._scan_result.get("file_tree"))
            except Exception as e:
                self._set_status(0, f"扫描失败: {e}")
                QMessageBox.critical(self, "扫描失败", str(e))
                return

        self.btn_generate.setEnabled(False)
        self._set_status(0, "正在生成数据包...")

        self._generate_thread = GenerateThread(
            self._scan_result, out_path, datapack_name
        )
        self._generate_thread.progress.connect(self._set_status)
        self._generate_thread.finished.connect(self._on_generate_finished)
        self._generate_thread.error.connect(self._on_generate_error)
        self._generate_thread.start()

    def _on_generate_finished(self, result_path: str):
        """生成完成回调"""
        self._set_status(100, "完成！")
        self.btn_generate.setEnabled(True)

        if self._auto_cycle_active:
            # 自动运行模式：不弹窗，链式执行 reload
            if self.auto_reload_check.isChecked() and self._rcon_config.get("password"):
                self._auto_reload_for_cycle()
            else:
                self._finish_auto_cycle()
        else:
            QMessageBox.information(
                self, "生成完成",
                f"数据包已生成到:\n{result_path}"
            )
            # 自动 reload
            if self.auto_reload_check.isChecked():
                self._auto_reload()

    def _on_generate_error(self, error_msg: str):
        """生成出错回调"""
        self._set_status(0, f"生成失败: {error_msg}")
        self.btn_generate.setEnabled(True)
        if self._auto_cycle_active:
            self.status_label.setText(f"生成失败: {error_msg}")
            self._finish_auto_cycle()
        else:
            QMessageBox.critical(self, "生成失败", error_msg)

    # ------------------------------------------------------------------
    # 自动 reload
    # ------------------------------------------------------------------

    def _auto_reload(self):
        """生成完成后自动发送 /reload 命令"""
        if not self._rcon_config["password"]:
            QMessageBox.warning(
                self, "自动 reload",
                "未配置 RCON 密码，请在 RCON 配置中设置密码"
            )
            return

        self._set_status(100, "正在通过 RCON 发送 /reload...")

        def _do_reload():
            rcon = RconClient(
                host=self._rcon_config["host"],
                port=self._rcon_config["port"],
                password=self._rcon_config["password"],
            )
            try:
                rcon.connect()
                response = rcon.send_command("/reload")
                # 在主线程显示结果
                self._on_reload_result(response)
            except Exception as e:
                self._on_reload_result(f"错误: {e}")
            finally:
                rcon.close()

        t = threading.Thread(target=_do_reload, daemon=True)
        t.start()

    def _on_reload_result(self, result: str):
        """在主线程更新 reload 结果（线程安全由 QTimer 保证）"""
        def _update():
            self._set_status(100, f"Reload 结果: {result.strip()}")
            if result.startswith("错误:"):
                QMessageBox.warning(self, "自动 reload 失败", result)
        QTimer.singleShot(0, _update)

    # ------------------------------------------------------------------
    # 公共 API: RCON
    # ------------------------------------------------------------------

    def send_rcon_command(self, command: str):
        """发送 RCON 命令（公开接口）"""
        rcon = RconClient(
            host=self._rcon_config["host"],
            port=self._rcon_config["port"],
            password=self._rcon_config["password"],
        )
        try:
            rcon.connect()
            response = rcon.send_command(command)
            rcon.close()
            return response
        except Exception as e:
            if rcon:
                rcon.close()
            raise ConnectionError(f"RCON 命令发送失败: {e}") from e

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _set_status(self, percent: int, message: str):
        """更新进度条和状态文字"""
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)

    # ------------------------------------------------------------------
    # 首次配置引导
    # ------------------------------------------------------------------

    def _is_config_valid(self):
        """检查当前配置是否有效（不是默认空值）"""
        src = self.src_path_edit.text().strip()
        if not src or src == "e:/Project/YourProject":
            return False
        return True

    def _save_config(self):
        """保存当前设置到 config.json"""
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        config = {
            "source_path": self.src_path_edit.text().strip(),
            "output_datapack_name": self.datapack_name_edit.text().strip(),
            "mc_saves_path": self.out_path_edit.text().strip(),
            "auto_run": self.auto_run_checkbox.isChecked(),
            "interval_seconds": self.interval_spinbox.value(),
            "rcon": {
                "enabled": self.auto_reload_check.isChecked(),
                "host": self._rcon_config["host"],
                "port": self._rcon_config["port"],
                "password": self._rcon_config["password"]
            }
        }
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except IOError:
            pass  # 静默失败，不影响使用

    def _browse_dir(self, line_edit):
        """浏览文件夹并填入 QLineEdit"""
        path = QFileDialog.getExistingDirectory(self, "选择目录")
        if path:
            line_edit.setText(path)

    def _show_setup_dialog(self):
        """首次使用配置引导对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("首次使用 - 配置引导")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)

        # 标题
        title = QLabel("欢迎使用 Minecraft 项目结构查看器！\n请填写以下配置信息：")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        # 表单
        form = QFormLayout()

        src_edit = QLineEdit()
        src_btn = QPushButton("浏览...")
        src_row = QHBoxLayout()
        src_row.addWidget(src_edit)
        src_row.addWidget(src_btn)
        src_btn.clicked.connect(lambda: self._browse_dir(src_edit))
        form.addRow("源项目路径:", src_row)

        out_edit = QLineEdit()
        out_btn = QPushButton("浏览...")
        out_row = QHBoxLayout()
        out_row.addWidget(out_edit)
        out_row.addWidget(out_btn)
        out_btn.clicked.connect(lambda: self._browse_dir(out_edit))
        form.addRow("Minecraft datapacks 目录:", out_row)

        name_edit = QLineEdit("project-structure-viewer")
        form.addRow("数据包名称:", name_edit)

        layout.addLayout(form)

        # 提示
        hint = QLabel("提示：之后可在设置面板中随时修改这些配置。")
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)

        # 按钮
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存配置")
        skip_btn = QPushButton("跳过")
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(skip_btn)
        layout.addLayout(btn_layout)

        def on_save():
            self.src_path_edit.setText(src_edit.text().strip())
            self.out_path_edit.setText(out_edit.text().strip())
            self.datapack_name_edit.setText(name_edit.text().strip())
            self._save_config()
            dialog.accept()

        def on_skip():
            dialog.accept()

        save_btn.clicked.connect(on_save)
        skip_btn.clicked.connect(on_skip)

        dialog.exec_()


# ------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------

def main():
    """启动 GUI"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ProjectViewerGUI()
    window.show()
    # 自动执行一次扫描（如果路径已填写）
    if window.src_path_edit.text().strip():
        QTimer.singleShot(300, window.scan_project)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
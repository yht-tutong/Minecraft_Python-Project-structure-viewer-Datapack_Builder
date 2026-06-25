# fluent_gui.py
# Fluent Design GUI 主窗口 - 参考 DyberPet 项目结构

import os
import sys
import json
import time
import socket
import threading
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout
from qfluentwidgets import (
    FluentWindow, NavigationInterface, NavigationItemPosition,
    PushButton, PrimaryPushButton, LineEdit, TextEdit, SpinBox,
    SwitchSettingCard, ComboBoxSettingCard, ScrollArea, ExpandLayout,
    SettingCardGroup, InfoBar, InfoBarPosition, MessageBox,
    ProgressRing, BodyLabel, StrongBodyLabel, CaptionLabel,
    setTheme, Theme, FluentIcon as FIF
)

from scanner import ProjectScanner
from datapack_generator import DatapackGenerator


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


class ScanWorker(QThread):
    """后台扫描和生成工作线程"""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str, dict)

    def __init__(self, source_path, output_path, name):
        super().__init__()
        self.source_path = source_path
        self.output_path = output_path
        self.name = name
        self._running = True

    def run(self):
        try:
            self.progress.emit(0, "正在扫描项目...")
            scanner = ProjectScanner(self.source_path)
            scan_result = scanner.scan(progress_callback=self._scan_progress)

            self.progress.emit(50, "正在生成数据包...")
            generator = DatapackGenerator(scan_result, self.output_path, self.name)
            datapack_path = generator.generate(progress_callback=self._gen_progress)

            stats = scan_result.get("_stats", {})
            result = {
                "datapack_path": datapack_path,
                "scan_result": scan_result,
                "stats": stats,
                "file_count": stats.get("file_count", 0),
                "dir_count": stats.get("dir_count", 0),
            }
            self.finished.emit(True, datapack_path, result)
        except Exception as e:
            self.finished.emit(False, str(e), {})

    def _scan_progress(self, percent, message):
        mapped = int(percent * 0.5)
        self.progress.emit(mapped, f"[扫描] {message}")

    def _gen_progress(self, percent, message):
        mapped = 50 + int(percent * 0.5)
        self.progress.emit(mapped, f"[生成] {message}")

    def stop(self):
        self._running = False


class HomeInterface(ScrollArea):
    """首页面板"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("HomeInterface")
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)

        self.source_path = ""
        self.output_path = ""
        self.datapack_name = "project-structure-viewer"
        self.auto_run_enabled = False
        self.interval_seconds = 30
        self.timer = QTimer()
        self.timer.timeout.connect(self._on_timer)
        self.countdown = 0
        self.scan_worker = None
        self.log_callback = None

        self._init_ui()

    def _init_ui(self):
        # 标题区域
        header_group = SettingCardGroup(self.tr("项目结构查看器"), self.scrollWidget)
        header_label = StrongBodyLabel(self.tr("在 Minecraft 中可视化项目文件树、依赖关系和执行顺序"))
        header_group.layout.addWidget(header_label)

        # 路径配置组
        path_group = SettingCardGroup(self.tr("路径配置"), self.scrollWidget)

        # 源项目路径
        self.source_edit = LineEdit()
        self.source_edit.setPlaceholderText(self.tr("请输入要扫描的项目目录"))
        source_row = QHBoxLayout()
        source_row.addWidget(BodyLabel(self.tr("源项目路径:")), 0)
        source_row.addWidget(self.source_edit, 1)
        browse_source_btn = PushButton(self.tr("浏览"))
        browse_source_btn.clicked.connect(lambda: self._browse_dir(self.source_edit))
        source_row.addWidget(browse_source_btn, 0)
        path_group.layout.addLayout(source_row)

        # 输出路径
        self.output_edit = LineEdit()
        self.output_edit.setPlaceholderText(self.tr("请输入 Minecraft datapacks 目录"))
        output_row = QHBoxLayout()
        output_row.addWidget(BodyLabel(self.tr("输出路径:")), 0)
        output_row.addWidget(self.output_edit, 1)
        browse_output_btn = PushButton(self.tr("浏览"))
        browse_output_btn.clicked.connect(lambda: self._browse_dir(self.output_edit))
        output_row.addWidget(browse_output_btn, 0)
        path_group.layout.addLayout(output_row)

        # 数据包名称
        name_row = QHBoxLayout()
        name_row.addWidget(BodyLabel(self.tr("数据包名称:")), 0)
        self.name_edit = LineEdit("project-structure-viewer")
        name_row.addWidget(self.name_edit, 1)
        path_group.layout.addLayout(name_row)

        # 操作按钮组
        action_group = SettingCardGroup(self.tr("操作"), self.scrollWidget)
        action_layout = QHBoxLayout()

        self.gen_btn = PrimaryPushButton(self.tr("生成数据包"))
        self.gen_btn.clicked.connect(self._generate)
        action_layout.addWidget(self.gen_btn)

        self.stop_btn = PushButton(self.tr("停止"))
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        action_layout.addWidget(self.stop_btn)

        action_group.layout.addLayout(action_layout)

        # 进度条
        progress_row = QHBoxLayout()
        self.progress_ring = ProgressRing()
        self.progress_ring.setValue(0)
        self.progress_ring.setFixedSize(48, 48)
        self.progress_label = CaptionLabel(self.tr("准备就绪"))
        progress_row.addWidget(self.progress_ring, 0)
        progress_row.addWidget(self.progress_label, 1, Qt.AlignVCenter)
        action_group.layout.addLayout(progress_row)

        # 自动运行组
        auto_group = SettingCardGroup(self.tr("自动运行"), self.scrollWidget)

        self.auto_run_card = SwitchSettingCard(
            FIF.AUTO_REFRESH,
            self.tr("定时自动生成"),
            self.tr(f"每隔 {self.interval_seconds} 秒自动扫描并生成数据包"),
            parent=self.scrollWidget
        )
        self.auto_run_card.switchButton.checkedChanged.connect(self._toggle_auto_run)
        auto_group.addSettingCard(self.auto_run_card)

        interval_row = QHBoxLayout()
        interval_row.addWidget(BodyLabel(self.tr("间隔时间:")), 0)
        self.interval_spin = SpinBox()
        self.interval_spin.setRange(10, 300)
        self.interval_spin.setValue(self.interval_seconds)
        self.interval_spin.valueChanged.connect(self._on_interval_changed)
        interval_row.addWidget(self.interval_spin, 0)
        interval_row.addWidget(BodyLabel(self.tr("秒")), 0)
        self.countdown_label = CaptionLabel("")
        interval_row.addWidget(self.countdown_label, 1, Qt.AlignRight)
        auto_group.layout.addLayout(interval_row)

        # 统计信息组
        stats_group = SettingCardGroup(self.tr("上次生成统计"), self.scrollWidget)
        stats_layout = QHBoxLayout()

        self.file_count_label = BodyLabel(self.tr("文件数: --"))
        self.dir_count_label = BodyLabel(self.tr("目录数: --"))
        self.pack_path_label = CaptionLabel("")
        self.pack_path_label.setWordWrap(True)

        stats_layout.addWidget(self.file_count_label, 1)
        stats_layout.addWidget(self.dir_count_label, 1)
        stats_group.layout.addLayout(stats_layout)
        stats_group.layout.addWidget(self.pack_path_label)

        # 添加到布局
        self.expandLayout.addWidget(header_group)
        self.expandLayout.addWidget(path_group)
        self.expandLayout.addWidget(action_group)
        self.expandLayout.addWidget(auto_group)
        self.expandLayout.addWidget(stats_group)

    def _browse_dir(self, line_edit):
        from PyQt5.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, self.tr("选择目录"))
        if path:
            line_edit.setText(path)

    def _generate(self):
        source = self.source_edit.text().strip()
        output = self.output_edit.text().strip()
        name = self.name_edit.text().strip() or "project-structure-viewer"

        if not source:
            self._show_info("error", self.tr("请输入源项目路径"))
            return
        if not output:
            self._show_info("error", self.tr("请输入输出路径"))
            return
        if not os.path.isdir(source):
            self._show_info("error", self.tr("源项目路径不存在或不是目录"))
            return

        self.source_path = source
        self.output_path = output
        self.datapack_name = name

        self._save_config()
        self._start_scan()

    def _start_scan(self):
        if self.scan_worker and self.scan_worker.isRunning():
            return

        self.gen_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_ring.start()
        self.progress_label.setText(self.tr("正在扫描..."))

        self.scan_worker = ScanWorker(self.source_path, self.output_path, self.datapack_name)
        self.scan_worker.progress.connect(self._on_progress)
        self.scan_worker.finished.connect(self._on_finished)
        self.scan_worker.start()

        if self.log_callback:
            self.log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] 开始扫描: {os.path.basename(self.source_path)}")

    def _stop(self):
        if self.scan_worker:
            self.scan_worker.stop()
            self.scan_worker.wait()
        self._reset_ui()

    def _reset_ui(self):
        self.gen_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_ring.stop()
        self.progress_ring.setValue(0)
        self.progress_label.setText(self.tr("准备就绪"))

    def _on_progress(self, percent, message):
        self.progress_ring.setValue(percent)
        self.progress_label.setText(message)
        if self.log_callback:
            self.log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] {message} ({percent}%)")

    def _on_finished(self, success, message, result):
        self._reset_ui()
        if success:
            self.progress_label.setText(self.tr("生成完成"))
            self.file_count_label.setText(self.tr(f"文件数: {result.get('file_count', 0)}"))
            self.dir_count_label.setText(self.tr(f"目录数: {result.get('dir_count', 0)}"))
            self.pack_path_label.setText(self.tr(f"数据包: {result.get('datapack_path', '')}"))
            self._show_info("success", self.tr(f"数据包生成成功!\n路径: {message}"))
            if self.log_callback:
                self.log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ 生成成功: {message}")
        else:
            self.progress_label.setText(self.tr("生成失败"))
            self._show_info("error", self.tr(f"生成失败: {message}"))
            if self.log_callback:
                self.log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ 生成失败: {message}")

    def _toggle_auto_run(self, checked):
        self.auto_run_enabled = checked
        self.interval_spin.setEnabled(not checked)
        self._save_config()

        if checked:
            self.countdown = self.interval_seconds
            self.timer.start(1000)
            if self.log_callback:
                self.log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] 自动运行已启用，间隔 {self.interval_seconds} 秒")
        else:
            self.timer.stop()
            self.countdown_label.setText("")
            if self.log_callback:
                self.log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] 自动运行已停止")

    def _on_interval_changed(self, value):
        self.interval_seconds = value
        self.countdown = value
        self._save_config()

    def _on_timer(self):
        self.countdown -= 1
        self.countdown_label.setText(self.tr(f"下次运行: {self.countdown}s"))
        if self.countdown <= 0:
            self.countdown = self.interval_seconds
            self._generate()

    def _show_info(self, type_, message):
        if type_ == "success":
            InfoBar.success(title=self.tr("成功"), content=message, orient=Qt.Horizontal,
                           isClosable=True, position=InfoBarPosition.TOP_RIGHT, duration=3000, parent=self)
        else:
            InfoBar.error(title=self.tr("错误"), content=message, orient=Qt.Horizontal,
                         isClosable=True, position=InfoBarPosition.TOP_RIGHT, duration=5000, parent=self)

    def _save_config(self):
        config = {
            "source_path": self.source_edit.text().strip(),
            "output_datapack_name": self.name_edit.text().strip(),
            "mc_saves_path": self.output_edit.text().strip(),
            "auto_run": self.auto_run_enabled,
            "interval_seconds": self.interval_seconds,
            "rcon": {
                "enabled": False,
                "host": "127.0.0.1",
                "port": 25575,
                "password": ""
            }
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except IOError:
            pass

    def load_config(self, config):
        if "source_path" in config:
            self.source_edit.setText(config["source_path"])
        if "mc_saves_path" in config:
            self.output_edit.setText(config["mc_saves_path"])
        if "output_datapack_name" in config:
            self.name_edit.setText(config["output_datapack_name"])
        if "auto_run" in config:
            self.auto_run_card.switchButton.setChecked(config["auto_run"])
        if "interval_seconds" in config:
            self.interval_spin.setValue(config["interval_seconds"])
            self.interval_seconds = config["interval_seconds"]


class SettingsInterface(ScrollArea):
    """设置面板"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("SettingsInterface")
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)

        self.rcon_enabled = False
        self.rcon_host = "127.0.0.1"
        self.rcon_port = 25575
        self.rcon_password = ""

        self._init_ui()

    def _init_ui(self):
        # RCON 配置组
        rcon_group = SettingCardGroup(self.tr("RCON 配置"), self.scrollWidget)

        self.rcon_switch = SwitchSettingCard(
            FIF.WIFI,
            self.tr("启用 RCON"),
            self.tr("通过 RCON 自动发送 /reload 命令"),
            parent=self.scrollWidget
        )
        self.rcon_switch.switchButton.checkedChanged.connect(self._toggle_rcon)
        rcon_group.addSettingCard(self.rcon_switch)

        # RCON 主机
        host_row = QHBoxLayout()
        host_row.addWidget(BodyLabel(self.tr("主机地址:")), 0)
        self.host_edit = LineEdit("127.0.0.1")
        host_row.addWidget(self.host_edit, 1)
        rcon_group.layout.addLayout(host_row)

        # RCON 端口
        port_row = QHBoxLayout()
        port_row.addWidget(BodyLabel(self.tr("端口:")), 0)
        self.port_spin = SpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(25575)
        port_row.addWidget(self.port_spin, 0)
        rcon_group.layout.addLayout(port_row)

        # RCON 密码
        pass_row = QHBoxLayout()
        pass_row.addWidget(BodyLabel(self.tr("密码:")), 0)
        self.pass_edit = LineEdit()
        self.pass_edit.setEchoMode(LineEdit.Password)
        pass_row.addWidget(self.pass_edit, 1)
        rcon_group.layout.addLayout(pass_row)

        # 测试按钮
        test_row = QHBoxLayout()
        self.test_btn = PushButton(self.tr("测试连接"))
        self.test_btn.clicked.connect(self._test_rcon)
        self.test_result = CaptionLabel("")
        test_row.addWidget(self.test_btn, 0)
        test_row.addWidget(self.test_result, 1, Qt.AlignRight)
        rcon_group.layout.addLayout(test_row)

        # 主题配置组
        theme_group = SettingCardGroup(self.tr("界面主题"), self.scrollWidget)

        theme_row = QHBoxLayout()
        theme_row.addWidget(BodyLabel(self.tr("主题:")), 0)
        self.theme_combo = ComboBoxSettingCard(
            FIF.BRIGHTNESS,
            self.tr("主题模式"),
            self.tr("切换亮色/暗色主题"),
            texts=[self.tr("自动"), self.tr("亮色"), self.tr("暗色")],
            parent=self.scrollWidget
        )
        self.theme_combo.comboBox.currentIndexChanged.connect(self._on_theme_changed)
        theme_group.addSettingCard(self.theme_combo)

        # 添加到布局
        self.expandLayout.addWidget(rcon_group)
        self.expandLayout.addWidget(theme_group)

    def _toggle_rcon(self, checked):
        self.rcon_enabled = checked
        self.host_edit.setEnabled(checked)
        self.port_spin.setEnabled(checked)
        self.pass_edit.setEnabled(checked)
        self.test_btn.setEnabled(checked)
        self._save_config()

    def _test_rcon(self):
        host = self.host_edit.text().strip()
        port = self.port_spin.value()
        password = self.pass_edit.text()

        self.test_result.setText(self.tr("正在测试..."))

        def test():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                result = sock.connect_ex((host, port))
                sock.close()

                if result == 0:
                    self.test_result.setText(self.tr("✓ 连接成功"))
                    self.test_result.setStyleSheet("color: green")
                else:
                    self.test_result.setText(self.tr("✗ 无法连接"))
                    self.test_result.setStyleSheet("color: red")
            except Exception as e:
                self.test_result.setText(self.tr(f"✗ 错误: {str(e)}"))
                self.test_result.setStyleSheet("color: red")

        threading.Thread(target=test, daemon=True).start()

    def _on_theme_changed(self, index):
        if index == 0:
            setTheme(Theme.AUTO)
        elif index == 1:
            setTheme(Theme.LIGHT)
        elif index == 2:
            setTheme(Theme.DARK)

    def _save_config(self):
        config = {}
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (IOError, json.JSONDecodeError):
            pass

        config["rcon"] = {
            "enabled": self.rcon_enabled,
            "host": self.host_edit.text().strip(),
            "port": self.port_spin.value(),
            "password": self.pass_edit.text()
        }

        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except IOError:
            pass

    def load_config(self, config):
        rcon = config.get("rcon", {})
        if rcon.get("enabled"):
            self.rcon_switch.switchButton.setChecked(True)
        if "host" in rcon:
            self.host_edit.setText(rcon["host"])
        if "port" in rcon:
            self.port_spin.setValue(rcon["port"])
        if "password" in rcon:
            self.pass_edit.setText(rcon["password"])


class LogsInterface(ScrollArea):
    """日志面板"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("LogsInterface")
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)

        self._init_ui()

    def _init_ui(self):
        log_group = SettingCardGroup(self.tr("运行日志"), self.scrollWidget)

        self.log_text = TextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(400)
        self.log_text.setPlaceholderText(self.tr("运行日志将显示在这里..."))

        clear_btn = PushButton(self.tr("清空日志"))
        clear_btn.clicked.connect(self._clear_logs)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(clear_btn)

        log_group.layout.addWidget(self.log_text)
        log_group.layout.addLayout(btn_row)

        self.expandLayout.addWidget(log_group)

    def add_log(self, message):
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def _clear_logs(self):
        self.log_text.clear()


class FluentMainWindow(FluentWindow):
    """Fluent Design 主窗口"""

    def __init__(self):
        super().__init__()

        # 创建子面板
        self.home_interface = HomeInterface()
        self.settings_interface = SettingsInterface()
        self.logs_interface = LogsInterface()

        # 连接日志回调
        self.home_interface.log_callback = self.logs_interface.add_log

        # 初始化导航
        self._init_navigation()

        # 加载配置
        self._load_config()

        # 设置窗口
        self._init_window()

    def _init_navigation(self):
        self.navigationInterface.addItem(
            routeKey="home",
            icon=FIF.HOME,
            text=self.tr("首页"),
            onClick=lambda: self.switchTo(self.home_interface)
        )
        self.navigationInterface.addItem(
            routeKey="settings",
            icon=FIF.SETTING,
            text=self.tr("设置"),
            onClick=lambda: self.switchTo(self.settings_interface)
        )
        self.navigationInterface.addItem(
            routeKey="logs",
            icon=FIF.FILE_TEXT,
            text=self.tr("日志"),
            onClick=lambda: self.switchTo(self.logs_interface)
        )

        self.navigationInterface.setExpandWidth(150)

    def _init_window(self):
        self.setWindowTitle(self.tr("Minecraft 项目结构查看器"))
        self.resize(900, 650)

        desktop = QApplication.primaryScreen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move((w - self.width()) // 2, (h - self.height()) // 2)

        self.logs_interface.add_log(f"[{datetime.now().strftime('%H:%M:%S')}] 应用启动")

    def _load_config(self):
        config = {}
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (IOError, json.JSONDecodeError):
            pass

        self.home_interface.load_config(config)
        self.settings_interface.load_config(config)


def main():
    """Fluent GUI 入口"""
    app = QApplication(sys.argv)

    setTheme(Theme.AUTO)

    window = FluentMainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
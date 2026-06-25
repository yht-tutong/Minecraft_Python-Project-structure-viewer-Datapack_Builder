# launcher.py
# 交互式启动器：菜单式配置和运行

import os
import sys
import json


# ------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------

def clear_screen():
    """清屏"""
    os.system("cls" if os.name == "nt" else "clear")


def print_header():
    """打印启动器标题"""
    print("=" * 40)
    print("  Minecraft 项目结构查看器 - 数据包生成器")
    print("  B站: https://space.bilibili.com/630095673")
    print("=" * 40)


def print_menu():
    """打印操作菜单"""
    print()
    print("请选择操作：")
    print("  [1] 打开 PyQt 图形界面")
    print("  [2] 打开 Fluent 图形界面（推荐）")
    print("  [3] 命令行生成数据包")
    print("  [4] 查看帮助")
    print("  [0] 退出")
    print()


def is_config_valid(config_path):
    """检查 config.json 是否有效（存在且不为空对象）

    Returns:
        bool: 配置是否有效
    """
    if not os.path.isfile(config_path):
        return False
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 检查是否有 source_path 且不是占位值
        source = data.get("source_path", "")
        if not source or source == "e:/Project/YourProject":
            return False
        return True
    except (json.JSONDecodeError, IOError):
        return False


def setup_config():
    """引导用户创建配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")

    print()
    print("  ══════════════════════════════════════")
    print("    首次使用 - 配置引导")
    print("  ══════════════════════════════════════")
    print()
    print("  请按提示填入以下信息：")
    print()

    # 源项目路径
    source = input("  1. 源项目路径（要扫描的项目目录）: ").strip().strip('"')
    if not source:
        print("  已取消配置。")
        return False

    # 输出路径
    print()
    print("  2. Minecraft 存档的 datapacks 目录")
    print("     例如: E:/Project/.minecraft/versions/1.21.11/saves/我的存档/datapacks")
    output = input("     datapacks 目录路径: ").strip().strip('"')
    if not output:
        print("  已取消配置。")
        return False

    # 数据包名称
    print()
    name = input("  3. 数据包名称（默认: project-structure-viewer）: ").strip()
    if not name:
        name = "project-structure-viewer"

    # RCON 配置
    print()
    print("  4. RCON 自动 reload 配置（可选，用于自动 /reload）")
    rcon_enabled = input("     启用 RCON？(y/n，默认 n): ").strip().lower() in ("y", "yes")
    rcon_host = "127.0.0.1"
    rcon_port = 25575
    rcon_password = ""
    if rcon_enabled:
        host_input = input("     RCON 主机（默认 127.0.0.1）: ").strip()
        if host_input:
            rcon_host = host_input
        port_input = input("     RCON 端口（默认 25575）: ").strip()
        if port_input:
            try:
                rcon_port = int(port_input)
            except ValueError:
                rcon_port = 25575
        rcon_password = input("     RCON 密码: ").strip()

    # 自动运行
    print()
    auto_run = input("  5. 默认启用自动运行？(y/n，默认 n): ").strip().lower() in ("y", "yes")
    interval = 30
    if auto_run:
        interval_input = input("     扫描间隔秒数（默认 30）: ").strip()
        if interval_input:
            try:
                interval = int(interval_input)
            except ValueError:
                interval = 30

    # 写入配置文件
    config = {
        "source_path": source,
        "output_datapack_name": name,
        "mc_saves_path": output,
        "auto_run": auto_run,
        "interval_seconds": interval,
        "rcon": {
            "enabled": rcon_enabled,
            "host": rcon_host,
            "port": rcon_port,
            "password": rcon_password
        }
    }

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        print()
        print("  ✓ 配置已保存到 config.json")
        print()
        return True
    except IOError as e:
        print(f"  错误: 无法写入配置文件 - {e}")
        return False


def check_config():
    """检查 config.json 是否存在且有效，无效则引导设置

    Returns:
        str | None: 配置文件路径（如果有效），否则 None
    """
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if is_config_valid(config_path):
        print(f"  检测到有效配置文件 config.json")
        return config_path
    elif os.path.isfile(config_path):
        print(f"  配置文件 config.json 未设置或无效。")
    else:
        print(f"  未检测到配置文件 config.json。")

    print()
    choice = input("  是否现在进行配置？(y/n，默认 y): ").strip().lower()
    if choice in ("", "y", "yes"):
        if setup_config():
            return config_path
    return None


# ------------------------------------------------------------------
# 选项 1: 打开 GUI
# ------------------------------------------------------------------

def launch_gui():
    """启动 PyQt 图形界面（旧版）"""
    try:
        from gui import main as gui_main
    except ImportError:
        print("  错误: 无法导入 GUI 模块，请确保 gui.py 存在")
        return
    except Exception as e:
        print(f"  错误: 导入 GUI 模块时发生异常 - {e}")
        return

    try:
        import PyQt5  # noqa: F401
    except ImportError:
        print()
        print("  错误: 未检测到 PyQt5，请先安装：")
        print("    pip install PyQt5")
        print()
        input("  按回车键返回菜单...")
        return

    print("  正在启动图形界面...")
    gui_main()


def launch_fluent_gui():
    """启动 Fluent 图形界面（新版推荐）"""
    try:
        from fluent_gui import main as fluent_main
    except ImportError:
        print("  错误: 无法导入 Fluent GUI 模块，请确保 fluent_gui.py 存在")
        return
    except Exception as e:
        print(f"  错误: 导入 Fluent GUI 模块时发生异常 - {e}")
        return

    try:
        from qfluentwidgets import FluentWindow  # noqa: F401
    except ImportError:
        print()
        print("  错误: 未检测到 PyQt-Fluent-Widgets，请先安装：")
        print("    pip install PyQt-Fluent-Widgets[full]")
        print()
        input("  按回车键返回菜单...")
        return

    print("  正在启动 Fluent 图形界面...")
    fluent_main()


# ------------------------------------------------------------------
# 选项 2: 命令行生成
# ------------------------------------------------------------------

def cmd_generate():
    """命令行引导生成数据包"""
    from main import generate_datapack, cli_progress
    from main import load_config as load_cfg

    # 尝试加载配置文件
    config_path = check_config()
    config = {}
    if config_path:
        config = load_cfg(config_path)
        if config:
            print(f"    源项目路径: {config.get('source', '未设置')}")
            print(f"    输出路径:   {config.get('output', '未设置')}")
            print(f"    数据包名称: {config.get('name', '未设置')}")
            print()
            choice = input("  是否使用配置文件中的设置？(y/n，默认 y): ").strip().lower()
            if choice in ("", "y", "yes"):
                source = config.get("source")
                output = config.get("output")
                name = config.get("name", "project-structure-viewer")
            else:
                source = None
                output = None
                name = "project-structure-viewer"
        else:
            source = None
            output = None
            name = "project-structure-viewer"
    else:
        source = None
        output = None
        name = "project-structure-viewer"

    # 如果未使用配置文件，手动输入
    if source is None:
        print()
        print("  --- 请输入生成参数 ---")
        source = input("  源项目路径: ").strip().strip('"')
        if not source:
            print("  错误: 源项目路径不能为空")
            return

        output = input("  输出路径（Minecraft datapacks 目录）: ").strip().strip('"')
        if not output:
            print("  错误: 输出路径不能为空")
            return

        name_input = input("  数据包名称（默认 project-structure-viewer）: ").strip()
        name = name_input if name_input else "project-structure-viewer"

    # 规范化路径
    source = os.path.abspath(source)
    output = os.path.abspath(output)

    # 验证路径
    if not os.path.exists(source):
        print(f"  错误: 源项目路径不存在: {source}")
        return
    if not os.path.isdir(source):
        print(f"  错误: 源项目路径不是目录: {source}")
        return

    # 确保输出目录存在
    try:
        os.makedirs(output, exist_ok=True)
    except PermissionError:
        print(f"  错误: 没有权限创建输出目录: {output}")
        return

    # 执行生成
    print()
    print(f"  源项目: {source}")
    print(f"  输出目录: {output}")
    print(f"  数据包名称: {name}")
    print()

    try:
        datapack_path, scan_result = generate_datapack(
            source_path=source,
            output_path=output,
            name=name,
            progress_callback=cli_progress,
        )
    except FileNotFoundError as e:
        print(f"\n  错误: 文件未找到 - {e}")
        return
    except PermissionError as e:
        print(f"\n  错误: 权限不足 - {e}")
        return
    except Exception as e:
        print(f"\n  错误: 生成数据包时发生异常 - {e}")
        return

    # 输出完成信息
    stats = scan_result.get("_stats", {})
    print()
    print("=" * 60)
    print("  数据包生成完成!")
    print("=" * 60)
    print(f"  数据包路径: {datapack_path}")
    print(f"  扫描文件数: {stats.get('file_count', '?')}")
    print(f"  扫描目录数: {stats.get('dir_count', '?')}")
    print(f"  Python 依赖: {len(scan_result.get('dependencies', {}))} 个文件")
    print(f"  mcfunction 调用: {len(scan_result.get('function_calls', {}))} 个文件")
    print(f"  执行顺序: {len(scan_result.get('execution_order', []))} 条记录")
    print()
    print("  使用说明:")
    print(f"    1. 打开 Minecraft 并进入存档")
    print(f"    2. 在游戏中执行 /reload 加载数据包")
    print(f"    3. 执行 /trigger {name}.trigger set 1  查看文件树")
    print(f"    4. 执行 /trigger {name}.trigger set 2  查看依赖关系")
    print(f"    5. 执行 /trigger {name}.trigger set 3  查看执行顺序")
    print("=" * 60)


# ------------------------------------------------------------------
# 选项 3: 帮助
# ------------------------------------------------------------------

def show_help():
    """显示帮助信息"""
    print()
    print("=" * 60)
    print("  使用说明")
    print("=" * 60)
    print()
    print("  【功能概述】")
    print("  本工具用于扫描 Python/Minecraft 数据包项目目录，")
    print("  并将其结构、依赖关系、执行顺序生成为 Minecraft 数据包，")
    print("  以便在游戏中通过聊天栏可视化查看。")
    print()
    print("  【两种使用方式】")
    print("  1. GUI 模式（选项 1）：")
    print("     - 图形化界面，操作直观")
    print("     - 支持文件树预览、依赖关系图")
    print("     - 支持 RCON 自动 reload")
    print("  2. 命令行模式（选项 2）：")
    print("     - 交互式引导输入参数")
    print("     - 支持从 config.json 读取配置")
    print("     - 也可直接使用 main.py 命令行参数")
    print()
    print("  【配置文件 config.json】")
    print("  运行程序时会自动引导配置，也可手动创建 config.json，内容格式：")
    print("  {")
    print('    "source_path": "你的源项目路径",')
    print('    "mc_saves_path": "Minecraft datapacks 目录",')
    print('    "output_datapack_name": "project-structure-viewer",')
    print('    "rcon": {')
    print('      "enabled": false,')
    print('      "host": "127.0.0.1",')
    print('      "port": 25575,')
    print('      "password": ""')
    print("    }")
    print("  }")
    print()
    print("  【Minecraft 内使用方法】")
    print("  1. 将生成的数据包放入存档的 datapacks 目录")
    print("  2. 进入游戏后执行 /reload 加载数据包")
    print("  3. 执行 /trigger projview.trigger set 1  查看文件树")
    print("  4. 执行 /trigger projview.trigger set 2  查看依赖关系")
    print("  5. 执行 /trigger projview.trigger set 3  查看执行顺序")
    print()
    print("  【更多信息】")
    print("  B站: https://space.bilibili.com/630095673")
    print("  GitHub: 见项目 README.md")
    print("=" * 60)


# ------------------------------------------------------------------
# 主循环
# ------------------------------------------------------------------

def main():
    """启动器主入口"""
    clear_screen()
    print_header()

    # 检查配置文件
    config_path = check_config()
    if config_path is None:
        print("  提示: 未配置，可在菜单中选择 [3] 查看帮助，或之后手动编辑 config.json")
        print()

    while True:
        print_menu()
        try:
            choice = input("请输入选项 (0-4): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  再见！")
            sys.exit(0)

        print()

        if choice == "1":
            launch_gui()
            clear_screen()
            print_header()
            check_config()

        elif choice == "2":
            launch_fluent_gui()
            clear_screen()
            print_header()
            check_config()

        elif choice == "3":
            cmd_generate()
            print()
            input("按回车键返回菜单...")
            clear_screen()
            print_header()
            check_config()

        elif choice == "4":
            show_help()
            print()
            input("按回车键返回菜单...")
            clear_screen()
            print_header()
            check_config()

        elif choice == "0":
            print("  再见！")
            sys.exit(0)

        else:
            print(f"  无效选项: '{choice}'，请输入 0-3 之间的数字")
            input("按回车键继续...")


# ------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  再见！")
        sys.exit(0)
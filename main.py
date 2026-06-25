# main.py
# 项目主入口：整合扫描引擎和数据包生成器，提供命令行接口

import os
import sys
import json
import argparse

from scanner import ProjectScanner
from datapack_generator import DatapackGenerator


# ------------------------------------------------------------------
# 核心整合函数
# ------------------------------------------------------------------

def generate_datapack(source_path, output_path, name="project-structure-viewer", progress_callback=None):
    """扫描项目并生成数据包

    Args:
        source_path: 源项目目录路径
        output_path: Minecraft 存档的 datapacks 目录路径
        name: 数据包文件夹名称（默认 "project-structure-viewer"）
        progress_callback: 进度回调函数 callback(percent, message)

    Returns:
        tuple: (生成的数据包目录路径, 扫描结果字典)
    """
    # ---- 阶段1：扫描项目（0-50%） ----
    scanner = ProjectScanner(source_path)

    # 包装进度回调，将扫描的 0-100% 映射到 0-50%
    def scan_progress(percent, message):
        mapped = int(percent * 0.5)
        if progress_callback:
            progress_callback(mapped, f"[扫描] {message}")

    scan_result = scanner.scan(progress_callback=scan_progress)

    # ---- 统计扫描结果 ----
    file_tree = scan_result.get("file_tree", {})
    file_count, dir_count = _count_tree_nodes(file_tree)

    # ---- 阶段2：生成数据包（50-100%） ----
    generator = DatapackGenerator(scan_result, output_path, name)

    # 包装进度回调，将生成的 0-100% 映射到 50-100%
    def gen_progress(percent, message):
        mapped = 50 + int(percent * 0.5)
        if progress_callback:
            progress_callback(mapped, f"[生成] {message}")

    datapack_path = generator.generate(progress_callback=gen_progress)

    # 将统计信息附加到扫描结果，供外部使用
    scan_result["_stats"] = {
        "file_count": file_count,
        "dir_count": dir_count,
    }

    return datapack_path, scan_result


def _count_tree_nodes(file_tree):
    """递归统计文件树中的文件数和目录数

    Args:
        file_tree: 文件树根节点

    Returns:
        tuple: (文件数, 目录数)
    """
    file_count = 0
    dir_count = 0

    def _walk(node):
        nonlocal file_count, dir_count
        node_type = node.get("type", "")
        if node_type == "file":
            file_count += 1
        elif node_type == "directory":
            dir_count += 1
        for child in node.get("children", []):
            _walk(child)

    if file_tree:
        _walk(file_tree)

    return file_count, dir_count


# ------------------------------------------------------------------
# 配置文件加载
# ------------------------------------------------------------------

def load_config(config_path):
    """从 JSON 配置文件加载参数

    Args:
        config_path: 配置文件路径

    Returns:
        dict: 配置参数字典，文件不存在或解析失败时返回空字典
    """
    if not os.path.isfile(config_path):
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        print(f"警告: 无法解析配置文件 '{config_path}'，将使用默认参数")
        return {}

    # 统一键名映射
    mapped = {}
    if "source_path" in config:
        mapped["source"] = config["source_path"]
    if "mc_saves_path" in config:
        mapped["output"] = config["mc_saves_path"]
    if "output_datapack_name" in config:
        mapped["name"] = config["output_datapack_name"]
    if "auto_run" in config:
        mapped["auto_run"] = config["auto_run"]
    if "interval_seconds" in config:
        mapped["interval_seconds"] = config["interval_seconds"]

    return mapped


# ------------------------------------------------------------------
# 命令行进度回调
# ------------------------------------------------------------------

def cli_progress(percent, message):
    """命令行进度输出回调

    Args:
        percent: 进度百分比（0-100）
        message: 进度描述信息
    """
    bar_len = 40
    filled = int(bar_len * percent / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"\r  进度: [{bar}] {percent:3d}%  {message}", end="", flush=True)
    if percent >= 100:
        print()


# ------------------------------------------------------------------
# 命令行参数解析
# ------------------------------------------------------------------

def build_parser():
    """构建命令行参数解析器

    Returns:
        argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="项目结构查看器 - 扫描项目目录并生成 Minecraft 数据包，在游戏中可视化项目结构",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py -s "E:/Project/MyProject" -o "E:/.../datapacks"
  python main.py -s "E:/Project/MyProject" -o "E:/.../datapacks" -n "my-viewer"
  python main.py -c config.json
  python main.py -g
        """,
    )

    parser.add_argument(
        "--source", "-s",
        type=str,
        default=None,
        help="源项目目录路径",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Minecraft 存档的 datapacks 目录路径",
    )
    parser.add_argument(
        "--name", "-n",
        type=str,
        default="project-structure-viewer",
        help='数据包文件夹名称（默认: "project-structure-viewer"）',
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="从 JSON 配置文件读取参数",
    )
    parser.add_argument(
        "--gui", "-g",
        action="store_true",
        default=False,
        help="启动 PyQt 图形界面",
    )

    return parser


# ------------------------------------------------------------------
# 主函数
# ------------------------------------------------------------------

def main():
    """命令行入口"""
    parser = build_parser()
    args = parser.parse_args()

    # --gui 模式
    if args.gui:
        try:
            from gui import start_gui
            start_gui()
        except ImportError:
            print("错误: 无法导入 GUI 模块。请确保已安装 PyQt 并创建 gui.py 文件。")
            sys.exit(1)
        return

    # 从配置文件加载参数
    config = {}
    if args.config:
        config = load_config(args.config)
        if config:
            print(f"  已从配置文件加载参数: {args.config}")

    # 合并参数：命令行参数优先级高于配置文件
    source = args.source or config.get("source")
    output = args.output or config.get("output")
    name = args.name or config.get("name", "project-structure-viewer")

    # 验证必填参数
    if not source:
        print("错误: 未指定源项目路径。请使用 -s/--source 或配置文件提供。")
        parser.print_usage()
        sys.exit(1)

    if not output:
        print("错误: 未指定输出 datapacks 目录。请使用 -o/--output 或配置文件提供。")
        parser.print_usage()
        sys.exit(1)

    # 规范化路径
    source = os.path.abspath(source)
    output = os.path.abspath(output)

    # 验证路径
    if not os.path.exists(source):
        print(f"错误: 源项目路径不存在: {source}")
        sys.exit(1)
    if not os.path.isdir(source):
        print(f"错误: 源项目路径不是目录: {source}")
        sys.exit(1)

    # 确保输出目录存在
    try:
        os.makedirs(output, exist_ok=True)
    except PermissionError:
        print(f"错误: 没有权限创建输出目录: {output}")
        sys.exit(1)

    # 执行生成
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
        print(f"\n错误: 文件未找到 - {e}")
        sys.exit(1)
    except PermissionError as e:
        print(f"\n错误: 权限不足 - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n错误: 生成数据包时发生异常 - {e}")
        sys.exit(1)

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
# 入口
# ------------------------------------------------------------------

if __name__ == "__main__":
    main()
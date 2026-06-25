# datapack_generator.py
# 数据包生成器：根据扫描结果生成符合五子棋数据包格式的 Minecraft 数据包

import os
import json
import shutil
from collections import defaultdict


class DatapackGenerator:
    """数据包生成器：根据 ProjectScanner 的扫描结果生成完整 Minecraft 数据包"""

    # 每页渲染的行数
    PAGE_SIZE = 15

    # 文件扩展名 → 颜色映射（Minecraft 聊天颜色）
    EXT_COLOR_MAP = {
        # Python
        ".py": "blue", ".pyw": "blue",
        # Minecraft 数据包
        ".mcfunction": "#CE9178", ".json": "green",
        # 文档
        ".md": "aqua", ".txt": "aqua", ".readme": "aqua", ".rst": "aqua",
        # 配置文件
        ".cfg": "gray", ".ini": "gray", ".toml": "gray",
        ".yml": "gray", ".yaml": "gray", ".properties": "gray",
        ".editorconfig": "gray",
        # Web
        ".html": "#E44D26", ".htm": "#E44D26",
        ".css": "#264DE4", ".scss": "#264DE4", ".less": "#264DE4",
        ".js": "#F7DF1E", ".ts": "#3178C6", ".tsx": "#3178C6",
        ".jsx": "#F7DF1E", ".vue": "#42B883",
        # 图片
        ".png": "#C586C0", ".jpg": "#C586C0", ".jpeg": "#C586C0",
        ".gif": "#C586C0", ".bmp": "#C586C0", ".svg": "#C586C0",
        ".webp": "#C586C0", ".ico": "#C586C0",
        # 脚本
        ".sh": "dark_green", ".bat": "dark_green", ".ps1": "dark_green",
        # 其他
        ".xml": "dark_aqua", ".sql": "light_purple",
        ".log": "dark_gray", ".env": "dark_gray",
        ".gitignore": "gray", ".lock": "dark_gray",
        ".gitattributes": "gray",
    }

    # 文件扩展名 → 方块类型映射
    EXT_BLOCK_MAP = {
        # Python
        ".py": "minecraft:light_blue_concrete", ".pyw": "minecraft:light_blue_concrete",
        # Minecraft 数据包
        ".mcfunction": "minecraft:orange_concrete", ".json": "minecraft:lime_concrete",
        # 文档
        ".md": "minecraft:cyan_concrete", ".txt": "minecraft:cyan_concrete",
        ".readme": "minecraft:cyan_concrete", ".rst": "minecraft:cyan_concrete",
        # 配置文件
        ".cfg": "minecraft:light_gray_concrete", ".ini": "minecraft:light_gray_concrete",
        ".toml": "minecraft:light_gray_concrete", ".yml": "minecraft:light_gray_concrete",
        ".yaml": "minecraft:light_gray_concrete", ".properties": "minecraft:light_gray_concrete",
        ".editorconfig": "minecraft:light_gray_concrete",
        # Web
        ".html": "minecraft:red_concrete", ".htm": "minecraft:red_concrete",
        ".css": "minecraft:blue_concrete", ".scss": "minecraft:blue_concrete",
        ".less": "minecraft:blue_concrete",
        ".js": "minecraft:yellow_concrete", ".ts": "minecraft:blue_concrete",
        ".tsx": "minecraft:blue_concrete", ".jsx": "minecraft:yellow_concrete",
        ".vue": "minecraft:green_concrete",
        # 图片
        ".png": "minecraft:purple_concrete", ".jpg": "minecraft:purple_concrete",
        ".jpeg": "minecraft:purple_concrete", ".gif": "minecraft:purple_concrete",
        ".bmp": "minecraft:purple_concrete", ".svg": "minecraft:purple_concrete",
        ".webp": "minecraft:purple_concrete", ".ico": "minecraft:purple_concrete",
        # 脚本
        ".sh": "minecraft:green_concrete", ".bat": "minecraft:green_concrete",
        ".ps1": "minecraft:green_concrete",
        # 其他
        ".xml": "minecraft:cyan_concrete", ".sql": "minecraft:magenta_concrete",
        ".log": "minecraft:gray_concrete", ".env": "minecraft:gray_concrete",
        ".gitignore": "minecraft:light_gray_concrete", ".lock": "minecraft:gray_concrete",
        ".gitattributes": "minecraft:light_gray_concrete",
    }

    # 方块树每行最大方块数（垂直列表布局：1 列）
    BLOCK_ROW_SIZE = 1
    # 方块树每页最大行数
    BLOCK_PAGE_ROWS = 25

    def __init__(self, scan_result: dict, output_path: str, datapack_name: str = "projview"):
        """初始化生成器

        Args:
            scan_result: ProjectScanner.scan() 的返回值
            output_path: Minecraft 存档的 datapacks 目录
            datapack_name: 数据包文件夹名称
        """
        self.scan_result = scan_result
        self.output_path = output_path
        self.datapack_name = datapack_name
        # 命名空间 ID：只允许小写字母、数字、下划线、点
        self._namespace = self._sanitize_namespace(datapack_name)
        self._datapack_path = os.path.join(output_path, datapack_name)

        # 预计算：扁平化文件树
        self._flat_tree = self._flatten_tree()

    @staticmethod
    def _sanitize_namespace(name: str) -> str:
        """清理命名空间 ID：只保留小写字母、数字、下划线、点"""
        import re
        result = name.lower()
        result = re.sub(r'[^a-z0-9_.]', '_', result)
        # 不能以数字开头
        if result and result[0].isdigit():
            result = '_' + result
        return result or 'projview'

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def generate(self, progress_callback=None) -> str:
        """生成完整数据包

        Args:
            progress_callback: 可选，签名 callback(percent, message)

        Returns:
            str: 数据包目录路径
        """
        self._report(progress_callback, 0, "正在创建目录结构...")
        self._create_directory_structure()

        self._report(progress_callback, 5, "正在生成 pack.mcmeta...")
        self._generate_pack_mcmeta()

        self._report(progress_callback, 10, "正在生成 load.json / tick.json...")
        self._generate_tag_files()

        self._report(progress_callback, 15, "正在生成 init.mcfunction...")
        self._generate_init_function()

        self._report(progress_callback, 30, "正在生成 tick/main.mcfunction...")
        self._generate_tick_function()

        self._report(progress_callback, 40, "正在生成宏函数...")
        self._generate_macro_functions()

        self._report(progress_callback, 43, "正在生成方块节点宏...")
        self._generate_block_node_macro()

        self._report(progress_callback, 50, "正在生成文件树渲染函数...")
        self._generate_file_tree_render()

        self._report(progress_callback, 70, "正在生成依赖关系渲染函数...")
        self._generate_dependencies_render()

        self._report(progress_callback, 85, "正在生成执行顺序渲染函数...")
        self._generate_exec_order_render()

        self._report(progress_callback, 90, "正在生成方块可视化渲染...")
        self._generate_anchor_function()
        self._generate_cleanup_function()
        self._generate_block_tree_render()

        self._report(progress_callback, 100, "数据包生成完成")

        return self._datapack_path

    # ------------------------------------------------------------------
    # 目录结构
    # ------------------------------------------------------------------

    def _create_directory_structure(self):
        """创建数据包目录结构"""
        dirs = [
            os.path.join(self._datapack_path, "data", "minecraft", "tags", "function"),
            os.path.join(self._datapack_path, "data", self._namespace, "function", ".load"),
            os.path.join(self._datapack_path, "data", self._namespace, "function", ".tick"),
            os.path.join(self._datapack_path, "data", self._namespace, "function", "_macro"),
            os.path.join(self._datapack_path, "data", self._namespace, "function", "render"),
        ]
        # 如果数据包目录已存在，先删除
        if os.path.exists(self._datapack_path):
            shutil.rmtree(self._datapack_path)
        for d in dirs:
            os.makedirs(d, exist_ok=True)

    # ------------------------------------------------------------------
    # pack.mcmeta
    # ------------------------------------------------------------------

    def _generate_pack_mcmeta(self):
        """生成 pack.mcmeta"""
        source_path = self.scan_result.get("source_path", "Unknown Project")
        project_name = os.path.basename(source_path) or source_path

        mcmeta = {
            "pack": {
                "description": f"Project Structure Viewer: {project_name}",
                "pack_format": 80,
                "supported_formats": [48, 80],
                "min_format": [88, 0],
                "max_format": [94, 1],
            }
        }
        self._write_json(os.path.join(self._datapack_path, "pack.mcmeta"), mcmeta)

    # ------------------------------------------------------------------
    # load.json / tick.json
    # ------------------------------------------------------------------

    def _generate_tag_files(self):
        """生成 load.json 和 tick.json"""
        load_json = {"values": [f"{self._namespace}:.load/init"]}
        tick_json = {"values": [f"{self._namespace}:.tick/main"]}

        tags_dir = os.path.join(self._datapack_path, "data", "minecraft", "tags", "function")
        self._write_json(os.path.join(tags_dir, "load.json"), load_json)
        self._write_json(os.path.join(tags_dir, "tick.json"), tick_json)

    # ------------------------------------------------------------------
    # .load/init.mcfunction
    # ------------------------------------------------------------------

    def _generate_init_function(self):
        """生成初始化函数：记分板、常量、storage 数据"""
        lines = []
        lines.append("# .load/init.mcfunction")
        lines.append("# 初始化记分板、storage 和文件树数据")

        # ---- 记分板 ----
        lines.append("")
        lines.append("# 记分板")
        lines.append(f"scoreboard objectives add {self._namespace}.trigger trigger")
        lines.append(f"scoreboard objectives add {self._namespace}.page dummy")
        lines.append(f"scoreboard objectives add {self._namespace}.mode dummy")
        lines.append(f"scoreboard objectives add {self._namespace}.const dummy")

        # ---- 常量 ----
        lines.append("")
        lines.append("# 常量")
        lines.append(f"scoreboard players set #0 {self._namespace}.const 0")
        lines.append(f"scoreboard players set #1 {self._namespace}.const 1")
        lines.append(f"scoreboard players set #2 {self._namespace}.const 2")
        lines.append(f"scoreboard players set #3 {self._namespace}.const 3")
        lines.append(f"scoreboard players set #15 {self._namespace}.const 15")

        # ---- 初始化 storage ----
        lines.append("")
        lines.append("# 初始化 storage")
        lines.append(f"data remove storage {self._namespace}:data tree")
        lines.append(f"data modify storage {self._namespace}:data tree set value []")

        # ---- tick 计数器 ----
        lines.append("")
        lines.append("# tick 计数器")
        lines.append(f"scoreboard players set #tick_counter {self._namespace}.const 0")

        # ---- 生成可视化锚点 ----
        lines.append("")
        lines.append("# 生成可视化锚点")
        lines.append(f"function {self._namespace}:.load/spawn_anchor")

        # ---- 初始渲染 ----
        lines.append("")
        lines.append("# 初始渲染")
        lines.append(f"function {self._namespace}:render/block_tree")

        self._write_mcfunction(
            os.path.join(self._datapack_path, "data", self._namespace, "function", ".load", "init.mcfunction"),
            lines
        )

    # ------------------------------------------------------------------
    # .tick/main.mcfunction
    # ------------------------------------------------------------------

    def _generate_tick_function(self):
        """生成 tick 主循环函数：自动渲染方块可视化"""
        ns = self._namespace
        lines = []
        lines.append("# .tick/main.mcfunction")
        lines.append("# 主 tick 循环：自动渲染方块可视化")
        lines.append("")

        # 检测 anchor 是否存在，不存在则重新生成
        lines.append("# 检测 anchor 是否存在，不存在则重新生成")
        lines.append(f"execute unless entity @e[tag=projview_anchor,limit=1] run function {ns}:.load/spawn_anchor")
        lines.append("")

        # 每 20 tick（1 秒）刷新一次渲染
        lines.append("# 每 20 tick（1 秒）刷新一次渲染")
        lines.append(f"execute if score #tick_counter {ns}.const matches 20.. run function {ns}:render/block_tree")
        lines.append(f"execute if score #tick_counter {ns}.const matches 20.. run scoreboard players set #tick_counter {ns}.const 0")
        lines.append(f"scoreboard players add #tick_counter {ns}.const 1")
        lines.append("")

        # 保留 trigger 兼容：手动触发模式
        lines.append("# 保留 trigger 兼容：手动触发模式")
        lines.append(f"scoreboard players enable @s {ns}.trigger")
        lines.append(f"execute as @a[scores={{{ns}.trigger=1..}}] at @s run function {ns}:render/file_tree")
        lines.append(f"execute as @a[scores={{{ns}.trigger=2..}}] at @s run function {ns}:render/dependencies")
        lines.append(f"execute as @a[scores={{{ns}.trigger=3..}}] at @s run function {ns}:render/exec_order")
        lines.append(f"execute as @a[scores={{{ns}.trigger=1..}}] at @s run scoreboard players reset @s {ns}.trigger")

        self._write_mcfunction(
            os.path.join(self._datapack_path, "data", ns, "function", ".tick", "main.mcfunction"),
            lines
        )

    # ------------------------------------------------------------------
    # 宏函数
    # ------------------------------------------------------------------

    def _generate_macro_functions(self):
        """生成宏函数：file_tree_line 和 dep_line"""
        ns = self._namespace

        # file_tree_line 宏
        lines = [
            "# _macro/file_tree_line.mcfunction",
            "# 渲染文件树的单行（宏函数）",
            "# 参数: indent_text, icon, name, color",
            "",
            "$tellraw @s [{\"text\":\"$(indent_text)$(icon) $(name)\",\"color\":\"$(color)\"}]",
        ]
        self._write_mcfunction(
            os.path.join(self._datapack_path, "data", ns, "function", "_macro", "file_tree_line.mcfunction"),
            lines
        )

        # dep_line 宏
        lines = [
            "# _macro/dep_line.mcfunction",
            "# 渲染依赖关系的单行（宏函数）",
            "# 参数: text, color",
            "",
            "$tellraw @s [{\"text\":\"$(text)\",\"color\":\"$(color)\"}]",
        ]
        self._write_mcfunction(
            os.path.join(self._datapack_path, "data", ns, "function", "_macro", "dep_line.mcfunction"),
            lines
        )

    def _generate_block_node_macro(self):
        """生成 _macro/block_node.mcfunction 宏函数"""
        ns = self._namespace
        lines = [
            "# _macro/block_node.mcfunction",
            "# 渲染单个方块节点（宏函数）",
            "# 参数: x, y, z, block, text_component, y_above",
            "",
            "# 生成 block_display（方块）",
            "$summon minecraft:block_display ~ ~ ~ {block_state:{Name:\"$(block)\"},transformation:{translation:[$(x)f,$(y)f,$(z)f],scale:[0.4f,0.4f,0.4f],left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f]},Tags:[\"projview_display\"],teleport_duration:5,interpolation_duration:5}",
            "",
            "# 生成 text_display（悬浮文字，在方块上方 0.5 格）",
            "$summon minecraft:text_display ~ ~ ~ {text:'$(text_component)',transformation:{translation:[$(x)f,$(y_above)f,$(z)f],scale:[0.3f,0.3f,0.3f],left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f]},Tags:[\"projview_display\"],teleport_duration:5,interpolation_duration:5,text_opacity:128,see_through:1b}",
        ]
        self._write_mcfunction(
            os.path.join(self._datapack_path, "data", ns, "function", "_macro", "block_node.mcfunction"),
            lines
        )

    # ------------------------------------------------------------------
    # 文件树渲染
    # ------------------------------------------------------------------

    def _flatten_tree(self):
        """将嵌套文件树扁平化为行列表，包含深度信息

        Returns:
            list: [{indent_text, icon, name, color, depth, ext, type, modified}, ...]
        """
        file_tree = self.scan_result.get("file_tree")
        if not file_tree:
            return []

        flat = []

        def _walk(node, depth):
            name = node.get("name", "")
            node_type = node.get("type", "file")

            indent_text = "  " * depth
            if node_type == "directory":
                icon = "📁"
                color = "gold"
            else:
                icon = "📄"
                ext = node.get("ext", "").lower()
                color = self.EXT_COLOR_MAP.get(ext, "white")

            flat.append({
                "indent_text": indent_text,
                "icon": icon,
                "name": name,
                "color": color,
                "depth": depth,
                "ext": node.get("ext", "").lower(),
                "type": node_type,
                "modified": node.get("modified", False),
            })

            for child in node.get("children", []):
                _walk(child, depth + 1)

        # 根节点本身不渲染，只渲染其子节点
        for child in file_tree.get("children", []):
            _walk(child, 0)

        return flat

    def _generate_file_tree_render(self):
        """生成文件树渲染函数（分页）"""
        ns = self._namespace
        flat = self._flat_tree

        # 主渲染函数
        main_lines = [
            "# render/file_tree.mcfunction",
            "# 渲染项目文件树（分页）",
            "",
        ]

        if not flat:
            main_lines.append(f'tellraw @s [{{"text":"📂 文件树为空，没有找到文件","color":"gray"}}]')
            self._write_mcfunction(
                os.path.join(self._datapack_path, "data", ns, "function", "render", "file_tree.mcfunction"),
                main_lines
            )
            return

        total_pages = (len(flat) + self.PAGE_SIZE - 1) // self.PAGE_SIZE

        # 生成标题
        main_lines.append("# 显示标题")
        source_path = self.scan_result.get("source_path", "Unknown")
        project_name = os.path.basename(source_path)
        main_lines.append(
            f'tellraw @s [{{"text":"📂 项目文件树: {project_name}","color":"gold","bold":true}}]'
        )
        main_lines.append(
            f'tellraw @s [{{"text":"共 {total_pages} 页 / {len(flat)} 个条目","color":"gray"}}]'
        )
        main_lines.append("")

        # 根据 page 分发到各页
        main_lines.append(f"# 根据 page 计分板分发到对应页函数")
        main_lines.append(f"execute if score @s {ns}.page matches 0 run function {ns}:render/_ft_page/0")
        for p in range(1, total_pages):
            main_lines.append(f"execute if score @s {ns}.page matches {p} run function {ns}:render/_ft_page/{p}")

        self._write_mcfunction(
            os.path.join(self._datapack_path, "data", ns, "function", "render", "file_tree.mcfunction"),
            main_lines
        )

        # 生成每页的子函数
        page_dir = os.path.join(self._datapack_path, "data", ns, "function", "render", "_ft_page")
        os.makedirs(page_dir, exist_ok=True)

        for p in range(total_pages):
            page_lines = [
                f"# render/_ft_page/{p}.mcfunction",
                f"# 文件树第 {p + 1} 页",
                "",
            ]
            start = p * self.PAGE_SIZE
            end = min(start + self.PAGE_SIZE, len(flat))

            for i in range(start, end):
                item = flat[i]
                # 将数据放入 temp storage 并调用宏
                indent = item["indent_text"].replace("\\", "\\\\").replace('"', '\\"')
                name = item["name"].replace("\\", "\\\\").replace('"', '\\"')
                page_lines.append(
                    f'data modify storage {ns}:temp macro set value '
                    f'{{indent_text:"{indent}",icon:"{item["icon"]}",name:"{name}",color:"{item["color"]}"}}'
                )
                page_lines.append(f"function {ns}:_macro/file_tree_line with storage {ns}:temp macro")

            self._write_mcfunction(
                os.path.join(page_dir, f"{p}.mcfunction"),
                page_lines
            )

    # ------------------------------------------------------------------
    # 依赖关系渲染
    # ------------------------------------------------------------------

    def _generate_dependencies_render(self):
        """生成依赖关系渲染函数"""
        ns = self._namespace
        dependencies = self.scan_result.get("dependencies", {})
        function_calls = self.scan_result.get("function_calls", {})

        main_lines = [
            "# render/dependencies.mcfunction",
            "# 渲染依赖关系",
            "",
        ]

        if not dependencies and not function_calls:
            main_lines.append(
                'tellraw @s [{"text":"📦 没有发现依赖关系","color":"gray"}]'
            )
            self._write_mcfunction(
                os.path.join(self._datapack_path, "data", ns, "function", "render", "dependencies.mcfunction"),
                main_lines
            )
            return

        # 标题
        main_lines.append(
            'tellraw @s [{"text":"📦 依赖关系","color":"gold","bold":true}]'
        )
        main_lines.append("")

        # 构建反向依赖映射
        reverse_deps = defaultdict(list)
        for file_path, imports in dependencies.items():
            for imp in imports:
                # 尝试匹配实际文件
                for other_file in dependencies:
                    base = os.path.splitext(os.path.basename(other_file))[0]
                    if base == imp:
                        reverse_deps[other_file].append(file_path)
                        break

        # 生成 Python import 依赖行
        line_count = 0
        for file_path, imports in dependencies.items():
            if imports:
                file_name = os.path.basename(file_path)
                import_str = ", ".join(imports[:5])
                if len(imports) > 5:
                    import_str += f" ... (+{len(imports) - 5})"
                text = f"📄 {file_name} → imports: {import_str}"
                escaped = text.replace("\\", "\\\\").replace('"', '\\"')
                main_lines.append(
                    f'data modify storage {ns}:temp macro set value {{text:"{escaped}",color:"white"}}'
                )
                main_lines.append(f"function {ns}:_macro/dep_line with storage {ns}:temp macro")
                line_count += 1

        # 生成被依赖行
        if reverse_deps:
            main_lines.append("")
            main_lines.append(
                'tellraw @s [{"text":"--- 被依赖关系 ---","color":"gray","italic":true}]'
            )
            for file_path, imported_by in reverse_deps.items():
                if imported_by:
                    file_name = os.path.basename(file_path)
                    by_str = ", ".join([os.path.basename(f) for f in imported_by[:5]])
                    if len(imported_by) > 5:
                        by_str += f" ... (+{len(imported_by) - 5})"
                    text = f"📄 {file_name} ← imported by: {by_str}"
                    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
                    main_lines.append(
                        f'data modify storage {ns}:temp macro set value {{text:"{escaped}",color:"#9CDCFE"}}'
                    )
                    main_lines.append(f"function {ns}:_macro/dep_line with storage {ns}:temp macro")
                    line_count += 1

        # 生成 .mcfunction 调用关系
        if function_calls:
            main_lines.append("")
            main_lines.append(
                'tellraw @s [{"text":"--- .mcfunction 调用关系 ---","color":"gray","italic":true}]'
            )
            for file_path, calls in function_calls.items():
                if calls:
                    file_name = os.path.basename(file_path)
                    calls_str = ", ".join(calls[:5])
                    if len(calls) > 5:
                        calls_str += f" ... (+{len(calls) - 5})"
                    text = f"📄 {file_name} → calls: {calls_str}"
                    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
                    main_lines.append(
                        f'data modify storage {ns}:temp macro set value {{text:"{escaped}",color:"#CE9178"}}'
                    )
                    main_lines.append(f"function {ns}:_macro/dep_line with storage {ns}:temp macro")
                    line_count += 1

        if line_count == 0:
            main_lines.append(
                'tellraw @s [{"text":"  没有发现依赖关系","color":"gray"}]'
            )

        self._write_mcfunction(
            os.path.join(self._datapack_path, "data", ns, "function", "render", "dependencies.mcfunction"),
            main_lines
        )

    # ------------------------------------------------------------------
    # 执行顺序渲染
    # ------------------------------------------------------------------

    def _generate_exec_order_render(self):
        """生成执行顺序渲染函数"""
        ns = self._namespace
        exec_order = self.scan_result.get("execution_order", [])
        function_calls = self.scan_result.get("function_calls", {})

        main_lines = [
            "# render/exec_order.mcfunction",
            "# 渲染 .mcfunction 执行顺序",
            "",
        ]

        if not exec_order and not function_calls:
            main_lines.append(
                'tellraw @s [{"text":"⚡ 没有发现 .mcfunction 执行链","color":"gray"}]'
            )
            self._write_mcfunction(
                os.path.join(self._datapack_path, "data", ns, "function", "render", "exec_order.mcfunction"),
                main_lines
            )
            return

        # 标题
        main_lines.append(
            'tellraw @s [{"text":"⚡ 执行顺序","color":"gold","bold":true}]'
        )
        main_lines.append("")

        if exec_order:
            # 显示执行顺序链
            order_map = {}
            for entry in exec_order:
                caller = entry.get("caller", "")
                callee = entry.get("callee", "")
                order = entry.get("order", 0)
                order_map[order] = (caller, callee)

            sorted_orders = sorted(order_map.keys())
            for i, order in enumerate(sorted_orders):
                caller, callee = order_map[order]
                text = f"{i + 1}. {caller} → {callee}"
                escaped = text.replace("\\", "\\\\").replace('"', '\\"')
                main_lines.append(
                    f'data modify storage {ns}:temp macro set value {{text:"{escaped}",color:"white"}}'
                )
                main_lines.append(f"function {ns}:_macro/dep_line with storage {ns}:temp macro")
        else:
            # 没有执行顺序，但有 function_calls，显示调用关系
            main_lines.append(
                'tellraw @s [{"text":"  无法从入口追踪执行链，显示原始调用关系","color":"gray","italic":true}]'
            )
            main_lines.append("")
            order_num = 0
            for file_path, calls in function_calls.items():
                if calls:
                    file_name = os.path.basename(file_path)
                    for call in calls:
                        order_num += 1
                        text = f"{order_num}. {file_name} → {call}"
                        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
                        main_lines.append(
                            f'data modify storage {ns}:temp macro set value {{text:"{escaped}",color:"white"}}'
                        )
                        main_lines.append(f"function {ns}:_macro/dep_line with storage {ns}:temp macro")

        self._write_mcfunction(
            os.path.join(self._datapack_path, "data", ns, "function", "render", "exec_order.mcfunction"),
            main_lines
        )

    # ------------------------------------------------------------------
    # 方块可视化渲染
    # ------------------------------------------------------------------

    def _generate_anchor_function(self):
        """生成 .load/spawn_anchor.mcfunction：在玩家附近生成锚点 marker"""
        ns = self._namespace
        lines = [
            "# .load/spawn_anchor.mcfunction",
            "# 在玩家附近生成可视化锚点",
            "",
            "# 在玩家上方 2 格、前方 5 格处生成 anchor",
            f"execute as @a at @s run summon minecraft:marker ^ ^2 ^5 {{Tags:[\"projview_anchor\"]}}",
        ]
        self._write_mcfunction(
            os.path.join(self._datapack_path, "data", ns, "function", ".load", "spawn_anchor.mcfunction"),
            lines
        )

    def _generate_cleanup_function(self):
        """生成 render/cleanup.mcfunction：清除所有可视化实体"""
        ns = self._namespace
        lines = [
            "# render/cleanup.mcfunction",
            "# 清除所有可视化显示实体",
            "",
            "kill @e[tag=projview_display]",
        ]
        self._write_mcfunction(
            os.path.join(self._datapack_path, "data", ns, "function", "render", "cleanup.mcfunction"),
            lines
        )

    def _generate_block_tree_render(self):
        """生成 render/block_tree.mcfunction：方块文件树渲染主函数"""
        ns = self._namespace
        flat = self._flat_tree

        if not flat:
            main_lines = [
                "# render/block_tree.mcfunction",
                "# 渲染方块文件树（空）",
                "",
                "# 清除旧实体",
                f"function {ns}:render/cleanup",
                "",
                'summon minecraft:text_display ~ ~ ~ {text:"{\\"text\\":\\"📂 项目结构为空\\",\\"color\\":\\"gray\\"}",transformation:{translation:[0f,2.5f,0f],scale:[0.5f,0.5f,0.5f],left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f]},Tags:["projview_display"]}',
            ]
            self._write_mcfunction(
                os.path.join(self._datapack_path, "data", ns, "function", "render", "block_tree.mcfunction"),
                main_lines
            )
            return

        total_items = len(flat)
        max_per_page = self.BLOCK_ROW_SIZE * self.BLOCK_PAGE_ROWS  # 200
        total_pages = (total_items + max_per_page - 1) // max_per_page

        # 统计文件与目录数量
        total_files = sum(1 for item in flat if item["type"] == "file")
        total_dirs = sum(1 for item in flat if item["type"] == "directory")

        # 进度条：绿色方块数量（至少 1，最多 10）
        green_count = min(10, max(1, total_items // 20))

        # 主渲染函数
        main_lines = [
            "# render/block_tree.mcfunction",
            "# 渲染方块文件树",
            "",
            "# 清除旧实体",
            f"function {ns}:render/cleanup",
            "",
            "# 标题 text_display",
            'summon minecraft:text_display ~ ~ ~ {text:"{\\"text\\":\\"📂 项目结构\\",\\"color\\":\\"gold\\",\\"bold\\":true}",transformation:{translation:[0f,2.5f,0f],scale:[0.5f,0.5f,0.5f],left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f]},Tags:["projview_display"]}',
            "",
            "# 进度条方块（y=2.8）",
        ]

        # 生成 10 个进度条方块
        for i in range(10):
            block = "minecraft:lime_concrete" if i < green_count else "minecraft:light_gray_concrete"
            x = round(i * 0.6, 1)
            main_lines.append(
                f"summon minecraft:block_display ~ ~ ~ "
                f"{{block_state:{{Name:\"{block}\"}},"
                f"transformation:{{translation:[{x}f,2.8f,0f],scale:[0.4f,0.4f,0.4f],"
                f"left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f]}},"
                f"Tags:[\"projview_display\"],teleport_duration:5,interpolation_duration:5}}"
            )

        # 进度条统计文字
        stat_text = f"{total_files} 个文件, {total_dirs} 个目录"
        main_lines.append(
            'summon minecraft:text_display ~ ~ ~ '
            '{text:"{\\"text\\":\\"' + stat_text + '\\",\\"color\\":\\"gray\\",\\"italic\\":true}",'
            'transformation:{translation:[6.0f,2.8f,0f],scale:[0.3f,0.3f,0.3f],'
            'left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f]},'
            'Tags:["projview_display"],text_opacity:128}'
        )
        main_lines.append("")

        if total_pages == 1:
            # 单页，直接内联生成
            self._build_block_tree_page(main_lines, flat, 0, total_items)
        else:
            # 多页，生成子函数
            page_dir = os.path.join(self._datapack_path, "data", ns, "function", "render", "_bt_page")
            os.makedirs(page_dir, exist_ok=True)

            main_lines.append(f"# 根据 page 计分板分发到对应页函数")
            main_lines.append(f"execute if score @s {ns}.page matches 0 run function {ns}:render/_bt_page/0")
            for p in range(1, total_pages):
                main_lines.append(f"execute if score @s {ns}.page matches {p} run function {ns}:render/_bt_page/{p}")

            for p in range(total_pages):
                start = p * max_per_page
                end = min(start + max_per_page, total_items)
                page_lines = [
                    f"# render/_bt_page/{p}.mcfunction",
                    f"# 方块树第 {p + 1} 页",
                    "",
                ]
                self._build_block_tree_page(page_lines, flat[start:end], 0, end - start)
                self._write_mcfunction(
                    os.path.join(page_dir, f"{p}.mcfunction"),
                    page_lines
                )

        self._write_mcfunction(
            os.path.join(self._datapack_path, "data", ns, "function", "render", "block_tree.mcfunction"),
            main_lines
        )

    def _build_block_tree_page(self, lines: list, items: list, start_y: float = 0, count: int = 0):
        """将扁平文件树条目转为 block_node 宏调用行，追加到 lines

        Args:
            lines: 目标行列表
            items: 扁平文件树条目列表
            start_y: 起始 y 坐标偏移（用于多页）
            count: 条目数（可选，如果为 0 则使用 len(items)）
        """
        ns = self._namespace
        row_size = self.BLOCK_ROW_SIZE
        y = 2.0  # 第一行 y 坐标

        for i, item in enumerate(items):
            col = i % row_size
            row = i // row_size

            # 深度缩进：每层向右偏移 0.5 格
            depth = item.get("depth", 0)
            depth_offset = round(depth * 0.5, 1)
            x = round(col * 0.6 + depth_offset, 1)
            # 垂直布局：每行一个文件，从上到下排列
            current_y = round(y - row * 0.6, 1)
            # 文字在方块上方 0.5 格
            y_above = round(current_y + 0.5, 1)
            z = 0.0

            # 确定方块类型和颜色：修改过的文件使用红色
            name = item["name"]
            if item.get("modified"):
                block = "minecraft:red_concrete"
                color = "red"
            elif item["type"] == "directory":
                block = "minecraft:yellow_concrete"
                color = item["color"]
            else:
                block = self.EXT_BLOCK_MAP.get(item["ext"], "minecraft:white_concrete")
                color = item["color"]

            # 用 json.dumps 构建 JSON 文本组件，避免转义问题
            text_component = json.dumps(
                {"text": f"{item['icon']} {name}", "color": color},
                ensure_ascii=False,
                separators=(',', ':')
            )
            # 替换单引号防止破坏 NBT 单引号字符串
            text_component = text_component.replace("'", "\\u0027")

            lines.append(
                f"function {ns}:_macro/block_node "
                f"{{x:{x}, y:{current_y}, z:{z}, y_above:{y_above}, "
                f"block:\"{block}\", text_component:'{text_component}'}}"
            )

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _write_json(self, path: str, data: dict):
        """写入 JSON 文件（UTF-8 without BOM，LF 换行）"""
        with open(path, "w", encoding="utf-8", newline="") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _write_mcfunction(self, path: str, lines: list):
        """写入 .mcfunction 文件（UTF-8 without BOM，LF 换行）"""
        with open(path, "w", encoding="utf-8", newline="") as f:
            for line in lines:
                f.write(line + "\n")

    def _report(self, callback, percent: int, message: str):
        """调用进度回调"""
        if callback:
            try:
                callback(percent, message)
            except Exception:
                pass
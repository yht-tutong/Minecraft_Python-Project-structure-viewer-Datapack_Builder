# scanner.py
# 项目扫描引擎：递归扫描目录，解析依赖和调用关系

import os
import re
import ast
import json
import time
from collections import defaultdict, deque
from fnmatch import fnmatch


class ProjectScanner:
    """项目扫描器：递归扫描目录，解析文件依赖关系与执行顺序"""

    # 默认忽略的目录名
    DEFAULT_IGNORE_DIRS = {
        ".git", "__pycache__", ".venv", "venv", "node_modules",
        ".idea", ".vscode", ".pytest_cache", ".mypy_cache", ".tox",
        ".nox", ".eggs", "dist", "build", "env", ".pixi",
    }

    def __init__(self, source_path: str):
        """初始化扫描器

        Args:
            source_path: 要扫描的源项目根目录路径
        """
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"源路径不存在: {source_path}")
        if not os.path.isdir(source_path):
            raise NotADirectoryError(f"源路径不是目录: {source_path}")

        self.source_path = os.path.abspath(source_path)
        self._gitignore_patterns = []     # .gitignore 解析后的模式列表
        self._negate_patterns = []        # ! 取反模式列表

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def scan(self, progress_callback=None) -> dict:
        """执行完整扫描

        Args:
            progress_callback: 可选回调，签名 callback(percent, message)

        Returns:
            dict: {
                "source_path": str,
                "file_tree": dict,
                "dependencies": dict,       # Python import 依赖
                "function_calls": dict,     # .mcfunction function 调用
                "execution_order": list,    # 执行顺序（拓扑排序）
            }
        """
        self._report(progress_callback, 0, "正在读取 .gitignore...")
        self._load_gitignore()

        self._report(progress_callback, 10, "正在扫描目录结构...")
        file_tree = self._scan_directory(self.source_path)

        self._report(progress_callback, 40, "正在解析 Python import...")
        py_files = self._collect_files_by_ext(file_tree, ".py")
        dependencies = self._parse_python_imports(py_files)

        self._report(progress_callback, 60, "正在解析 .mcfunction 调用...")
        mc_files = self._collect_files_by_ext(file_tree, ".mcfunction")
        function_calls = self._parse_mcfunction_calls(mc_files)

        self._report(progress_callback, 80, "正在分析执行顺序...")
        execution_order = self._analyze_execution_order(function_calls, file_tree)

        self._report(progress_callback, 100, "扫描完成")

        return {
            "source_path": self.source_path,
            "file_tree": file_tree,
            "dependencies": dependencies,
            "function_calls": function_calls,
            "execution_order": execution_order,
        }

    # ------------------------------------------------------------------
    # .gitignore 解析
    # ------------------------------------------------------------------

    def _load_gitignore(self):
        """读取并解析项目根目录下的 .gitignore 文件"""
        gitignore_path = os.path.join(self.source_path, ".gitignore")
        if not os.path.isfile(gitignore_path):
            return

        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # 跳过空行和注释
                    if not line or line.startswith("#"):
                        continue
                    # 取反模式
                    if line.startswith("!"):
                        self._negate_patterns.append(line[1:])
                    else:
                        self._gitignore_patterns.append(line)
        except (OSError, UnicodeDecodeError):
            pass  # 读取失败则忽略，继续扫描

    def _is_ignored(self, rel_path: str, is_dir: bool) -> bool:
        """判断相对路径是否被 gitignore 规则忽略

        Args:
            rel_path: 相对于项目根目录的路径（使用正斜杠）
            is_dir: 是否为目录

        Returns:
            bool: True 表示应忽略
        """
        # 先检查取反模式
        for pattern in self._negate_patterns:
            if self._match_gitignore_pattern(pattern, rel_path, is_dir):
                return False

        # 再检查普通模式
        for pattern in self._gitignore_patterns:
            if self._match_gitignore_pattern(pattern, rel_path, is_dir):
                return True

        return False

    def _match_gitignore_pattern(self, pattern: str, path: str, is_dir: bool) -> bool:
        """检查路径是否匹配单个 gitignore 模式

        支持: *（匹配除 / 外的任意字符）、**（匹配任意路径段）、
              ?（匹配单个字符）、[abc]（字符组）

        Args:
            pattern: gitignore 模式
            path: 相对路径
            is_dir: 是否为目录

        Returns:
            bool: 是否匹配
        """
        # 去除尾部空格
        pattern = pattern.rstrip()

        # 如果模式以 / 结尾，只匹配目录
        if pattern.endswith("/"):
            if not is_dir:
                return False
            pattern = pattern[:-1]

        # 如果模式以 / 开头，从根目录匹配
        if pattern.startswith("/"):
            pattern = pattern[1:]
            # 转换为 fnmatch 用的格式
            return self._fnmatch_path(path, pattern)

        # 模式不以 / 开头，匹配任意层级
        # 检查路径的每一级后缀
        if self._fnmatch_path(path, pattern):
            return True
        # 也检查路径的任意后缀
        parts = path.split("/")
        for i in range(len(parts)):
            sub_path = "/".join(parts[i:])
            if self._fnmatch_path(sub_path, pattern):
                return True
        return False

    def _fnmatch_path(self, path: str, pattern: str) -> bool:
        """使用 fnmatch 匹配路径，额外处理 ** 模式

        Args:
            path: 待匹配路径
            pattern: 匹配模式

        Returns:
            bool: 是否匹配
        """
        # 处理 ** 模式
        if "**" in pattern:
            return self._match_double_star(pattern, path)
        return fnmatch(path, pattern)

    def _match_double_star(self, pattern: str, path: str) -> bool:
        """处理包含 ** 的 gitignore 模式匹配

        Args:
            pattern: 包含 ** 的匹配模式
            path: 待匹配路径

        Returns:
            bool: 是否匹配
        """
        # 将 ** 替换为占位符，再用 fnmatch 匹配
        # 策略：将模式按 ** 分割，检查路径是否依次包含各段
        parts = pattern.split("**")
        # 如果 pattern 就是 "**"，匹配一切
        if pattern == "**":
            return True

        # 构建正则表达式
        regex_parts = []
        for i, part in enumerate(parts):
            if part:
                # 将 fnmatch 模式转为正则
                regex_parts.append(re.escape(part).replace(r"\*", "[^/]*").replace(r"\?", "."))
            if i < len(parts) - 1:
                regex_parts.append(r"(?:.*/)?")

        regex_str = "".join(regex_parts)
        # 确保匹配完整路径
        regex_str = "^" + regex_str + "$"
        try:
            return bool(re.match(regex_str, path))
        except re.error:
            return False

    # ------------------------------------------------------------------
    # 目录扫描
    # ------------------------------------------------------------------

    def _scan_directory(self, dir_path: str) -> dict:
        """递归扫描目录，生成文件树数据结构

        Args:
            dir_path: 要扫描的目录绝对路径

        Returns:
            dict: 文件树节点
        """
        dir_name = os.path.basename(dir_path) or dir_path
        node = {
            "name": dir_name,
            "type": "directory",
            "path": os.path.relpath(dir_path, os.path.dirname(self.source_path)),
            "children": [],
        }

        try:
            entries = sorted(os.listdir(dir_path))
        except PermissionError:
            return node
        except OSError:
            return node

        for entry in entries:
            entry_path = os.path.join(dir_path, entry)
            is_dir = os.path.isdir(entry_path)

            # 跳过默认忽略目录
            if is_dir and entry in self.DEFAULT_IGNORE_DIRS:
                continue

            # 计算相对路径用于 gitignore 匹配
            try:
                rel_path = os.path.relpath(entry_path, self.source_path).replace("\\", "/")
            except ValueError:
                continue

            # 检查 gitignore 规则
            if self._is_ignored(rel_path, is_dir):
                continue

            if is_dir:
                child = self._scan_directory(entry_path)
                if child["children"]:  # 只保留非空目录
                    node["children"].append(child)
                else:
                    # 空目录也保留
                    node["children"].append(child)
            else:
                ext = os.path.splitext(entry)[1].lower()
                # 检查文件修改时间：24 小时内修改过的标记为 modified
                try:
                    mtime = os.path.getmtime(entry_path)
                    modified = (time.time() - mtime) < 86400
                except OSError:
                    modified = False
                child = {
                    "name": entry,
                    "type": "file",
                    "path": os.path.relpath(entry_path, os.path.dirname(self.source_path)).replace("\\", "/"),
                    "ext": ext,
                    "modified": modified,
                }
                node["children"].append(child)

        return node

    def _collect_files_by_ext(self, file_tree: dict, ext: str) -> list:
        """从文件树中收集指定扩展名的文件路径列表

        Args:
            file_tree: 文件树根节点
            ext: 文件扩展名（如 ".py"）

        Returns:
            list: 文件绝对路径列表
        """
        result = []

        def _walk(node):
            if node["type"] == "file" and node.get("ext") == ext:
                # 将相对路径转为绝对路径
                abs_path = os.path.join(
                    os.path.dirname(self.source_path), node["path"]
                )
                result.append(os.path.normpath(abs_path))
            for child in node.get("children", []):
                _walk(child)

        _walk(file_tree)
        return result

    # ------------------------------------------------------------------
    # Python import 解析
    # ------------------------------------------------------------------

    def _parse_python_imports(self, py_files: list) -> dict:
        """解析所有 Python 文件的 import 语句

        Args:
            py_files: Python 文件绝对路径列表

        Returns:
            dict: {file_path: [imported_modules], ...}
        """
        dependencies = {}

        for file_path in py_files:
            rel_path = os.path.relpath(
                file_path, os.path.dirname(self.source_path)
            ).replace("\\", "/")
            try:
                imports = self._parse_single_py_file(file_path)
                dependencies[rel_path] = imports
            except Exception:
                dependencies[rel_path] = []

        return dependencies

    def _parse_single_py_file(self, file_path: str) -> list:
        """解析单个 Python 文件的 import 语句

        Args:
            file_path: Python 文件绝对路径

        Returns:
            list: 导入的模块名列表
        """
        imports = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return imports

        try:
            tree = ast.parse(source)
        except SyntaxError:
            # 语法错误时回退到正则匹配
            return self._parse_imports_with_regex(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                # import X, import X.Y
                for alias in node.names:
                    imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                # from X import Y, from .X import Y
                if node.module is not None:
                    imports.append(node.module.split(".")[0])
                elif node.level is not None and node.level > 0:
                    # 相对导入: from . import Y  或  from .. import Y
                    imports.append(self._resolve_relative_import(file_path, node.level))

        return imports

    def _parse_imports_with_regex(self, source: str) -> list:
        """正则方式解析 import 语句（AST 解析失败时的回退方案）

        Args:
            source: Python 源代码字符串

        Returns:
            list: 导入的模块名列表
        """
        imports = []
        # 匹配 import X 或 import X, Y
        import_pattern = re.compile(
            r"^\s*import\s+([\w\d_]+(?:\s*,\s*[\w\d_]+)*)",
            re.MULTILINE
        )
        # 匹配 from X import Y 或 from .X import Y
        from_pattern = re.compile(
            r"^\s*from\s+(\.*)([\w\d_]+(?:\.[\w\d_]+)*)\s+import",
            re.MULTILINE
        )

        for match in import_pattern.finditer(source):
            line = match.group(0)
            # 跳过注释行（理论上不会匹配到，但做安全处理）
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            modules = match.group(1).split(",")
            for mod in modules:
                mod = mod.strip().split(".")[0]
                if mod:
                    imports.append(mod)

        for match in from_pattern.finditer(source):
            line = match.group(0)
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            module = match.group(2)
            imports.append(module.split(".")[0])

        return imports

    def _resolve_relative_import(self, file_path: str, level: int) -> str:
        """将相对导入 level 解析为模块名

        Args:
            file_path: 当前文件绝对路径
            level: 相对导入层级（1 表示当前目录，2 表示上级目录...）

        Returns:
            str: 解析后的模块名表示
        """
        # 从文件路径向上走 level 层
        rel = os.path.relpath(file_path, self.source_path)
        parts = rel.replace("\\", "/").split("/")
        # 去掉文件名
        parts = parts[:-1]
        # 向上走 level-1 层（level=1 表示当前包目录）
        if level > len(parts):
            return f"<relative:{level}>"
        # 取对应层级的目录名作为模块名
        target_parts = parts[:len(parts) - level + 1] if level > 1 else parts
        return target_parts[-1] if target_parts else f"<relative:{level}>"

    # ------------------------------------------------------------------
    # .mcfunction 调用解析
    # ------------------------------------------------------------------

    def _parse_mcfunction_calls(self, mc_files: list) -> dict:
        """解析所有 .mcfunction 文件中的 function 调用

        Args:
            mc_files: .mcfunction 文件绝对路径列表

        Returns:
            dict: {file_path: [called_functions], ...}
        """
        function_calls = {}

        for file_path in mc_files:
            rel_path = os.path.relpath(
                file_path, os.path.dirname(self.source_path)
            ).replace("\\", "/")
            try:
                calls = self._parse_single_mcfunction(file_path)
                function_calls[rel_path] = calls
            except Exception:
                function_calls[rel_path] = []

        return function_calls

    def _parse_single_mcfunction(self, file_path: str) -> list:
        """解析单个 .mcfunction 文件中的 function 调用

        Args:
            file_path: .mcfunction 文件绝对路径

        Returns:
            list: 被调用的 function 列表（格式: namespace:path）
        """
        calls = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    # 跳过注释行（以 # 开头）
                    if not stripped or stripped.startswith("#"):
                        continue
                    # 匹配 function namespace:path 调用
                    # 格式: function <namespace>:<path>
                    match = re.match(
                        r"^\s*function\s+([\w\d_]+:[\w\d_/.-]+)",
                        stripped
                    )
                    if match:
                        calls.append(match.group(1))
        except (OSError, UnicodeDecodeError):
            pass

        return calls

    # ------------------------------------------------------------------
    # 执行顺序分析
    # ------------------------------------------------------------------

    def _analyze_execution_order(self, function_calls: dict, file_tree: dict) -> list:
        """从 load.json/tick.json 入口开始，递归追踪 function 调用链

        使用拓扑排序确保正确的执行顺序，同时检测循环依赖。

        Args:
            function_calls: {file_path: [called_functions], ...}
            file_tree: 文件树数据结构

        Returns:
            list: [{caller, callee, order}, ...]
        """
        # 找到 load.json 和 tick.json 的入口函数
        entry_functions = self._find_entry_functions(file_tree)

        if not entry_functions:
            return []

        # 构建调用图: {caller_function: [callee_functions]}
        call_graph = defaultdict(list)
        # 解析 function 调用中的 namespace:path 到文件路径的映射
        ns_to_path = self._build_namespace_path_map(file_tree)

        for caller_path, calls in function_calls.items():
            # 将 caller 路径转为 namespace:path 格式
            caller_ns = self._filepath_to_namespace(caller_path)
            for callee_ns in calls:
                # 将 callee 解析为实际文件路径
                callee_path = ns_to_path.get(callee_ns)
                if callee_path:
                    call_graph[caller_ns].append(callee_ns)
                else:
                    # 外部调用（不在本项目中的 function），仍记录
                    call_graph[caller_ns].append(callee_ns)

        # BFS 遍历 + 拓扑排序
        visited = set()
        order_index = 0
        result = []

        # 从入口开始 BFS
        queue = deque(entry_functions)
        in_queue = set(entry_functions)

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            for callee in call_graph.get(current, []):
                result.append({
                    "caller": current,
                    "callee": callee,
                    "order": order_index,
                })
                order_index += 1

                if callee not in visited and callee not in in_queue:
                    queue.append(callee)
                    in_queue.add(callee)

        return result

    def _find_entry_functions(self, file_tree: dict) -> list:
        """从文件树中查找 load.json 和 tick.json 中定义的入口函数

        Args:
            file_tree: 文件树数据结构

        Returns:
            list: 入口 function 的 namespace:path 格式列表
        """
        entry_functions = []

        # 查找 data/<namespace>/tags/function/load.json 和 tick.json
        def _find_tag_files(node, path_parts=None):
            if path_parts is None:
                path_parts = []
            if node["type"] == "file":
                if node["name"] in ("load.json", "tick.json"):
                    # 检查是否在 tags/function 目录下
                    if len(path_parts) >= 3 and path_parts[-2:] == ["tags", "function"]:
                        # 提取命名空间: path_parts[-3] 是 namespace
                        namespace = path_parts[-3]
                        entry_functions.append((node["path"], namespace))
            for child in node.get("children", []):
                _find_tag_files(child, path_parts + [node["name"]])

        _find_tag_files(file_tree)

        # 解析 load.json 和 tick.json 中的 values
        entries = []
        for json_path, namespace in entry_functions:
            abs_json_path = os.path.join(
                os.path.dirname(self.source_path), json_path
            )
            try:
                with open(abs_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                values = data.get("values", [])
                for val in values:
                    if isinstance(val, str):
                        # 格式: "namespace:path" 或 "namespace:path"
                        if ":" in val:
                            entries.append(val)
                        else:
                            # 省略命名空间的情况，使用 JSON 所在命名空间
                            entries.append(f"{namespace}:{val}")
                    elif isinstance(val, dict):
                        # 可能包含额外的配置
                        name = val.get("name") or val.get("id") or ""
                        if name:
                            entries.append(name)
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                pass

        return entries

    def _build_namespace_path_map(self, file_tree: dict) -> dict:
        """构建 namespace:path 到文件相对路径的映射

        例如: "mydatapack:load/init" -> "data/mydatapack/function/load/init.mcfunction"

        Args:
            file_tree: 文件树数据结构

        Returns:
            dict: {namespace:path: file_relative_path}
        """
        ns_map = {}

        def _walk(node):
            if node["type"] == "file" and node.get("ext") == ".mcfunction":
                path = node["path"].replace("\\", "/")
                ns = self._filepath_to_namespace(path)
                if ns:
                    ns_map[ns] = path
            for child in node.get("children", []):
                _walk(child)

        _walk(file_tree)
        return ns_map

    def _filepath_to_namespace(self, file_path: str) -> str:
        """将文件路径转为 namespace:path 格式

        例如: "data/mydatapack/function/load/init.mcfunction" -> "mydatapack:load/init"
        也支持带根目录前缀的路径，如 "ProjectName/data/mydatapack/function/...".

        Args:
            file_path: 文件相对路径

        Returns:
            str: namespace:path 格式，或空字符串
        """
        path = file_path.replace("\\", "/")
        # 匹配 data/<namespace>/function(s)/<path>.mcfunction
        # 路径可能以 "项目名/data/" 或 "data/" 开头
        match = re.search(
            r"data/([\w\d_]+)/functions?/(.+)\.mcfunction$",
            path
        )
        if match:
            namespace = match.group(1)
            func_path = match.group(2)
            return f"{namespace}:{func_path}"
        return ""

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _report(self, callback, percent: int, message: str):
        """调用进度回调（如果提供）"""
        if callback:
            try:
                callback(percent, message)
            except Exception:
                pass
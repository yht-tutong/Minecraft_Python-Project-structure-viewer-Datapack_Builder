# Minecraft Python Project Structure Viewer Datapack Builder

一个 Python 工具，扫描任意项目目录，自动生成 Minecraft 数据包，在游戏内以**方块实体**可视化展示项目的文件树、依赖关系、执行顺序，支持定时自动运行和热重载。

## 作者信息

- **B站主页**：[https://space.bilibili.com/630095673](https://space.bilibili.com/630095673)

## 功能特性

- 扫描 Python 项目目录，解析 import 依赖关系
- 扫描 Minecraft 数据包目录，解析 .mcfunction 调用链和执行顺序
- 自动生成兼容 1.21.9+ 的 Minecraft 数据包
- 数据包支持热重载：`/reload` 后自动刷新方块可视化
- **方块可视化**：使用 `block_display` 实体在 Minecraft 世界中渲染彩色文件树
  - 目录：黄色 | .py：浅蓝 | .mcfunction：橙色 | .json：黄绿 | 图片：紫色 | 修改过：红色
- **定时自动运行**：每 N 秒自动扫描→生成→RCON `/reload`
- PyQt5 图形界面：文件树预览、依赖关系图、进度监控、自动运行控制
- 支持 RCON 自动 reload

## 配置方法

**无需手动创建配置文件！** 首次运行程序时会自动弹出配置引导，按提示填入路径即可。

配置文件 `config.json` 格式如下（程序自动生成，仅作参考）：

```json
{
    "source_path": "e:/Project/YourProject",
    "output_datapack_name": "project-structure-viewer",
    "mc_saves_path": "e:/Project/.minecraft/versions/1.21.11/saves/你的存档/datapacks",
    "auto_run": false,
    "interval_seconds": 30,
    "rcon": {
        "enabled": false,
        "host": "127.0.0.1",
        "port": 25575,
        "password": ""
    }
}
```

配置保存在本地 `config.json`，不会被提交到 Git（已在 `.gitignore` 中忽略）。

## 使用方法

### 一键启动（推荐）

```bash
python launcher.py
```

启动后选择：
- `[1]` 打开 PyQt 图形界面（推荐）
- `[2]` 命令行生成数据包
- `[3]` 查看帮助

### 自动运行模式

在 GUI 中勾选"自动运行"，设置间隔秒数（默认 30），程序会定时自动：
1. 重新扫描项目目录
2. 重新生成数据包
3. 通过 RCON 发送 `/reload`（需配置 RCON）
4. Minecraft 中自动刷新方块可视化

### 命令行

```bash
# 生成数据包
python main.py -s "E:/Project/YourProject" -o "E:/Project/.minecraft/versions/1.21.11/saves/你的存档/datapacks" -n "project-viewer"

# 使用配置文件
python main.py -c config.json

# 仅打开 GUI
python gui.py
```

### Minecraft 中使用

生成数据包后，在游戏中：
1. 放入存档的 `datapacks/` 目录
2. 执行 `/reload` 重载数据包
3. 方块可视化墙会自动出现在玩家前方
4. 也可使用 `/trigger` 手动查看：
   - `/trigger <namespace>.trigger set 1` — 文件树
   - `/trigger <namespace>.trigger set 2` — 依赖关系
   - `/trigger <namespace>.trigger set 3` — 执行顺序

## 项目结构

```
├── main.py                  # 主入口：整合扫描+生成，命令行接口
├── scanner.py               # 扫描引擎：递归扫描、解析依赖、执行顺序
├── datapack_generator.py    # 数据包生成器：生成五子棋格式 datapack + 方块渲染
├── gui.py                   # PyQt5 图形界面
├── launcher.py              # 交互式启动器
├── requirements.txt         # 依赖列表
├── config.json              # 配置文件（自动生成，不提交）
├── .gitignore
├── LICENSE
└── README.md
```

## 依赖

- Python 3.7+
- PyQt5

```bash
pip install -r requirements.txt
```

## RCON 配置（可选）

如需自动 `/reload`，在 Minecraft 存档的 `server.properties` 中添加：

```properties
enable-rcon=true
rcon.port=25575
rcon.password=你的密码
```

然后在 `config.json` 中填入对应的 RCON 配置。

## License

MIT License
# UMA-bot-discord

基于 [NoneBot2](https://nonebot.dev/) 的 Discord 多功能机器人，以 **美浦波旁**（Mihono Bourbon）角色为交互载体。

## 功能一览

| 模块 | 说明 |
|------|------|
| AI 对话 | 基于 DeepSeek / Ollama，带记忆系统 + FAISS 向量知识库 + 联网搜索 + 图片识别 |
| AI 绘图 | 对接本地 ComfyUI，支持多种工作流、Lora 管理、高清修复、多角色合成 |
| 今日担当 | 每日随机赛马娘角色邂逅 |   #需自行在项目根目录下配置pixiv_images文件夹，下属不同角色的子文件夹以及图片。
| 人设切换 | 多种 AI 角色人格切换 |
| 内容审核 | 垃圾消息检测、用户黑名单、每日配额管理 |
| 知识管理 | Tkinter GUI 工具管理 FAISS 知识库 |

## 项目结构

```
├── bot.py                    # 启动入口
├── bpdiscord/
│   └── plugins/bpdiscord/    # 核心插件
│       ├── ai/               #   AI 对话模块
│       ├── features/         #   功能模块 (绘图、今日担当)
│       ├── admin/            #   管理员命令
│       ├── config.py         #   统一配置
│       └── help.py           #   帮助信息
├── comfyui/                  # ComfyUI 工作流 JSON 模板
├── data/
│   ├── aisetting/            # AI 人设文件
│   └── knowledge_db/         # FAISS 知识库文本
├── knowledge_manager.py      # 知识库管理 GUI
├── pyproject.toml
└── requirements.txt
```

## 快速开始

### 1. 环境要求

- Python 3.9+
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI)（绘图功能需要）
- Discord Bot Token（[申请地址](https://discord.com/developers/applications)）

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置文件

复制环境变量模板并填写真实值：

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 API Key 和 Discord Bot Token：

| 变量 | 说明 |
|------|------|
| `AICHATKEY1` | DeepSeek API Key |
| `BINGSEARCHKEY1` | 搜索 API Key (bocha.cn) |
| `VIRSIONKEY1` | Doubao 视觉识别 API Key |
| `DISCORD_BOTS` | Discord Bot Token (JSON 格式) |
| `ADMIN1` / `SUPERUSER` | 管理员 Discord 用户 ID |
| `COMFYUI_URL` | ComfyUI 服务器地址 |

### 4. ComfyUI 工作流

`comfyui/` 目录下包含 5 个工作流模板：

| 文件 | 说明 |
|------|------|
| `discord.json` | 标准 SDXL 绘图 |
| `discord_高清.json` | 图生图高清修复（放大+超分） |
| `multidraw.json` | 多角色分区绘制 |
| `discord_anima.json` | Anima UNet 架构绘图 |
| `uma.json` | 赛马娘专用工作流 |

### 5. 启动

```bash
nb run
```

或直接：

```bash
python bot.py
```

### 6. 使用命令

在 Discord 中发送 `help` 查看完整命令列表。

部分常用命令：

| 命令 | 功能 |
|------|------|
| `波旁 <内容>` | AI 对话 |
| `draw <提示词>` | AI 绘图 |
| `今日担当` | 每日随机角色 |
| `lora列表` | 查看可用 Lora |
| `切换工作流 anima` | 切换 Anima 绘图模型 |

## 知识库管理

```bash
python knowledge_manager.py
```

启动 Tkinter GUI，支持导入 / 搜索 / 删除 / 导出知识条目。

## License

MIT

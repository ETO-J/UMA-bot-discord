# 验证证据清单（申请材料 ⇄ 当前代码 逐条核对）

> 目的：把申请表单/隐私政策里的每一条事实性陈述，锚定到当前代码、文档与实机日志的证据。
> 依据：机器人主体 `C:\Users\Administrator\bpdsh`（DeepSeek Harness 0.1.5-rc.1 + discord.js 14.27，
> Node v24.14.0），网页绘图站 `C:\Users\Administrator\bpdiscord\webapp`（FastAPI）。
> 核对日期：2026-10-19。**路径约定**：无盘符前缀的 `packages/...`、`src/...`、`.env`、
> `docs/STATUS.md` 等均相对 `C:\Users\Administrator\bpdsh`；`webapp/...` 相对
> `C:\Users\Administrator\bpdiscord`。本清单由一次代码级审计 + 子代理复核生成。

---

## A. 已验证为真（可直接用于表单）

| # | 申请材料中的陈述 | 证据 |
|---|---|---|
| A1 | 机器人只请求 Guilds / GuildMessages / DirectMessages / **MessageContent** 四个 intent | `packages/dsh-bot-discord/src/index.js:132-141`；实机日志显示能读到文本（intent 实际生效） |
| A2 | 所有命令都是**纯文本消息**，不是 Discord 应用命令（无 InteractionCreate / 无 SlashCommandBuilder） | 全仓无 `InteractionCreate`、无 `SlashCommandBuilder`；驱动把 `allowBare:true` 传入 `index.js:325,356,564` |
| A3 | Discord 上命令 `/` 可省略（`波旁 你好`＝`/波旁 你好`；`帮助`＝`/帮助`） | `packages/dsh-bot-core/src/commands.js:24-41`（matchTrigger） |
| A4 | 核心命令：波旁 对话、帮助、人设列表/切换人设、学习/批量学习/知识列表/删除知识、识图、涩图、今日担当、debug、广播、清除、重启 | 帮助文本 `packages/dsh-bot-core/src/index.js:149-162`；处理 `:180-211`；知识 `src/knowledge.js:122-125`；管理 `src/admin.js:40-65` |
| A5 | Discord 专属管理员命令：撤回、长期撤回、ban、抓取 | `src/moderation.js:68-74,133,153,178`；`src/grabbing.js:111-145,791-913`；接线 `src/index.js:436-493` |
| A6 | 自由聊天：频道白名单内、非命令消息读取文本并交 AI 门卫判断（当前 `BOPANG_AUTOCHAT=off` 关闭） | `src/index.js:586-637`；`src/freechat.js:98-120`；`.env` 中 `BOPANG_AUTOCHAT=off` |
| A7 | 自动翻译：配置频道（2 个）内每条人类文本消息检测语言并回复译文 | `src/translate.js:19-34,153-189` |
| A8 | 陷阱频道审核：配置频道（7 个）内**任何**消息 → 封禁+7 天消息清除+解封；10 分钟扫描近 50 条；**不读取消息文本** | `src/censor.js:42-70,100-140,188-246`（判定只用 guild/channel/author id） |
| A9 | 黑名单用户：不回复、不进入会话记忆；但**入站消息在检查前已写入活动日志**（≤300 字符） | `src/admin.js:35-38`；驱动检查 `src/index.js:343-353`；日志在 `index.js:336-341`（先于黑名单检查） |
| A10 | 会话记忆：按频道（私聊按用户）保存于 dsh 会话存储（`.dsh/sessions/...jsonl.zstd`，压缩 JSONL）；**无自动过期/清理** | 实机目录 `.dsh/sessions/--C-Users-Administrator-bpdsh-bot-workspace--/`；`dsh-session-persistence-jsonl/README.md:54-70,157` |
| A11 | `/清除` 只让后续消息进入新会话记录（内存中的代际计数），**不删除磁盘文件**，且重启后可能恢复旧会话 | `src/index.js:129-130,166-167,415-433`；持久化 README "no deletion API" |
| A12 | 管理命令、抓取、撤回、ban 走 REST API（不需要 Server Members intent） | `src/grabbing.js`（channel.messages.fetch）；`src/moderation.js`（REST 删/封）；`index.js:676-680` |
| A13 | 出站审查（默认开启）：主消息路径在发送前检查凭据形态并替换；**但 `广播`、自动翻译回复、审核通知等路径绕过** | `src/index.js:211-235`（guardOutbound）；绕过：`index.js:388`（广播）、`translate.js:178`（翻译回复） |
| A14 | 发送前审查先审全文再切段（防跨切分凭据） | `src/messages.js`（buildOutgoingMessages）；`guard.js:193-197` |
| A15 | AI 运行时沙箱：写入限制在 `bot-workspace`（workspace-write、Windows ACL），**读取不受限**；机密保护靠提示词约束+出站审查 | `packages/bot-workspace/README.md:21-22`；`guard.js:13-23`；`overlays/bot-sandbox.yml:25-32`；`agent.js:40,119-123` |
| A16 | 知识库（学习/批量学习/删除）为本地 FAISS，**跨服务器共享**；当前 246 条；管理员可删 | `data/knowledge_db/`；sidecar `127.0.0.1:8765`；`packages/dsh-bot-core/src/knowledge.js:58-101,122-125` |
| A17 | 外部服务：DeepSeek（对话/视觉/门卫/翻译/搜索）、SauceNAO（识图，图片字节）、Pixiv（关键词）、Discord、本地 ComfyUI（网页绘图）；无出售/训练管线 | 代码与实机日志；`sidecar/app/config.py`；无任何训练代码 |
| A18 | 可选遥测：dsh OTel 端点 `harness-telemetry.deepseeksvc.com` 为 FEEDBACK_ONLY，日常流量不导出；显式提交反馈才含会话片段 | `dsh-base/cordis.patch.yml:168-197` |
| A19 | QQ 机器人同一进程运行，共享知识库/会话库/日志/AI 运行时；两平台消息不互转 | `scripts/start-bot.ps1:111`（双 overlay）；实机日志同时有 `[qq]` 与 `[dc]` |
| A20 | 网页站与机器人同一 Discord 应用：OAuth2 仅 `identify` 权限；回调 `https://bourbon-draw.cn/api/auth/callback` | `webapp/auth.py:28-39`；`webapp/config.py:141-146`（DISCORD_CLIENT_ID=1452674140137066524） |
| A21 | 网页站 `https://bourbon-draw.cn` 当前公开可访问（绘图界面） | 实际抓取返回界面；nginx 配置 `webapp/nginx/bourbon-draw.cn.conf` |

## B. 必须你人工确认/处理（我无法代办）

| # | 事项 | 为什么必须人工 |
|---|---|---|
| B1 | Stripe 身份验证（App Verification 要求） | 需要你的证件与人脸/实名流程 |
| B2 | 提交表单 / 勾认证框 / 上传真实截图到 Imgur | 需要登录你的 Discord 开发者账号；截图取自真实服务器 |
| B3 | DeepSeek 平台"数据是否用于训练"设置 | 网页后台操作；若默认开启，需关闭后 "No" 才成立 |
| B4 | 支持服务器、联系方式占位符替换 | 需要你决定邮箱与服务器邀请链接 |
| B5 | 在 Bot 页打开 Message Content 开关（批准后） | 开发者后台操作 |

## C. 外部资料引用（第三方页面；以官方后台最终显示为准）

- 10,000 唯一用户门槛自 2026-06 起、批准后每年重申：CrowBots 文档
  <https://doc.crowbots.shop/gestion-v2/verification>、phpbotscout 文档
  <https://phpbotscout.phpboyscout.uk/how-to/discord-application/>。
- 应用验证需身份验证（Stripe）与完整应用信息：Discord-Media 2025-11 指南
  <https://discord-media.com/en/news/discord-app-verification-guide-get-your-coveted-badge.html>。
- Intent 表单字段与审核建议：StartIT 指南
  <https://startit.bot/blog/how-to-fill-discords-privileged-intents-form-as-startit-customer/>。

## D. 与 2026-09 旧稿的差异（已修正）

| 旧稿说法 | 事实 | 处理 |
|---|---|---|
| 机器人提供 `draw`/`multidraw`/Lora/工作流/高清等 Discord 绘图命令 | 无绘图命令；ComfyUI 仅健康监测；绘图在 bourbon-draw.cn 网页 | 已从描述与理由中删除 |
| 陷阱频道审核"扫描垃圾/滥用文本"并作为 intent 理由 | 审核不读文本，只对诱饵频道内的发言封禁+清屏 | 不再列为 content 用途 |
| 频道范围"由服务器管理员启用" | 全部由运营者全局环境变量配置，成员无法开关 | 已改为"运营者配置" |
| `/清除`"整体清空会话库" | 仅内存代际切换，不删磁盘文件，重启可恢复 | 隐私政策与证据已如实说明 |
| 消息"只临时发送给 AI/搜索 API" | 会话与日志在本地长期保存；另有 SauceNAO/Pixiv/Discord/可选遥测 | 隐私政策已完整列出 |
| 知识库"服务器专属" | 全局/跨服共享（246 条） | 已说明 |
| 黑名单用户"不被存储" | 不回复、不进记忆；但入站片段进活动日志 | 已补充说明 |
| "基于 NoneBot2" | dsh + discord.js | 已更新 |

## E. 未覆盖 / 如实备注

- `/抓取` 从未在真实频道完整实跑（`data/grabbing_data` 尚不存在）；如被问及，如实说明"管理员按需
  使用、尚未生产实跑"。
- 自由聊天当前关闭（`BOPANG_AUTOCHAT=off`），Discord 定时问候未配置频道（QQ 群问候正常）；
  审核测试时 @机器人 与所有命令不受影响。
- 活动日志文件名按启动日命名且不在午夜切换（`bot-20261017.log` 在 10-19 仍在写）；无自动保留，
  需运营者手动清理。
- README/verification-log 中几处旧描述（如 `/抓取` 不在 `/帮助`、所有出站都审查）与代码不符，
  供内部参考时以代码为准。

# 验证证据清单（申请材料 ⇄ 当前代码 逐条核对）

> 目的：把申请表单/隐私政策里的每一条事实性陈述，锚定到当前代码与文档的证据行。
> 依据：机器人主体 `C:\Users\Administrator\bpdsh`（DeepSeek Harness + discord.js，2026-10 现状），
> 网页绘图站 `C:\Users\Administrator\bpdiscord\webapp`（FastAPI）。
> 核对日期：2026-10-19。标注路径的行号以本次会话读到的版本为准。
> **路径约定**：无盘符前缀的 `packages/...`、`src/...`、`.env`、`docs/STATUS.md` 等均相对
> `C:\Users\Administrator\bpdsh`；`webapp/...` 相对 `C:\Users\Administrator\bpdiscord`。

---

## A. 已验证为真（可直接用于表单）

| # | 申请材料中的陈述 | 证据 |
|---|---|---|
| A1 | 机器人只申请 Guilds / GuildMessages / DirectMessages / **MessageContent** 四个 intent | `packages/dsh-bot-discord/src/index.js:132-139` |
| A2 | Discord 上命令的 `/` 可省略（`波旁 你好`＝`/波旁 你好`；`帮助`＝`/帮助`） | `packages/dsh-bot-core/src/commands.js:24-41`（matchTrigger allowBare）；驱动传入 `{allowBare:true}`：`src/index.js:325,356,564` |
| A3 | 核心命令：`/波旁` 对话、`/帮助`、`/人设列表`、`/切换人设`、`/学习`、`/知识列表`、`/删除知识`、`/识图`、`/涩图`、`/今日担当`、`/debug`、`/广播`、`/清除`、`/重启` | 帮助文本：`packages/dsh-bot-core/src/index.js:149-162`；处理：`index.js:180-211`；知识命令：`src/knowledge.js:124` 起；管理命令：`src/admin.js:56-68` |
| A4 | Discord 专属管理员命令：`/撤回`、`/长期撤回`、`/ban`、`/抓取` | `src/moderation.js`、`src/grabbing.js`（`isGrabbingCommand` 判定），驱动接线：`src/index.js:436-493` |
| A5 | 自由聊天：频道白名单内、非命令消息读取文本并交 AI 门卫判断是否插话 | `src/index.js:586-637`；门卫逻辑 `packages/dsh-bot-core/src/freechat.js`、`fatigue.js` |
| A6 | 黑名单用户：不回复、不写入记忆 | `src/admin.js:35-38`；驱动检查 `src/index.js:343-353` |
| A7 | 陷阱频道审核：配置频道内任何消息触发封禁+删消息、10 分钟扫一次近 50 条 | `src/censor.js:42-70`（TRAP_CHANNELS、SWEEP 间隔、sweep 上限） |
| A8 | 自动翻译：配置频道内每条人类文本消息检测语言并回复多语言译文 | `src/translate.js:19-40,153-189` |
| A9 | 会话记忆存储在运营者本机（dsh 会话存储）；`/清除` 开启新会话代数，旧日志保留在磁盘 | `src/index.js:415-433`（generation 递增）；`docs/STATUS.md`（DSH_HOME/会话） |
| A10 | 发送前出站审查：凭据形态内容被替换 | `src/index.js:219-235`（guardOutbound）；`packages/dsh-bot-core/src/guard.js` |
| A11 | 长回复分段发送（2000 字符上限） | `src/messages.js`（buildOutgoingMessages）；`DISCORD_MAX_CHARS` |
| A12 | Discord 侧**没有**绘图命令（ComfyUI 在 webapp） | `docs/STATUS.md` "Phase 3c ComfyUI /draw … 已与用户确认不做"；`README.md`「关于 /draw」一节明确 out of scope；`src/` 无 draw 处理器 |
| A13 | 网页绘图站用同一 Discord 应用 OAuth2，仅 `identify` 权限 | `bpdiscord/webapp/auth.py:28-39`（scope: identify）；`webapp/config.py:141-146`（DISCORD_CLIENT_ID=1452674140137066524、callback=bourbon-draw.cn） |
| A14 | 网页站与机器人共用同一应用 ID，网站 URL https://bourbon-draw.cn 可公开访问 | `webapp/nginx/bourbon-draw.cn.conf`；实际抓取 https://bourbon-draw.cn 返回绘图界面 |
| A15 | 知识库（`学习`/`批量学习`/删除）用本地 FAISS，管理员可删 | `bpdsh/packages/dsh-bot-core/src/knowledge.js`；sidecar `bpdsh/sidecar` |
| A16 | 定时问候按环境变量频道/群号发送；当前 `.env` 中 `BOPANG_AUTOCHAT=off`（自主插话关闭） | `.env.example`；`bpdsh/.env` 中 `BOPANG_AUTOCHAT=off`（仅读取该键） |
| A17 | 运营者不使用消息内容训练模型（代码中无训练回路；仅推理调用） | 全仓无训练相关代码；LLM 调用为流式推理（`src/translate.js` 等） |

## B. 需你人工确认/处理（我无法代替）

| # | 事项 | 为什么必须人工 |
|---|---|---|
| B1 | Stripe 身份验证（App Verification 要求） | 需要你的证件与人脸/实名流程 |
| B2 | 提交表单 / 点击认证框 / 上传截图到 Imgur | 需要登录你的 Discord 开发者账号；截图取自真实服务器 |
| B3 | DeepSeek 平台"数据是否用于训练"设置 | 网页后台操作；若默认开启，需关闭后 "No" 才成立 |
| B4 | 支持服务器、落地页联系方式占位符 | 需要你决定联系邮箱/服务器邀请链接 |
| B5 | 在 Bot 页打开 Message Content 开关（批准后） | 开发者后台操作 |

## C. 对外部资料的引用（来源为第三方页面，以官方后台最终显示为准）

- 10,000 唯一用户门槛自 2026-06 起、批准后每年重申：CrowBots 文档
  <https://doc.crowbots.shop/gestion-v2/verification>、phpbotscout 文档
  <https://phpbotscout.phpboyscout.uk/how-to/discord-application/>。
- 应用验证需身份验证（Stripe）与完整应用信息：Discord-Media 2025-11 指南
  <https://discord-media.com/en/news/discord-app-verification-guide-get-your-coveted-badge.html>。
- 验证表单字段与审核建议：StartIT 指南
  <https://startit.bot/blog/how-to-fill-discords-privileged-intents-form-as-startit-customer/>。
- → 打开 Developer Portal 时以页面实际字段为准；以上仅用于预填内容。

## D. 与旧稿的差异（已修正）

旧稿（2026-09 版 `discord_intent_application.md`）基于 NoneBot2 版 bpdiscord，包含以下**已不成立**
的描述，新稿已删除/改写：

1. "draw / multidraw / 高清 / 切换工作流 / lora列表 … 是 Discord 文本命令" → **现无绘图命令**，
   绘图在网页站 bourbon-draw.cn。
2. "机器人基于 NoneBot2" → 现为 DeepSeek Harness + discord.js。
3. "所有消息都经过缓冲合并再判断" → 现在只有自由聊天门卫；命令即时处理。
4. 记忆存储描述 → 现为 dsh 会话存储 + 本地日志；`/清除` 清空。

## E. 未覆盖 / 建议后续

- 真实频道上的 `/抓取` 完整流程尚未实跑（STATUS.md 已注明）；审核人员一般不验证该管理员功能，
  但若被问到，如实说明"管理员按需使用、尚未生产实跑"。
- 若审核人员要求演示自由聊天：当前 `BOPANG_AUTOCHAT=off`，需临时设为 on 才能演示未被 @ 的自主
  插话；@机器人 与 `/波旁` 任何时候都可用。

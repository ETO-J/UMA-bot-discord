# Discord Message Content Intent — 申请表单填写稿 (Ready-to-Paste)

> 目标表单: https://discord.com/developers/applications/1452674140137066524/request-additional-intents
>
> **2026-10 版（按 DeepSeek Harness 合并架构重写，并经代码级审计逐条修正）**：
> 机器人主体已迁移到 dsh 架构（`C:\Users\Administrator\bpdsh`，Node.js + discord.js），
> 网页绘图站（bourbon-draw.cn）仍在 `bpdiscord` 目录。已修正若干与事实不符的旧描述：
> 机器人**没有** Discord 绘图命令、陷阱频道审核**不读**消息文本、`/清除` 不删除磁盘会话、
> 知识库为跨服共享、频道范围由**运营者**全局配置。已用子代理逐文件核对（见
> `docs/verification_evidence.md`）。
>
> 背景：Discord 自 2026-06 起将审核门槛从"100 个服务器"改为**跨所有安装的 10,000 名唯一
> 用户**；达到后提交本表单，每次批准有效期为一年（到期需重新申请）。
> 以下英文段落可整段复制粘贴；带 ⚠️ 的字段需要你自己处理（截图、隐私政策链接、登录提交）。

---

## 一、在表单里勾选（Privileged Gateway Intents）

- ☑ **Message Content Intent**（唯一需要的权限）
- ☐ Server Members Intent —— 代码未使用任何 guild member 事件/成员名单功能，**不要勾**
- ☐ Presence Intent —— 代码未使用在线状态功能，**不要勾**

> 代码依据：`packages/dsh-bot-discord/src/index.js:132-141`，客户端只请求
> `Guilds / GuildMessages / DirectMessages / MessageContent` 四个 intent。
> 管理员 ban/kick、抓取、撤回等操作走 REST API 权限，不需要 Server Members intent。

---

## 二、Application Details

### 字段: What does your application do?（请尽量详细，并可附图片/视频链接）

```
This application is "Bourbon (美浦波旁)", a multi-function AI companion and community bot
for Discord, built on the DeepSeek Harness agent runtime (Node.js, discord.js) and operated
by an individual developer. It is invite-only and runs only on the servers the operator
explicitly chooses. Its features are accessed as ordinary chat text -- there are no Discord
application commands; even the leading "/" is optional. Main features:

1. AI conversation with persistent memory. Users talk to the bot by typing "波旁 <message>"
   or by @-mentioning it; direct messages are answered too. When the operator enables
   free-chat for a channel, the bot follows the ongoing conversation there, keeps a short
   rolling context, applies an AI "should I join in?" gate, and, when it replies, runs a
   conversational AI turn with per-channel memory. The bot also supports persona switching,
   a knowledge base that users or admins can teach ("学习" / knowledge commands; shared by the
   operator across servers), image understanding when a user sends an image, web search, a
   daily random-character image ("今日担当"), image-source lookup ("识图"), a random Pixiv
   image command ("涩图"), and scheduled greetings.

2. Auto-translation. In a small number of channels the operator configures, the bot reads
   every human message, detects its language and posts a zh/en/ja translation reply in the
   channel -- a mixed-language community feature.

3. Moderation and utility commands. Designated decoy ("trap") channels are watched: any user
   who posts there can be removed and their recent messages purged. Administrators additionally
   have message-removal commands ("撤回", "长期撤回"), "ban", channel-history archiving
   ("抓取") and operational commands ("debug", "广播", "清除", "重启"). Which channels are
   watched or translated is configured by the operator.

4. The same Discord application also powers an optional web drawing interface at
   https://bourbon-draw.cn: users sign in with Discord OAuth2 (identify scope: user id,
   username, avatar) and use an AI image/video generation workspace with per-user quotas,
   history and a media asset library. The web interface is separate from the bot; the bot
   itself does not run an image-generation command, and the web interface does not read
   Discord message content.
```

### 字段: Do you have a public Privacy Policy telling your users about their data usage?

```
Yes
```

### 字段: Where is your Privacy Policy available?

如为下拉/文本框，选择 **Website I own/operate**（或最接近选项），并填入下面的链接。
（部分表单版本没有此字段，直接跳过。）

### 字段: Please share a link to your Privacy Policy.

```
⚠️ 填入你发布后的隐私政策真实 URL，例如
https://eto-j.github.io/UMA-bot-discord/privacy.html
（仓库 docs/PRIVACY_POLICY.md 已更新为当前架构；发布到 GitHub Pages / 其他公开网址后粘贴链接）
```

---

## 三、Message Content Intent 部分

### 字段: Can users opt-out of having their message content data tracked?

```
No
```

说明（不需要填进表单）：当前机器人没有逐用户"关闭记忆"命令；但机器人只加入运营者选择的服务器，
自由聊天/翻译/审核频道范围由运营者全局配置（服务器成员无法自行开启或关闭），被拉黑用户的消息不
回复、不进入对话记忆（仅可能以片段形式出现在运营者运行日志中）。后续可增加用户级
`关闭记忆` 命令以进一步提升可信度。

### 字段: Are you storing message content data off-platform (outside of Discord)?

```
Yes
```

说明：会话记录（dsh 会话存储，压缩 JSONL，**无自动过期**）、`学习` 知识库（FAISS，**跨服务器
共享**）、活动/控制台/sidecar 日志、以及管理员 `抓取` 归档，均保存在运营者自己的私有服务器/本机
磁盘，不存到任何第三方平台。隐私政策详细说明了存储、`清除`（不删磁盘文件）与删除方式。

### 字段: Will the message content data be used to train machine learning or AI Models?

```
No
```

说明：内容仅被**临时**发送给生成当次回复所需的 AI/搜索/识图服务（DeepSeek 对话与视觉、
harness 联网搜索、SauceNAO、Pixiv、本地 ComfyUI 网页绘图），运营者不用于训练任何模型。
⚠️ 提交前请确认 DeepSeek 开放平台的 API 数据设置已关闭"用于训练"（如有该选项）。

### 字段: Why do you need the Message Content intent?

```
Message Content is required for the following current features. The bot is not built around
Discord's interaction (application command) system, so message text is the only input:

1) Plain-text commands. Nearly every feature is triggered by text typed in chat: "波旁 …"
   (chat), "帮助", "学习 …", "人设列表" / "切换人设 …", "今日担当", "识图" (with an
   image), "涩图 <keyword>", and the administrator commands "撤回", "长期撤回", "ban",
   "抓取", "debug", "广播", "清除", "重启". On Discord the leading "/" is optional. Without
   the Message Content Intent Discord empties message.content for guild messages, so the
   command word and its arguments are invisible and these features cannot work. Discord's
   built-in exceptions (mentions, replies, DMs) do not cover prefix-style text commands.

2) Free-form conversation (operator-enabled). When the operator enables free-chat for a
   channel, the bot reads the ordinary conversation there (it keeps the last lines as
   context for a model-based "should I reply?" decision), and when it replies it runs a
   conversational AI turn with persistent memory. Reading non-addressed messages is exactly
   what this intent exists for.

3) Auto-translation channels. In the channels the operator configures, the bot reads each
   human message to detect its language and posts a translation reply. This is an automatic
   feature, not a command.

4) Operational diagnostics. The bot keeps a local activity log of incoming messages (sender
   plus a clipped preview of up to about 300 characters) so the operator can diagnose faults.
   The log stays on the operator's own server and is not used for anything else; it is
   described in the public privacy policy.

Scope and safeguards: the bot is invite-only and only processes the servers where its
operator installed it; the channels it reads for free-chat, moderation and translation are
configured by the operator (server members cannot change the scope); blacklisted users are
ignored (no reply and not used as conversation memory); message content is used solely for
the features above; it is never sold or shared for advertising or profiling; it is only
transmitted transiently to the AI/vision/search/image services needed for the current
request; the operator does not use the content to train any machine-learning model.
Conversation sessions are stored on the operator's own server; configured administrators can
start a fresh session with "清除" and delete knowledge with "删除知识"; users may contact the
operator (see the public privacy policy) to request deletion of their data.
```

### 字段: Please provide links to screenshots and/or videos that demonstrate your use case

```
⚠️ 需要你上传截图后粘贴链接（Imgur 等图床即可）。建议至少 4 张：
1. 频道里发送「波旁 你好」（或 /波旁 你好），机器人回复——证明读取文本命令与内容
2. 开启自由聊天的频道里，机器人自然参与对话（若暂时关闭了自主插话，可临时开启后截图；
   @机器人 回复始终可用）
3. 「/帮助」命令输出
4. 自动翻译频道里，机器人对一条消息回复多语言译文
5. （可选）陷阱频道处理垃圾消息的提示/管理日志截图
上传到 imgur.com 后，把相册或图片直链粘贴到此字段，例如 https://imgur.com/a/xxxxxxxx
```

---

## 四、Acknowledgement and Submit（表单底部）

- 勾选认证框："By clicking Submit, you certify that the information provided above is
  accurate and complete, and that you and your app are in compliance with Discord's
  Developer Terms of Service and Developer Policy..."
- 点击 **Submit**。

> ⚠️ 这两步需要你在已登录 Discord 的浏览器中亲自完成（需要你的开发者账号会话），
> 我无法代替你提交。批准后约一年需重新提交。

---

## 提交前 Checklist

1. ☐ 发布隐私政策到公开 URL，并替换占位联系方式（见 `docs/discord_verification_checklist.md`
   第 1 步；草案在 `docs/PRIVACY_POLICY.md`，推荐 GitHub Pages：
   `https://eto-j.github.io/UMA-bot-discord/privacy.html`）
2. ☐ 只勾选 Message Content Intent
3. ☐ 上传 3–5 张演示截图并填入 Imgur 链接
4. ☐ 确认 DeepSeek 平台数据设置关闭"使用数据训练"（保证 "No" 答案真实）
5. ☐ 通读英文答案；如与线上行为有出入先改答案再提交
6. ☐ 登录 Developer Portal 打开本表单链接 → 粘贴 → 勾认证框 → Submit

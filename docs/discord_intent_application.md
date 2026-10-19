# Discord Message Content Intent — 申请表单填写稿 (Ready-to-Paste)

> 目标表单: https://discord.com/developers/applications/1452674140137066524/request-additional-intents
>
> **重要更新（2026-10 版）**：机器人主体已迁移到 **DeepSeek Harness (dsh)** 架构
> （`C:\Users\Administrator\bpdsh`，Node.js + discord.js），不再是旧的 NoneBot2 实现；
> 网页绘图站（bourbon-draw.cn）仍在 `bpdiscord` 目录。本稿按**当前线上机器人**的实际功能撰写，
> 并修正了旧稿中"机器人提供 draw 绘图命令"等已不成立的描述。
>
> Discord 自 2026-06 起将审核门槛从"100 个服务器"改为**跨所有安装的 10,000 名唯一用户**；
> 达到后需提交本表单，且每次批准有效期为一年（到期需重新申请）。
> 以下英文段落可整段复制粘贴；带 ⚠️ 的字段需要你自己处理（截图、隐私政策链接、登录提交）。

---

## 一、在表单里勾选（Privileged Gateway Intents）

- ☑ **Message Content Intent**（唯一需要的权限）
- ☐ Server Members Intent —— 代码未使用任何 guild member 事件/成员名单功能，**不要勾**
- ☐ Presence Intent —— 代码未使用在线状态功能，**不要勾**

> 代码依据：`packages/dsh-bot-discord/src/index.js` 的 `new Client({ intents: [Guilds,
> GuildMessages, DirectMessages, MessageContent] })`。除 MessageContent 外没有申请其他特权 intent。
> 管理员 ban/kick 等操作走 REST API 权限，不需要 Server Members intent。

---

## 二、Application Details

### 字段: What does your application do?（请尽量详细，并可附图片/视频链接）

```
This application is "Bourbon (美浦波旁)", a multi-function AI companion and community bot
for Discord, built on the DeepSeek Harness agent runtime (Node.js, discord.js) and operated
by an individual developer. It is invite-only and runs only on the servers the operator
explicitly chooses. Its main features are:

1. AI conversation with persistent memory. Users talk to the bot by typing a plain-text
   command, "波旁 <message>" (the leading "/" is optional), or by @-mentioning it; direct
   messages are answered too. In channels where the server's bot configuration enables
   free-chat, the bot follows the ongoing conversation, keeps a short rolling context, runs a
   fatigue/interest gate in which an AI judge decides whether it is natural to join in, and,
   when it replies, runs a conversational AI turn with per-channel memory so answers stay
   coherent. The bot also supports persona switching, a server-taught knowledge base
   ("学习" / knowledge commands), image understanding when a user sends an image, web search,
   a daily random-character image ("今日担当"), image-source lookup ("识图"), a random Pixiv
   image command ("涩图"), and scheduled greetings.

2. Moderation and utility commands. Designated trap/moderation channels are watched and spam
   posters there can be removed; administrators have message-removal commands ("撤回",
   "长期撤回"), "ban", channel-history archiving ("抓取"), and operational commands
   ("debug", "广播", "清除", "重启"). Server administrators control which channels are
   monitored or translated.

3. The same Discord application also powers an optional web drawing interface at
   https://bourbon-draw.cn: users sign in with Discord OAuth2 (identify scope: user id,
   username, avatar) and use an AI image/video generation workspace with per-user quotas,
   history and a media asset library. The web interface does not read Discord message
   content; image generation is intentionally NOT offered as a Discord chat command.
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

说明（不需要填进表单）：当前机器人没有逐用户"关闭记忆"命令；但处理范围受服务器管理员配置的频道
白名单限制，且被拉黑用户的消息既不回复也不作为记忆保存。若要进一步提升体验，可后续增加
`隐私模式`/`关闭记忆` 用户命令——这会显著增强可信度，但会增加开发量。

### 字段: Are you storing message content data off-platform (outside of Discord)?

```
Yes
```

说明：会话记录（dsh 会话存储）、`学习` 知识库（FAISS）、活动/控制台/sidecar 日志、以及管理员
`抓取` 归档，均保存在运营者自己的私有服务器/本机磁盘，不存到任何第三方平台。隐私政策详细说明了
存储与删除方式（`清除`、`删除知识`、联系运营者）。

### 字段: Will the message content data be used to train machine learning or AI Models?

```
No
```

说明：内容仅被**临时**发送给生成当次回复所需的 AI/搜索/识图服务（DeepSeek 对话与视觉 API、
harness 联网搜索、SauceNAO、Pixiv、本地 ComfyUI），运营者不用于训练任何模型。
⚠️ 提交前请确认 DeepSeek 开放平台的 API 数据设置已关闭"用于训练"（如有该选项），保证与回答一致。

### 字段: Why do you need the Message Content intent?

```
Message Content is required for three groups of features that operate on ordinary messages
rather than user-invoked slash commands:

1) Plain-text prefix commands. Nearly every feature is triggered by text typed in chat:
   "波旁 <message>" for AI chat, "帮助/help", "学习 <fact>", "人设列表" / "切换人设 <name>",
   "今日担当 [character]", "识图" (with an image), "涩图 <keyword>", and the administrator
   commands "撤回 <id>", "长期撤回 <user>", "ban <user>", "抓取 [mode] [channel]",
   "debug", "广播 <text>", "清除", "重启". On Discord the leading "/" is optional. Without the
   Message Content Intent Discord empties message.content for guild messages, so the bot
   cannot see the command word or its arguments and none of these features can work.
   Discord's built-in message-content exceptions (bot mentions, replies, direct messages)
   do not apply to these prefix-style commands.

2) Free-form conversation. In channels where the server administrator has enabled the bot,
   the bot reads the ordinary conversation, keeps the last few lines as context for an AI
   "should I join in?" gate, and, when it replies, runs a conversational AI turn with
   persistent per-channel memory. This requires reading the text of messages that neither
   mention nor reply to the bot -- exactly the case the intent exists for.

3) Moderation and auto-translation in configured channels. Trap-channel moderation must
   evaluate messages posted by any user at the moment they are sent; the auto-translation
   feature reads every human message in a handful of configured channels and replies with a
   translation. Both operate on all messages in those channels, not only addressed ones.

Privacy safeguards: the bot is invite-only and only processes the servers its operator has
chosen to serve; chat and moderation run only in channel allowlists configured by the
operator/server administrator; blacklisted users are ignored entirely (no reply, no memory);
message content is used solely to provide the features above; it is never sold or shared for
advertising or profiling; it is only transmitted transiently to the AI/vision/search/image
APIs needed to answer the current request; and the operator does not use the content to
train any machine-learning model. Conversation sessions are stored on the operator's own
server; administrators can clear memory with "清除", delete knowledge with "删除知识", and
users may contact the operator (see the privacy policy) to request deletion of their data.
```

### 字段: Please provide links to screenshots and/or videos that demonstrate your use case

```
⚠️ 需要你上传截图后粘贴链接（Imgur 等图床即可）。建议至少 4 张：
1. 频道里发送「波旁 你好」（或 /波旁 你好），机器人回复——证明读取文本命令与内容
2. 开启自由聊天的频道里，机器人自然参与对话（或 @机器人 回复）
3. 「/帮助」命令输出
4. 开启自动翻译的频道里，机器人对消息回复多语言译文
5. （可选）陷阱频道自动处理垃圾消息的提示/日志截图
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

1. ☐ 发布隐私政策到公开 URL，并替换占位联系方式（草案 `docs/PRIVACY_POLICY.md`；
   推荐用仓库 docs/ 开 GitHub Pages：Settings → Pages → Deploy from branch → master /docs，
   链接示例 https://eto-j.github.io/UMA-bot-discord/privacy.html）
2. ☐ 只勾选 Message Content Intent
3. ☐ 上传 3–5 张演示截图并填入 Imgur 链接
4. ☐ 确认 DeepSeek 平台数据设置关闭"使用数据训练"（保证 "No" 答案真实）
5. ☐ 通读英文答案；如与线上行为有出入先改答案再提交
6. ☐ 登录 Developer Portal 打开本表单链接 → 粘贴 → 勾认证框 → Submit

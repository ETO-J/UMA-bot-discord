# Privacy Policy — Bourbon (美浦波旁) Discord Bot

_Last updated: [填入发布日期，如 2026-06-01]_

This Privacy Policy explains how the Discord bot **Bourbon (美浦波旁)** ("the Bot", "we", "us")
handles data when you use it in a Discord server. The Bot is operated by its individual
developer/operator ("the Operator").

By using the Bot you agree to the practices described below.

---

## 1. What data does the Bot process?

The Bot processes the following data, only to the extent needed to provide its features:

- **Discord identifiers**: your user ID, display name/username, and the IDs of the channels
  and servers in which the Bot operates.
- **Message content**: the text of messages sent in the servers/channels where the Bot is
  present and enabled. This includes chat messages you send to or around the Bot, prefix
  commands typed as plain text (e.g. `波旁 …`, `draw …`, `help`, `学习 …`), and messages in
  channels where the server administrator has enabled the Bot's chat or moderation features.
- **Images / attachments**: images you send to the Bot (e.g. for image understanding) and the
  images the Bot generates for you.
- **Usage data**: AI generation prompts, command parameters, and related feature usage needed
  to operate the Bot (e.g. per-user drawing quotas).

## 2. Why does the Bot process this data?

The Bot is a multi-function AI companion bot. Data is processed to provide:

- **AI chat with conversation memory** — the Bot reads the ongoing conversation in enabled
  channels so it can answer coherently and remember recent context.
- **AI image generation** — parsing text prompts (`draw`, `multidraw`, Lora and workflow
  management) and rendering images.
- **Knowledge learning** — facts taught by users/admins (`学习`) are stored in a local
  knowledge base so later answers can use them.
- **Content moderation** — spam/abuse detection, blacklists, and anti-abuse quotas in
  moderation-enabled channels.
- **Daily / entertainment features and admin tools** — e.g. the daily character command, image
  search, scheduled messages, and administrator commands such as message removal and user bans.

## 3. Where is the data stored, and for how long?

- Conversation history and knowledge are stored **locally on the Operator's own private server
  or machine** in database and vector (FAISS) files. They are **not** stored by any third
  party on the Operator's behalf.
- Conversation history is kept to provide memory for the AI and is retained until it is
  deleted: server administrators can wipe the whole conversation-history database at any time
  with the `清除` command, and the Operator can delete data on request (see section 6).
- Knowledge-base entries remain until an administrator removes them (`删除知识`).
- Where an administrator uses the optional history-archive feature (`抓取`), a copy of the
  selected channel's text/images is saved to the Operator's local disk and is kept only as
  long as the administrator needs it.

## 4. Do we share or transfer your data?

- **We never sell or rent your data**, and we never transfer message content to third parties
  for advertising or profiling.
- To generate a reply or an image, the message/prompt you give the Bot may be transmitted
  **transiently** to the AI providers the Operator uses (e.g. the DeepSeek chat API, a
  vision-understanding API, an optional local model, and a web-search API). These calls are
  made only to process your current request and are not used by the Operator to train any
  machine-learning model.

## 5. How is the data protected?

- The Bot and its data run on infrastructure controlled by the Operator, with access limited
  to the Operator and to Discord server administrators acting through the Bot's admin
  commands (e.g. ban/purge actions, which require Discord moderation permissions).
- The Operator keeps the Bot's deployment, tokens, and database access credentials private.
- Sensitive moderation actions (banning, purging messages) are performed only when triggered
  by an administrator and require the corresponding Discord permissions.

## 6. Your rights and choices

- **Disable the Bot**: users who do not wish their messages to be read by the Bot may ask the
  server administrator to remove the Bot or to disable it in specific channels.
- **Blocked users**: the Operator may blacklist a user; blacklisted users' messages are never
  answered by the Bot.
- **Deletion requests**: you may contact the Operator (see section 7) to request that your
  data be deleted. Server administrators can also delete conversation history and knowledge
  entries themselves using the Bot's admin commands.
- **Discord's own controls**: you can always manage your privacy through Discord's settings.

## 7. Contact

For any privacy question or deletion request, contact the Operator:

- Email: **[请填入运营者联系邮箱]**
- Discord: **[请填入运营者 Discord 用户名 / 支持服务器链接]**

## 8. Changes to this policy

We may update this policy from time to time. The date at the top of this page shows the latest
revision. Continued use of the Bot after changes means you accept the updated policy.

---

## 中文摘要 (Chinese Summary)

机器人 **波旁（美浦波旁）** 仅处理其运行所需的 Discord 标识（用户/频道/服务器 ID、昵称）与
消息文本/图片：用于 AI 对话与上下文记忆、按文字命令解析的 AI 绘图、`学习` 知识库、开启频道
的内容审核、以及日常/管理功能。

- 数据保存在**运营者自己的私有服务器**（本地数据库 / FAISS / 文件），不向第三方出售或共享；
  仅在生成回复或图片时，将当次内容**临时**发送给所使用的 AI/视觉/搜索 API，运营者不用于训练模型。
- 会话记忆由管理员用 `清除` 命令即可整体删除，知识条目可用 `删除知识` 删除；用户可联系运营者
  要求删除个人数据。
- 不希望被读取消息的用户可请服务器管理员移除机器人或在特定频道停用。
- 联系方式见上文第 7 节。

---

> **发布提示 (Publish this page)**: Discord 需要此隐私政策可以通过公开链接访问。发布方式任选其一：
> 1. 推到公开 GitHub 仓库并用 GitHub Pages 发布（推荐）；
> 2. 用 gist.github.com 粘贴后使用 Raw 链接；
> 3. 放在你自己的任何公开网页上。
> 发布后把真实 URL 填进申请表单，并把第 7 节的联系方式占位符替换成真实信息。

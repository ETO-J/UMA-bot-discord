# Privacy Policy — Bourbon (美浦波旁) Discord Application

_Last updated: 2026-10-19_

This Privacy Policy explains how the Discord application **Bourbon (美浦波旁)** ("the App",
"we", "us") handles data when you interact with it on Discord or use its web drawing
interface at **bourbon-draw.cn**. The App is operated by its individual developer/operator
("the Operator").

By using the App you agree to the practices described below.

---

## 1. What is the App?

The App is a multi-function AI companion bot for Discord (invite-only; it runs only on the
servers its Operator has chosen) plus an optional browser-based AI image/video drawing
interface at bourbon-draw.cn. The same Discord application powers both; the web interface
uses Discord OAuth2 login with the **identify** scope only.

The App's features are accessed as **plain-text messages**: on Discord the leading `/` is
optional (e.g. `波旁 …`, `帮助`, `学习 …`). It does not register Discord slash/application
commands. It does not draw or generate images inside Discord; image generation exists only in
the web interface.

## 2. What data does the App process?

**2.1 Discord bot**

- **Discord identifiers**: your user ID, display name/username, avatar, and the IDs of
  servers and channels in which the App operates.
- **Message content**: the text of messages the App can see in the servers/channels where it
  is enabled. This includes plain-text commands (e.g. `波旁 …`, `帮助`, `学习 …`,
  `人设列表`, `切换人设 …`, `今日担当`, `识图`, `涩图`, and the administrator commands
  `撤回`, `长期撤回`, `ban`, `抓取`, `debug`, `广播`, `清除`, `重启`), ordinary
  conversation in channels where the Operator has enabled free-chat, and every message in the
  auto-translation channels configured by the Operator (the App posts a translated reply).
  On Discord the leading `/` is optional.
- **Images and attachments**: images you send to the App for understanding, image-source
  lookup (`识图`), or images the App sends to you (cached Pixiv or daily-character images for
  `涩图`/`今日担当`).
- **Conversation memory and logs**: recent conversation turns kept per channel (or per user
  for DMs), and operational logs kept by the Operator, including an activity log that records
  incoming messages (sender, clipped to about 300 characters), feature decisions, tool calls
  and outbound messages for diagnostics. Incoming-message logging happens before some access
  checks, so clipped snippets from blacklisted users may also appear there.
- **Knowledge entries**: facts users/admins teach with `学习` (and admins with `批量学习`),
  stored in the App's knowledge base. The knowledge base is **shared by the Operator across
  the servers the bot runs in** (a fact taught in one server can surface in another).

**2.2 Web drawing interface (bourbon-draw.cn)**

- **Discord account data** after OAuth2 login with the identify scope: user ID, username,
  avatar. A signed session token is stored in your browser (valid for 7 days).
- **Content you create**: prompts, negative prompts, workflow/settings choices, uploaded
  source images or media, generated images/videos, per-user generation quotas and, where
  enabled, your media library/asset uploads.
- **Published media**: when the asset-publish feature is enabled, the thumbnail/attachment
  of a published work may be posted to a configured Discord channel by the Operator's bot.

## 3. Why is this data processed?

- **Conversational AI**: answering questions and keeping coherent context; deciding whether
  to take part in free-form channel conversation (when the Operator enables it); image
  understanding.
- **Knowledge base**: grounding answers in facts users/admins taught to the App.
- **Commands and utilities**: persona switching, image-source lookup, Pixiv image lookup,
  daily random character image, scheduled greetings, help.
- **Moderation and safety**: message removal, ban and trap-channel enforcement commands used
  by configured administrators.
- **Administration**: channel-history archiving (`抓取`), restart/clear/debug commands.
- **Web drawing**: signing you in, remembering your settings/quotas, generating media and
  keeping your generation history/assets.

## 4. Where is the data stored and retained?

- Everything the bot stores is stored **locally on the Operator's own private server/**
  machine: conversation sessions (DeepSeek Harness session store — compressed JSONL files in
  the operator's `.dsh` directory), the knowledge base (FAISS index and text files),
  activity/console/sidecar logs, and archives produced by the administrator-only `抓取`
  command. Nothing in this list is hosted by a third party on the Operator's behalf.
- Conversation sessions are retained to provide memory and **there is no automatic expiry or
  deletion**. Configured administrators can start a fresh session with `清除`; this detaches
  the current session so new messages go to a new session record, but it does **not** delete
  the stored session log, and the change is not guaranteed to survive a process restart (the
  bot may resume a previous session after a restart). Only the Operator's manual deletion of
  stored files makes a wipe permanent. Knowledge entries can be removed with `删除知识`. Users
  may contact the Operator (section 9) to request deletion.
- The Operator also runs a separate QQ bot on the same server, sharing the same knowledge base,
  the same AI runtime and the same logging infrastructure; facts added through one platform can
  surface through the other. The QQ bot is a separate surface, not part of this Discord
  application.
- The web interface stores user settings, quotas, task queues and generated media in the
  Operator's local databases and on its local disks. Generated media and uploaded assets are
  retained until you or the Operator deletes them.
- Logs are kept for operations/security and are deleted by the Operator from time to time
  or on request. There is no fixed automatic retention period.

## 5. Do we share or transfer your data?

- **We never sell or rent your data**, and we do not share message content with third
  parties for advertising or profiling.
- To provide a response, your prompt/message may be transmitted **transiently** to the
  services the Operator uses (e.g. DeepSeek's chat API for conversation, vision, the
  free-chat judge and auto-translation; the web-search tool's provider; SauceNAO for
  image-source lookup — image bytes; the Pixiv API for image lookup — keywords; a locally
  hosted ComfyUI for web image/video generation). These services process the data only to
  answer that request. The Operator does not use your content to train any machine-learning
  model.
- The underlying DeepSeek Harness runtime may optionally send feedback/telemetry to its
  provider's telemetry endpoint. In the Operator's current configuration ordinary traffic is
  not exported; only an explicitly submitted feedback item would include a session excerpt.
- The web interface's login flow talks only to Discord's OAuth2 endpoints.

## 6. How is the data protected?

- The App runs on infrastructure controlled by the Operator; access to credentials,
  databases and logs is limited to the Operator.
- Outbound text from the bot's main message paths is inspected before sending; known
  credentials and credential-shaped strings are replaced rather than published. Some
  messages are sent through separate paths that may not run this check (for example: the
  admin-only `广播` broadcast, auto-translation replies, and moderation notices).
- The AI conversation runtime's write access is restricted to a dedicated workspace on the
  Operator's machine. Its file reads are not restricted by that OS sandbox; the Operator's
  safety settings and the outbound checks are the controls for confidential data.
- Moderation actions (purge/ban) and archive commands are available only to configured
  administrator IDs and require the corresponding Discord permissions.

## 7. Your rights and choices

- **Remove or disable the App**: ask the Operator to remove the App or stop processing your
  server (the Operator configures all processing scope globally). Users do not need to
  interact with the App.
- **Blacklisted users**: users blacklisted by the Operator are never answered and their
  messages are not used as conversation memory; a clipped record may still appear in the
  Operator's activity log as described in section 2.
- **Deletion requests**: contact the Operator (section 9) to request deletion of your data.
  Configured administrators can start a fresh session on demand (`清除`) and remove knowledge
  entries (`删除知识`); fully deleting stored session files is a manual Operator action.
- **Web interface**: you can stop using it at any time and ask the Operator to delete your
  account data, settings, quotas and generated media.

## 8. Children

The App is intended for users aged 13+ (or the minimum age required by Discord's Terms of
Service in your country). We do not knowingly collect data from children below that age.

## 9. Contact

- Email: **[请填入运营者联系邮箱]**
- Discord: **[请填入运营者 Discord 用户名 / 支持服务器链接]**

## 10. Changes to this policy

We may update this policy from time to time. The "Last updated" date at the top of this page
reflects the latest revision. Continued use of the App after changes means you accept the
updated policy.

---

## 中文摘要

机器人 **波旁（美浦波旁）** 处理运行所需的数据：Discord 标识、启用频道中的消息文本（文本命令、
自由对话、自动翻译频道）、图片、会话记忆与运行日志、`学习` 知识库（跨服共享）；网站
bourbon-draw.cn 通过 Discord OAuth2（仅 identify 权限）登录，处理你的设置、生成任务、上传与
生成媒体。

- 数据都保存在**运营者自己的私有服务器**上，不向第三方出售或共享；仅在生成回答/识图/搜索时
  将当次内容**临时**发送给所用 AI/搜索/识图/Pixiv/本地绘图服务，运营者不用于训练模型。
- 会话记忆无自动过期；`清除` 只是让之后的对话进入新会话记录，**不删除**磁盘上的旧会话文件，
  且重启后可能恢复旧会话；彻底删除需运营者手动处理。知识可用 `删除知识` 删除；可联系运营者
  要求删除数据。
- 被拉黑用户不会得到回复、不进入对话记忆，但其消息片段可能出现在运营者的运行日志中。
- 联系方式见第 9 节。

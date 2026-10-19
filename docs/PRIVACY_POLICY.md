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

## 2. What data does the App process?

**2.1 Discord bot**

- **Discord identifiers**: your user ID, display name/username, avatar, and the IDs of
  servers and channels in which the App operates.
- **Message content**: the text of messages the App can see in the servers/channels where it
  is enabled. This includes plain-text commands (e.g. `/波旁 …`, `/帮助`, `/学习 …`,
  `/人设列表`, `/切换人设 …`, `/今日担当`, `/识图`, `/涩图`, and the administrator commands
  `/撤回`, `/长期撤回`, `/ban`, `/抓取`, `/debug`, `/广播`, `/清除`, `/重启`), ordinary
  conversation in channels where the App's chat or moderation features are enabled, and
  moderation/auto-translation channels configured by the server administrator. On Discord the
  leading `/` is optional.
- **Images and attachments**: images you send to the App for understanding, image-source
  lookup (`/识图`), or images the App sends to you (e.g. `/涩图`, `/今日担当`).
- **Conversation memory and logs**: recent conversation turns per channel/user session, and
  operational logs (inbound messages, feature decisions, tool calls, outbound messages) kept
  by the Operator for the bot's proper functioning and troubleshooting.
- **Knowledge entries**: facts users/admins teach with `/学习` (and admins with
  `/批量学习`), stored in the App's knowledge base.

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
  to take part in free-form channel conversation; image understanding.
- **Knowledge base**: grounding answers in server-specific facts taught to the App.
- **Commands and utilities**: persona switching, image-source lookup, Pixiv image lookup,
  daily random character image, scheduled greetings, help.
- **Moderation and safety**: trap-channel spam detection, user blacklists, message removal
  and ban commands used by administrators.
- **Administration**: channel-history archiving (`/抓取`), restart/clear/debug commands.
- **Web drawing**: signing you in, remembering your settings/quotas, generating media and
  keeping your generation history/assets.

## 4. Where is the data stored and retained?

- Everything the bot stores is stored **locally on the Operator's own private server/**
  machine — conversation sessions (DeepSeek Harness session store), the knowledge base
  (FAISS index and text files), activity/console/sidecar logs, and archives produced by the
  administrator-only `/抓取` command. Nothing in this list is hosted by a third party on the
  Operator's behalf.
- Conversation sessions are retained to provide memory. Server administrators can clear a
  session with `/清除`, which starts a fresh session generation; the previous local session
  log remains on the Operator's disk until the Operator removes it, but it is no longer used
  as active memory. Knowledge entries can be removed with `/删除知识`. Users may contact the
  Operator (section 9) to request deletion.
- The web interface stores user settings, quotas, task queues and generated media in the
  Operator's local databases and on its local disks. Generated media and uploaded assets are
  retained until you or the Operator deletes them.
- Logs are kept for operations/security and are deleted by the Operator from time to time
  or on request. There is no fixed automatic retention period.

## 5. Do we share or transfer your data?

- **We never sell or rent your data**, and we do not share message content with third
  parties for advertising or profiling.
- To provide a response, your prompt/message may be transmitted **transiently** to the AI
  providers the Operator uses (e.g. DeepSeek's chat API for conversation and vision; the
  search API used by the harness's web-search tool; SauceNAO for image-source lookup; the
  Pixiv API for image lookup; a locally hosted ComfyUI for image/video generation). These
  services process the data only to answer that request. The Operator does not use your
  content to train any machine-learning model.
- The web interface's login flow talks only to Discord's OAuth2 endpoints.

## 6. How is the data protected?

- The App runs on infrastructure controlled by the Operator; access to credentials,
  databases and logs is limited to the Operator.
- Sensitive outbound content is inspected before being sent to Discord; known credentials
  and credential-shaped strings are replaced rather than published.
- Autonomous AI operations are confined to a dedicated workspace on the Operator's machine.
- Moderation actions (purge/ban) and archive commands are available only to configured
  administrator IDs and require the corresponding Discord permissions.

## 7. Your rights and choices

- **Remove or disable the App**: ask a server administrator to remove the App, or disable its
  features in a channel (server configuration). Users do not need to interact with the App.
- **Blacklisted users**: users blacklisted by the Operator are never answered and their
  messages are not stored as memory.
- **Deletion requests**: contact the Operator (section 9) to request deletion of your data.
  Administrators can clear conversation memory on demand (`/清除`), and remove knowledge
  entries (`/删除知识`).
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

机器人 **波旁（美浦波旁）** 仅处理其运行所需的数据：Discord 标识、启用频道中的消息文本
（文本命令、自由对话、审核/翻译频道）、图片、会话记忆与运行日志、`学习` 知识库；网站
bourbon-draw.cn 通过 Discord OAuth2（仅 identify 权限）登录，处理你的设置、生成任务、上传与
生成媒体。

- 数据都保存在**运营者自己的私有服务器**上，不向第三方出售或共享；仅在生成回答/图片/搜索时
  将当次内容**临时**发送给所用 AI/搜索/识图/Pixiv 服务，运营者不用于训练模型。
- 会话记忆可用 `/清除` 重置（旧日志留存于运营者磁盘，不再作为记忆使用），知识可用 `/删除知识`
  删除；可联系运营者要求删除数据。
- 不希望被读取消息的用户可请管理员移除机器人或停用相关频道。
- 联系方式见第 9 节。

# Discord Message Content Intent — 申请表单填写稿 (Ready-to-Paste)

> 目标表单: https://discord.com/developers/applications/1452674140137066524/request-additional-intents
> 本稿根据项目代码 (bpdiscord / NoneBot2 + Discord adapter) 的实际功能撰写。
> 以下英文段落可整段复制粘贴；带 ⚠️ 的字段需要你自己处理（登录提交、截图、隐私政策链接）。

---

## 一、在表单里勾选（Privileged Gateway Intents）

- ☑ **Message Content Intent**（唯一需要的权限）
- ☐ Server Members Intent —— 代码中未使用任何 guild member 事件/名单功能，不要勾
- ☐ Presence Intent —— 代码中未使用在线状态功能，不要勾

---

## 二、Application Details

### 字段: What does your application do?

```
This application is a multi-function AI companion Discord bot called "Bourbon (美浦波旁)",
built on NoneBot2 and the Discord API. It is operated by an individual developer and deployed
by invitation to a small number of community servers. Its features include:

1. AI chat with conversation memory. Users talk to the bot by typing "波旁 <text>" or by
   mentioning @Bourbon. In servers/channels that the server administrator has enabled, the bot
   also joins ordinary free-form conversation: it reads the natural flow of the channel,
   buffers a few consecutive messages, and uses an AI decision step to decide whether and when
   it is natural to reply. It keeps the recent conversation turns of each channel/user session
   so that answers stay coherent and context-aware.

2. AI image generation. Text commands such as "draw <prompt>", "multidraw", resolution and
   workflow switching ("切换工作流", "切换分辨率"), negative-prompt management, and Lora
   management ("lora列表", "添加lora", "删除lora") are all typed into the chat as ordinary
   text messages. The bot parses the command word and parameters from the message text and
   renders images on a locally hosted ComfyUI instance.

3. Knowledge learning. Commands like "学习 <fact>" and the admin command "批量学习" let users
   and administrators teach the bot facts; these are stored in a local knowledge base so later
   AI answers can draw on server-specific knowledge.

4. Content moderation. In channels where moderation is enabled, the bot scans every message for
   spam/abuse, maintains user blacklists and per-user drawing quotas, and can (with the
   required Discord permissions) take action against repeat offenders. Server administrators
   control which channels are monitored.

5. Daily and utility features. Daily random character pick ("今日担当"), image search,
   scheduled messages, an in-chat help guide ("help"), and administrator commands such as
   deleting messages ("撤回"), banning users ("ban"), and restarting the bot.

The bot is invite-only: it only operates on the servers chosen by its operator, and its chat
and moderation features only process the channels that each server administrator has enabled.
```

### 字段: Do you have a public Privacy Policy telling your users about their data usage?

```
Yes
```

### 字段: Where is your Privacy Policy available?

如为下拉选择: 选 **A website I own/operate**（或对应最接近的选项）。

### 字段: Please share a link to your Privacy Policy.

```
⚠️ 填入你发布后的隐私政策真实 URL。
草案已写好: 仓库 docs/PRIVACY_POLICY.md —— 发布到 GitHub Pages / gist / 自建网页后粘贴链接，
例如 https://<你的用户名>.github.io/<仓库>/PRIVACY_POLICY.html （先替换第7节联系方式的占位符）。
```

---

## 三、Message Content Intent 部分

### 字段: Can users opt-out of having their message content data tracked?

```
No
```
说明（不需要填进表单，供你了解）: 机器人没有逐用户"关闭记忆"命令；但机器人只加入运营者邀请的
服务器、只处理服务器管理员开启的频道，且不回复被拉黑用户的消息。如果以后想做得更好，可以给机器人
加一个 `隐私模式`/`关闭记忆` 的用户命令，能显著提高获批率与口碑。

### 字段: Are you storing message content data off-platform (outside of Discord)?

```
Yes
```
说明（供参考）: 会话历史、`学习` 知识库和（管理员触发的）抓取存档保存在运营者自己的服务器/本机
数据库与 FAISS 文件中，不存到任何第三方平台；管理员可用 `清除` 命令整体清空会话库、用
`删除知识` 删除知识条目。隐私政策中已如实说明。

### 字段: Will the message content data be used to train machine learning or AI Models?

```
No
```
说明（供参考）: 内容只被临时发送给生成回复/图片所需的 AI 与搜索 API（DeepSeek 对话、
视觉理解、联网搜索、本地 ComfyUI），运营者不用它训练任何模型。建议顺带在 DeepSeek 开放平台的
数据设置中关闭"使用数据训练"选项，以保持与声明的完全一致。

### 字段: Why do you need the Message Content intent?

```
The bot's core features act on the free text of messages sent in the channels where it is
enabled, not on user-invoked slash commands:

1. Plain-text prefix commands. Nearly every feature is triggered by text written directly in
   chat: "波旁 <text>" for AI chat, "draw <prompt>" / "multidraw" for image generation,
   "高清" / "切换分辨率" / "切换工作流" / "lora列表" / "添加lora" for drawing options,
   "今日担当" for the daily feature, "学习 <fact>" for knowledge teaching, "切换人设" for
   personality switching, and "help" for the command guide. Without the Message Content
   Intent, Discord strips the content of ordinary messages, so the bot cannot see the command
   word or its arguments and none of these features can run. The built-in message-content
   exceptions (bot mentions, replies, and direct messages) do not help here, because users
   invoke these commands with text prefixes rather than by mentioning the bot.

2. Free-form conversation in enabled channels. The bot is an AI chat companion. In channels
   enabled by each server's administrator, it follows the ongoing conversation, buffers a few
   messages, and uses an AI judge to decide when it is natural to reply. This requires reading
   message text that is neither a bot mention nor a reply to the bot, which is exactly what the
   Message Content Intent provides.

3. Content moderation in configured channels. Spam/abuse scanning, user blacklists and
   anti-abuse quotas must inspect the text of each message at send time to work.

4. Conversation memory and knowledge grounding. The bot stores recent conversation turns
   locally and uses server-taught knowledge entries so that replies are coherent and grounded;
   both are built from message text.

Privacy safeguards: the bot is invite-only and only processes the servers chosen by its
operator; chat and moderation are restricted to the channels each server administrator
enables; message content is used solely to provide the features described above; content is
never sold or shared for advertising or profiling, and is only transmitted transiently to the
AI/vision/search API needed to generate a reply; the operator does not use the data to train
any machine-learning model. Conversation history is stored on the operator's own server and
can be wiped by administrators with the "清除" command, knowledge entries can be removed with
"删除知识", and users can contact the operator (see the public privacy policy) to request
deletion of their data.
```

### 字段: Please provide links to screenshots and/or videos that demonstrate your use case

```
⚠️ 需要你上传截图后粘贴链接（Imgur 等图床即可）。建议至少 4 张：
1. "波旁 <内容>" 对话被回复（证明需要读取文本命令与内容）
2. 开启的频道里自然对话、机器人主动加入聊天（自由聊天）
3. "draw <prompt>" 生成图片（含负面词/分辨率等参数解析效果更佳）
4. "help" 命令列表
可选第 5 张: 审核频道自动处理垃圾消息的效果
上传后把 imgur 相册链接粘贴到此字段，例如 https://imgur.com/a/xxxxxxx
```

---

## 四、Acknowledgement and Submit（表单底部）

- 勾选认证框: "By clicking Submit, you certify that the information provided above is
  accurate and complete..."
- 点击 **Submit**。

> ⚠️ 这一步需要你在已登录 Discord 的浏览器中亲自完成（需要你的开发者账号会话），
> 我无法代替你提交。

---

## 提交前 Checklist

1. ☐ 发布隐私政策到公开 URL，并把链接填进表单（草案在 docs/PRIVACY_POLICY.md）
2. ☐ 替换隐私政策第 7 节的联系方式占位符
3. ☐ 只勾选 Message Content Intent
4. ☐ 上传 3–5 张功能演示截图并把 Imgur 链接填入
5. ☐ 通读一遍英文答案，确认与你实际部署一致（如有出入请修改后再提交）
6. ☐ 登录 Discord Developer Portal → 打开本表单链接 → 粘贴 → 勾选认证框 → Submit

> 审核一般需要几天到两周；如果被拒会收到邮件，通常可以修改后重新提交。
> 提醒: 内容必须真实——表单下方有认证条款，虚假陈述可能导致申请被拒。

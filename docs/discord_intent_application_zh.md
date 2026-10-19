# Discord Message Content Intent — 申请表填写稿（中文对照版）

> 目标表单: https://discord.com/developers/applications/1452674140137066524/request-additional-intents
>
> **2026-10 版（按 DeepSeek Harness 合并架构重写，并经代码级审计逐条修正）**：
> 机器人主体已迁移到 dsh 架构（`C:\Users\Administrator\bpdsh`，Node.js + discord.js），
> 网页绘图站（bourbon-draw.cn）仍在 `bpdiscord` 目录。已修正若干与事实不符的旧描述：
> 机器人**没有** Discord 绘图命令、陷阱频道审核**不读**消息文本、`/清除` 不删除磁盘会话、
> 知识库为跨服共享、频道范围由**运营者**全局配置。已用子代理逐文件核对（见
> `docs/verification_evidence.md`）。
>
> ⚠️ **本文件是中文对照版，仅供理解内容使用。提交给 Discord 时必须使用
> `docs/discord_intent_application.md` 中的英文原文**（Discord 申请流程为英文，中文内容
> 会显著降低获批概率）。两份文件结构完全对应，可按节对照。
>
> 背景：Discord 自 2026-06 起将审核门槛从"100 个服务器"改为**跨所有安装的 10,000 名唯一
> 用户**；达到后提交本表单，每次批准有效期为一年（到期需重新申请）。

---

## 一、在表单里勾选（Privileged Gateway Intents）

- ☑ **Message Content Intent**（唯一需要的权限）
- ☐ Server Members Intent —— 代码未使用任何 guild member 事件/成员名单功能，不要勾
- ☐ Presence Intent —— 代码未使用在线状态功能，不要勾

> 代码依据：`packages/dsh-bot-discord/src/index.js:132-141`，客户端只请求
> `Guilds / GuildMessages / DirectMessages / MessageContent` 四个 intent。
> 管理员 ban/kick、抓取、撤回等操作走 REST API 权限，不需要 Server Members intent。

---

## 二、Application Details（应用详情）

### 字段：What does your application do?（你的应用是做什么的？）

【中文对照——提交时请在英文填写稿中复制对应英文段落】

本应用是一个名为"波旁（美浦波旁）"的 Discord 多功能 AI 陪伴与社区机器人，基于 DeepSeek
Harness agent 运行时（Node.js、discord.js）构建，由个人开发者运营，仅通过邀请加入运营者明确选择
的服务器。功能以普通聊天文本访问——没有 Discord 应用命令，开头的 `/` 可省略。主要功能：

1. **带持久记忆的 AI 对话**。用户通过输入"波旁 <内容>"或 @提及机器人与其对话；私聊也会回复。
   运营者为某频道开启自由聊天时，机器人会跟随该频道的进行中的对话、保留滚动上下文、通过 AI
   "是否插话"门卫判断，并在回复时运行带频道记忆的对话轮次。机器人还支持人设切换、用户/管理员可
   教学的**知识库**（"学习"/知识命令；由运营者**跨服务器共享**）、用户发图时的图片理解、联网
   搜索、每日随机角色图（"今日担当"）、识图（"识图"）、随机 Pixiv 图片（"涩图"）与定时问候。

2. **自动翻译**。在运营者配置的少量频道中，机器人读取每条人类消息、判断语言，并在频道内回复
   zh/en/ja 译文——一个多语言社区功能。

3. **审核与实用命令**。指定的诱饵（"陷阱"）频道会被监视：在其中发言的用户可被移除并清除近期
   消息。管理员另有删除消息（"撤回"、"长期撤回"）、"ban"、频道历史抓取（"抓取"）以及运维命令
   （"debug"、"广播"、"清除"、"重启"）。哪些频道被监视或翻译由**运营者**配置。

4. **同一个 Discord 应用还提供可选的网页绘图界面 bourbon-draw.cn**：用户通过 Discord OAuth2
   （identify 权限：用户 ID、用户名、头像）登录，使用带按用户配额、历史与素材库的 AI 图片/视频
   生成工作区。网页界面与机器人是分离的：机器人本身不提供图片生成命令，网页界面也不读取
   Discord 消息内容。

### 字段：Do you have a public Privacy Policy telling your users about their data usage?
（你是否有向用户说明数据使用方式的公开隐私政策？）

```
Yes（是）
```

### 字段：Where is your Privacy Policy available?（你的隐私政策在哪里可访问？）

如为下拉/文本框，选择 **Website I own/operate**（或最接近选项），填入下面链接。
（部分表单版本没有此字段，直接跳过。）

### 字段：Please share a link to your Privacy Policy.（请提供隐私政策链接）

```
⚠️ 填入你发布后的隐私政策真实 URL，例如
https://eto-j.github.io/UMA-bot-discord/privacy.html
（仓库 docs/PRIVACY_POLICY.md 已更新为当前架构；发布到 GitHub Pages / 其他公开网址后粘贴链接）
```

---

## 三、Message Content Intent 部分

### 字段：Can users opt-out of having their message content data tracked?
（用户能否选择退出消息内容数据的追踪？）

```
No（不能）
```

说明（不需要填进表单）：当前机器人没有逐用户"关闭记忆"命令；但机器人只加入运营者选择的服务器，
自由聊天/翻译/审核频道范围由运营者全局配置（服务器成员无法自行开启或关闭），被拉黑用户的消息不
回复、不进入对话记忆（仅可能以片段形式出现在运营者运行日志中）。后续可增加用户级
`关闭记忆` 命令以进一步提升可信度。

### 字段：Are you storing message content data off-platform (outside of Discord)?
（你是否将消息内容数据存储在 Discord 平台之外？）

```
Yes（是）
```

说明：会话记录（dsh 会话存储，压缩 JSONL，**无自动过期**）、`学习` 知识库（FAISS，**跨服务器
共享**）、活动/控制台/sidecar 日志、以及管理员 `抓取` 归档，均保存在运营者自己的私有服务器/本机
磁盘，不存到任何第三方平台。隐私政策详细说明了存储、`清除`（不删磁盘文件）与删除方式。

### 字段：Will the message content data be used to train machine learning or AI Models?
（消息内容数据是否会被用于训练机器学习或 AI 模型？）

```
No（不会）
```

说明：内容仅被**临时**发送给生成当次回复所需的 AI/搜索/识图服务（DeepSeek 对话与视觉、
harness 联网搜索、SauceNAO、Pixiv、本地 ComfyUI 网页绘图），运营者不用于训练任何模型。
⚠️ 提交前请确认 DeepSeek 开放平台的 API 数据设置已关闭"用于训练"（如有该选项）。

### 字段：Why do you need the Message Content intent?（你为什么需要 Message Content 权限？）

【中文对照——提交时请在英文填写稿中复制对应英文段落】

Message Content 权限被以下**当前实际功能**所需要。机器人不是围绕 Discord 交互（应用命令）体系
构建的，消息文本是唯一的输入：

1) **纯文本命令**。几乎所有功能由直接写在聊天框里的文本触发："波旁 <内容>"（对话）、"帮助"、
   "学习 <内容>"、"人设列表" / "切换人设 <名称>"、"今日担当"、"识图"（带图片）、
   "涩图 <关键词>"，以及管理员命令 "撤回"、"长期撤回"、"ban"、"抓取"、"debug"、"广播"、
   "清除"、"重启"。在 Discord 上开头的 `/` 可省略。没有 Message Content 权限时，Discord 会
   清空服务器消息的 message.content，命令词与参数不可见，以上功能无法工作。Discord 内置的消息
   内容豁免（提及、回复、私信）不覆盖这些前缀式文本命令。

2) **自由对话（运营者开启时）**。运营者为频道开启自由聊天后，机器人阅读该频道的普通对话
   （保留最近几行作为基于模型的"是否回复"判断的上下文），并在回复时运行带持久记忆的对话轮次。
   读取未被针对的消息正是该权限存在的场景。

3) **自动翻译频道**。在运营者配置的频道中，机器人读取每条人类消息以判断语言并回复译文。
   这是自动功能，不是命令。

4) **运行诊断**。机器人在本地记录入站消息的活动日志（发送者 + 截断到约 300 字符的预览），用于
   运营者排障。日志只保留在运营者自己的服务器上，不用于其它用途，已在公开隐私政策中说明。

**范围与保障**：机器人仅限邀请加入，只处理运营者安装它的服务器；自由聊天/审核/翻译的频道范围由
运营者配置（服务器成员无法改变范围）；被拉黑用户被忽略（不回复、不进入对话记忆）；消息内容仅用于
上述功能；绝不出售或提供给广告/用户画像；仅在当次请求时临时发送给所需的 AI/视觉/搜索/图片服务；
运营者不使用内容训练任何机器学习模型。会话记录存储在运营者自己的服务器上；配置的管理员可用
"清除"开始新会话、用"删除知识"删除知识条目；用户也可联系运营者（见公开隐私政策）请求删除数据。

### 字段：Please provide links to screenshots and/or videos that demonstrate your use case
（请提供能演示你的使用场景的截图/视频链接）

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

## 四、Acknowledgement and Submit（确认与提交，位于表单底部）

- 勾选认证框："By clicking Submit, you certify that the information provided above is
  accurate and complete, and that you and your app are in compliance with Discord's
  Developer Terms of Service and Developer Policy..."
- 点击 **Submit**（提交）。

> ⚠️ 这两步需要你在已登录 Discord 的浏览器中亲自完成（需要你的开发者账号会话），
> 我无法代替你提交。批准后约一年需重新提交。

---

## 提交前 Checklist（检查清单）

1. ☐ 发布隐私政策到公开 URL，并替换占位联系方式（见 `docs/discord_verification_checklist.md`
   第 1 步；草案在 `docs/PRIVACY_POLICY.md`，推荐 GitHub Pages：
   `https://eto-j.github.io/UMA-bot-discord/privacy.html`）
2. ☐ 只勾选 Message Content Intent
3. ☐ 上传 3–5 张演示截图并填入 Imgur 链接
4. ☐ 确认 DeepSeek 平台数据设置关闭"使用数据训练"（保证 "No" 答案真实）
5. ☐ 通读英文答案；如与线上行为有出入先改答案再提交
6. ☐ 登录 Developer Portal 打开本表单链接 → 粘贴 → 勾认证框 → Submit

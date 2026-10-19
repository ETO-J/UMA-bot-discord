# Discord Message Content Intent — 申请表填写稿（中文对照版）

> 目标表单: https://discord.com/developers/applications/1452674140137066524/request-additional-intents
>
> **重要更新（2026-10 版）**：机器人主体已迁移到 DeepSeek Harness (dsh) 架构
> （Node.js + discord.js），不再是旧的 NoneBot2 实现；网页绘图站 bourbon-draw.cn 仍在
> bpdiscord 目录。本稿按**当前线上机器人**的实际功能撰写，并修正了旧稿中"机器人提供 draw 绘图
> 命令"等已不成立的描述。
>
> ⚠️ **本文件是中文对照版，仅供理解内容使用。提交给 Discord 时必须使用
> `docs/discord_intent_application.md` 中的英文原文**（Discord 申请流程为英文，中文内容
> 会显著降低获批概率）。两份文件结构完全对应，可按节对照。
>
> 背景：Discord 自 2026-06 起将审核门槛从"100 个服务器"改为**跨所有安装的 10,000 名唯一
> 用户**；达到后需提交本表单，每次批准有效期为一年，到期需重新申请。

---

## 一、在表单里勾选（Privileged Gateway Intents）

- ☑ **Message Content Intent**（唯一需要的权限）
- ☐ Server Members Intent —— 代码未使用任何 guild member 事件/成员名单功能，不要勾
- ☐ Presence Intent —— 代码未使用在线状态功能，不要勾

> 代码依据：`packages/dsh-bot-discord/src/index.js` 的
> `new Client({ intents: [Guilds, GuildMessages, DirectMessages, MessageContent] })`。
> 管理员 ban/kick 等操作走 REST API 权限，不需要 Server Members intent。

---

## 二、Application Details（应用详情）

### 字段：What does your application do?（你的应用是做什么的？）

【中文对照——提交时请在英文填写稿中复制对应英文段落】

本应用是一个名为"波旁（美浦波旁）"的 Discord 多功能 AI 陪伴与社区机器人，基于 DeepSeek
Harness agent 运行时（Node.js、discord.js）构建，由个人开发者运营，仅通过邀请加入运营者明确选择
的服务器。主要功能：

1. **带持久记忆的 AI 对话**。用户通过输入纯文本命令"波旁 <内容>"（开头的 `/` 可省略）或
   @提及机器人与其对话；私聊也会回复。在服务器配置开启自由聊天的频道中，机器人跟随进行中的对话、
   保留一小段滚动上下文、通过 AI 判断步骤（疲劳/兴趣门卫）决定是否自然插话，并在回复时运行带
   频道记忆的对话 AI 轮次，使回答保持连贯。机器人还支持人设切换、服务器教给它的知识库
   （"学习"/知识命令）、用户发图时的图片理解、联网搜索、每日随机角色图（"今日担当"）、
   识图（"识图"）、随机 Pixiv 图片（"涩图"）与定时问候。

2. **审核与实用命令**。指定的陷阱/审核频道会被监控，在其中的垃圾发布者可被处理；管理员拥有
   删除消息（"撤回"、"长期撤回"）、"ban"、频道历史抓取（"抓取"）以及运维命令（"debug"、
   "广播"、"清除"、"重启"）。哪些频道被监控或自动翻译由服务器管理员控制。

3. **同一个 Discord 应用还提供可选的网页绘图界面 bourbon-draw.cn**：用户通过 Discord OAuth2
   （identify 权限：用户 ID、用户名、头像）登录，使用带按用户配额、历史与素材库的 AI 图片/视频
   生成工作区。网页界面不读取 Discord 消息内容；**绘图被有意做成网页功能，而非 Discord 聊天命令**。

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

说明（不需要填进表单）：当前机器人没有逐用户"关闭记忆"命令；但处理范围受服务器管理员配置的频道
白名单限制，且被拉黑用户的消息既不回复也不作为记忆保存。若要进一步提升体验，可后续增加
`隐私模式`/`关闭记忆` 用户命令——这会显著增强可信度，但会增加开发量。

### 字段：Are you storing message content data off-platform (outside of Discord)?
（你是否将消息内容数据存储在 Discord 平台之外？）

```
Yes（是）
```

说明：会话记录（dsh 会话存储）、`学习` 知识库（FAISS）、活动/控制台/sidecar 日志、以及管理员
`抓取` 归档，均保存在运营者自己的私有服务器/本机磁盘，不存到任何第三方平台。隐私政策详细说明了
存储与删除方式（`清除`、`删除知识`、联系运营者）。

### 字段：Will the message content data be used to train machine learning or AI Models?
（消息内容数据是否会被用于训练机器学习或 AI 模型？）

```
No（不会）
```

说明：内容仅被**临时**发送给生成当次回复所需的 AI/搜索/识图服务（DeepSeek 对话与视觉 API、
harness 联网搜索、SauceNAO、Pixiv、本地 ComfyUI），运营者不用于训练任何模型。
⚠️ 提交前请确认 DeepSeek 开放平台的 API 数据设置已关闭"用于训练"（如有该选项），保证与回答一致。

### 字段：Why do you need the Message Content intent?（你为什么需要 Message Content 权限？）

【中文对照——提交时请在英文填写稿中复制对应英文段落】

Message Content 权限被三组作用于"普通消息"而非用户主动调用的斜杠命令的功能所需要：

1) **纯文本前缀命令**。几乎所有功能由直接写在聊天框里的文本触发："波旁 <内容>" 用于 AI 对话，
   "帮助/help"，"学习 <内容>"，"人设列表" / "切换人设 <名称>"，"今日担当 [角色]"，"识图"
   （带图片），"涩图 <关键词>"，以及管理员命令 "撤回 <id>"、"长期撤回 <用户>"、
   "ban <用户>"、"抓取 [模式] [频道]"、"debug"、"广播 <内容>"、"清除"、"重启"。在 Discord
   上开头的 `/` 可省略。没有 Message Content 权限时，Discord 会清空服务器消息的 message.content，
   机器人看不到命令词与参数，以上功能无法工作。Discord 内置的消息内容豁免（提及机器人、回复、
   私信）不适用于这些前缀式命令。

2) **自由对话**。在服务器管理员已启用的频道中，机器人会阅读普通对话、保留最近几行作为 AI
   "是否插话"门卫的上下文，并在回复时运行带持久频道记忆的对话 AI 轮次。这需要读取既没有 @机器人、
   也没有回复机器人的消息文本——正是该权限存在的场景。

3) **已配置频道中的审核与自动翻译**。陷阱频道审核需要在用户发送消息的当下检查任意用户的消息；
   自动翻译功能会读取少量已配置频道中的每条人类消息并回复译文。两者都作用于这些频道中的全部消息，
   而不只是被针对的消息。

隐私保护措施：机器人仅限邀请加入，只处理运营者选择服务的服务器；聊天与审核功能只在运营者/服务器
管理员配置的频道白名单中运行；被拉黑用户被完全忽略（不回复、不写记忆）；消息内容仅用于提供上述
功能；绝不出售或提供给广告/用户画像；仅在回答当次请求时临时发送给所需的 AI/视觉/搜索/图片 API；
运营者不使用内容训练任何机器学习模型。会话记录存储在运营者自己的服务器上；管理员可用"清除"
清空记忆、用"删除知识"删除知识条目，用户也可联系运营者（见隐私政策）请求删除数据。

### 字段：Please provide links to screenshots and/or videos that demonstrate your use case
（请提供能演示你的使用场景的截图/视频链接）

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

## 四、Acknowledgement and Submit（确认与提交，位于表单底部）

- 勾选认证框："By clicking Submit, you certify that the information provided above is
  accurate and complete, and that you and your app are in compliance with Discord's
  Developer Terms of Service and Developer Policy..."
- 点击 **Submit**（提交）。

> ⚠️ 这两步需要你在已登录 Discord 的浏览器中亲自完成（需要你的开发者账号会话），
> 我无法代替你提交。批准后约一年需重新提交。

---

## 提交前 Checklist（检查清单）

1. ☐ 发布隐私政策到公开 URL，并替换占位联系方式（草案 `docs/PRIVACY_POLICY.md`；
   推荐用仓库 docs/ 开 GitHub Pages：Settings → Pages → Deploy from branch → master /docs，
   链接示例 https://eto-j.github.io/UMA-bot-discord/privacy.html）
2. ☐ 只勾选 Message Content Intent
3. ☐ 上传 3–5 张演示截图并填入 Imgur 链接
4. ☐ 确认 DeepSeek 平台数据设置关闭"使用数据训练"（保证 "No" 答案真实）
5. ☐ 通读英文答案；如与线上行为有出入先改答案再提交
6. ☐ 登录 Developer Portal 打开本表单链接 → 粘贴 → 勾认证框 → Submit

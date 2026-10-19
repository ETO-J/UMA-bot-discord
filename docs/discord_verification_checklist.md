# Discord 应用验证 (App Verification) 完成清单

> 目标：完成应用验证与 Message Content Intent 审核所需的全部材料与填写内容。
> 适用应用：`美浦波旁`（Application ID `1452674140137066524`）。
> 现状：机器人主体在 `C:\Users\Administrator\bpdsh`（DeepSeek Harness + discord.js）；
> 网页绘图站 bourbon-draw.cn 在 `C:\Users\Administrator\bpdiscord`（FastAPI，同一 Discord 应用
> 的 OAuth2 登录，identify 权限）。
>
> 核对时间：2026-10-19。以下"需要你亲自做"的步骤（Stripe 身份验证、浏览器提交、手机/邮箱验证）
> 我无法代办，其余材料均已备好。

---

## 0. 先分清两条线（容易混淆）

| 项目 | 是什么 | 在哪做 | 门槛 |
|---|---|---|---|
| **Message Content Intent 申请** | 给机器人放开"读取普通消息文本"的特权 intent | Developer Portal → 应用 → `request-additional-intents` 表单 | 跨所有安装 **10,000 名唯一用户**（2026-06 起生效，取代旧的 100 服务器门槛）；批准后**每年**重新申请 |
| **应用验证 (App Verification)** | 给应用"已验证"徽章，可在 100+ 服务器运行、可申请上架 App Directory | Developer Portal → 应用 → **App Verification** 页 | 应用信息齐全、身份验证（Stripe）、遵守开发者条款 |

两条线材料互相引用（隐私政策、服务条款、网站），下面的内容**两条线通用**。

---

## 1. 发布公开页面（Website / Privacy / Terms）——推荐 GitHub Pages

验证要求网站可公开访问，且能打开隐私政策与服务条款链接。最省事的方式：用现有公开仓库
`github.com/ETO-J/UMA-bot-discord` 的 `docs/` 目录开 GitHub Pages。

**操作（你来做，约 3 分钟）：**

1. 把本仓库改动的 `docs/` 提交并推送（**先把文件里的联系方式占位符**
   `[请填入运营者联系邮箱]`、`[请填入运营者 Discord 用户名 / 支持服务器链接]`、
   `[请填入支持服务器链接]` 替换成真实信息，出现在 `PRIVACY_POLICY.md`、
   `PRIVACY_POLICY_zh.md`、`TERMS_OF_SERVICE.md`、`index.html` 中）：

   ```powershell
   cd C:\Users\Administrator\bpdiscord
   git add docs/
   git commit -m "docs: 验证材料（隐私政策/服务条款/落地页/申请稿）按 dsh 架构更新"
   git push origin master
   ```
2. 打开仓库 **Settings → Pages**：
   - Source 选 **Deploy from a branch**
   - Branch 选 **master**，目录选 **/docs**
   - 保存，等待 1–2 分钟构建完成。
3. 验证以下 URL 都能在无登录状态下打开（这是回复审核时必须能点开的链接）：
   - 落地页：`https://eto-j.github.io/UMA-bot-discord/`
   - 隐私政策：`https://eto-j.github.io/UMA-bot-discord/PRIVACY_POLICY.html`
   - 服务条款：`https://eto-j.github.io/UMA-bot-discord/TERMS_OF_SERVICE.html`

> 如果 GitHub Pages 不可用，备选：用 gist.github.com 发布同样的 HTML/Markdown 并取 Raw 链接；
> 或把 `docs/` 里的 HTML 拷到 `webapp/static/` 由 nginx 提供（需要改站点配置，不推荐）。
> 网站也可以指向 `https://bourbon-draw.cn`，但那只显示绘图界面登录页，**不**含政策页面，
> 审核请优先用 Pages 落地页。

---

## 2. Developer Portal — General Information 字段填写

打开 https://discord.com/developers/applications/1452674140137066524 → **General Information**。

### 2.1 Description（应用简介，上限 400 字符）

```
Bourbon (美浦波旁) is an invite-only AI companion bot for Discord: chat with memory
(「波旁 …」 or @mention), server-taught knowledge, image understanding, persona switching,
daily character images, and practical moderation/admin tools (message removal, ban,
channel archive). It also offers an optional AI drawing site (bourbon-draw.cn) via Discord
login.
```

### 2.2 Tags（标签，按 App Directory 分类挑 2–3 个）

建议：`Artificial Intelligence`、`Fun`、`Utilities`（按实际能选到的分类选择；审核偏好
"权限与实际功能相符"，不要堆标签）。

### 2.3 链接字段

| 字段 | 填什么 |
|---|---|
| **Website** | `https://eto-j.github.io/UMA-bot-discord/` （备选 `https://bourbon-draw.cn`） |
| **Privacy Policy URL** | `https://eto-j.github.io/UMA-bot-discord/PRIVACY_POLICY.html` |
| **Terms of Service URL** | `https://eto-j.github.io/UMA-bot-discord/TERMS_OF_SERVICE.html` |

> 若之后迁移到自己的域名（如 bourbon-draw.cn/legal/privacy），只需更新这三个链接并保证页面存在。

### 2.4 App Icon（应用图标）

上传 512×512 或以上、圆形裁切下好看的图标（与机器人头像一致即可）。头像在成员列表里只显示约
40px 的圆形缩略图，选高对比、无小字的图。

### 2.5 其他

- **Support Server**（若填写）：填你的支持服务器邀请链接；没有就先建一个（见 3.1）。
- **Interactions Endpoint URL**：保持留空（本机器人不用 HTTP 交互回调）。
- **Bot 页 → Public Bot**：按现状保持（私有应用没问题；审核人员通过你提供的测试服务器测试）。

---

## 3. App Verification 页流程

Developer Portal 应用页左侧 **App Verification**：

1. 逐项把 checklist 变绿：
   - ✅ 应用描述 / 图标 / 隐私政策 / 服务条款 / 网站
   - ✅ **身份验证（Stripe）**：团队所有者需用有效证件完成（只有你能做）。
   - ✅ Discord 账号开启 2FA（Bot 在 100+ 服务器/管理类权限时必需）。
2. 点击 **Verify App** 提交；通过后获得验证徽章，可上架 App Directory。
3. 审核一般数天到数周；被拒会收到原因，修正后可重提。

### 3.1 支持服务器（建议）

建一个公开的 Discord 支持服务器，设置好频道与规则，把邀请链接填到 Support Server 字段，
并在落地页与隐私政策里放同一链接。审核人员常通过它联系开发者或实测机器人。

---

## 4. Message Content Intent 提交（另行完成）

详细逐字段答案见 **`docs/discord_intent_application.md`**（中文对照版
`docs/discord_intent_application_zh.md`）。要点：

- 只勾 **Message Content Intent**；
- 复制其中两段英文长答（What does your application do / Why do you need the intent）；
- 隐私政策处选 Yes 并填 Pages 链接；
- 三个 Yes/No 问题：opt-out=**No**、存储 off-platform=**Yes**、训练模型=**No**；
- 上传 3–5 张功能截图（Imgur）后填链接；
- 提交后每年重新申请一次。

---

## 5. 测试说明（给审核人员）

在邮件/表单回复中可附以下说明（英文，直接粘贴）：

```
How to test the bot
- Invite it to a fresh test server with these permissions: View Channels, Send Messages,
  Read Message History, Embed Links, Attach Files, Manage Messages, Kick Members,
  Ban Members. Scopes: bot + applications.commands.
- 1) Send "波旁 你好" (or "/波旁 你好") — the bot replies with a conversation answer.
- 2) Send "/帮助" — the bot lists its commands.
- 3) @mention the bot in any channel — it replies.
- 4) Send an image with "/识图" — it returns image-source results.
- 5) (Optional) Put the bot in a channel configured as a moderation "trap channel" and post
  a message — the bot demonstrates the moderation action.
- Commands work with or without the leading slash.
```

**邀请链接生成**：Developer Portal → **OAuth2 → URL Generator**，Scopes 勾 `bot` +
`applications.commands`，Permissions 勾上表所列（+ 如需要 `Manage Threads` 以支持 `/抓取` 线程）。
把生成出的邀请链接交给审核人员或填进测试服务器。

---

## 6. 截图清单（Intent 表单用，Imgur 上传）

| # | 截什么 | 证明什么 |
|---|---|---|
| 1 | 频道内发送「波旁 你好」→ 机器人回复 | 读取普通消息文本 + 命令解析 |
| 2 | 开启自由聊天的频道中机器人自然加入对话（或 @机器人 回复） | 自由对话需读消息文本 |
| 3 | 「/帮助」输出 | 命令系统整体 |
| 4 | 自动翻译频道中对一条消息回复多语言译文 | 审核/翻译频道读全量消息 |
| 5 | （可选）陷阱频道处理垃圾消息的提示/日志 | 审核副作用说明 |

截图请**真实**、与表单文字一致；审核会核对权限与实际行为是否相符。

---

## 7. 已知风险与提交前修正项

1. **公开仓库 README 与线上机器人不一致**：`UMA-bot-discord` 仓库 README 仍描述旧的
   NoneBot2 版本（含机器人 `draw` 命令），线上机器人已是 dsh 版且**不做** Discord 绘图。
   建议在 README 顶部加一行指向 `docs/` 的说明，或用 bpdsh 的 README 更新仓库介绍——
   审核人员查到仓库时，材料需与机器人行为一致。
2. **bpdsh 仓库尚未上传到 GitHub**（无 remote）。若要把源码公开供审核参考，可新建仓库
   推送 bpdsh；不公开也不影响验证，但"网页/隐私政策/条款"必须公开可访问。
3. **DeepSeek 数据设置**：提交前在 DeepSeek 开放平台确认 API 数据不被用于训练，保证
   "Will message content be used to train models? → No" 为真。
4. **机器人邀请必须人工完成**：invite-only 机器人无法被审核人员自行加入，务必提供测试服务器
   与邀请链接/说明。
5. **每年重审**：Intent 批准一年后需重新提交表单；到期前会有通知。

---

## 8. 提交后

- 审核期间机器人照常运行。
- 通过后：在 Bot 页启用 **Message Content Intent** 开关（若表单批准对应开关会自动允许），
  检查 `[dc]` 启动日志回执。
- 被拒：按邮件原因修正（常见：官网/政策不可访问、权限与功能不符、机器人无法测试）。
  修正后重提即可，不必气馁。

# Mihono Bourbon Discord Bot — User Manual

> Version: 2026.5.26

---

## Table of Contents

1. [Quick Start & Command Reference](#1-quick-start--command-reference)
2. [Core Drawing: draw](#2-core-drawing-draw)
3. [Drawing Parameters](#3-drawing-parameters)
4. [Multi-Character Drawing: multidraw & Related Parameters](#4-multi-character-drawing-multidraw--related-parameters)
5. [AI Chat](#5-ai-chat)
6. [Other Features](#6-other-features)
7. [FAQ](#7-faq)

---

## 1. Quick Start & Command Reference

Mihono Bourbon is a comprehensive Discord bot powered by a ComfyUI backend. Simply enter commands in the chat box, and the bot will invoke AI models to chat with you, generate images, and provide other services.

All services provided by the bot are completely free. The developer (eto20040612) reserves all rights of final interpretation and adjudication regarding the bot. The developer reserves the right to discontinue service to any unwelcome individual at any time.

All commands support both the `/` prefix and the non-prefix form (e.g., `draw` and `/draw` work identically).

### Command Quick Reference:

#### 1.1 AI Chat

| Command | Format |
|------|------|
| **波旁** | `波旁 your input` | Use "波旁" as a sentence-initial wake word to force the bot to reply to your message. |
| Any input other than commands | In free chat mode, the bot will selectively reply to any non-command messages in the group chat based on built-in algorithms. |

#### 1.2 Core Drawing Commands

| Command | Format | Quota |
|------|------|------|
| **draw** | `draw prompt` | 1 |
| **multidraw** | `multidraw global AND character1 AND character2` | 10 |

#### 1.3 Quality & Resolution Settings

| Command | Format | Description |
|------|------|------|
| **高清** | `高清 on/off` or `高清 开/关` | Toggle HD mode |
| **切换分辨率** | `切换分辨率 width height` | Modify output resolution (pixels) |
| **partone** | `partone width height X Y` | Set multi-character region 1 |
| **parttwo** | `parttwo width height X Y` | Set multi-character region 2 |

#### 1.4 Prompt Settings

| Command | Format | Description |
|------|------|------|
| **切换负面** | `切换负面 negative_prompt` | Set custom negative prompt |
| **重置负面** | `重置负面` | Clear custom negative prompt |

#### 1.5 Workflow & Lora

| Command | Format | Description |
|------|------|------|
| **切换工作流** | `切换工作流 anima/discord/高清` | Change workflow architecture |
| **lora列表** | `lora列表` | View available and mounted Loras |
| **添加lora** | `添加lora name [weight]` | Mount a Lora (default weight 0.8) |
| **删除lora** | `删除lora full_filename` | Unmount a specific Lora |
| **重置lora** | `重置lora` | Unmount all Loras |

#### 1.6 Other Features

| Command | Format | Description |
|------|------|------|
| **今日担当** | `今日担当 [character_name]` | Random daily waifu draw (once per day) |

---

## 2. Core Drawing: `draw`

### 2.1 Core Concepts at a Glance

| Concept | Explanation | Analogy |
|------|------|------|
| **Prompt** | Describes the elements you want in the image | A written brief for the artist |
| **Negative Prompt** | Tells the AI what NOT to draw | "Don't mess it up, don't make it blurry" |
| **Workflow** | The base model / architecture the AI uses | Different art style tools used by an artist |
| **Lora** | A fine-tuning overlay applied to the base model | Extra reference material packs for the artist |
| **Quota** | Daily limit on the number of drawings | Available uses per day |

**Quota Details:**

Each user has a fixed daily drawing limit (default: 25 times). Different commands consume different amounts:

| Command | Quota Cost |
|------|---------|
| `draw` (normal mode) | 1 |
| `draw` (HD mode) | 100 |
| `multidraw` | 10 |

The drawing quota is designed to reduce low-quality AI creations and encourage using AI for artworks with higher artistic merit. The initial limit is 25 drawing requests per day (including draw and ezdraw), resetting daily at 00:00 (Beijing time). If you need more quota, please consult the AI manager ETO (eto200406), select your two best AI works (must be high-quality and safe for work), and submit them to the server administrator eto20040612 for review.

### 2.2 Basic Usage

```
draw [prompt]
```

This is the most commonly used command. Input a description of the image you want, and the bot will generate an image for you.

Example:
```
draw 1girl,solo,king halo,umamusume,girl with tail,tracen school uniform,
```

The bot will generate an image of the character King Halo from *Uma Musume* wearing the Tracen school uniform.
*Prompts only support English.*

**How to write a good prompt:**

Principle: Use a moderate number of tags. You can organize them with the following structure:

```
Quality tags: masterpiece, best quality, score_9, score_8, newest, etc.
Meta tags: year 2025, year 2024, ...
Character description: 1girl, solo, king halo, xxx eyes, small/medium/large breasts, ...
Clothing description: tracen school uniform, purple shirt, white skirt, white thighhighs, white panties, ...
Expression: smile, grin, angry, ...
Action: hand on hip, hand on stomach, sex from behind, missionary sex, ...
Environment & scene details: school, classroom, love hotel, outdoor, simple background, sunshine/sunset/night, bed, chair, used condoms, condom wrappers, ...
Camera shot: close up, mid shot, wide shot, from above, frontview, from side, from below, cowboy shot, full body, ...
Lighting: soft lighting, sun light, moon light, rim light, silhouette, ...
Other details: heart bubbles, speed lines, motion lines, sound effects, motion blur, ...
Natural language supplement: The girl standing against the wall with grin, a beam of light on her face. ...
```

**Notes:**

The bot will first display "正在生成中..." (Generating...) and then send the image. If no image is received after a long time, it may be a network issue — try again. If your quota is insufficient, the bot will tell you how many uses remain.

---

## 3. Drawing Parameters

Diffusion-based image generation has several key parameters:

### 3.1 Image Resolution

Resolution determines the size and shape of an image.

Use the following command to change your resolution settings:

```
切换分辨率 [width] [height]
```
Example: `切换分辨率 1216 832`

Common resolutions include:

- 832 x 1216 (portrait rectangle)
- 1024 x 1024 (square)
- 1216 x 832 (landscape rectangle)

If you are using the default discord workflow, try to stick with the above resolutions. Excessively high resolution not only takes longer to generate but is also very likely to cause unpredictable image artifacts.

If you are using a more advanced workflow such as anima, the bot also supports high-resolution parameters like:

- 1600 x 900 (16:9)
- 1920 x 1080 (2K)

### 3.2 Negative Prompt

The negative prompt determines what you do NOT want to appear in the image. If you wish to exclude certain elements from your image, add them to your negative prompt.

Use the following command to change your negative prompt:

```
切换负面 [negative_prompt]
```
Example: `切换负面 text,speech bubbles,worst quality, low quality, score_1, score_2, score_3, blurry, jpeg artifacts, sepia,censored,text,speech bubble,Mosaic,`

**重置负面**: Resets your negative prompt to the default.

### 3.3 Seed

The seed is a core intrinsic property when a diffusion model generates an image. Using a fixed seed with the same drawing parameters will produce the exact same image each time. The bot currently uses randomly generated seeds. Custom seed settings are not supported.

### 3.4 Steps

Steps represent the number of denoising sampling iterations the diffusion model takes to generate an image from random noise. Generally, more steps yield more detailed images. The bot currently uses 30 steps, balancing high quality and speed. Custom step settings are not supported.

### 3.5 CFG

CFG represents how strongly the text prompt constrains the image. A higher CFG makes the image conform more closely to the prompt, but excessively high CFG can also degrade image quality. The default discord workflow uses CFG 6; the anima workflow uses CFG 4. Custom CFG settings are not supported.

### 3.6 Sampler

The sampler represents the algorithm used by the model for denoising, affecting generation speed, image quality, and artistic style. The default discord sampler is `dpmpp_2m`; the anima workflow sampler is `er_sde`. Custom sampler settings are not supported.

### 3.7 Scheduler

The scheduler represents the method by which the model controls gradual noise removal. The default discord scheduler is `karras`; the anima workflow scheduler is `simple`. Custom scheduler settings are not supported.

### 3.8 Workflow & Lora

#### 3.8.1 Workflow

The workflow represents the overall image generation pipeline the bot uses. The bot currently offers three workflows:

- **discord**: The default workflow. The main model is `waiIllustriousSDXL_v170`, based on the Illustrious architecture. Fast generation, high image quality, and a strong Lora ecosystem. Disadvantages include difficulty understanding natural language, difficulty understanding complex logical relationships, poor multi-character support, and low native resolution.
- **discord_高清**: The HD workflow, built on the same architecture as above, with an added secondary upscale-sampling HD node. Generates higher-resolution images (4x the original) with richer detail. *Each use consumes 100 quota points.*
- **anima**: A new-generation workflow in the experimental stage. The main model is `anima_base` and its fine-tuned variants. Compared to older models like Illustrious, the Anima series generates slightly slower but delivers better image quality and significantly improved model intelligence — strong multi-character comprehension, balanced tag-language and natural-language understanding, and native high-resolution support (2K).

Use the following commands to change your workflow:

```
切换工作流 [discord/anima]
高清 [on/off]
```

#### 3.8.2 Lora

Lora (Low-Rank Adaptation) is like a "plugin node" mounted on top of the existing workflow, used to modify the workflow's properties. Mounting Loras can achieve the following (and more):

- **Character enhancement**: Mounting a character Lora enables the model to generate characters that are otherwise hard to produce, generate alternate outfits (e.g., different racing uniforms of Uma Musume characters), and strengthen character styling.
- **Art style adjustment**: Mounting a style Lora can make your generated artwork adopt a specific artistic style.
- **Concept enhancement**: Mounting a concept Lora allows the model to generate conceptual content that would otherwise be difficult to produce.

Use the following commands to mount and adjust your Loras:

- **lora列表**: Lists all available Loras in the database and displays your currently mounted Loras.
- **添加lora [lora_name] [weight]**: Mounts a Lora onto your current workflow at a specified strength. Weight can be negative; recommended range [0–1]. Example: `添加lora haki_style 1`
- **删除lora [lora_name]**: Removes a mounted Lora and displays your other mounted Loras. Example: `删除lora haki_style.safetensors`
- **重置lora**: Clears all your mounted Loras.

*Note: Loras for the discord workflow and the anima workflow cannot be used interchangeably. When switched to the anima workflow, the Lora list will only display Anima-exclusive Loras.*

---

## 4. Multi-Character Drawing: multidraw & Related Parameters

Traditional workflows have always struggled with multi-character capabilities. Using the `draw` command directly often makes it difficult to generate compositions with multiple scenes or characters. To address this, we developed a multi-character drawing feature based on prompt-region technology, enabling precise control over multi-character and multi-scene generation tasks.

### 4.1 Region Resolution Settings

Before drawing multi-character images, you must set the resolution for each region individually. The `partone` command sets the generation area for character 1. The `parttwo` command sets the generation area for character 2. Moderate overlap between partone and parttwo is allowed to mitigate visual seams between the two regions.

Use the following commands to set the generation regions for character 1 and character 2:

```
partone [width] [height] [X] [Y]
parttwo [width] [height] [X] [Y]
```

Example:
```
partone 652 832 0 0
parttwo 652 832 564 0
```
Using these parameters generates an image with a total size of 1216 x 832. Character 1's generation region is [(0,0), (0,832), (652,832), (652,0)] (the left half of the image). Character 2's generation region is [(564,0), (564,832), (1216,832), (1216,0)] (the right half). The overlapping area is [(564,0), (564,832), (652,832), (652,0)].

### 4.2 multidraw Syntax & Detailed Explanation

Use the following command to draw multi-character images:

```
multidraw [Prompt A AND Prompt B AND Prompt C]
```

- **Prompt A** is the global prompt, controlling global attributes such as quality tags, meta tags, environment/scene, and lighting.
- **Prompt B** is the specific content for character 1, e.g., `1girl,king halo,umamusume,tracen school uniform,xxx`.
- **Prompt C** is the specific content for character 2, e.g., `1girl,mejiro mcqueen,xxxxx`.

Example:
```
multidraw
2girls,unworn_clothes,dark bedroom,video recording view,vcr,masterpiece,best quality,ultra detailed,2girls,unworn_clothes,dark bedroom,video recording view,vcr,masterpiece,best quality,ultra detailed,
AND
1girl,gentildonna(umamusume),girl with tail,nude,pubic_hair,sweat,steaming_body,large_breasts,pink_nipple,1man,faceless strong man,sex,rape,vaginal,sex from behind,standing sex,moaning during sex,looking at viewer,frontview,masterpiece,best quality,ultra detailed,
AND
1girl,verxina(umamusume),girl with tail,nude,1man,faceless strong man,sex,rape,doggystyle,arms grab,kneeling on bed,sideview,(wide_shot:1.2),(perspective:1.2),masterpiece,best quality,ultra detailed,
```

The default workflow for multidraw is discord, so Lora usage and prompt writing techniques should follow the relevant content for the discord workflow. Adaptation of the anima workflow for multidraw is currently in progress.

---

## 5. AI Chat

The bot is equipped with a large-model reasoning engine based on deepseek-v4-pro and real-time web search capabilities, enabling conversational interaction.

Use the following command to chat with the bot:

```
波旁 [prompt]
```

Example:
```
波旁 今天天气如何？
```

When an admin enables simulated chat mode, the bot will also selectively reply to users' non-specific, non-command chat messages based on built-in algorithms.

The AI chat feature supports English and Japanese.

---

## 6. Other Features

### 今日担当

A daily one-time waifu gacha draw.

Usage:
```
今日担当 [name (optional)]
```
If no name is provided, a random character is drawn.

---

## 7. FAQ

### Q: Why did the generation fail?

Possible reasons:
- The ComfyUI backend is not running or is experiencing issues.
- The prompt triggered a safety filter.
- Network problems.

Except for network issues, failed generations will automatically refund your quota — just try again later. Quota lost due to network problems cannot be automatically refunded.

### Q: Why did the image come out different from what I wanted?

AI drawing is not precise "ordering from a menu." The following factors can affect the result:
- **Insufficiently specific prompt**: Try to describe the subject, scene, and style in as much detail as possible.
- **Lora conflict**: Mounting multiple Loras simultaneously can cause mutual interference. It is recommended to mount 1–2 at a time.
- **Overly strict negative prompt**: A negative prompt that is too harsh can limit the AI's creativity.
- **Workflow differences**: The Anima and SDXL base models have different art styles.

### Q: HD mode costs 100 quota. How do I know if I have enough?

When using `draw`, the bot will display "今日剩余配额: XX" (Remaining quota today: XX). If your quota is insufficient, it will refuse and tell you the remaining count.

### Q: Why are character positions wrong in multidraw?

Character positions are controlled by `partone` / `parttwo` (see Section 4). The defaults are left-right side by side. Check that your region settings are reasonable.

### Q: How do I check my current settings?

There is currently no one-click function to view your settings. However, you can:
- Use `lora列表` to view mounted Loras and workflow type.
- Other settings (resolution, negative prompt, etc.) can only be confirmed via the confirmation messages that appear when you run the corresponding commands.

### Q: How do I find out Lora names?

Use `lora列表` to view all available Loras and find the name you want (fuzzy search is supported).

### Q: What are the differences between workflows?

- **SDXL (discord)**: Focuses on realism and detail; compatible with the most general-purpose Loras.
- **Anima**: A purer anime art style with distinctive line work and coloring.
- **高清**: Primarily for upscaling and refinement; does not change the art style itself.

---

> An advanced AI drawing tutorial is currently in development. If you are interested in collaborating, please contact the server administrator eto20040612.
> If you have any questions, please contact the server administrator eto20040612.

const I18N = {
  zh: {
    title: "Bourbon Webui",
    quota: "配额",
    online: "在线",
    resolution: "分辨率",
    custom: "自定义",
    prompt: "提示词",
    artistChain: "画师串",
    promptPlaceholder: "输入提示词...",
    artistPlaceholder: "artist1, artist2, ...",
    negativePrompt: "负面提示词",
    negativePlaceholder: "输入负面提示词...",
    advToggleClosed: "高级参数 ▸",
    advToggleOpen: "高级参数 ▾",
    seed: "种子",
    sampler: "采样器",
    samplerDefault: "使用工作流默认",
    scheduler: "调度器",
    schedulerDefault: "使用工作流默认",
    steps: "步数",
    stepsPlaceholder: "使用工作流默认",
    cfg: "CFG",
    cfgPlaceholder: "使用工作流默认",
    loraTitle: "LoRA 管理器",
    loraDefaultWeight: "默认权重:",
    loraRemoveAll: "全部移除",
    loraRefresh: "刷新列表",
    loraNoFiles: "未找到任何 LoRA 文件",
    loraLoadFail: "加载 LoRA 列表失败",
    loraManage: "管理 LoRA ▸",
    generate: "生成",
    generating: "生成中...",
    submitting: "提交中...",
    multidrawGenerate: "多角色生成",
    workflow: "工作流",
    workflowAnimaV2: "Anima V2 (画师融合)",
    workflowMultidraw: "多角色合成 (Multidraw)",
    history: "生成历史",
    historyRefresh: "刷新",
    globalPrompt: "全局提示词",
    char1Prompt: "角色 1 提示词",
    char2Prompt: "角色 2 提示词",
    area1: "区域 1 (w h x y)",
    area2: "区域 2 (w h x y)",
    globalPlaceholder: "共享的背景/风格描述",
    char1Placeholder: "第一个角色的描述",
    char2Placeholder: "第二个角色的描述",
    waiting: "等待生成...",
    taskSubmitted: "任务已提交",
    queued: "排队中",
    processing: "生成中",
    completed: "已完成",
    failed: "失败",
    error: "错误",
    queuePosition: "排队位置",
    queueAhead: "前方",
    queueTotal: "人中",
    estimatedWait: "预计等待",
    estimatedRemaining: "预计剩余",
    elapsed: "已用时",
    sec: "秒",
    min: "分",
    promptRequired: "请输入提示词",
    allPromptsRequired: "请填写全部三个提示词",
    imageLoaded: "已加载历史图片",
    params: "参数",
    expandTitle: "放大/还原",
    login: "Discord 登录",
    logout: "退出",
    loginRequired: "🔐 请先点击右上角 Discord 登录按钮进行登录",
    quotaExhausted: "🔒 今日免费配额已用完，请联系网站创建者获取更多免费额度",
    taskNotFound: "任务不存在（可能因服务重启已清除）",
    workflowVideo: "视频生成 (Wan2.2)",
    videoFirstFrame: "首帧图像",
    videoLastFrame: "尾帧图像（可选）",
    videoDropHint: "点击或拖拽上传首帧",
    videoDropHintOptional: "点击或拖拽上传尾帧（可选）",
    videoQuality: "画质",
    videoDuration: "时长",
    videoGenerate: "生成视频",
    videoEnhance: "动态增强",
    videoEnhanceStrength: "强度",
    videoNegPlaceholder: "留空使用工作流默认",
    firstFrameRequired: "请先上传首帧图像",
    cost: "消耗",
    hdMode: "高清增强",
    hdModeHint: "消耗 10 配额，放大+精炼生成更高质量图像",
    workflowFlux2Edit: "Flux2 图像编辑 (Klein 9B)",
    flux2Generate: "Flux2 编辑",
    flux2PromptPlaceholder: "描述编辑目标...",
    flux2SourceImage: "原图（必须）",
    flux2SourceDropHint: "点击或拖拽上传原图",
    flux2RefImage: "参考图（可选）",
    flux2RefDropHint: "点击或拖拽上传参考图（可选）",
    flux2SourceRequired: "请先上传原图",
  },

  en: {
    title: "Bourbon Webui",
    quota: "Quota",
    online: "Online",
    resolution: "Resolution",
    custom: "Custom",
    prompt: "Prompt",
    artistChain: "Artist Chain",
    promptPlaceholder: "Enter prompt...",
    artistPlaceholder: "artist1, artist2, ...",
    negativePrompt: "Negative Prompt",
    negativePlaceholder: "Enter negative prompt...",
    advToggleClosed: "Advanced ▸",
    advToggleOpen: "Advanced ▾",
    seed: "Seed",
    sampler: "Sampler",
    samplerDefault: "Use workflow default",
    scheduler: "Scheduler",
    schedulerDefault: "Use workflow default",
    steps: "Steps",
    stepsPlaceholder: "Use workflow default",
    cfg: "CFG",
    cfgPlaceholder: "Use workflow default",
    loraTitle: "LoRA Manager",
    loraDefaultWeight: "Default weight:",
    loraRemoveAll: "Remove All",
    loraRefresh: "Refresh",
    loraNoFiles: "No LoRA files found",
    loraLoadFail: "Failed to load LoRA list",
    loraManage: "Manage LoRA ▸",
    generate: "Generate",
    generating: "Generating...",
    submitting: "Submitting...",
    multidrawGenerate: "Multidraw",
    workflow: "Workflow",
    workflowAnimaV2: "Anima V2 (Artist Fusion)",
    workflowMultidraw: "Multidraw (Multi-Char)",
    history: "History",
    historyRefresh: "Refresh",
    globalPrompt: "Global Prompt",
    char1Prompt: "Character 1 Prompt",
    char2Prompt: "Character 2 Prompt",
    area1: "Area 1 (w h x y)",
    area2: "Area 2 (w h x y)",
    globalPlaceholder: "Shared background/style description",
    char1Placeholder: "Description of first character",
    char2Placeholder: "Description of second character",
    waiting: "Waiting for generation...",
    taskSubmitted: "Task submitted",
    queued: "Queued",
    processing: "Processing",
    completed: "Completed",
    failed: "Failed",
    error: "Error",
    queuePosition: "Queue",
    queueAhead: "",
    queueTotal: "",
    estimatedWait: "Est. wait",
    estimatedRemaining: "Est. remaining",
    elapsed: "Elapsed",
    sec: "s",
    min: "m",
    promptRequired: "Please enter a prompt",
    allPromptsRequired: "Please fill in all three prompts",
    imageLoaded: "Loaded history image",
    params: "Params",
    expandTitle: "Expand/Collapse",
    login: "Login with Discord",
    logout: "Logout",
    loginRequired: "🔐 Please click the Discord login button at the top right first",
    quotaExhausted: "🔒 Daily free quota exhausted. Please contact the website creator for more free quota.",
    taskNotFound: "Task not found (likely cleared by server restart)",
    workflowVideo: "Video Generation (Wan2.2)",
    videoFirstFrame: "First Frame",
    videoLastFrame: "Last Frame (optional)",
    videoDropHint: "Click or drag to upload first frame",
    videoDropHintOptional: "Click or drag to upload last frame (optional)",
    videoQuality: "Quality",
    videoDuration: "Duration",
    videoGenerate: "Generate Video",
    videoEnhance: "Dynamic Enhancement",
    videoEnhanceStrength: "Strength",
    videoNegPlaceholder: "Leave empty for workflow default",
    firstFrameRequired: "Please upload a first frame image",
    cost: "Cost",
    hdMode: "HD Enhance",
    hdModeHint: "Costs 10 quota. Upscale + refine for higher quality.",
    workflowFlux2Edit: "Flux2 Image Edit (Klein 9B)",
    flux2Generate: "Flux2 Edit",
    flux2PromptPlaceholder: "Describe the edit goal...",
    flux2SourceImage: "Source Image (required)",
    flux2SourceDropHint: "Click or drag to upload source image",
    flux2RefImage: "Reference Image (optional)",
    flux2RefDropHint: "Click or drag to upload reference image (optional)",
    flux2SourceRequired: "Please upload a source image first",
  },

  ja: {
    title: "Bourbon Webui",
    quota: "クォータ",
    online: "オンライン",
    resolution: "解像度",
    custom: "カスタム",
    prompt: "プロンプト",
    artistChain: "画師チェーン",
    promptPlaceholder: "プロンプトを入力...",
    artistPlaceholder: "artist1, artist2, ...",
    negativePrompt: "ネガティブプロンプト",
    negativePlaceholder: "ネガティブプロンプトを入力...",
    advToggleClosed: "詳細設定 ▸",
    advToggleOpen: "詳細設定 ▾",
    seed: "シード",
    sampler: "サンプラー",
    samplerDefault: "ワークフロー既定",
    scheduler: "スケジューラー",
    schedulerDefault: "ワークフロー既定",
    steps: "ステップ数",
    stepsPlaceholder: "ワークフロー既定",
    cfg: "CFG",
    cfgPlaceholder: "ワークフロー既定",
    loraTitle: "LoRA マネージャー",
    loraDefaultWeight: "既定の重み:",
    loraRemoveAll: "すべて解除",
    loraRefresh: "更新",
    loraNoFiles: "LoRAファイルが見つかりません",
    loraLoadFail: "LoRAリストの読み込みに失敗",
    loraManage: "LoRA管理 ▸",
    generate: "生成",
    generating: "生成中...",
    submitting: "送信中...",
    multidrawGenerate: "マルチキャラ生成",
    workflow: "ワークフロー",
    workflowAnimaV2: "Anima V2 (画師融合)",
    workflowMultidraw: "マルチキャラ合成",
    history: "履歴",
    historyRefresh: "更新",
    globalPrompt: "全体プロンプト",
    char1Prompt: "キャラ1 プロンプト",
    char2Prompt: "キャラ2 プロンプト",
    area1: "領域 1 (w h x y)",
    area2: "領域 2 (w h x y)",
    globalPlaceholder: "共有の背景・スタイル説明",
    char1Placeholder: "1人目のキャラ説明",
    char2Placeholder: "2人目のキャラ説明",
    waiting: "生成待機中...",
    taskSubmitted: "タスク送信済み",
    queued: "待機中",
    processing: "生成中",
    completed: "完了",
    failed: "失敗",
    error: "エラー",
    queuePosition: "待ち順位",
    queueAhead: "前方",
    queueTotal: "人",
    estimatedWait: "推定待ち時間",
    estimatedRemaining: "推定残り時間",
    elapsed: "経過時間",
    sec: "秒",
    min: "分",
    promptRequired: "プロンプトを入力してください",
    allPromptsRequired: "3つのプロンプトをすべて入力してください",
    imageLoaded: "履歴画像を読み込みました",
    params: "パラメータ",
    expandTitle: "拡大/縮小",
    login: "Discordでログイン",
    logout: "ログアウト",
    loginRequired: "🔐 右上のDiscordログインボタンを先にクリックしてください",
    quotaExhausted: "🔒 本日の無料クォータを使い切りました。サイト作成者にお問い合わせください。",
    taskNotFound: "タスクが見つかりません（サーバー再起動で削除された可能性）",
    workflowVideo: "動画生成 (Wan2.2)",
    videoFirstFrame: "先頭フレーム",
    videoLastFrame: "末尾フレーム（任意）",
    videoDropHint: "クリックまたはドラッグで先頭フレームをアップロード",
    videoDropHintOptional: "クリックまたはドラッグで末尾フレームをアップロード（任意）",
    videoQuality: "画質",
    videoDuration: "長さ",
    videoGenerate: "動画を生成",
    videoEnhance: "動的エンハンス",
    videoEnhanceStrength: "強度",
    videoNegPlaceholder: "空欄でワークフロー既定値",
    firstFrameRequired: "先頭フレーム画像をアップロードしてください",
    cost: "消費",
    hdMode: "HDエンハンス",
    hdModeHint: "10クォータ消費。アップスケール+精錬で高品質化。",
    workflowFlux2Edit: "Flux2 画像編集 (Klein 9B)",
    flux2Generate: "Flux2 編集",
    flux2PromptPlaceholder: "編集目標を記述...",
    flux2SourceImage: "元画像（必須）",
    flux2SourceDropHint: "クリックまたはドラッグで元画像をアップロード",
    flux2RefImage: "参照画像（任意）",
    flux2RefDropHint: "クリックまたはドラッグで参照画像をアップロード（任意）",
    flux2SourceRequired: "元画像を先にアップロードしてください",
  }
};

let currentLang = localStorage.getItem("lang") || "zh";

function t(key) {
  const lang = I18N[currentLang] || I18N.zh;
  return lang[key] ?? I18N.zh[key] ?? key;
}

function setLang(lang) {
  if (!I18N[lang]) return;
  currentLang = lang;
  localStorage.setItem("lang", lang);
  applyTranslations();
}

function applyTranslations() {
  document.documentElement.lang = currentLang;
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.dataset.i18n;
    const text = t(key);
    if (!text) return;
    if (el.tagName === "OPTION") {
      el.text = text;
    } else if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
      el.placeholder = text;
    } else if (el.children.length > 0) {
      for (const child of el.childNodes) {
        if (child.nodeType === 3 && child.textContent.trim()) {
          child.textContent = text;
          break;
        }
      }
    } else {
      el.textContent = text;
    }
  });
  document.querySelectorAll("[data-i18n-title]").forEach(el => {
    el.title = t(el.dataset.i18nTitle);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  updateLangagedUI();
}

function updateLangagedUI() {
  const advPanel = document.getElementById("adv-panel");
  const advOpen = advPanel && advPanel.style.display !== "none";
  const advBtn = document.getElementById("btn-adv-toggle");
  if (advBtn) advBtn.textContent = advOpen ? t("advToggleOpen") : t("advToggleClosed");

  const loraBtn = document.getElementById("btn-open-lora");
  if (loraBtn) loraBtn.textContent = t("loraManage");

  const wfEl = document.getElementById("sel-workflow");
  if (wfEl) {
    const isMulti = wfEl.value === "multidraw";
    const genBtn = document.getElementById("btn-generate");
    if (genBtn && !genBtn.disabled) {
      genBtn.textContent = isMulti ? t("multidrawGenerate") : t("generate");
    }
  }

  const quotaEl = document.getElementById("quota-display");
  if (quotaEl && quotaEl.dataset.raw) {
    quotaEl.textContent = t("quota") + ": " + quotaEl.dataset.raw;
  }

  const onlineEl = document.getElementById("online-display");
  if (onlineEl && onlineEl.dataset.raw) {
    onlineEl.textContent = t("online") + ": " + onlineEl.dataset.raw;
  }

  // Re-render the queue/task status text (queue position, estimated wait,
  // elapsed time) in the newly selected language.
  if (typeof g_activeTask !== "undefined" && g_activeTask &&
      (g_activeTask.status === "queued" || g_activeTask.status === "processing") &&
      typeof taskStatusText === "function" && typeof setStatus === "function") {
    setStatus(taskStatusText(g_activeTask), g_activeTask.status);
  }

  // Re-render task history items (queued/processing statuses etc.).
  if (typeof g_lastTasks !== "undefined" && g_lastTasks &&
      typeof renderTaskList === "function") {
    renderTaskList(g_lastTasks);
  }

}

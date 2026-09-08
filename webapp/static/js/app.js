const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
const RESOLUTIONS = { 1: [832, 1216], 2: [1024, 1024], 3: [1216, 832], 0: null };

function formatTime(seconds) {
  if (seconds == null || seconds <= 0) return "";
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (m > 0) return m + t("min") + s + t("sec");
  return s + t("sec");
}

// Build the multi-line status text for a queued/processing task,
// including real ComfyUI queue position, ETA and elapsed time.
function taskStatusText(task) {
  let statusText = t(task.status) + "... (" + task.task_id + ")";
  const pos = task.queue_position;
  const hasQueue = pos != null && task.queue_total != null;
  if (hasQueue && pos > 0) {
    // Waiting inside the ComfyUI queue
    statusText += "\n" + t("queuePosition") + ": " + (pos + 1) + "/" + task.queue_total;
    if (task.estimated_seconds != null && task.estimated_seconds > 0) {
      statusText += "  " + t("estimatedWait") + ": ~" + formatTime(task.estimated_seconds);
    }
  } else if (task.status === "processing" || (hasQueue && task.is_running)) {
    // Currently executing on ComfyUI
    if (task.elapsed_seconds != null && task.elapsed_seconds > 0) {
      statusText += "\n" + t("elapsed") + ": " + formatTime(task.elapsed_seconds);
    }
    if (task.estimated_seconds != null && task.estimated_seconds > 0) {
      statusText += "  " + t("estimatedRemaining") + ": ~" + formatTime(task.estimated_seconds);
    }
  }
  return statusText;
}

let currentRes = "1";
let advOpen = false;
const pollingTimers = {};
let g_authenticated = false;
let g_is_admin = false;

let g_videoFirstImage = null;
let g_videoLastImage = null;
let g_videoQuality = "480p";
let g_videoOrientation = "portrait";
let g_videoMode = "fl2va";
let g_videoRatio = "16:9";
let g_refImages = Array(6).fill(null);
let g_refVideos = Array(2).fill(null);
let g_refAudios = Array(3).fill(null);
let g_assetTab = "my";
let g_assetFolderId = "__root__";
let g_assetRootId = "__root__";
let g_assetRootName = "根目录";
let g_assetPrivateFolderId = "__root__";
let g_assetFolders = [];
let g_assetSelectionMode = false;
let g_assetSelection = new Map();
let g_isAdmin = false;
let g_hdMode = false;
let g_flux2SourceImage = null;
let g_flux2RefImage = null;
let g_flux2Mode = "edit";
let g_diffSourceImage = null;

// Last queued/processing task shown in the preview area, and the last
// fetched task list — both used to re-render texts on language switch.
let g_activeTask = null;
let g_lastTasks = null;

async function checkAuth() {
  const el = $("#header-user");
  if (!el) return;
  try {
    const resp = await fetch("/api/auth/me");
    const data = await resp.json();
    if (data.authenticated) {
      g_authenticated = true;
      g_is_admin = !!data.is_admin;
      const avatarHtml = data.avatar_url
        ? `<img src="${escAttr(data.avatar_url)}" alt="">`
        : "";
      el.innerHTML = `
        <span class="header-user">${avatarHtml}${escHtml(data.username)}</span>
        <a href="/api/auth/logout" class="btn-logout">${t("logout")}</a>`;
      return;
    }
    g_authenticated = false;
    el.innerHTML = `<a href="/api/auth/login" class="btn-login">${t("login")}</a>`;
  } catch (e) {
    console.error("Auth check failed:", e);
    g_authenticated = false;
    el.innerHTML = `<a href="/api/auth/login" class="btn-login">${t("login")}</a>`;
  }
}

async function loadSettings() {
  try {
    const s = await API.getSettings();
    $("#txt-negative").value = s.negative_prompt;
    $("#txt-artist-chain").value = s.artist_chain;
    g_hdMode = !!s.is_hd_mode;
    $("#chk-hd-mode").checked = g_hdMode;
    const match = Object.entries(RESOLUTIONS).find(([k, v]) => v && v[0] === s.resolution[0] && v[1] === s.resolution[1]);
    currentRes = match ? match[0] : "0";
    if (currentRes === "0") {
      $("#txt-custom-w").value = s.resolution[0];
      $("#txt-custom-h").value = s.resolution[1];
    }
    $$(".res-btn").forEach(b => b.classList.toggle("active", b.dataset.res === currentRes));
    toggleCustomRes();
    $("#txt-part1-w").value = s.part1[0];
    $("#txt-part1-h").value = s.part1[1];
    $("#txt-part1-x").value = s.part1[2];
    $("#txt-part1-y").value = s.part1[3];
    $("#txt-part2-w").value = s.part2[0];
    $("#txt-part2-h").value = s.part2[1];
    $("#txt-part2-x").value = s.part2[2];
    $("#txt-part2-y").value = s.part2[3];
  } catch (e) {
    console.error("Failed to load settings:", e);
  }
}

async function loadOnlineCount() {
  try {
    const resp = await fetch("/api/auth/online");
    if (!resp.ok) return;
    const data = await resp.json();
    const el = $("#online-display");
    el.textContent = t("online") + ": " + data.count;
    el.dataset.raw = data.count;
    el.style.display = "";
  } catch (e) {
    console.error("Failed to load online count:", e);
  }
}

async function loadQuota() {
  try {
    const q = await API.getQuota();
    const text = q.remaining + "/" + q.limit;
    const el = $("#quota-display");
    el.dataset.raw = text;
    el.textContent = t("quota") + ": " + text;
  } catch (e) {
    console.error("Failed to load quota:", e);
  }
}

async function loadLoraList() {
  try {
    const data = await API.getLoraList(currentWorkflow());
    renderLoraGallery(data);
  } catch (e) {
    console.error("Failed to load lora list:", e);
  }
}

function renderActiveLoras(active) { /* unused, kept for compat */ }

function escHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function escAttr(s) {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function currentWorkflow() {
  return $("#sel-workflow").value;
}

function getAdvancedParams() {
  const seed = parseInt($("#txt-seed").value);
  const sampler = $("#sel-sampler").value || null;
  const scheduler = $("#sel-scheduler").value || null;
  return {
    seed: seed >= 0 ? seed : null,
    sampler_name: sampler,
    scheduler: scheduler,
  };
}

function getGenerateButtonText() {
  const wf = currentWorkflow();
  if (wf === "multidraw") return t("multidrawGenerate");
  if (wf === "webui_video") return t("videoGenerate");
  if (wf === "discord_flux2_9b_edit") return t("flux2Generate");
  if (wf === "discord_差分") return t("diffGenerate");
  return t("generate");
}

function switchWorkflowUI() {
  const wf = currentWorkflow();
  const isMulti = wf === "multidraw";
  const isVideo = wf === "webui_video";
  const isFlux2 = wf === "discord_flux2_9b_edit";
  const isDiff = wf === "discord_差分";

  $("#fields-anima").style.display = (isMulti || isVideo || isFlux2) ? "none" : "";
  $("#fields-diff-image").style.display = isDiff ? "" : "none";
  $("#fields-multidraw").style.display = isMulti ? "" : "none";
  $("#fields-video").style.display = isVideo ? "" : "none";
  $("#fields-flux2").style.display = isFlux2 ? "" : "none";

  const resSection = document.getElementById("section-resolution");
  if (resSection) resSection.style.display = (isVideo || isFlux2 || isDiff) ? "none" : "";

  const negSection = document.getElementById("section-negative");
  if (negSection) negSection.style.display = (isVideo || isFlux2) ? "none" : "";

  document.querySelectorAll(".adv-image-only").forEach(el => {
    el.style.display = isVideo ? "none" : "";
  });
  document.querySelectorAll(".adv-video-only").forEach(el => {
    el.style.display = isVideo ? "" : "none";
  });
  document.querySelectorAll(".adv-ref-only").forEach(el => {
    el.style.display = isVideo && g_videoMode === "ref2va" ? "" : "none";
  });
  document.querySelectorAll(".adv-video-lora-only").forEach(el => {
    el.style.display = isVideo && g_videoMode !== "ref2va" ? "" : "none";
  });
  document.querySelectorAll(".adv-diff-only").forEach(el => {
    el.style.display = isDiff ? "" : "none";
  });

  if (isVideo) { updateVideoModeUI(); updateVideoCost(); }
  updateDrawCost();
  updateGenerateButton();
}

function updateGenerateButton() {
  const btn = $("#btn-generate");
  if (btn.disabled) return;
  btn.textContent = getGenerateButtonText();
}

// ---- Thumbnail helpers ----
function loraDisplayName(filename) {
  return filename.replace(/\.(safetensors|ckpt|pt|pth)$/i, "").replace(/[-_]/g, " ");
}
const PLACEHOLDER_SVG = "data:image/svg+xml," + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" fill="%2316213e"><rect width="200" height="200"/><text x="100" y="100" text-anchor="middle" dy=".35em" fill="%23444" font-size="32" font-family="sans-serif">N/A</text></svg>'
);

async function renderLoraGallery(data) {
  const container = $("#lora-gallery");
  try {
    if (!data) data = await API.getLoraList(currentWorkflow());
    const available = data.available;
    const active = data.active || {};
    const thumbUrls = data.thumb_urls || {};
    if (!available || Object.keys(available).length === 0) {
      container.innerHTML = `<span style="color:#666;font-size:12px">${t("loraNoFiles")}</span>`;
      return;
    }
    let html = "";
    for (const [cat, files] of Object.entries(available)) {
      if (!files || files.length === 0) continue;
      html += `<div class="lora-cat-header">${escHtml(cat)}</div><div class="lora-grid">`;
      for (const filename of files) {
        const isActive = filename in active;
        const weight = isActive ? active[filename] : parseFloat($("#txt-lora-defweight").value) || 0.8;
        const cls = isActive ? " active" : "";
        const thumbSrc = thumbUrls[filename] || PLACEHOLDER_SVG;
      html += `
          <div class="lora-card${cls}" data-filename="${escAttr(filename)}">
            <img src="${thumbSrc}" loading="lazy">
            <div class="lora-name" title="${escAttr(filename)}">${escHtml(loraDisplayName(filename))}</div>
            <div class="lora-row">
              <input type="checkbox" ${isActive ? "checked" : ""}>
              <input type="range" min="0" max="2" step="0.05" value="${weight}">
              <span class="lora-val">${weight.toFixed(2)}</span>
            </div>
          </div>`;
      }
      html += "</div>";
    }
    container.innerHTML = html;
    container.querySelectorAll(".lora-card").forEach(card => {
      const filename = card.dataset.filename;
      const img = card.querySelector("img");
      const cb = card.querySelector("input[type=checkbox]");
      const range = card.querySelector("input[type=range]");
      const valSpan = card.querySelector(".lora-val");

      img.addEventListener("error", () => {
        // Defensive only: the backend reports the real file, so a failure here
        // means it disappeared between scan and request.
        img.src = PLACEHOLDER_SVG;
        img.onerror = null;
      });

      function updateVal() { valSpan.textContent = parseFloat(range.value).toFixed(2); }
      range.addEventListener("input", updateVal);
      range.addEventListener("change", async () => {
        updateVal();
        const w = parseFloat(range.value);
        if (cb.checked) { await API.addLora(filename, w, currentWorkflow()); card.classList.add("active"); }
      });
      cb.addEventListener("change", async () => {
        const w = parseFloat(range.value);
        if (cb.checked) {
          await API.addLora(filename, w, currentWorkflow());
          card.classList.add("active");
        } else {
          await API.removeLora(filename);
          card.classList.remove("active");
        }
      });
    });
  } catch (e) {
    console.error("Failed to load lora gallery:", e);
    container.innerHTML = `<span style="color:#f87171;font-size:12px">${t("loraLoadFail")}</span>`;
  }
}

// ---- Events ----
function setupEvents() {
  $("#sel-workflow").addEventListener("change", () => {
    switchWorkflowUI();
  });

  function toggleCustomRes() {
    const show = currentRes === "0";
    $("#res-custom").style.display = show ? "flex" : "none";
  }

  function applyRes(w, h) {
    return API.setResolution(w, h);
  }

  $$(".res-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const res = btn.dataset.res;
      currentRes = res;
      $$(".res-btn").forEach(b => b.classList.toggle("active", b.dataset.res === res));
      toggleCustomRes();
      if (res !== "0") {
        const [w, h] = RESOLUTIONS[res];
        await applyRes(w, h);
      } else {
        const w = parseInt($("#txt-custom-w").value) || 832;
        const h = parseInt($("#txt-custom-h").value) || 1216;
        await applyRes(w, h);
      }
    });
  });

  for (const id of ["#txt-custom-w", "#txt-custom-h"]) {
    $(id).addEventListener("change", async () => {
      if (currentRes === "0") {
        let w = parseInt($("#txt-custom-w").value) || 832;
        let h = parseInt($("#txt-custom-h").value) || 1216;
        w = Math.min(1920, Math.max(64, w));
        h = Math.min(1920, Math.max(64, h));
        await applyRes(w, h);
      }
    });
  }

  $$(".btn-expand").forEach(btn => {
    btn.addEventListener("click", () => {
      const ta = $("#" + btn.dataset.target);
      if (ta) ta.classList.toggle("expanded");
    });
  });

  $("#txt-negative").addEventListener("blur", async () => {
    await API.setNegativePrompt($("#txt-negative").value);
  });

  $("#txt-artist-chain").addEventListener("blur", async () => {
    await API.setArtistChain($("#txt-artist-chain").value);
  });

  $("#chk-hd-mode").addEventListener("change", async () => {
    g_hdMode = $("#chk-hd-mode").checked;
    updateDrawCost();
    try { await API.setHdMode(g_hdMode); } catch {}
  });

  $("#btn-generate").addEventListener("click", generate);

  $("#btn-adv-toggle").addEventListener("click", () => {
    advOpen = !advOpen;
    $("#adv-panel").style.display = advOpen ? "block" : "none";
    updateLangagedUI();
  });

  const dsRange = document.getElementById("rng-diff-strength");
  const dsVal = document.getElementById("diff-strength-val");
  if (dsRange && dsVal) {
    dsRange.addEventListener("input", () => {
      dsVal.textContent = parseFloat(dsRange.value).toFixed(2);
    });
  }

  $("#btn-open-lora").addEventListener("click", () => {
    $("#lora-modal").style.display = "flex";
    loadLoraList();
  });
  $("#btn-open-video-lora").addEventListener("click", () => {
    $("#lora-modal").style.display = "flex";
    loadLoraList();
  });
  $("#btn-close-lora").addEventListener("click", () => {
    $("#lora-modal").style.display = "none";
  });
  $("#lora-modal").addEventListener("click", (e) => {
    if (e.target === $("#lora-modal")) $("#lora-modal").style.display = "none";
  });
  $("#btn-lora-reset").addEventListener("click", async () => {
    await API.resetLora();
    await loadLoraList();
  });
  $("#btn-lora-refresh").addEventListener("click", () => loadLoraList());

  const partSelectors = ["#txt-part1-w", "#txt-part1-h", "#txt-part1-x", "#txt-part1-y",
    "#txt-part2-w", "#txt-part2-h", "#txt-part2-x", "#txt-part2-y"];
  partSelectors.forEach(sel => $(sel).addEventListener("blur", saveMultidrawParts));

  $("#btn-refresh-history").addEventListener("click", refreshTaskList);

  $("#txt-prompt").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      generate();
    }
  });

  const vp = document.getElementById("txt-video-prompt");
  if (vp) {
    vp.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        generate();
      }
    });
  }

  setupVideoUpload("video-first-drop", "video-first-input", "video-first-preview", "video-first-placeholder", true);
  setupVideoUpload("video-last-drop", "video-last-input", "video-last-preview", "video-last-placeholder", false);
  const videoModeSel = document.getElementById("sel-video-mode");
  if (videoModeSel) {
    videoModeSel.addEventListener("change", () => {
      g_videoMode = videoModeSel.value;
      updateVideoModeUI();
    });
  }
  const videoRatioSel = document.getElementById("sel-video-ratio");
  if (videoRatioSel) {
    videoRatioSel.addEventListener("change", () => {
      g_videoRatio = videoRatioSel.value;
    });
  }
  for (let i = 0; i < 6; i++) setupRefSlot("image", i);
  for (let i = 0; i < 2; i++) setupRefSlot("video", i);
  for (let i = 0; i < 3; i++) setupRefSlot("audio", i);
  for (let i = 0; i < 6; i++) renderRefSlot("image", i);
  for (let i = 0; i < 2; i++) renderRefSlot("video", i);
  for (let i = 0; i < 3; i++) renderRefSlot("audio", i);
  setupFlux2Upload("flux2-source-drop", "flux2-source-input", "flux2-source-preview", "flux2-source-placeholder", true);
  setupFlux2Upload("flux2-ref-drop", "flux2-ref-input", "flux2-ref-preview", "flux2-ref-placeholder", false);
  setupDiffUpload("diff-source-drop", "diff-source-input", "diff-source-preview", "diff-source-placeholder");
  $$(".flux2-mode-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      $$(".flux2-mode-btn").forEach(b => b.classList.toggle("active", b === btn));
      g_flux2Mode = btn.dataset.mode;
      updateFlux2ModeUI();
    });
  });

  const fp = document.getElementById("txt-flux2-prompt");
  if (fp) {
    fp.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        generate();
      }
    });
  }

  $$(".quality-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      $$(".quality-btn").forEach(b => b.classList.toggle("active", b === btn));
      g_videoQuality = btn.dataset.quality;
      updateVideoCost();
    });
  });

  const durSel = document.getElementById("sel-video-duration");
  if (durSel) durSel.addEventListener("change", updateVideoCost);

  $("#btn-open-assets").addEventListener("click", showAssetModal);
  $("#btn-close-assets").addEventListener("click", () => $("#asset-modal").style.display = "none");
  $("#asset-modal").addEventListener("click", (e) => {
    if (e.target === $("#asset-modal")) $("#asset-modal").style.display = "none";
  });
  const assetFileInput = document.getElementById("asset-file");
  $("#btn-asset-upload").addEventListener("click", () => assetFileInput?.click());
  if (assetFileInput) assetFileInput.addEventListener("change", uploadAssetFromModal);
  $("#btn-asset-folder").addEventListener("click", createAssetFolderFromModal);
  $("#btn-asset-refresh").addEventListener("click", async () => {
    await loadAssetFolders();
    await refreshAssets();
  });
  $("#btn-asset-my").addEventListener("click", openMyAssetLibrary);
  $("#btn-asset-public").addEventListener("click", openPublicAssetLibrary);
  $("#btn-asset-multiselect").addEventListener("click", toggleAssetSelectionMode);
  $("#btn-asset-use").addEventListener("click", useSelectedAssets);
  $("#btn-asset-publish").addEventListener("click", publishSelectedAssets);
  $("#btn-asset-delete").addEventListener("click", deleteSelectedAssets);
  $("#btn-asset-save").addEventListener("click", saveSelectedPublicAssets);
  $("#btn-asset-clear").addEventListener("click", clearAssetSelection);
  $("#btn-asset-pub-upload").addEventListener("click", () => $("#asset-public-file").click());
  $("#btn-asset-pub-edit").addEventListener("click", editPublicAsset);
  $("#btn-asset-pub-remove").addEventListener("click", removePublicAssets);
  $("#asset-public-file").addEventListener("change", uploadPublicAssetsFromModal);
}

async function saveMultidrawParts() {
  const p1w = parseInt($("#txt-part1-w").value) || 832;
  const p1h = parseInt($("#txt-part1-h").value) || 608;
  const p1x = parseInt($("#txt-part1-x").value) || 0;
  const p1y = parseInt($("#txt-part1-y").value) || 0;
  const p2w = parseInt($("#txt-part2-w").value) || 832;
  const p2h = parseInt($("#txt-part2-h").value) || 608;
  const p2x = parseInt($("#txt-part2-x").value) || 832;
  const p2y = parseInt($("#txt-part2-y").value) || 0;
  await API.setPart1(p1w, p1h, p1x, p1y);
  await API.setPart2(p2w, p2h, p2x, p2y);
}

// ---- Video helpers ----
function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      resolve(result.substring(result.indexOf(",") + 1));
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function detectOrientation(w, h) {
  if (w > h * 1.1) return "landscape";
  if (h > w * 1.1) return "portrait";
  return "square";
}

function setupVideoUpload(zoneId, inputId, previewId, placeholderId, isFirst) {
  const zone = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  const preview = document.getElementById(previewId);
  const placeholder = document.getElementById(placeholderId);
  if (!zone) return;

  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    if (e.dataTransfer.files.length > 0) handleVideoImage(e.dataTransfer.files[0]);
  });
  input.addEventListener("change", () => {
    if (input.files.length > 0) handleVideoImage(input.files[0]);
  });

  async function handleVideoImage(file) {
    try {
      const b64 = await fileToBase64(file);
      if (isFirst) {
        g_videoFirstImage = b64;
        const img = new Image();
        img.onload = () => {
          g_videoOrientation = detectOrientation(img.naturalWidth, img.naturalHeight);
        };
        img.src = URL.createObjectURL(file);
      } else {
        g_videoLastImage = b64;
      }
      preview.src = URL.createObjectURL(file);
      preview.style.display = "block";
      placeholder.style.display = "none";
    } catch (e) {
      console.error("Image load failed:", e);
    }
  }
}

function setupFlux2Upload(zoneId, inputId, previewId, placeholderId, isSource) {
  const zone = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  const preview = document.getElementById(previewId);
  const placeholder = document.getElementById(placeholderId);
  if (!zone) return;

  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    if (e.dataTransfer.files.length > 0) handleFlux2Image(e.dataTransfer.files[0]);
  });
  input.addEventListener("change", () => {
    if (input.files.length > 0) handleFlux2Image(input.files[0]);
  });

  async function handleFlux2Image(file) {
    try {
      const b64 = await fileToBase64(file);
      if (isSource) {
        g_flux2SourceImage = b64;
      } else {
        g_flux2RefImage = b64;
      }
      preview.src = URL.createObjectURL(file);
      preview.style.display = "block";
      placeholder.style.display = "none";
    } catch (e) {
      console.error("Image load failed:", e);
    }
  }
}

function setupDiffUpload(zoneId, inputId, previewId, placeholderId) {
  const zone = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  const preview = document.getElementById(previewId);
  const placeholder = document.getElementById(placeholderId);
  if (!zone) return;

  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    if (e.dataTransfer.files.length > 0) handleDiffImage(e.dataTransfer.files[0]);
  });
  input.addEventListener("change", () => {
    if (input.files.length > 0) handleDiffImage(input.files[0]);
  });

  async function handleDiffImage(file) {
    try {
      const b64 = await fileToBase64(file);
      g_diffSourceImage = b64;
      preview.src = URL.createObjectURL(file);
      preview.style.display = "block";
      placeholder.style.display = "none";
    } catch (e) {
      console.error("Diff image load failed:", e);
    }
  }
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let value = bytes;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return value.toFixed(i ? 1 : 0) + " " + units[i];
}

function refArray(kind) {
  if (kind === "image") return g_refImages;
  if (kind === "video") return g_refVideos;
  return g_refAudios;
}

function renderRefSlot(kind, index) {
  const el = document.getElementById(`ref-${kind}-slot-${index}`);
  if (!el) return;
  const item = refArray(kind)[index];
  if (!item) {
    el.innerHTML = `<input type="file" accept="${kind === "image" ? "image/*" : kind === "video" ? "video/*" : "audio/*"}" hidden><span class="video-drop-text">${t(kind === "image" ? "refImageSlot" : kind === "video" ? "refVideoSlot" : "refAudioSlot")} ${index + 1}</span>`;
    return;
  }
  const preview = item.thumbnail_url
    ? `<img class="video-preview-img" src="${escAttr(item.thumbnail_url)}">`
    : `<span class="video-drop-text">${escHtml(item.title || item.name || t("refLoaded"))}</span>`;
  el.innerHTML = `<input type="file" accept="${kind === "image" ? "image/*" : kind === "video" ? "video/*" : "audio/*"}" hidden>${preview}<button class="ref-clear" data-ref-kind="${kind}" data-ref-index="${index}">×</button>`;
}

function setupRefSlot(kind, index) {
  const el = document.getElementById(`ref-${kind}-slot-${index}`);
  if (!el) return;
  el.addEventListener("click", (e) => {
    const clear = e.target.closest(".ref-clear");
    if (clear) {
      refArray(kind)[index] = null;
      renderRefSlot(kind, index);
      return;
    }
    const input = el.querySelector("input[type=file]");
    if (input) input.click();
  });
  el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("drag-over"); });
  el.addEventListener("dragleave", () => el.classList.remove("drag-over"));
  el.addEventListener("drop", async (e) => {
    e.preventDefault();
    el.classList.remove("drag-over");
    if (e.dataTransfer.files.length > 0) {
      await uploadRefFile(e.dataTransfer.files[0], kind, index);
    }
  });
  el.addEventListener("change", async (e) => {
    if (e.target.files.length > 0) await uploadRefFile(e.target.files[0], kind, index);
  });
}

async function uploadRefFile(file, kind, index) {
  try {
    const storeToLibrary = document.getElementById("chk-store-ref-assets")?.checked ?? true;
    const res = await API.uploadVideoReference(file, storeToLibrary);
    if (res.kind !== kind) {
      setStatus(t("refTypeMismatch") + ": " + res.kind, "failed");
      return;
    }
    refArray(kind)[index] = res.storage_mode === "asset"
      ? {
          asset_id: res.asset_id,
          title: file.name,
          thumbnail_url: res.thumbnail_url || (kind === "image" ? URL.createObjectURL(file) : null),
        }
      : {
          upload_id: res.id,
          title: file.name,
          thumbnail_url: kind === "image" ? URL.createObjectURL(file) : null,
        };
    renderRefSlot(kind, index);
  } catch (e) {
    setStatus(t("error") + ": " + e.message, "failed");
  }
}

function assignAssetToRef(asset) {
  if (asset.visibility && asset.visibility !== "private") {
    setStatus(t("assetSharedUseHint"), "failed");
    return;
  }
  const items = refArray(asset.kind);
  let index = items.findIndex(x => x == null);
  if (index < 0) {
    setStatus(t("refSlotsFull"), "failed");
    return;
  }
  items[index] = { asset_id: asset.id, title: asset.title, thumbnail_url: asset.thumbnail_url };
  renderRefSlot(asset.kind, index);
  if (asset.kind !== "image") $("#asset-modal").style.display = "none";
}

async function showAssetModal() {
  $("#asset-modal").style.display = "flex";
  updateAssetViewMode();
  await loadAssetQuota();
  await loadAssetFolders();
  await refreshAssets();
}

async function loadAssetFolders() {
  try {
    g_assetFolders = await API.listAssetFolders();
  } catch (e) {
    console.error("Asset folders failed:", e);
    g_assetFolders = [];
  }
  const rootFolder = g_assetFolders.find(folder => folder.is_root);
  if (rootFolder) {
    g_assetRootId = rootFolder.id;
    g_assetRootName = rootFolder.name;
  }
  renderAssetTree();
  renderBreadcrumb();
}

function folderChildren(parentId) {
  const normalized = parentId === "__root__" ? null : parentId;
  return g_assetFolders.filter(f => !f.is_root && (f.parent_id || null) === normalized);
}

function folderPath() {
  if (g_assetFolderId === "__root__") {
    return [{ id: "__root__", name: g_assetRootName }];
  }
  const byId = new Map(g_assetFolders.map(f => [f.id, f]));
  const path = [];
  let currentId = g_assetFolderId;
  while (currentId && byId.has(currentId) && path.length < 32) {
    const folder = byId.get(currentId);
    path.unshift({ id: folder.id, name: folder.name });
    currentId = folder.parent_id || "__root__";
  }
  return [{ id: "__root__", name: g_assetRootName }, ...path];
}

function renderBreadcrumb() {
  const el = document.getElementById("asset-breadcrumb");
  if (!el) return;
  el.innerHTML = folderPath()
    .map(item => `<span class="asset-crumb" data-folder-id="${escAttr(item.id)}">${escHtml(item.name)}</span>`)
    .join('<span class="asset-crumb-sep">›</span>');
  el.querySelectorAll(".asset-crumb").forEach(crumb => {
    crumb.addEventListener("click", () => openAssetFolder(crumb.dataset.folderId));
  });
}

function renderAssetTree() {
  const el = document.getElementById("asset-tree");
  if (!el) return;
  const rootClass = g_assetFolderId === "__root__" ? " active" : "";
  let html = `<div class="asset-tree-item${rootClass}" data-folder-id="__root__"><span>📁</span>${escHtml(g_assetRootName)}</div>`;
  const renderLevel = (parentId, depth) => {
    for (const folder of folderChildren(parentId)) {
      const active = folder.id === g_assetFolderId ? " active" : "";
      html += `<div class="asset-tree-item${active}" data-folder-id="${escAttr(folder.id)}" style="padding-left:${12 + depth * 16}px"><span>📁</span>${escHtml(folder.name)}</div>`;
      renderLevel(folder.id, depth + 1);
    }
  };
  renderLevel("__root__", 0);
  el.innerHTML = html;
  el.querySelectorAll(".asset-tree-item").forEach(item => {
    item.addEventListener("click", () => openAssetFolder(item.dataset.folderId));
  });
}

function openAssetFolder(folderId) {
  g_assetTab = "my";
  g_assetFolderId = folderId || "__root__";
  g_assetPrivateFolderId = g_assetFolderId;
  g_assetSelection.clear();
  updateAssetToolbar();
  renderAssetTree();
  renderBreadcrumb();
  refreshAssets();
}

async function loadAssetQuota() {
  try {
    const q = await API.getAssetQuota();
    g_isAdmin = !!(q && q.is_admin);
    const el = document.getElementById("asset-quota-display");
    const fileInput = document.getElementById("asset-file");
    const uploadBtn = document.getElementById("btn-asset-upload");
    if (!q.asset_enabled) {
      el.textContent = t("assetDisabled") + " (" + t("quota") + ": " + q.limit + ")";
      if (fileInput) fileInput.disabled = true;
      if (uploadBtn) uploadBtn.disabled = true;
      updateAssetViewMode();
      return;
    }
    el.textContent = t("assetStorage") + ": " + formatBytes(q.asset_used_bytes) + " / " + formatBytes(q.asset_limit_bytes);
    if (fileInput) fileInput.disabled = false;
    if (uploadBtn) uploadBtn.disabled = false;
    updateAssetViewMode();
  } catch (e) {
    console.error("Asset quota failed:", e);
  }
}

async function refreshAssets() {
  const grid = document.getElementById("asset-grid");
  try {
    updateAssetViewMode();
    const isPublic = g_assetTab === "public";
    const folderId = g_assetFolderId === "__root__" ? "__root__" : g_assetFolderId;
    const params = { shared: isPublic };
    if (!isPublic) params.folder_id = folderId;
    const data = await API.listAssets(params);
    const folders = isPublic ? [] : folderChildren(g_assetFolderId);
    let html = "";
    html += folders.map(folder => `
      <div class="asset-folder-card${g_assetSelection.has(folder.id) ? " selected" : ""}" data-folder-id="${escAttr(folder.id)}" data-folder-name="${escAttr(folder.name)}" title="${t("assetFolderContextHint")}">
        <div class="asset-folder-icon">📁</div>
        <div class="asset-file-name">${escHtml(folder.name)}</div>
        <div class="asset-file-meta">${folder.asset_count || 0} ${t("assetItems")}</div>
      </div>
    `).join("");
    html += (data.items || []).map(asset => `
      <div class="asset-card${g_assetSelection.has(asset.id) ? " selected" : ""}" data-asset-id="${escAttr(asset.id)}" data-asset-kind="${escAttr(asset.kind)}" data-asset-title="${escAttr(asset.title)}" data-asset-thumb="${escAttr(asset.thumbnail_url || "")}" data-asset-visibility="${escAttr(asset.visibility || "")}">
        ${asset.thumbnail_url ? `<img src="${escAttr(asset.thumbnail_url)}" loading="lazy">` : `<div class="asset-no-thumb">${escHtml(asset.kind.toUpperCase())}</div>`}
        <div class="asset-file-name" title="${escAttr(asset.title)}">${escHtml(asset.title)}</div>
        <div class="asset-file-meta">${escHtml(asset.kind)} · ${formatBytes(asset.size_bytes)}</div>
        ${isPublic ? `
        <div class="asset-public-foot">
          <span class="asset-uploader" title="${t("assetUploader")}">${escHtml(asset.publisher_name || ("用户 " + String(asset.publisher_id || "?").slice(0, 6)))}</span>
          <button class="asset-like-btn${asset.liked_by_me ? " liked" : ""}" data-like-id="${escAttr(asset.id)}" title="${t("assetLike")}">${asset.liked_by_me ? "❤️" : "🤍"} <span class="asset-like-count">${asset.like_count || 0}</span></button>
        </div>` : ""}
      </div>
    `).join("");
    if (!html) {
      grid.innerHTML = `<span class="hint">${t("assetEmpty")}</span>`;
      return;
    }
    grid.innerHTML = html;
    const assetById = new Map((data.items || []).map(asset => [asset.id, asset]));
    grid.querySelectorAll(".asset-folder-card").forEach(card => {
      card.addEventListener("click", () => {
        if (g_assetSelectionMode) {
          toggleAssetSelection({
            type: "folder",
            id: card.dataset.folderId,
            name: card.dataset.folderName,
          });
          return;
        }
        openAssetFolder(card.dataset.folderId);
      });
      card.addEventListener("contextmenu", async (e) => {
        e.preventDefault();
        if (g_assetSelectionMode) return;
        await deleteFolderDirectly({
          id: card.dataset.folderId,
          name: card.dataset.folderName,
        });
      });
    });
    grid.querySelectorAll(".asset-card").forEach(card => {
      const asset = assetById.get(card.dataset.assetId);
      card.addEventListener("click", () => {
        if (g_assetSelectionMode) {
          toggleAssetSelection({ type: "asset", ...asset });
          return;
        }
        g_assetSelection.clear();
        g_assetSelection.set(asset.id, { type: "asset", ...asset });
        applyAssetSelectionClasses();
        updateAssetToolbar();
      });
    });
    grid.querySelectorAll(".asset-like-btn").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        e.preventDefault();
        const id = btn.dataset.likeId;
        const asset = assetById.get(id);
        const liked = !(asset && asset.liked_by_me);
        try {
          const res = await API.likePublicAsset(id, liked);
          if (asset) {
            asset.liked_by_me = res.liked;
            asset.like_count = res.like_count;
          }
          btn.classList.toggle("liked", res.liked);
          btn.innerHTML = `${res.liked ? "❤️" : "🤍"} <span class="asset-like-count">${res.like_count}</span>`;
          btn.classList.remove("pop");
          void btn.offsetWidth;
          btn.classList.add("pop");
        } catch (err) {
          setStatus(t("error") + ": " + err.message, "failed");
        }
      });
    });
    updateAssetToolbar();
  } catch (e) {
    grid.innerHTML = `<span class="hint" style="color:var(--red)">${t("error")}: ${escHtml(e.message)}</span>`;
  }
}

function applyAssetSelectionClasses() {
  document.querySelectorAll(".asset-card").forEach(card => {
    card.classList.toggle("selected", g_assetSelection.has(card.dataset.assetId));
  });
  document.querySelectorAll(".asset-folder-card").forEach(card => {
    card.classList.toggle("selected", g_assetSelection.has(card.dataset.folderId));
  });
}

function toggleAssetSelection(item) {
  if (!item || !item.id) return;
  if (g_assetSelection.has(item.id)) {
    g_assetSelection.delete(item.id);
  } else {
    g_assetSelection.set(item.id, item);
  }
  applyAssetSelectionClasses();
  updateAssetToolbar();
}

function clearAssetSelection() {
  g_assetSelection.clear();
  applyAssetSelectionClasses();
  updateAssetToolbar();
}

async function autoRefreshAssets() {
  await loadAssetFolders();
  await refreshAssets();
}

function updateAssetToolbar() {
  const useBtn = document.getElementById("btn-asset-use");
  const deleteBtn = document.getElementById("btn-asset-delete");
  const publishBtn = document.getElementById("btn-asset-publish");
  const saveBtn = document.getElementById("btn-asset-save");
  const clearBtn = document.getElementById("btn-asset-clear");
  const count = g_assetSelection.size;
  const hasAsset = [...g_assetSelection.values()].some(item => item.type === "asset");
  const hasFolder = [...g_assetSelection.values()].some(item => item.type === "folder");
  const publicMode = g_assetTab === "public";
  if (useBtn) {
    useBtn.disabled = publicMode || !hasAsset || hasFolder;
    useBtn.textContent = count > 1 ? `${t("assetUse")} (${count})` : t("assetUse");
  }
  if (deleteBtn) {
    deleteBtn.disabled = publicMode || count === 0;
    deleteBtn.textContent = count > 1 ? `${t("assetDelete")} (${count})` : t("assetDelete");
  }
  if (publishBtn) {
    publishBtn.disabled = publicMode || !hasAsset || hasFolder;
    const selectedAssets = [...g_assetSelection.values()].filter(item => item.type === "asset");
    const allPublished = selectedAssets.length > 0 && selectedAssets.every(item => item.published_id);
    publishBtn.textContent = allPublished ? t("assetUnpublish") : t("assetPublish");
  }
  if (saveBtn) {
    saveBtn.disabled = !publicMode || count === 0 || hasFolder;
    saveBtn.textContent = count > 1 ? `${t("assetSave")} (${count})` : t("assetSave");
  }
  const pubEditBtn = document.getElementById("btn-asset-pub-edit");
  const pubRemoveBtn = document.getElementById("btn-asset-pub-remove");
  if (pubEditBtn) {
    pubEditBtn.disabled = !publicMode || count !== 1 || !hasAsset || hasFolder;
  }
  if (pubRemoveBtn) {
    pubRemoveBtn.disabled = !publicMode || !hasAsset || hasFolder;
  }
  if (clearBtn) clearBtn.style.display = count ? "" : "none";
}

function updateAssetViewMode() {
  const isPublic = g_assetTab === "public";
  const myTab = document.getElementById("btn-asset-my");
  const pubTab = document.getElementById("btn-asset-public");
  if (myTab) myTab.classList.toggle("active", !isPublic);
  if (pubTab) pubTab.classList.toggle("active", isPublic);
  const treePanel = document.querySelector(".asset-tree-panel");
  if (treePanel) treePanel.style.display = isPublic ? "none" : "";
  const breadcrumb = document.getElementById("asset-breadcrumb");
  if (breadcrumb) breadcrumb.style.display = isPublic ? "none" : "";
  const uploadBtn = document.getElementById("btn-asset-upload");
  const folderBtn = document.getElementById("btn-asset-folder");
  const multiBtn = document.getElementById("btn-asset-multiselect");
  const useBtn = document.getElementById("btn-asset-use");
  const publishBtn = document.getElementById("btn-asset-publish");
  const deleteBtn = document.getElementById("btn-asset-delete");
  const saveBtn = document.getElementById("btn-asset-save");
  if (uploadBtn) uploadBtn.style.display = isPublic ? "none" : "";
  if (folderBtn) folderBtn.style.display = isPublic ? "none" : "";
  if (multiBtn) multiBtn.style.display = isPublic ? "none" : "";
  if (useBtn) useBtn.style.display = isPublic ? "none" : "";
  if (publishBtn) publishBtn.style.display = isPublic ? "none" : "";
  if (deleteBtn) deleteBtn.style.display = isPublic ? "none" : "";
  if (saveBtn) saveBtn.style.display = isPublic ? "" : "none";
  const adminPublic = isPublic && g_isAdmin;
  const pubUploadBtn = document.getElementById("btn-asset-pub-upload");
  const pubEditBtn = document.getElementById("btn-asset-pub-edit");
  const pubRemoveBtn = document.getElementById("btn-asset-pub-remove");
  if (pubUploadBtn) pubUploadBtn.style.display = adminPublic ? "" : "none";
  if (pubEditBtn) pubEditBtn.style.display = adminPublic ? "" : "none";
  if (pubRemoveBtn) pubRemoveBtn.style.display = adminPublic ? "" : "none";
  updateAssetToolbar();
}

function toggleAssetSelectionMode() {
  g_assetSelectionMode = !g_assetSelectionMode;
  const btn = document.getElementById("btn-asset-multiselect");
  if (btn) btn.classList.toggle("active", g_assetSelectionMode);
  if (!g_assetSelectionMode) clearAssetSelection();
}

async function useSelectedAssets() {
  if (g_assetTab === "public") return;
  const assets = [...g_assetSelection.values()].filter(item => item.type === "asset");
  for (const asset of assets) {
    assignAssetToRef(asset);
  }
}

async function deleteSelectedAssets() {
  if (g_assetTab === "public") return;
  const items = [...g_assetSelection.values()];
  if (!items.length) return;
  if (!confirm(t("assetDeleteConfirm"))) return;
  try {
    for (const item of items) {
      if (item.type === "asset") {
        await API.deleteAsset(item.id);
        continue;
      }
      await deleteFolderDirectly(item, true);
    }
    clearAssetSelection();
    await autoRefreshAssets();
    await loadAssetQuota();
  } catch (e) {
    setStatus(t("error") + ": " + e.message, "failed");
  }
}

async function deleteFolderDirectly(folder, alreadyConfirmed = false) {
  if (!alreadyConfirmed && !confirm(t("assetDeleteConfirm"))) return;
  try {
    const stats = await API.getAssetFolderStats(folder.id);
    if (stats && stats.total_items > 0) {
      const message = `${t("assetFolderDeleteConfirm")} （${stats.total_items} ${t("assetItems")}）`;
      if (!confirm(message)) return;
    }
    await API.deleteAssetFolder(folder.id, true);
    await autoRefreshAssets();
    await loadAssetQuota();
  } catch (e) {
    setStatus(t("error") + ": " + e.message, "failed");
  }
}

function currentPrivateFolderId() {
  return g_assetPrivateFolderId === "__root__" ? g_assetRootId : g_assetPrivateFolderId;
}

async function publishSelectedAssets() {
  if (g_assetTab === "public") return;
  const assets = [...g_assetSelection.values()].filter(item => item.type === "asset");
  if (!assets.length) return;
  let syncFailed = false;
  try {
    for (const asset of assets) {
      if (asset.published_id) {
        const res = await API.unpublishAsset(asset.id);
        if (res && res.discord_message_deleted === false) syncFailed = true;
      } else {
        const res = await API.publishAsset(asset.id);
        if (res && res.discord_posted === false) syncFailed = true;
      }
    }
    clearAssetSelection();
    await autoRefreshAssets();
    await loadAssetQuota();
    if (syncFailed) {
      setStatus(t("assetDiscordSyncFailed"), "failed");
    }
  } catch (e) {
    setStatus(t("error") + ": " + e.message, "failed");
  }
}

async function saveSelectedPublicAssets() {
  if (g_assetTab !== "public") return;
  const assets = [...g_assetSelection.values()].filter(item => item.type === "asset");
  if (!assets.length) return;
  try {
    const folderId = currentPrivateFolderId();
    for (const asset of assets) {
      await API.savePublicAsset(asset.id, folderId);
    }
    setStatus(`${t("assetSaved")} ${assets.length}/${assets.length}`, "completed");
    clearAssetSelection();
    await autoRefreshAssets();
  } catch (e) {
    setStatus(t("error") + ": " + e.message, "failed");
  }
}

async function uploadPublicAssetsFromModal() {
  if (g_assetTab !== "public") return;
  const input = document.getElementById("asset-public-file");
  if (!input.files.length) return;
  const files = Array.from(input.files);
  let ok = 0, failed = 0;
  try {
    for (const file of files) {
      try {
        await API.uploadPublicAsset(file);
        ok++;
      } catch (e) {
        failed++;
        setStatus(t("uploadFailed") + ": " + file.name + " - " + e.message, "failed");
      }
    }
    if (ok) {
      setStatus(`${t("assetPublicUploaded")} ${ok}/${files.length}`, failed ? "failed" : "completed");
    }
  } finally {
    input.value = "";
    await autoRefreshAssets();
  }
}

async function editPublicAsset() {
  if (g_assetTab !== "public") return;
  const items = [...g_assetSelection.values()].filter(item => item.type === "asset");
  if (items.length !== 1) return;
  const asset = items[0];
  const title = prompt(t("assetPublicEditTitle"), asset.title || "");
  if (title === null) return;
  const description = prompt(t("assetPublicEditDesc"), asset.description || "");
  if (description === null) return;
  const tagsRaw = prompt(t("assetPublicEditTags"), (asset.tags || []).join(", "));
  if (tagsRaw === null) return;
  try {
    await API.updatePublicAsset(asset.id, {
      title: title.trim(),
      description: description,
      tags: tagsRaw.split(/[,，]/).map(s => s.trim()).filter(Boolean),
    });
    clearAssetSelection();
    await autoRefreshAssets();
  } catch (e) {
    setStatus(t("error") + ": " + e.message, "failed");
  }
}

async function removePublicAssets() {
  if (g_assetTab !== "public") return;
  const items = [...g_assetSelection.values()].filter(item => item.type === "asset");
  if (!items.length) return;
  if (!confirm(`${t("assetPublicRemoveConfirm")}（${items.length}）`)) return;
  let failed = 0;
  for (const asset of items) {
    try {
      await API.deletePublicAsset(asset.id);
    } catch (e) {
      failed++;
      setStatus(t("error") + ": " + e.message, "failed");
    }
  }
  clearAssetSelection();
  await autoRefreshAssets();
}

async function uploadAssetFromModal() {
  const input = document.getElementById("asset-file");
  if (!input.files.length) {
    setStatus(t("assetChooseFile"), "failed");
    return;
  }
  const files = Array.from(input.files);
  const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
  const folderId = g_assetFolderId === "__root__" ? g_assetRootId : g_assetFolderId;
  let doneBytes = 0;
  let failed = 0;
  const progressWrap = document.getElementById("asset-upload-progress");
  const progressBar = document.getElementById("asset-upload-bar");
  const progressText = document.getElementById("asset-upload-status");
  const uploadBtn = document.getElementById("btn-asset-upload");
  progressWrap.style.display = "block";
  uploadBtn.disabled = true;
  const startedAt = Date.now();
  for (const file of files) {
    try {
      await uploadOneAssetWithProgress(file, folderId, doneBytes, totalBytes, startedAt, progressBar, progressText);
    } catch (e) {
      failed++;
      progressText.textContent = `${t("uploadFailed")}: ${file.name}`;
    }
    doneBytes += file.size;
  }
  progressBar.style.width = "100%";
  progressText.textContent = failed
    ? `${t("uploadDone")} ${files.length - failed}/${files.length}`
    : `${t("uploadDone")} ${files.length}/${files.length}`;
  progressWrap.style.display = "none";
  uploadBtn.disabled = false;
  input.value = "";
  if (failed) {
    setStatus(`${t("uploadFailed")} ${failed}/${files.length}`, "failed");
  }
  await autoRefreshAssets();
  await loadAssetQuota();
}

function uploadOneAssetWithProgress(file, folderId, baseBytes, totalBytes, startedAt, bar, text) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/assets");
    const form = new FormData();
    form.append("file", file);
    if (folderId) form.append("folder_id", folderId);
    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) return;
      const loaded = baseBytes + e.loaded;
      const percent = totalBytes ? Math.min(100, (loaded / totalBytes) * 100) : 0;
      bar.style.width = percent.toFixed(1) + "%";
      const elapsed = Math.max(0.1, (Date.now() - startedAt) / 1000);
      const speed = loaded / elapsed;
      const remainingSeconds = speed > 0 ? Math.ceil((totalBytes - loaded) / speed) : 0;
      text.textContent = remainingSeconds > 0
        ? `${t("uploading")} ${filesLabel(baseBytes, totalBytes)} · ${t("uploadRemaining")} ~${remainingSeconds}${t("sec")}`
        : `${t("uploading")} ${filesLabel(baseBytes, totalBytes)}`;
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        let message = `HTTP ${xhr.status}`;
        try {
          const parsed = JSON.parse(xhr.responseText);
          message = parsed.detail || message;
        } catch (parseError) { /* keep default */ }
        reject(new Error(message));
      }
    };
    xhr.onerror = () => reject(new Error("Network error"));
    xhr.onabort = () => reject(new Error("Upload aborted"));
    xhr.send(form);
  });
}

function filesLabel(baseBytes, totalBytes) {
  return `${formatBytes(baseBytes)} / ${formatBytes(totalBytes)}`;
}

async function createAssetFolderFromModal() {
  const name = prompt(t("assetFolderName"));
  if (!name || !name.trim()) return;
  try {
    await API.createAssetFolder(name.trim(), g_assetFolderId === "__root__" ? null : g_assetFolderId);
    await autoRefreshAssets();
  } catch (e) {
    setStatus(t("error") + ": " + e.message, "failed");
  }
}

async function openMyAssetLibrary() {
  g_assetTab = "my";
  g_assetPrivateFolderId = g_assetFolderId;
  g_assetSelection.clear();
  updateAssetViewMode();
  await loadAssetQuota();
  await loadAssetFolders();
  await refreshAssets();
}

async function openPublicAssetLibrary() {
  g_assetTab = "public";
  g_assetSelection.clear();
  updateAssetViewMode();
  await loadAssetFolders();
  await refreshAssets();
}

function updateFlux2ModeUI() {
  const direct = g_flux2Mode === "cutout";
  const promptSection = document.getElementById("flux2-prompt-section");
  const refSection = document.getElementById("flux2-ref-section");
  const negSection = document.getElementById("flux2-negative-section");
  ["flux2-prompt-section", "flux2-ref-section", "flux2-negative-section"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = direct ? "none" : "";
  });
  const promptArea = document.getElementById("txt-flux2-prompt");
  const negArea = document.getElementById("txt-flux2-negative");
  if (promptArea) promptArea.disabled = direct;
  if (negArea) negArea.disabled = direct;
  updateDrawCost();
}

function updateVideoCost() {
  const quality = g_videoQuality;
  const duration = parseInt(document.getElementById("sel-video-duration")?.value || "5");
  let rate = quality === "480p" ? 50 : 200;
  if (duration > 10) rate *= 2;
  let cost = rate * duration;
  if (g_videoMode === "ref2va") cost = Math.ceil(cost * 1.5);
  const el = document.getElementById("video-cost-display");
  if (el) el.textContent = t("cost") + ": " + cost;
}

function updateVideoModeUI() {
  const isRef = g_videoMode === "ref2va";
  $("#video-fl2va-fields").style.display = isRef ? "none" : "";
  $("#video-ref2va-fields").style.display = isRef ? "" : "none";
  document.querySelectorAll(".adv-ref-only").forEach(el => {
    el.style.display = isRef ? "" : "none";
  });
  document.querySelectorAll(".adv-video-lora-only").forEach(el => {
    el.style.display = isRef ? "none" : "";
  });
  updateVideoCost();
}

function updateDrawCost() {
  const el = document.getElementById("draw-cost-display");
  if (!el) return;
  const wf = currentWorkflow();
  if (wf === "webui_video") { el.textContent = ""; return; }
  if (wf === "discord_flux2_9b_edit") {
    const cost = g_flux2Mode === "cutout" ? 1 : 20;
    el.textContent = t("cost") + ": " + cost;
    return;
  }
  const cost = (wf === "multidraw") ? 10 : (g_hdMode ? 10 : 1);
  el.textContent = t("cost") + ": " + cost;
}

// ---- Generate ----
async function generate() {
  if (!g_authenticated) {
    setStatus(t("loginRequired"), "failed");
    return;
  }

  const wf = currentWorkflow();
  const isMulti = wf === "multidraw";
  const isVideo = wf === "webui_video";
  const isFlux2 = wf === "discord_flux2_9b_edit";

  if (!isVideo && !isFlux2) {
    try {
      await API.setNegativePrompt($("#txt-negative").value);
      if (!isMulti) await API.setArtistChain($("#txt-artist-chain").value);
      if (isMulti) await saveMultidrawParts();
    } catch {}
  }

  const btn = $("#btn-generate");
  btn.disabled = true;
  btn.textContent = t("submitting");

  try {
    let result;
    const adv = getAdvancedParams();

    if (isVideo) {
      const prompt = $("#txt-video-prompt").value.trim();
      if (!prompt) {
        setStatus(t("promptRequired"));
        btn.disabled = false;
        btn.textContent = t("videoGenerate");
        return;
      }
      if (g_videoMode === "ref2va") {
        const hasRef = g_refImages.some(Boolean) || g_refVideos.some(Boolean) || g_refAudios.some(Boolean);
        if (!hasRef) {
          setStatus(t("refRequired"), "failed");
          btn.disabled = false;
          btn.textContent = t("videoGenerate");
          return;
        }
        adv.video_mode = "ref2va";
        adv.reference_image_uploads = g_refImages.map(x => x && x.upload_id).filter(Boolean);
        adv.reference_video_uploads = g_refVideos.map(x => x && x.upload_id).filter(Boolean);
        adv.reference_audio_uploads = g_refAudios.map(x => x && x.upload_id).filter(Boolean);
        adv.reference_image_asset_ids = g_refImages.map(x => x && x.asset_id).filter(Boolean);
        adv.reference_video_asset_ids = g_refVideos.map(x => x && x.asset_id).filter(Boolean);
        adv.reference_audio_asset_ids = g_refAudios.map(x => x && x.asset_id).filter(Boolean);
        adv.output_last_frame = $("#chk-output-last-frame").checked;
        adv.aspect_ratio = g_videoRatio;
      } else if (!g_videoFirstImage) {
        setStatus(t("firstFrameRequired"), "failed");
        btn.disabled = false;
        btn.textContent = t("videoGenerate");
        return;
      }
      const duration = parseInt($("#sel-video-duration").value);
      result = await API.videoAsync(
        prompt, g_videoMode === "ref2va" ? null : g_videoFirstImage,
        g_videoMode === "ref2va" ? null : g_videoLastImage,
        g_videoQuality, duration, g_videoOrientation, adv
      );
    } else if (isFlux2) {
      const prompt = $("#txt-flux2-prompt").value.trim();
      if (g_flux2Mode !== "cutout" && !prompt) {
        setStatus(t("promptRequired"));
        btn.disabled = false;
        btn.textContent = t("flux2Generate");
        return;
      }
      if (!g_flux2SourceImage) {
        setStatus(t("flux2SourceRequired"), "failed");
        btn.disabled = false;
        btn.textContent = t("flux2Generate");
        return;
      }
      const flux2Neg = $("#txt-flux2-negative").value.trim() || null;
      result = await API.flux2EditAsync(
        prompt, g_flux2SourceImage, g_flux2RefImage, flux2Neg, adv, g_flux2Mode
      );
    } else if (isMulti) {
      const g = $("#txt-md-global").value.trim();
      const p1 = $("#txt-md-p1").value.trim();
      const p2 = $("#txt-md-p2").value.trim();
      if (!g || !p1 || !p2) {
        alert(t("allPromptsRequired"));
        btn.disabled = false;
        btn.textContent = t("multidrawGenerate");
        return;
      }
      result = await API.multidrawAsync(p1, p2, g, adv);
    } else {
      const prompt = $("#txt-prompt").value.trim();
      if (!prompt) {
        setStatus(t("promptRequired"));
        btn.disabled = false;
        btn.textContent = getGenerateButtonText();
        return;
      }
      if (g_hdMode) adv.hd_mode = true;
      if (wf === "discord_差分") {
        if (!g_diffSourceImage) {
          setStatus(t("diffSourceRequired"), "failed");
          btn.disabled = false;
          btn.textContent = t("diffGenerate");
          return;
        }
        const denoise = parseFloat($("#rng-diff-strength").value);
        if (!Number.isNaN(denoise)) adv.denoise = denoise;
        result = await API.diffDrawAsync(prompt, g_diffSourceImage, adv);
      } else {
        result = await API.drawAsync(prompt, adv);
      }
    }

    btn.textContent = t("generating");
    // The submit response already carries queue info — show it immediately
    // instead of a plain "task submitted" message.
    g_activeTask = result;
    setStatus(taskStatusText(result), result.status === "queued" ? "queued" : "processing");
    startPolling(result.task_id, isMulti);
  } catch (e) {
    btn.disabled = false;
    btn.textContent = getGenerateButtonText();
    if (e.status === 429) {
      setStatus(t("quotaExhausted"), "failed");
    } else {
      setStatus(t("error") + ": " + e.message, "failed");
    }
  }
}

function startPolling(taskId, isMulti) {
  if (pollingTimers[taskId]) clearInterval(pollingTimers[taskId]);
  pollingTimers[taskId] = setInterval(async () => {
    try {
      const task = await API.getTask(taskId);
      refreshSingleTaskItem(taskId, task);
      if (task.status === "completed" && task.has_image) {
        clearInterval(pollingTimers[taskId]);
        delete pollingTimers[taskId];
        g_activeTask = null;
        let downloadError = null;
        if (task.output_type === "video") {
          try {
            const blob = await API.getTaskVideo(taskId);
            showVideo(URL.createObjectURL(blob));
          } catch (e) {
            downloadError = e;
            console.error("Video download failed:", e);
          }
          if (task.has_last_frame) {
            try {
              const frameBlob = await API.getTaskLastFrame(taskId);
              showLastFrame(URL.createObjectURL(frameBlob));
            } catch (e) {
              console.error("Last frame download failed:", e);
            }
          }
        } else {
          try {
            const blob = await API.getTaskImage(taskId);
            showImage(URL.createObjectURL(blob));
          } catch (e) {
            downloadError = e;
            console.error("Image download failed:", e);
          }
        }
        $("#btn-generate").disabled = false;
        $("#btn-generate").textContent = getGenerateButtonText();
        setStatus(
          downloadError ? `${t("completed")} - ${downloadError.message || t("error")}` : t("completed"),
          downloadError ? "failed" : "completed"
        );
        await loadQuota();
        addTaskToHistory(task);
      } else if (task.status === "failed") {
        clearInterval(pollingTimers[taskId]);
        delete pollingTimers[taskId];
        g_activeTask = null;
        $("#btn-generate").disabled = false;
        $("#btn-generate").textContent = getGenerateButtonText();
        setStatus(t("failed") + ": " + (task.error || ""), "failed");
        await loadQuota();
      } else {
        g_activeTask = task;
        setStatus(taskStatusText(task), task.status);
      }
    } catch (e) {
      console.error("Poll error:", e);
      if (e.status === 404) {
        clearInterval(pollingTimers[taskId]);
        delete pollingTimers[taskId];
        g_activeTask = null;
        $("#btn-generate").disabled = false;
        $("#btn-generate").textContent = getGenerateButtonText();
        setStatus(t("taskNotFound") + ": " + taskId, "failed");
        refreshSingleTaskItem(taskId, { task_id: taskId, status: "failed", error: t("taskNotFound"), created_at: Date.now() / 1000, prompt: "", has_image: false });
      }
    }
  }, 1500);
}

function showImage(url) {
  $("#preview-placeholder").style.display = "none";
  $("#preview-spinner").style.display = "none";
  $("#preview-video").style.display = "none";
  const lf = document.getElementById("preview-last-frame-wrap");
  if (lf) lf.style.display = "none";
  const img = $("#preview-img");
  img.src = url;
  img.style.display = "block";
}

function showVideo(url) {
  $("#preview-placeholder").style.display = "none";
  $("#preview-spinner").style.display = "none";
  $("#preview-img").style.display = "none";
  const lf = document.getElementById("preview-last-frame-wrap");
  if (lf) lf.style.display = "none";
  const video = $("#preview-video");
  video.src = url;
  video.style.display = "block";
}

function showLastFrame(url) {
  const wrap = document.getElementById("preview-last-frame-wrap");
  const img = document.getElementById("preview-last-frame");
  if (!wrap || !img) return;
  img.src = url;
  img.style.display = "block";
  wrap.style.display = "block";
}

function setStatus(text, cls = "") {
  const el = $("#preview-status");
  el.textContent = text;
  el.className = "status-text";
  if (cls) el.classList.add("status-" + cls);
  if (cls === "processing" || cls === "queued") {
    $("#preview-spinner").style.display = "block";
    $("#preview-placeholder").style.display = "none";
  }
}

// ---- Task History ----
function renderTaskList(tasks) {
  g_lastTasks = tasks;
  const container = $("#task-list");
  const sorted = tasks.sort((a, b) => b.created_at - a.created_at);
  container.innerHTML = sorted.map(t => taskItemHtml(t)).join("");
  container.querySelectorAll(".task-item").forEach(el => {
    el.addEventListener("click", async () => {
      const tid = el.dataset.taskId;
      try {
        const task = await API.getTask(tid);
        if (task.status === "completed" && task.has_image) {
          if (task.output_type === "video") {
            const blob = await API.getTaskVideo(tid);
            showVideo(URL.createObjectURL(blob));
            if (task.has_last_frame) {
              try {
                const frameBlob = await API.getTaskLastFrame(tid);
                showLastFrame(URL.createObjectURL(frameBlob));
              } catch (e) {
                console.error("Last frame download failed:", e);
              }
            }
          } else {
            const blob = await API.getTaskImage(tid);
            showImage(URL.createObjectURL(blob));
          }
          setStatus(t("imageLoaded") + ": " + tid, "completed");
        } else if (task.status === "processing" || task.status === "queued") {
          startPolling(tid, currentWorkflow() === "multidraw");
        }
      } catch (e) {
        if (e.status === 404) {
          el.remove();
          setStatus(t("taskNotFound") + ": " + tid, "failed");
        } else {
          console.error("Task load failed:", e);
        }
      }
    });
  });
}

async function refreshTaskList() {
  try {
    const tasks = await API.listTasks();
    renderTaskList(tasks);
  } catch (e) { console.error("Failed to refresh tasks:", e); }
}

function refreshSingleTaskItem(taskId, task) {
  const el = $(`.task-item[data-task-id="${taskId}"]`);
  if (el) el.outerHTML = taskItemHtml(task);
}

function addTaskToHistory(task) {
  const container = $("#task-list");
  if (!$(`.task-item[data-task-id="${task.task_id}"]`)) {
    container.insertAdjacentHTML("afterbegin", taskItemHtml(task));
  }
}

function taskItemHtml(task) {
  const shortPrompt = (task.prompt || "").substring(0, 40);
  const time = new Date(task.created_at * 1000).toLocaleTimeString();
  const typeIcon = task.output_type === "video" ? "🎬 " : "";
  const params = [];
  if (task.seed != null) params.push(t("seed") + ": " + task.seed);
  if (task.sampler_name) params.push(t("sampler") + ": " + task.sampler_name);
  if (task.scheduler) params.push(t("scheduler") + ": " + task.scheduler);
  if (task.steps != null) params.push(t("steps") + ": " + task.steps);
  if (task.cfg != null) params.push(t("cfg") + ": " + task.cfg);
  let detailHtml = "";
  if (task.prompt) detailHtml += `<div class="detail-row"><span class="detail-label">${t("prompt")}:</span><span class="detail-val">${escHtml(task.prompt)}</span></div>`;
  if (task.global_prompt) detailHtml += `<div class="detail-row"><span class="detail-label">${t("globalPrompt")}:</span><span class="detail-val">${escHtml(task.global_prompt)}</span></div>`;
  if (task.prompt1) detailHtml += `<div class="detail-row"><span class="detail-label">${t("char1Prompt")}:</span><span class="detail-val">${escHtml(task.prompt1)}</span></div>`;
  if (task.prompt2) detailHtml += `<div class="detail-row"><span class="detail-label">${t("char2Prompt")}:</span><span class="detail-val">${escHtml(task.prompt2)}</span></div>`;
  if (params.length > 0) detailHtml += `<div class="detail-row"><span class="detail-label">${t("params")}:</span><span class="detail-val">${escHtml(params.join(", "))}</span></div>`;
  if (task.error) detailHtml += `<div class="detail-row"><span class="detail-label" style="color:var(--red)">${t("error")}:</span><span class="detail-val" style="color:var(--red)">${escHtml(task.error)}</span></div>`;
  return `
    <div class="task-item" data-task-id="${escAttr(task.task_id)}">
      <div class="task-summary">
        <div class="task-id">${typeIcon}${escHtml(task.task_id)} <span style="color:#666">${time}</span></div>
        <div class="task-prompt">${escHtml(shortPrompt)}</div>
        <div class="task-status status-${task.status}">${t(task.status)}${task.error ? ": " + escHtml(task.error.substring(0, 30)) : ""}</div>
      </div>
      <div class="task-detail">${detailHtml}</div>
    </div>`;
}

async function init() {
  await checkAuth();
  await loadSettings();
  await loadQuota();
  if (g_is_admin) {
    await loadOnlineCount();
  }
  updateDrawCost();
  await refreshTaskList();
}

document.addEventListener("DOMContentLoaded", () => {
  applyTranslations();
  $("#sel-lang").value = currentLang;
  $("#sel-lang").addEventListener("change", () => setLang($("#sel-lang").value));
  setupEvents();
  switchWorkflowUI();
  init();
});

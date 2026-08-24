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
let g_hdMode = false;
let g_flux2SourceImage = null;
let g_flux2RefImage = null;
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
  document.querySelectorAll(".adv-diff-only").forEach(el => {
    el.style.display = isDiff ? "" : "none";
  });

  if (isVideo) updateVideoCost();
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
  setupFlux2Upload("flux2-source-drop", "flux2-source-input", "flux2-source-preview", "flux2-source-placeholder", true);
  setupFlux2Upload("flux2-ref-drop", "flux2-ref-input", "flux2-ref-preview", "flux2-ref-placeholder", false);
  setupDiffUpload("diff-source-drop", "diff-source-input", "diff-source-preview", "diff-source-placeholder");

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

function updateVideoCost() {
  const quality = g_videoQuality;
  const duration = parseInt(document.getElementById("sel-video-duration")?.value || "5");
  let rate = quality === "480p" ? 50 : 200;
  if (duration > 10) rate *= 2;
  const cost = rate * duration;
  const el = document.getElementById("video-cost-display");
  if (el) el.textContent = t("cost") + ": " + cost;
}

function updateDrawCost() {
  const el = document.getElementById("draw-cost-display");
  if (!el) return;
  const wf = currentWorkflow();
  if (wf === "webui_video") { el.textContent = ""; return; }
  if (wf === "discord_flux2_9b_edit") { el.textContent = t("cost") + ": 20"; return; }
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
      if (!g_videoFirstImage) {
        setStatus(t("firstFrameRequired"), "failed");
        btn.disabled = false;
        btn.textContent = t("videoGenerate");
        return;
      }
      const duration = parseInt($("#sel-video-duration").value);
      result = await API.videoAsync(
        prompt, g_videoFirstImage, g_videoLastImage,
        g_videoQuality, duration, g_videoOrientation, adv
      );
    } else if (isFlux2) {
      const prompt = $("#txt-flux2-prompt").value.trim();
      if (!prompt) {
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
        prompt, g_flux2SourceImage, g_flux2RefImage, flux2Neg, adv
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
  const img = $("#preview-img");
  img.src = url;
  img.style.display = "block";
}

function showVideo(url) {
  $("#preview-placeholder").style.display = "none";
  $("#preview-spinner").style.display = "none";
  $("#preview-img").style.display = "none";
  const video = $("#preview-video");
  video.src = url;
  video.style.display = "block";
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

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
const RESOLUTIONS = { 1: [832, 1216], 2: [1024, 1024], 3: [1216, 832], 0: null };

let currentRes = "1";
let advOpen = false;
const pollingTimers = {};
let g_authenticated = false;
let g_is_admin = false;

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
    const data = await API.getLoraList();
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
  const stepsVal = $("#txt-steps").value;
  const cfgVal = $("#txt-cfg").value;
  return {
    seed: seed >= 0 ? seed : null,
    sampler_name: sampler,
    scheduler: scheduler,
    steps: stepsVal ? parseInt(stepsVal) : null,
    cfg: cfgVal ? parseFloat(cfgVal) : null,
  };
}

function switchWorkflowUI() {
  const wf = currentWorkflow();
  const isMulti = wf === "multidraw";
  $("#fields-anima").style.display = isMulti ? "none" : "";
  $("#fields-multidraw").style.display = isMulti ? "" : "none";
  updateGenerateButton();
}

function updateGenerateButton() {
  const btn = $("#btn-generate");
  if (btn.disabled) return;
  btn.textContent = currentWorkflow() === "multidraw" ? t("multidrawGenerate") : t("generate");
}

// ---- Thumbnail helpers ----
const THUMB_EXTS = [".png", ".jpg", ".jpeg", ".webp"];
function thumbnailUrl(filename, ext = ".png") {
  return `/thumbnails/${encodeURIComponent(filename)}${ext}`;
}
function loraDisplayName(filename) {
  return filename.replace(/\.(safetensors|ckpt|pt|pth)$/i, "").replace(/[-_]/g, " ");
}
const PLACEHOLDER_SVG = "data:image/svg+xml," + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" fill="%2316213e"><rect width="200" height="200"/><text x="100" y="100" text-anchor="middle" dy=".35em" fill="%23444" font-size="32" font-family="sans-serif">N/A</text></svg>'
);

async function renderLoraGallery(data) {
  const container = $("#lora-gallery");
  try {
    if (!data) data = await API.getLoraList();
    const available = data.available;
    const active = data.active || {};
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
        html += `
          <div class="lora-card${cls}" data-filename="${escAttr(filename)}">
            <img src="${thumbnailUrl(filename)}" loading="lazy" data-thumb-base="${escAttr(filename)}" data-thumb-idx="0">
            <div class="lora-name" title="${escAttr(filename)}">${escHtml(loraDisplayName(filename))}</div>
            <div class="lora-row">
              <input type="checkbox" ${isActive ? "checked" : ""}>
              <input type="range" min="0" max="2" step="0.05" value="${weight}">
              <input type="number" class="lora-num" value="${weight.toFixed(2)}" min="0" max="2" step="0.05">
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
      const num = card.querySelector(".lora-num");

      img.addEventListener("error", () => {
        let idx = parseInt(img.dataset.thumbIdx) || 0;
        idx++;
        if (idx < THUMB_EXTS.length) {
          img.dataset.thumbIdx = idx;
          img.src = thumbnailUrl(img.dataset.thumbBase, THUMB_EXTS[idx]);
        } else {
          img.src = PLACEHOLDER_SVG;
          img.onerror = null;
        }
      });

      function syncRangeToNum() { num.value = parseFloat(range.value).toFixed(2); }
      function syncNumToRange() {
        let v = parseFloat(num.value);
        if (isNaN(v)) v = 0.8;
        v = Math.min(2, Math.max(0, v));
        range.value = v;
        num.value = v.toFixed(2);
      }
      range.addEventListener("input", syncRangeToNum);
      range.addEventListener("change", async () => {
        syncRangeToNum();
        const w = parseFloat(range.value);
        if (cb.checked) { await API.addLora(filename, w); card.classList.add("active"); }
      });
      num.addEventListener("change", async () => {
        syncNumToRange();
        const w = parseFloat(range.value);
        if (cb.checked) { await API.addLora(filename, w); card.classList.add("active"); }
      });
      cb.addEventListener("change", async () => {
        const w = parseFloat(range.value);
        if (cb.checked) {
          await API.addLora(filename, w);
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

  $("#btn-generate").addEventListener("click", generate);

  $("#btn-adv-toggle").addEventListener("click", () => {
    advOpen = !advOpen;
    $("#adv-panel").style.display = advOpen ? "block" : "none";
    updateLangagedUI();
  });

  $("#btn-open-lora").addEventListener("click", () => {
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

  $("#btn-expand-panel").addEventListener("click", () => {
    $("#panel-right").classList.toggle("expanded");
  });
  $("#btn-refresh-history").addEventListener("click", refreshTaskList);

  $("#txt-prompt").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      generate();
    }
  });
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

// ---- Generate ----
async function generate() {
  if (!g_authenticated) {
    setStatus(t("loginRequired"), "failed");
    return;
  }

  const wf = currentWorkflow();
  const isMulti = wf === "multidraw";

  try {
    await API.setNegativePrompt($("#txt-negative").value);
    if (!isMulti) await API.setArtistChain($("#txt-artist-chain").value);
    if (isMulti) await saveMultidrawParts();
  } catch {}

  const btn = $("#btn-generate");
  btn.disabled = true;
  btn.textContent = t("submitting");

  try {
    let result;
    const adv = getAdvancedParams();

    if (isMulti) {
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
        btn.textContent = t("generate");
        return;
      }
      result = await API.drawAsync(prompt, adv);
    }

    btn.textContent = t("generating");
    setStatus(t("taskSubmitted") + ": " + result.task_id, "processing");
    startPolling(result.task_id, isMulti);
  } catch (e) {
    btn.disabled = false;
    btn.textContent = isMulti ? t("multidrawGenerate") : t("generate");
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
        const blob = await API.getTaskImage(taskId);
        showImage(URL.createObjectURL(blob));
        $("#btn-generate").disabled = false;
        $("#btn-generate").textContent = isMulti ? t("multidrawGenerate") : t("generate");
        setStatus(t("completed"), "completed");
        await loadQuota();
        addTaskToHistory(task);
      } else if (task.status === "failed") {
        clearInterval(pollingTimers[taskId]);
        delete pollingTimers[taskId];
        $("#btn-generate").disabled = false;
        $("#btn-generate").textContent = isMulti ? t("multidrawGenerate") : t("generate");
        setStatus(t("failed") + ": " + (task.error || ""), "failed");
        await loadQuota();
      } else {
        setStatus(t(task.status) + "... (" + task.task_id + ")", task.status);
      }
    } catch (e) { console.error("Poll error:", e); }
  }, 1500);
}

function showImage(url) {
  $("#preview-placeholder").style.display = "none";
  $("#preview-spinner").style.display = "none";
  const img = $("#preview-img");
  img.src = url;
  img.style.display = "block";
}

function setStatus(text, cls = "") {
  const el = $("#preview-status");
  el.textContent = text;
  el.className = "status-text";
  if (cls) el.classList.add("status-" + cls);
  if (cls === "processing") {
    $("#preview-spinner").style.display = "block";
    $("#preview-placeholder").style.display = "none";
  }
}

// ---- Task History ----
async function refreshTaskList() {
  try {
    const tasks = await API.listTasks();
    const container = $("#task-list");
    const sorted = tasks.sort((a, b) => b.created_at - a.created_at);
    container.innerHTML = sorted.map(t => taskItemHtml(t)).join("");
    container.querySelectorAll(".task-item").forEach(el => {
      const summary = el.querySelector(".task-summary");
      const detail = el.querySelector(".task-detail");
      summary.addEventListener("click", () => {
        detail.classList.toggle("open");
      });
      el.addEventListener("dblclick", async () => {
        const tid = el.dataset.taskId;
        const task = await API.getTask(tid);
        if (task.status === "completed" && task.has_image) {
          const blob = await API.getTaskImage(tid);
          showImage(URL.createObjectURL(blob));
          setStatus(t("imageLoaded") + ": " + tid, "completed");
        } else if (task.status === "processing" || task.status === "queued") {
          startPolling(tid, currentWorkflow() === "multidraw");
        }
      });
    });
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
        <div class="task-id">${escHtml(task.task_id)} <span style="color:#666">${time}</span></div>
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
  await refreshTaskList();
}

document.addEventListener("DOMContentLoaded", () => {
  applyTranslations();
  $("#sel-lang").value = currentLang;
  $("#sel-lang").addEventListener("change", () => setLang($("#sel-lang").value));
  setupEvents();
  init();
});

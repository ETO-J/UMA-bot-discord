/* AI Drawing Assistant Chat Widget (draggable bubble) */
(function () {
  const bubble = document.getElementById("chat-bubble");
  const panel = document.getElementById("chat-panel");
  const messagesEl = document.getElementById("chat-messages");
  const inputEl = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send");
  const minimizeBtn = document.getElementById("chat-minimize");
  const clearBtn = document.getElementById("chat-clear");

  let isOpen = false;
  let isLoading = false;
  let historyLoaded = false;

  const POS_KEY = "chatBubblePos";
  const DRAG_THRESHOLD = 6; // px before we consider it a drag, not a click

  /* ---------- Bubble position helpers ---------- */

  function clamp(v, min, max) {
    return Math.min(max, Math.max(min, v));
  }

  function setBubblePosition(left, top) {
    const maxLeft = window.innerWidth - bubble.offsetWidth;
    const maxTop = window.innerHeight - bubble.offsetHeight;
    const l = clamp(left, 0, maxLeft);
    const t = clamp(top, 0, maxTop);
    bubble.style.left = l + "px";
    bubble.style.top = t + "px";
    bubble.style.right = "auto";
    bubble.style.bottom = "auto";
  }

  function saveBubblePosition() {
    const rect = bubble.getBoundingClientRect();
    try {
      localStorage.setItem(POS_KEY, JSON.stringify({ left: rect.left, top: rect.top }));
    } catch {}
  }

  function restoreBubblePosition() {
    try {
      const raw = localStorage.getItem(POS_KEY);
      if (!raw) return;
      const pos = JSON.parse(raw);
      if (typeof pos.left === "number" && typeof pos.top === "number") {
        setBubblePosition(pos.left, pos.top);
      }
    } catch {}
  }

  /* ---------- Panel positioning ---------- */

  function positionPanel() {
    const rect = bubble.getBoundingClientRect();
    const pw = panel.offsetWidth || 420;
    const ph = panel.offsetHeight || 600;

    // Horizontal: align panel's right edge with bubble's right edge.
    let left = rect.right - pw;
    left = clamp(left, 8, Math.max(8, window.innerWidth - pw - 8));

    // Vertical: prefer above the bubble; if no room, place below.
    let top = rect.top - ph - 12;
    if (top < 8) {
      top = rect.bottom + 12;
    }
    top = clamp(top, 8, Math.max(8, window.innerHeight - ph - 8));

    panel.style.left = left + "px";
    panel.style.top = top + "px";
    panel.style.right = "auto";
    panel.style.bottom = "auto";
  }

  function setPanelPosition(left, top) {
    const maxLeft = window.innerWidth - panel.offsetWidth;
    const maxTop = window.innerHeight - panel.offsetHeight;
    panel.style.left = clamp(left, 0, Math.max(0, maxLeft)) + "px";
    panel.style.top = clamp(top, 0, Math.max(0, maxTop)) + "px";
    panel.style.right = "auto";
    panel.style.bottom = "auto";
  }

  /* ---------- Panel drag (via header) ---------- */

  const panelHeader = panel.querySelector(".chat-header");
  let panelDrag = null;

  if (panelHeader) {
    panelHeader.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 && e.pointerType === "mouse") return;
      // Don't start a drag when the minimize button is the target.
      if (e.target.closest("#chat-minimize")) return;
      panelDrag = {
        pointerId: e.pointerId,
        startX: e.clientX,
        startY: e.clientY,
        panelLeft: panel.offsetLeft,
        panelTop: panel.offsetTop,
      };
    });
  }

  document.addEventListener("pointermove", (e) => {
    if (!panelDrag || e.pointerId !== panelDrag.pointerId) return;
    const dx = e.clientX - panelDrag.startX;
    const dy = e.clientY - panelDrag.startY;
    setPanelPosition(panelDrag.panelLeft + dx, panelDrag.panelTop + dy);
  });

  document.addEventListener("pointerup", (e) => {
    if (panelDrag && e.pointerId === panelDrag.pointerId) {
      panelDrag = null;
    }
  });

  document.addEventListener("pointercancel", (e) => {
    if (panelDrag && e.pointerId === panelDrag.pointerId) {
      panelDrag = null;
    }
  });

  /* ---------- Drag vs click ---------- */

  let dragState = null;
  let suppressClick = false;

  bubble.addEventListener("pointerdown", (e) => {
    // Only react to primary button (left click / touch).
    if (e.button !== 0 && e.pointerType === "mouse") return;
    // offsetLeft/offsetTop are transform-independent (unlike getBoundingClientRect),
    // so the hover scale won't cause a jump when the drag starts.
    dragState = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      bubbleLeft: bubble.offsetLeft,
      bubbleTop: bubble.offsetTop,
      moved: false,
    };
  });

  // Listen on document so drags keep working even when the pointer
  // leaves the bubble — no pointer capture required.
  document.addEventListener("pointermove", (e) => {
    if (!dragState || e.pointerId !== dragState.pointerId) return;
    const dx = e.clientX - dragState.startX;
    const dy = e.clientY - dragState.startY;
    if (!dragState.moved && Math.hypot(dx, dy) > DRAG_THRESHOLD) {
      dragState.moved = true;
      bubble.classList.add("dragging");
    }
    if (dragState.moved) {
      setBubblePosition(dragState.bubbleLeft + dx, dragState.bubbleTop + dy);
      if (isOpen) positionPanel();
    }
  });

  document.addEventListener("pointerup", (e) => {
    if (!dragState || e.pointerId !== dragState.pointerId) return;
    if (dragState.moved) {
      saveBubblePosition();
      suppressClick = true; // swallow the click that follows a drag
    }
    dragState = null;
    bubble.classList.remove("dragging");
  });

  document.addEventListener("pointercancel", (e) => {
    if (dragState && e.pointerId === dragState.pointerId) {
      dragState = null;
      bubble.classList.remove("dragging");
    }
  });

  bubble.addEventListener("click", () => {
    if (suppressClick) {
      suppressClick = false;
      return;
    }
    toggle();
  });

  window.addEventListener("resize", () => {
    // Keep bubble on-screen after viewport resize.
    const rect = bubble.getBoundingClientRect();
    setBubblePosition(rect.left, rect.top);
    if (isOpen) positionPanel();
  });

  restoreBubblePosition();

  /* ---------- Toggle ---------- */

  function toggle() {
    isOpen = !isOpen;
    if (isOpen) {
      // Compute the position BEFORE hiding the bubble — getBoundingClientRect()
      // returns all zeros for display:none elements, which would pin the panel
      // to the top-left corner.
      positionPanel();
      bubble.style.display = "none";
      panel.style.display = "flex";
      if (!historyLoaded) {
        loadHistory();
        historyLoaded = true;
      }
      inputEl.focus();
    } else {
      panel.style.display = "none";
      bubble.style.display = "flex";
    }
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function addMessage(role, content) {
    const welcome = messagesEl.querySelector(".chat-welcome");
    if (welcome) welcome.remove();

    const div = document.createElement("div");
    div.className = "chat-msg " + role;

    if (role === "assistant" && (content.includes("[PROMPT]") || content.includes("[NEGATIVE]"))) {
      renderAssistantWithPrompt(div, content);
    } else {
      div.textContent = content;
    }

    messagesEl.appendChild(div);
    scrollToBottom();
  }

  function renderAssistantWithPrompt(container, content) {
    const promptMatch = content.match(/\[PROMPT\]\s*\n?([\s\S]*?)\s*\[\/PROMPT\]/);
    const negMatch = content.match(/\[NEGATIVE\]\s*\n?([\s\S]*?)\s*\[\/NEGATIVE\]/);

    const promptIdx = content.indexOf("[PROMPT]");
    const textBefore = promptIdx > 0 ? content.substring(0, promptIdx).trim() : "";
    if (textBefore) {
      const p = document.createElement("div");
      p.textContent = textBefore;
      container.appendChild(p);
    }

    if (promptMatch) {
      const promptText = promptMatch[1].trim();
      const block = document.createElement("div");
      block.className = "chat-prompt-block";
      block.textContent = promptText;
      const btn = document.createElement("button");
      btn.className = "chat-prompt-apply";
      btn.textContent = t("chatApply");
      btn.addEventListener("click", () => applyToForm(promptText, negMatch ? negMatch[1].trim() : null));
      block.appendChild(btn);
      container.appendChild(block);
    }

    if (negMatch) {
      const negText = negMatch[1].trim();
      const block = document.createElement("div");
      block.className = "chat-prompt-block negative";
      block.textContent = negText;
      const btn = document.createElement("button");
      btn.className = "chat-prompt-apply";
      btn.textContent = t("chatApply");
      btn.addEventListener("click", () => applyToForm(null, negText));
      block.appendChild(btn);
      container.appendChild(block);
    }

    const afterNeg = content.indexOf("[/NEGATIVE]");
    const afterPrompt = content.indexOf("[/PROMPT]");
    const lastMarker = Math.max(afterNeg, afterPrompt);
    if (lastMarker > 0) {
      const closeTag = afterNeg > afterPrompt ? "[/NEGATIVE]" : "[/PROMPT]";
      const textAfter = content.substring(lastMarker + closeTag.length).trim();
      if (textAfter) {
        const p = document.createElement("div");
        p.style.marginTop = "6px";
        p.textContent = textAfter;
        container.appendChild(p);
      }
    }
  }

  function applyToForm(promptText, negativeText) {
    const wf = document.getElementById("sel-workflow").value;
    const isAnimaLike = wf === "discord_anima_v2" || wf === "discord_差分";

    if (promptText) {
      if (isAnimaLike) {
        document.getElementById("txt-prompt").value = promptText;
      } else if (wf === "discord_flux2_9b_edit") {
        document.getElementById("txt-flux2-prompt").value = promptText;
      } else if (wf === "webui_video") {
        document.getElementById("txt-video-prompt").value = promptText;
      } else if (wf === "multidraw") {
        document.getElementById("txt-md-global").value = promptText;
      }
    }

    if (negativeText) {
      if (isAnimaLike) {
        document.getElementById("txt-negative").value = negativeText;
      } else if (wf === "discord_flux2_9b_edit") {
        document.getElementById("txt-flux2-negative").value = negativeText;
      }
    }
  }

  function showLoading() {
    const div = document.createElement("div");
    div.className = "chat-msg assistant loading";
    div.id = "chat-loading";
    div.textContent = t("chatThinking");
    messagesEl.appendChild(div);
    scrollToBottom();
  }

  function removeLoading() {
    const el = document.getElementById("chat-loading");
    if (el) el.remove();
  }

  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text || isLoading) return;

    inputEl.value = "";
    inputEl.style.height = "auto";
    isLoading = true;
    sendBtn.disabled = true;
    inputEl.disabled = true;

    addMessage("user", text);
    showLoading();

    try {
      const resp = await fetch("/api/chat/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });

      removeLoading();

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        addMessage("assistant", t("chatError") + ": " + (err.detail || resp.statusText));
        if (resp.status === 429) {
          addMessage("assistant", t("quotaExhausted"));
        }
      } else {
        const data = await resp.json();
        addMessage("assistant", data.content);
        if (typeof loadQuota === "function") loadQuota();
      }
    } catch (e) {
      removeLoading();
      addMessage("assistant", t("chatError") + ": " + e.message);
    }

    isLoading = false;
    sendBtn.disabled = false;
    inputEl.disabled = false;
    inputEl.focus();
  }

  async function loadHistory() {
    try {
      const resp = await fetch("/api/chat/history");
      if (!resp.ok) return;
      const messages = await resp.json();
      if (messages.length > 0) {
        const welcome = messagesEl.querySelector(".chat-welcome");
        if (welcome) welcome.remove();
        messages.forEach(m => addMessage(m.role, m.content));
      }
    } catch (e) {
      console.error("Failed to load chat history:", e);
    }
  }

  async function clearHistory() {
    try {
      await fetch("/api/chat/clear", { method: "DELETE" });
      messagesEl.innerHTML = '<div class="chat-welcome">' + t("chatWelcome") + '</div>';
    } catch (e) {
      console.error("Failed to clear chat:", e);
    }
  }

  // Event listeners
  minimizeBtn.addEventListener("click", toggle);
  sendBtn.addEventListener("click", sendMessage);
  clearBtn.addEventListener("click", clearHistory);

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Auto-resize textarea
  inputEl.addEventListener("input", () => {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 80) + "px";
  });
})();

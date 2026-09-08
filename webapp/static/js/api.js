const API = {
  base: "/api",

  async _fetch(path, options = {}) {
    const url = this.base + path;
    const res = await fetch(url, options);
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const text = await res.text();
        const trimmed = text.trim();
        if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
          const parsed = JSON.parse(trimmed);
          msg = parsed.detail || msg;
        } else if (res.status === 524) {
          msg = "Request timed out (524)";
        } else {
          // Non-JSON pages (e.g. Cloudflare 5xx HTML) -> keep it short, don't
          // dump the whole error page into the status area.
          msg = trimmed.slice(0, 120) || msg;
        }
      } catch (e) { /* keep the default message */ }
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return res;
  },

  async _json(path, options = {}) {
    const res = await this._fetch(path, options);
    return res.json();
  },

  async _blob(path, options = {}) {
    const res = await this._fetch(path, options);
    return res.blob();
  },

  async _form(path, formData) {
    return this._json(path, { method: "POST", body: formData });
  },

  // Draw
  async drawAsync(prompt, advanced = {}) {
    const body = { prompt, ...advanced };
    Object.keys(body).forEach(k => {
      if (body[k] === "" || body[k] === null || body[k] === undefined) delete body[k];
    });
    return this._json("/draw/async", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  async diffDrawAsync(prompt, image, advanced = {}) {
    const body = { prompt, image, ...advanced };
    Object.keys(body).forEach(k => {
      if (body[k] === "" || body[k] === null || body[k] === undefined) delete body[k];
    });
    return this._json("/draw/diff/async", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  async setHdMode(enabled) {
    return this._json("/settings/hd_mode", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
  },

  async multidrawAsync(prompt1, prompt2, globalPrompt, advanced = {}) {
    const body = { prompt1, prompt2, global_prompt: globalPrompt, ...advanced };
    Object.keys(body).forEach(k => {
      if (body[k] === "" || body[k] === null || body[k] === undefined) delete body[k];
    });
    return this._json("/multidraw/async", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  async videoAsync(prompt, startImage, endImage, quality, duration, orientation, advanced = {}) {
    const body = {
      prompt,
      start_image: startImage,
      end_image: endImage || null,
      quality,
      duration,
      orientation,
      ...advanced,
    };
    Object.keys(body).forEach(k => {
      if (body[k] === "" || body[k] === null || body[k] === undefined) delete body[k];
    });
    return this._json("/video/async", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  async uploadVideoReference(file, storeToLibrary = true) {
    const form = new FormData();
    form.append("file", file);
    form.append("store_to_library", storeToLibrary ? "true" : "false");
    return this._form("/video/uploads", form);
  },

  // Asset library
  async getAssetQuota() {
    return this._json("/assets/quota");
  },

  async uploadAsset(file, meta = {}) {
    const form = new FormData();
    form.append("file", file);
    Object.entries(meta).forEach(([key, value]) => {
      if (value != null && value !== "") form.append(key, String(value));
    });
    return this._form("/assets", form);
  },

  async listAssetFolders() {
    return this._json("/assets/folders");
  },

  async createAssetFolder(name, parentId = null) {
    return this._json("/assets/folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, parent_id: parentId }),
    });
  },

  async getAssetFolderStats(folderId) {
    return this._json(`/assets/folders/${folderId}/stats`);
  },

  async deleteAssetFolder(folderId, confirm = false) {
    return this._json(`/assets/folders/${folderId}?confirm=${confirm ? "true" : "false"}`, {
      method: "DELETE",
    });
  },

  async listAssets(params = {}) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value != null && value !== "") q.set(key, String(value));
    });
    const suffix = q.toString() ? "?" + q.toString() : "";
    return this._json("/assets" + suffix);
  },

  async publishAsset(assetId) {
    return this._json(`/assets/${assetId}/publish`, { method: "POST" });
  },

  async unpublishAsset(assetId) {
    return this._json(`/assets/${assetId}/unpublish`, { method: "POST" });
  },

  async savePublicAsset(publishedId, folderId = "") {
    const q = folderId ? "?folder_id=" + encodeURIComponent(folderId) : "";
    return this._json(`/assets/public/${publishedId}/save${q}`, { method: "POST" });
  },

  async likePublicAsset(publishedId, liked = true) {
    return this._json(`/assets/public/${publishedId}/like`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ liked: !!liked }),
    });
  },

  async uploadPublicAsset(file, meta = {}) {
    const form = new FormData();
    form.append("file", file);
    Object.entries(meta).forEach(([key, value]) => {
      if (value != null && value !== "") form.append(key, String(value));
    });
    return this._form("/assets/public/upload", form);
  },

  async updatePublicAsset(publishedId, meta = {}) {
    return this._json(`/assets/public/${publishedId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(meta),
    });
  },

  async deletePublicAsset(publishedId) {
    return this._json(`/assets/public/${publishedId}`, { method: "DELETE" });
  },

  async deleteAsset(assetId) {
    return this._json(`/assets/${assetId}`, { method: "DELETE" });
  },

  async flux2EditAsync(prompt, sourceImage, referenceImage, negativePrompt, advanced = {}, mode = "edit") {
    const body = {
      prompt,
      source_image: sourceImage,
      reference_image: referenceImage || null,
      negative_prompt: negativePrompt || null,
      mode,
      ...advanced,
    };
    Object.keys(body).forEach(k => {
      if (body[k] === "" || body[k] === null || body[k] === undefined) delete body[k];
    });
    return this._json("/flux2_edit/async", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  async getTask(taskId) {
    return this._json(`/task/${taskId}`);
  },

  async getTaskImage(taskId) {
    return this._blob(`/task/${taskId}/image`);
  },

  async getTaskVideo(taskId) {
    return this._blob(`/task/${taskId}/video`);
  },

  async getTaskLastFrame(taskId) {
    return this._blob(`/task/${taskId}/last-frame`);
  },

  async listTasks() {
    return this._json("/tasks");
  },

  // Settings
  async getSettings() {
    return this._json("/settings");
  },

  async setResolution(width, height) {
    return this._json("/settings/resolution", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ width, height }),
    });
  },

  async setNegativePrompt(text) {
    return this._json("/settings/negative_prompt", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
  },

  async setArtistChain(text) {
    return this._json("/settings/artist_chain", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
  },

  async setPart1(w, h, x, y) {
    return this._json("/settings/part1", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ w, h, x, y }),
    });
  },

  async setPart2(w, h, x, y) {
    return this._json("/settings/part2", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ w, h, x, y }),
    });
  },

  // Lora
  async getLoraList(workflow) {
    const q = workflow ? "?workflow=" + encodeURIComponent(workflow) : "";
    return this._json("/lora" + q);
  },

  async addLora(name, weight, workflow) {
    return this._json("/lora/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, weight, workflow: workflow || null }),
    });
  },

  async removeLora(name) {
    return this._json("/lora/remove", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
  },

  async resetLora() {
    return this._json("/lora/reset", { method: "POST" });
  },

  // Quota
  async getQuota() {
    return this._json("/quota");
  },
};

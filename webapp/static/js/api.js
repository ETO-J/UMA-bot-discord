const API = {
  base: "/api",

  async _fetch(path, options = {}) {
    const url = this.base + path;
    const res = await fetch(url, options);
    if (!res.ok) {
      const text = await res.text();
      let msg = text;
      try { msg = JSON.parse(text).detail || text; } catch {}
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

  async videoAsync(prompt, startImage, endImage, quality, duration, orientation, loraEnabled, loraStrength, negativePrompt, advanced = {}) {
    const body = {
      prompt,
      start_image: startImage,
      end_image: endImage || null,
      quality,
      duration,
      orientation,
      lora_enabled: loraEnabled,
      lora_strength: loraStrength,
      negative_prompt: negativePrompt || null,
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

  async flux2EditAsync(prompt, sourceImage, referenceImage, negativePrompt, advanced = {}) {
    const body = {
      prompt,
      source_image: sourceImage,
      reference_image: referenceImage || null,
      negative_prompt: negativePrompt || null,
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
  async getLoraList() {
    return this._json("/lora");
  },

  async addLora(name, weight) {
    return this._json("/lora/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, weight }),
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

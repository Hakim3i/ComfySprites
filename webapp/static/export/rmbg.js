/** Export Lab — Make-style RMBG settings + all/current frame jobs. */

function exportRmbgMethods() {
  return {
    rmbgModels: typeof MAKE_LAB_RMBG_MODELS !== 'undefined' ? MAKE_LAB_RMBG_MODELS : ['RMBG-2.0'],
    rmbgProcessResOptions:
      typeof MAKE_LAB_RMBG_PROCESS_RES_OPTIONS !== 'undefined'
        ? MAKE_LAB_RMBG_PROCESS_RES_OPTIONS
        : ['512', '1024', '2048'],
    rmbgMaskBlurMax:
      typeof MAKE_LAB_RMBG_MASK_BLUR_MAX !== 'undefined' ? MAKE_LAB_RMBG_MASK_BLUR_MAX : 64,
    rmbgMaskOffsetMin:
      typeof MAKE_LAB_RMBG_MASK_OFFSET_MIN !== 'undefined' ? MAKE_LAB_RMBG_MASK_OFFSET_MIN : -64,
    rmbgMaskOffsetMax:
      typeof MAKE_LAB_RMBG_MASK_OFFSET_MAX !== 'undefined' ? MAKE_LAB_RMBG_MASK_OFFSET_MAX : 64,

    rmbg: {
      model: 'RMBG-2.0',
      sensitivity: '1',
      process_res: '1024',
      mask_blur: '0',
      mask_offset: '0',
      invert_output: false,
      refine_foreground: false,
      background: 'Alpha',
      background_color: '#000000',
    },

    rmbgRunning: false,
    rmbgError: '',
    rmbgStatus: '',
    _rmbgPollGen: 0,

    rmbgColorLabel() {
      return String(this.rmbg.background_color || '#000000').toUpperCase();
    },

    clampRmbgMaskBlur(event) {
      let raw = this.rmbg.mask_blur;
      if (event?.target?.value != null) raw = event.target.value;
      let n = parseInt(String(raw), 10);
      if (Number.isNaN(n) || n < 0) n = 0;
      if (n > this.rmbgMaskBlurMax) n = this.rmbgMaskBlurMax;
      this.rmbg.mask_blur = String(n);
    },

    stepRmbgMaskBlur(delta) {
      let n = parseInt(this.rmbg.mask_blur, 10);
      if (Number.isNaN(n)) n = 0;
      n = Math.min(this.rmbgMaskBlurMax, Math.max(0, n + delta));
      this.rmbg.mask_blur = String(n);
    },

    clampRmbgMaskOffset(event) {
      let raw = this.rmbg.mask_offset;
      if (event?.target?.value != null) raw = event.target.value;
      let n = parseInt(String(raw), 10);
      if (Number.isNaN(n)) n = 0;
      if (n < this.rmbgMaskOffsetMin) n = this.rmbgMaskOffsetMin;
      if (n > this.rmbgMaskOffsetMax) n = this.rmbgMaskOffsetMax;
      this.rmbg.mask_offset = String(n);
    },

    stepRmbgMaskOffset(delta) {
      let n = parseInt(this.rmbg.mask_offset, 10);
      if (Number.isNaN(n)) n = 0;
      n = Math.min(
        this.rmbgMaskOffsetMax,
        Math.max(this.rmbgMaskOffsetMin, n + delta)
      );
      this.rmbg.mask_offset = String(n);
    },

    buildRmbgPayload(frameUrls) {
      return {
        frames: frameUrls,
        source_prompt_id: this.openVideo?.prompt_id || null,
        rmbg: {
          model: this.rmbg.model,
          sensitivity: parseFloat(this.rmbg.sensitivity) || 1,
          process_res: parseInt(this.rmbg.process_res, 10) || 1024,
          mask_blur: parseInt(this.rmbg.mask_blur, 10) || 0,
          mask_offset: parseInt(this.rmbg.mask_offset, 10) || 0,
          invert_output: !!this.rmbg.invert_output,
          refine_foreground: !!this.rmbg.refine_foreground,
          background: this.rmbg.background,
          background_color:
            (this.rmbg.background_color || '#000000').trim() || '#000000',
        },
      };
    },

    async runRemoveBackgroundAll() {
      const targets = this.exportableFrames();
      if (!targets.length) {
        this.showError('No frames to process (all deleted).');
        return;
      }
      const frameUrls = [];
      const frameIds = [];
      for (const frame of targets) {
        const url = this.originalFrameDataUrl(frame);
        if (!url) continue;
        frameUrls.push(url);
        frameIds.push(frame.id);
      }
      await this._runRmbgJob(frameUrls, frameIds);
    },

    async runRemoveBackgroundCurrent() {
      const frame = this.currentFrame();
      if (!frame) {
        this.showError('No frame selected.');
        return;
      }
      if (frame.deleted) {
        this.showError('Current frame is removed — restore it first.');
        return;
      }
      const url = this.originalFrameDataUrl(frame);
      if (!url) {
        this.showError('Could not read current frame.');
        return;
      }
      await this._runRmbgJob([url], [frame.id]);
    },

    async _runRmbgJob(frameUrls, frameIds) {
      if (this.rmbgRunning || !frameUrls.length) return;
      this.rmbgRunning = true;
      this.rmbgError = '';
      this.rmbgStatus = 'Uploading frames…';
      try {
        const r = await fetch('/api/export/rmbg', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.buildRmbgPayload(frameUrls)),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || 'Background removal failed');
        this.rmbgStatus = 'Removing background…';
        await this._pollRmbgJob(data.prompt_id, frameIds);
      } catch (e) {
        this.rmbgError = e.message || String(e);
        this.showError(this.rmbgError);
      } finally {
        this.rmbgRunning = false;
        this.rmbgStatus = '';
      }
    },

    async _pollRmbgJob(promptId, frameIds) {
      this._rmbgPollGen += 1;
      const gen = this._rmbgPollGen;
      while (gen === this._rmbgPollGen) {
        const res = await fetchComfyuiJob(promptId);
        if (res.ok && res.data) {
          const job = res.data;
          if (job.status === 'complete') {
            await this._applyRmbgResults(job.preview_urls || [], frameIds);
            return;
          }
          if (job.status === 'error') {
            throw new Error(job.error || 'Background removal failed');
          }
          if (job.status === 'cancelled') {
            throw new Error('Background removal cancelled');
          }
        }
        await new Promise((resolve) => setTimeout(resolve, 600));
      }
    },

    async _applyRmbgResults(urls, frameIds) {
      if (!urls.length) throw new Error('Background removal returned no images');
      const count = Math.min(urls.length, frameIds.length);
      for (let i = 0; i < count; i++) {
        const img = await this._loadImage(urls[i]);
        const frameId = frameIds[i];
        this.setFrameRmbgImage(frameId, img);
        const frame = this.frames.find((f) => f.id === frameId);
        if (frame) frame.hasRmbg = true;
      }
      this.renderCurrentFrame();
    },

    _loadImage(url) {
      return new Promise((resolve, reject) => {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error('Could not load processed frame'));
        img.src = url + (url.includes('?') ? '&' : '?') + 't=' + Date.now();
      });
    },
  };
}

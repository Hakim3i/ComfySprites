/** Export Lab — client-side frame extraction + per-frame store + compositing.
 *
 * Heavy pixel data (full-resolution frame canvases and decoded RMBG images)
 * is kept in closure-scoped Maps so Alpine does not deep-proxy it. The
 * reactive `frames` array only holds lightweight metadata + small thumbnails.
 */

function exportFramesMethods() {
  const sourceCanvases = new Map(); // frameId -> HTMLCanvasElement (original)
  const rmbgImages = new Map(); // frameId -> HTMLImageElement (bg-removed)

  return {
    openVideo: null,
    frames: [],
    currentIndex: 0,
    reduceTarget: 16,
    extracting: false,
    extractProgress: 0,
    extractError: '',
    sourceFps: 24,

    _resetFrameStore() {
      sourceCanvases.clear();
      rmbgImages.clear();
      this.frames = [];
      this.currentIndex = 0;
    },

    async openVideoForEditing(item) {
      // Reopening the already-loaded video keeps the edited frame session.
      if (
        this.openVideo &&
        this.openVideo.prompt_id === item.prompt_id &&
        this.frames.length
      ) {
        this.$nextTick(() => this.renderCurrentFrame());
        return;
      }
      this.stopPlayback?.();
      this.extractError = '';
      this.openVideo = item;
      this._resetFrameStore();
      this.extracting = true;
      this.extractProgress = 0;
      this.closeVideoPicker?.();
      try {
        await this.extractFramesFromVideo(item);
        this.currentIndex = 0;
        this.reduceTarget = this.frames.length;
        this.form.filename = exportSanitizeFilename(
          (this.videoTitle(item) || '').replace(/ · /g, '_'),
          'frames'
        );
        this.$nextTick(() => this.renderCurrentFrame());
      } catch (e) {
        this.extractError = e.message || String(e);
        this.openVideo = null;
      } finally {
        this.extracting = false;
      }
    },

    /** Fully discard the current session (used when its video is deleted). */
    closeEditor() {
      this.stopPlayback?.();
      this._resetFrameStore();
      this.openVideo = null;
      this.extractError = '';
    },

    async extractFramesFromVideo(item) {
      const fps = Math.max(1, Math.round(Number(item?.request?.fps) || 24));
      this.sourceFps = fps;
      const video = document.createElement('video');
      video.muted = true;
      video.crossOrigin = 'anonymous';
      video.preload = 'auto';
      video.src = item.video_url;

      await new Promise((resolve, reject) => {
        video.onloadedmetadata = () => resolve();
        video.onerror = () => reject(new Error('Could not load video'));
      });

      const duration = video.duration;
      if (!Number.isFinite(duration) || duration <= 0) {
        throw new Error('Video has no readable duration');
      }
      let frameCount = Math.max(1, Math.round(duration * fps));
      if (frameCount > EXPORT_MAX_FRAMES) frameCount = EXPORT_MAX_FRAMES;

      const width = video.videoWidth;
      const height = video.videoHeight;
      const records = [];

      for (let i = 0; i < frameCount; i++) {
        const t = Math.min(duration - 1e-3, i / fps);
        await this._seekVideo(video, t);
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, width, height);
        const id = 'f' + i;
        sourceCanvases.set(id, canvas);
        records.push({
          id,
          index: i,
          deleted: false,
          flipX: false,
          flipY: false,
          rotation: 0,
          hasRmbg: false,
          thumb: this._makeThumb(canvas),
          w: width,
          h: height,
        });
        this.extractProgress = (i + 1) / frameCount;
      }

      try {
        video.src = '';
        video.load();
      } catch {
        /* ignore */
      }
      this.frames = records;
    },

    _seekVideo(video, time) {
      return new Promise((resolve, reject) => {
        let settled = false;
        const done = () => {
          if (settled) return;
          settled = true;
          video.removeEventListener('seeked', done);
          resolve();
        };
        video.addEventListener('seeked', done);
        const timer = setTimeout(done, 2000); // guard against missed seeked
        void timer;
        try {
          video.currentTime = time;
        } catch (e) {
          reject(e);
        }
      });
    },

    _makeThumb(canvas) {
      const w = EXPORT_THUMB_WIDTH;
      const h = Math.max(1, Math.round((canvas.height / canvas.width) * w));
      const tc = document.createElement('canvas');
      tc.width = w;
      tc.height = h;
      tc.getContext('2d').drawImage(canvas, 0, 0, w, h);
      return tc.toDataURL('image/jpeg', 0.7);
    },

    // --- per-frame pixel-source access (used by compose) ---

    frameSourceImage(frame) {
      if (frame.hasRmbg && rmbgImages.has(frame.id)) {
        return rmbgImages.get(frame.id);
      }
      return sourceCanvases.get(frame.id) || null;
    },

    /** Raw (pre-transform, pre-rmbg) frame PNG for sending to background removal. */
    originalFrameDataUrl(frame) {
      const canvas = sourceCanvases.get(frame.id);
      return canvas ? canvas.toDataURL('image/png') : null;
    },

    setFrameRmbgImage(frameId, img) {
      rmbgImages.set(frameId, img);
    },

    clearFrameRmbgImage(frameId) {
      rmbgImages.delete(frameId);
    },

    /** Compose one frame to a canvas: source priority (rmbg > original) + flip/rotate. */
    composeFrameCanvas(frame) {
      const src = this.frameSourceImage(frame);
      if (!src) return null;
      const sw = src.naturalWidth || src.width;
      const sh = src.naturalHeight || src.height;
      const rot = ((frame.rotation % 360) + 360) % 360;
      const swap = rot === 90 || rot === 270;
      const outW = swap ? sh : sw;
      const outH = swap ? sw : sh;
      const canvas = document.createElement('canvas');
      canvas.width = outW;
      canvas.height = outH;
      const ctx = canvas.getContext('2d');
      ctx.save();
      ctx.translate(outW / 2, outH / 2);
      if (rot !== 0) ctx.rotate((rot * Math.PI) / 180);
      const fx = frame.flipX ? -1 : 1;
      const fy = frame.flipY ? -1 : 1;
      ctx.scale(fx, fy);
      ctx.drawImage(src, -sw / 2, -sh / 2, sw, sh);
      ctx.restore();
      return canvas;
    },

    composedFrameSize(frame) {
      const src = this.frameSourceImage(frame);
      const sw = src ? src.naturalWidth || src.width : frame.w;
      const sh = src ? src.naturalHeight || src.height : frame.h;
      const rot = ((frame.rotation % 360) + 360) % 360;
      const swap = rot === 90 || rot === 270;
      return { w: swap ? sh : sw, h: swap ? sw : sh };
    },
  };
}

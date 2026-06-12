/** Export Lab — saved video library (list, preview, open, delete). */

function exportLibraryMethods() {
  return {
    videos: [],
    libraryLoading: false,
    libraryError: '',
    deletingId: '',
    confirmDeleteId: '',
    videoPickerOpen: false,

    openVideoPicker() {
      this.confirmDeleteId = '';
      this.videoPickerOpen = true;
      void this.loadVideos();
    },

    closeVideoPicker() {
      this.videoPickerOpen = false;
      this.confirmDeleteId = '';
    },

    selectVideo(item) {
      void this.openVideoForEditing(item);
    },

    async loadVideos() {
      this.libraryLoading = true;
      this.libraryError = '';
      try {
        const r = await fetch(
          '/api/export/videos?limit=' + EXPORT_LAB_VIDEO_LIMIT,
          { cache: 'no-store' }
        );
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || 'Failed to load videos');
        this.videos = Array.isArray(data.items) ? data.items : [];
      } catch (e) {
        this.libraryError = e.message || String(e);
        this.videos = [];
      } finally {
        this.libraryLoading = false;
      }
    },

    videoTitle(item) {
      return this.videoSceneLine(item);
    },

    videoSceneLine(item) {
      const parts = [];
      const anim = (item?.animation_slug || '').trim();
      if (anim) parts.push(anim);
      const char = (item?.character_slug || '').trim();
      if (char) parts.push(char);
      return parts.length ? parts.join(' · ') : 'Saved video';
    },

    videoInfoRows(item) {
      if (!item) return [];
      const req = item.request || {};
      const rows = [];
      const push = (label, value) => {
        const v = (value ?? '').toString().trim();
        if (v) rows.push({ label, value: v });
      };
      push('Animation', item.animation_slug);
      push('Character', item.character_slug);
      push('Background', item.background_slug);
      push('Style', item.style_slug);
      push('Model', item.model_id);
      if (req.cfg != null) push('CFG', req.cfg);
      if (req.steps != null) push('Steps', req.steps);
      if (req.shift != null) push('Shift', req.shift);
      if (req.fps) push('FPS', `${req.fps}`);
      if (req.length_seconds) push('Duration', `${req.length_seconds}s`);
      if (this.frames?.length && this.openVideo?.prompt_id === item.prompt_id) {
        const first = this.frames[0];
        if (first?.w && first?.h) push('Resolution', `${first.w} × ${first.h}px`);
        push('Extracted', `${this.frames.length} frames`);
        push('Exportable', `${this.exportableCount()}`);
      }
      push('Saved', this.videoSavedAt(item));
      return rows;
    },

    videoModelLine(item) {
      const model = (item?.model_id || '').trim();
      const style = (item?.style_slug || '').trim();
      if (model && style) return `${model} · ${style}`;
      return model || style || '';
    },

    videoTimingLine(item) {
      const bits = [];
      const fps = item?.request?.fps;
      if (fps) bits.push(`${fps} fps`);
      const secs = item?.request?.length_seconds;
      if (secs) bits.push(`${secs}s`);
      if (this.frames?.length && this.openVideo?.prompt_id === item.prompt_id) {
        bits.push(`${this.frames.length} frames`);
      }
      return bits.join(' · ');
    },

    videoDescription(item) {
      return [this.videoModelLine(item), this.videoTimingLine(item)]
        .filter(Boolean)
        .join(' · ');
    },

    videoSavedAt(item) {
      return exportFormatDate(item?.created_at);
    },

    onVideoHover(event, hovering) {
      const card = event.currentTarget;
      const node = card ? card.querySelector('video') : null;
      if (!node) return;
      if (hovering) {
        try {
          node.currentTime = 0;
          const p = node.play();
          if (p && p.catch) p.catch(() => {});
        } catch {
          /* ignore autoplay rejection */
        }
      } else {
        try {
          node.pause();
          node.currentTime = 0;
        } catch {
          /* ignore */
        }
      }
    },

    askDeleteVideo(item) {
      this.confirmDeleteId = item.prompt_id;
    },

    cancelDeleteVideo() {
      this.confirmDeleteId = '';
    },

    async deleteVideo(item) {
      this.deletingId = item.prompt_id;
      try {
        const r = await fetch(
          '/api/export/videos/' + encodeURIComponent(item.prompt_id),
          { method: 'DELETE' }
        );
        if (!r.ok) {
          const data = await r.json().catch(() => ({}));
          throw new Error(data.detail || 'Delete failed');
        }
        this.videos = this.videos.filter((v) => v.prompt_id !== item.prompt_id);
        if (this.openVideo?.prompt_id === item.prompt_id) {
          this.closeEditor();
        }
      } catch (e) {
        this.showError(e.message || String(e));
      } finally {
        this.deletingId = '';
        this.confirmDeleteId = '';
      }
    },
  };
}

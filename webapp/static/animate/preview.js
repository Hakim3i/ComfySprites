/** Animate Lab — preview stage and video transport. */

function animatePreviewMethods() {
  return {
    previewVideoUrl: null,
    viewportTick: 0,
    playback: {
      current: 0,
      duration: 0,
      playing: false,
      seeking: false,
    },

    onViewportResize() {
      this.viewportTick += 1;
      this.$nextTick(() => this.updateHistoryScrollState?.());
    },

    previewBounds() {
      void this.viewportTick;
      const row = this.$refs.previewRow;
      const wrap = this.$refs.previewWrap;
      const transport = this.$refs.previewTransport;
      const measure = wrap || row;
      const vh = typeof window !== 'undefined' ? window.innerHeight : 900;
      if (measure?.getBoundingClientRect) {
        const rect = measure.getBoundingClientRect();
        const maxW = Math.floor(rect.width);
        const maxH = Math.floor(rect.height);
        if (maxW > 0 && maxH > 0) return { maxW, maxH };
      }
      let fallbackW = 320;
      let fallbackH = 240;
      const center = this.$refs.studioCenter;
      if (center?.clientWidth > 0) fallbackW = center.clientWidth;
      if (row?.getBoundingClientRect) {
        const top = row.getBoundingClientRect().top;
        const transportH = transport?.offsetHeight || 52;
        fallbackH = Math.max(120, Math.floor(vh - top - 32 - transportH - 12));
      }
      return { maxW: Math.max(160, fallbackW), maxH: fallbackH };
    },

    expectedPreviewDimensions() {
      const sdxl = this.selectedSource?.build?.sdxl || {};
      let w = parseInt(sdxl.width, 10) || 768;
      let h = parseInt(sdxl.height, 10) || 1280;
      if (this.previewVideoUrl) {
        const v = this.previewVideoEl();
        if (v?.videoWidth > 0 && v?.videoHeight > 0) {
          w = v.videoWidth;
          h = v.videoHeight;
        }
      }
      return { width: w, height: h };
    },

    previewStageBox() {
      const { width: w, height: h } = this.expectedPreviewDimensions();
      const { maxW, maxH } = this.previewBounds();
      const scale = Math.min(maxW / w, maxH / h);
      return {
        w,
        h,
        boxW: Math.max(1, Math.floor(w * scale)),
        boxH: Math.max(1, Math.floor(h * scale)),
      };
    },

    previewStageStyle() {
      void this.viewportTick;
      const { boxW, boxH } = this.previewStageBox();
      return {
        width: boxW + 'px',
        height: boxH + 'px',
        maxWidth: '100%',
        maxHeight: '100%',
      };
    },

    previewVideoEl() {
      return this.$refs.previewVideo || null;
    },

    canControlPlayback() {
      return Boolean(this.previewVideoUrl);
    },

    videoTogglePlayPause() {
      const v = this.previewVideoEl();
      if (!v) return;
      if (v.paused) void v.play().catch(() => {});
      else v.pause();
    },

    videoStop() {
      const v = this.previewVideoEl();
      if (!v) return;
      v.pause();
      v.currentTime = 0;
      this.playback.current = 0;
      this.playback.playing = false;
    },

    onPreviewVideoLoaded() {
      const v = this.previewVideoEl();
      if (!v) return;
      this.playback.duration = Number.isFinite(v.duration) ? v.duration : 0;
      this.playback.current = v.currentTime || 0;
      this.onViewportResize();
    },

    onPreviewVideoTimeUpdate() {
      if (this.playback.seeking) return;
      const v = this.previewVideoEl();
      if (!v) return;
      this.playback.current = v.currentTime || 0;
      if (Number.isFinite(v.duration) && v.duration > 0) {
        this.playback.duration = v.duration;
      }
    },

    onPreviewVideoEnded() {
      this.playback.playing = false;
    },

    playbackSeekValue() {
      const d = this.playback.duration;
      if (!d || d <= 0) return 0;
      return Math.round(Math.max(0, Math.min(1000, (this.playback.current / d) * 1000)));
    },

    onPlaybackSeekInput(ev) {
      const d = this.playback.duration;
      if (!d || d <= 0) return;
      const raw = parseInt(ev.target.value, 10);
      const pct = Math.max(0, Math.min(1000, Number.isNaN(raw) ? 0 : raw)) / 1000;
      const t = pct * d;
      this.playback.current = t;
      const v = this.previewVideoEl();
      if (v) v.currentTime = t;
    },

    onPlaybackSeekCommit() {
      this.playback.seeking = false;
      const v = this.previewVideoEl();
      if (v) this.playback.current = v.currentTime || 0;
    },

    formatPlaybackTime(seconds) {
      const s = Math.max(0, Math.floor(Number(seconds) || 0));
      const m = Math.floor(s / 60);
      const r = s % 60;
      return `${m}:${String(r).padStart(2, '0')}`;
    },
  };
}

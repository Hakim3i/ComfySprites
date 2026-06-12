/** Edit Lab — image preview stage sizing. */

function editPreviewMethods() {
  return {
    previewResultUrl: null,
    lastEditImageUrl: null,
    viewportTick: 0,

    onViewportResize() {
      this.viewportTick += 1;
      this.$nextTick(() => this.updateHistoryScrollState?.());
    },

    previewBounds() {
      void this.viewportTick;
      const row = this.$refs.previewRow;
      const wrap = this.$refs.previewWrap;
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
        fallbackH = Math.max(120, Math.floor(vh - top - 32 - 12));
      }
      return { maxW: Math.max(160, fallbackW), maxH: fallbackH };
    },

    expectedPreviewDimensions() {
      const sdxl = this.selectedSource?.build?.sdxl || {};
      let w = parseInt(sdxl.width, 10) || 768;
      let h = parseInt(sdxl.height, 10) || 1280;
      const img = this.$refs.previewImg;
      if (img?.naturalWidth > 0 && img?.naturalHeight > 0) {
        w = img.naturalWidth;
        h = img.naturalHeight;
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

    onPreviewImageLoaded() {
      this.onViewportResize();
      if (this.$refs.previewImg?.src) {
        this.lastEditImageUrl = this.$refs.previewImg.src;
      }
      this.updateSourceOverlay?.();
    },

    onGenerationComplete(url, promptId) {
      if (!url) return;
      this.previewResultUrl = url;
      this.lastEditImageUrl = url;
      if (promptId) this.selectedHistoryId = promptId;
      this.resetImageEdits?.();
      void this.loadHistory();
      this.$nextTick(() => {
        this.onViewportResize();
        this.updateSourceOverlay?.();
      });
    },
  };
}

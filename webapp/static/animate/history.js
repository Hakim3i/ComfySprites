/** Animate Lab — history sidebar (scaffold). */

function animateHistoryMethods() {
  return {
    historyItems: [],
    historyLoading: false,
    selectedHistoryId: null,

    async loadHistory() {
      this.historyLoading = true;
      try {
        const r = await fetch(
          '/api/animate/history?limit=' + ANIMATE_LAB_HISTORY_LIMIT
        );
        const data = await r.json();
        this.historyItems = Array.isArray(data.items) ? data.items : [];
      } catch {
        /* keep existing */
      } finally {
        this.historyLoading = false;
        this.$nextTick(() => this.updateHistoryScrollState?.());
      }
    },

    formatHistoryDate(iso) {
      if (!iso) return '';
      try {
        return new Date(iso).toLocaleDateString(undefined, {
          month: 'short',
          day: 'numeric',
        });
      } catch {
        return '';
      }
    },

    async selectHistoryItem(item) {
      if (!item?.prompt_id) return;
      this.selectedHistoryId = item.prompt_id;
      if (item.video_url) {
        this.previewVideoUrl = item.video_url;
      }
    },
  };
}

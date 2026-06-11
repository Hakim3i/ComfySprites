/** Animate Lab — video history sidebar. */

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

    historySceneLabel(item) {
      const parts = [];
      const anim = (item?.animation_slug || '').trim();
      if (anim) parts.push(this.animationLabel(anim));
      const char = (item?.character_slug || '').trim();
      if (char) parts.push(char);
      return parts.length ? parts.join(' · ') : 'Video';
    },

    async fetchMakeSource(promptId) {
      if (!promptId) return null;
      const cached = this.sourceItems.find((s) => s.prompt_id === promptId);
      if (cached) return cached;
      try {
        const r = await fetch(
          '/api/gallery/items/' + encodeURIComponent(promptId)
        );
        if (!r.ok) return null;
        return await r.json();
      } catch {
        return null;
      }
    },

    async selectHistoryItem(item) {
      if (!item?.prompt_id) return;
      this.selectedHistoryId = item.prompt_id;
      if (item.video_url) {
        this.previewVideoUrl = item.video_url;
        this.videoStop?.();
      }
      if (item.source_prompt_id) {
        const source = await this.fetchMakeSource(item.source_prompt_id);
        if (source) {
          this.selectedSource = source;
          this.selectedSourceId = source.prompt_id;
        }
      }
      const animSlug = (item.animation_slug || '').trim();
      if (animSlug) {
        this.form.animation_slug = animSlug;
        await this.fetchAnimationBySlug(animSlug);
      }
      this.promptFieldsUserEdited = false;
      if (this.selectedSource?.prompt_id) {
        void this.loadLtxPreview();
      }
      this.$nextTick(() => this.onViewportResize());
    },
  };
}


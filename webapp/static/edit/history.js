/** Edit Lab — edit history sidebar. */

function editHistoryMethods() {
  return {
    historyItems: [],
    historyLoading: false,
    selectedHistoryId: null,

    async loadHistory() {
      this.historyLoading = true;
      try {
        const r = await fetch('/api/edit/history?limit=' + EDIT_LAB_HISTORY_LIMIT);
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
      return parts.length ? parts.join(' · ') : 'Edit';
    },

    async selectHistoryItem(item) {
      if (!item?.prompt_id) return;
      this.selectedHistoryId = item.prompt_id;
      if (item.image_url) {
        this.previewResultUrl = item.image_url;
        this.lastEditImageUrl = item.image_url;
        this.resetImageEdits?.();
      }
      if (item.source_prompt_id) {
        const source = this.sourceItems.find((s) => s.prompt_id === item.source_prompt_id);
        if (source) {
          this.selectedSource = source;
          this.selectedSourceId = source.prompt_id;
          this.selectedSourceKind = source.source_kind || item.source_kind || 'make';
        } else if (item.source_image_url) {
          this.selectedSource = {
            prompt_id: item.source_prompt_id,
            image_url: item.source_image_url,
            source_kind: item.source_kind || 'make',
            animation_slug: item.animation_slug,
          };
          this.selectedSourceId = item.source_prompt_id;
          this.selectedSourceKind = item.source_kind || 'make';
        }
      }
      const animSlug = (item.animation_slug || '').trim();
      if (animSlug) {
        this.form.animation_slug = animSlug;
        await this.fetchAnimationBySlug(animSlug);
      }
      this.promptFieldsUserEdited = false;
      if (this.selectedSource?.prompt_id) {
        void this.loadEditPreview();
      }
      this.$nextTick(() => {
        this.onViewportResize();
        this.updateSourceOverlay?.();
      });
    },
  };
}

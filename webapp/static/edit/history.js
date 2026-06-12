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

    isHistoryItemSelected(item) {
      const id = item?.prompt_id;
      return Boolean(id && this.selectedHistoryId === id);
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
        const kind = item.source_kind || 'make';
        const gallery = this.sourceItems.find(
          (s) => s.prompt_id === item.source_prompt_id
        );
        const record = gallery
          ? {
              ...gallery,
              image_url: item.source_image_url || gallery.image_url,
              animation_slug:
                item.animation_slug || gallery.animation_slug || '',
              character_slug: item.character_slug || gallery.character_slug,
              background_slug:
                item.background_slug || gallery.background_slug,
            }
          : {
              prompt_id: item.source_prompt_id,
              image_url: item.source_image_url || '',
              source_kind: kind,
              animation_slug: item.animation_slug || '',
              character_slug: item.character_slug,
              background_slug: item.background_slug,
              build: item.build,
            };
        this.applyEditSource(record, {
          promptId: item.source_prompt_id,
          kind,
        });
      }
      const animSlug = (item.animation_slug || '').trim();
      if (animSlug) {
        this.form.animation_slug = animSlug;
        await this.fetchAnimationBySlug(animSlug, { resetLoraStrengths: true });
      }
      this.promptFieldsUserEdited = false;
      if (this.selectedSourceId) {
        void this.loadEditPreview();
      }
      this.$nextTick(() => {
        this.onViewportResize();
        this.updateSourceOverlay?.();
      });
    },
  };
}

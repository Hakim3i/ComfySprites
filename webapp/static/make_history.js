(function (global) {
  function makeHistoryMethods() {
    return {





    async loadHistory() {
      this.historyLoading = true;
      try {
        const r = await fetch(
          '/api/make/history?limit=' + MAKE_LAB_HISTORY_LIMIT
        );
        if (!r.ok) return;
        const data = await r.json();
        this.historyItems = Array.isArray(data.items) ? data.items : [];
        this.syncHistorySelectionFromPreview();
      } catch {
        /* keep previous list */
      } finally {
        this.historyLoading = false;
        this.$nextTick(() => {
          this.onViewportResize();
          this.updateHistoryScrollState();
        });
      }
    },





    syncHistorySelectionFromPreview() {
      if (this.comfyuiAnyJobActive()) return;
      const id = this.focusedPreviewPromptId();
      if (!id) return;
      const hit = this.historyItems.find((it) => it.prompt_id === id);
      if (hit) {
        this.selectedHistoryId = hit.prompt_id;
      }
    },





    historySceneLabel(item) {
      const parts = [];
      const charSlug = item?.character_slug;
      if (charSlug) {
        const subj =
          this.subjectEntityBySlug(charSlug) || this.characterBySlug(charSlug);
        const name = subj?.menu_name || subj?.slug || charSlug;
        if (name) parts.push(name);
      }
      const animationSlug = item?.animation_slug;
      if (animationSlug && String(animationSlug).toLowerCase() !== 'none') {
        const act = this.actLabelForSlug(animationSlug);
        if (act && act !== 'ΓÇö') parts.push(act);
      }
      const place = this.locationLabelForKey(item?.background_slug);
      if (place) parts.push(place);
      return parts.length ? parts.join(' ┬╖ ') : 'ΓÇö';
    },





    historyActLabel(item) {
      return this.historySceneLabel(item);
    },





    isHistoryItemSelected(item) {
      const id = item?.prompt_id;
      if (!id) return false;
      return (
        this.selectedHistoryId === id ||
        this.previewFocusPromptId === id ||
        this.focusedPreviewPromptId() === id
      );
    },





    formatHistoryDate(iso) {
      if (!iso) return '';
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return '';
      return d.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    },





    async applyGalleryHandoff() {
      const params = new URLSearchParams(window.location.search);
      const restoreId = (params.get('restore') || '').trim();
      if (!restoreId) return;
      try {
        const r = await fetch(
          '/api/gallery/items/' + encodeURIComponent(restoreId)
        );
        if (!r.ok) return;
        const item = await r.json();
        this.selectHistoryItem(item);
        params.delete('restore');
        const qs = params.toString();
        window.history.replaceState(
          null,
          '',
          window.location.pathname + (qs ? '?' + qs : '')
        );
      } catch {
        /* handoff is best-effort */
      }
    },





    selectHistoryItem(item) {
      if (!item?.image_url) return;
      if (this.comfyuiAnyJobActive()) {
        this.previewLiveSampling = false;
      }
      this.previewFocusPromptId = null;
      this.previewAutoFollowInference = false;
      this.selectedHistoryId = item.prompt_id;
      this.outputImage = this.cacheBustUrl(item.image_url);
      this.resetOrientationToDefault();
      this.applyRequestToForm(item.request, item.build, { restoreDice: true });
      if (item.build) {
        this.result = item.build;
        this.applyBuildPreviewSize(item.build);
      } else {
        this.previewBuildSizeStale = true;
      }
      this.$nextTick(() => this.onViewportResize());
    },






    async fetchBuildForPromptId(promptId) {
      if (!promptId) return null;
      try {
        const r = await fetch(
          '/api/gallery/items/' + encodeURIComponent(promptId)
        );
        if (!r.ok) return null;
        const item = await r.json();
        return item.build || null;
      } catch {
        return null;
      }
    },





    async resolveMetadataBuild() {
      const focused = this.historyItemForFocusedPreview();
      if (focused?.build) return focused.build;

      if (this.outputImage && this.isPreviewPinnedToCompleted() && this.result) {
        return this.result;
      }

      const active = this.activePreviewPromptId();
      if (
        active &&
        this.trackedJobs.some((t) => t.promptId === active) &&
        this.result
      ) {
        return this.result;
      }

      const id = this.focusedPreviewPromptId();
      if (id) return this.fetchBuildForPromptId(id);

      return null;
    },





    openMetadataWithBuild(build) {
      this.result = build;
      this.applyBuildPreviewSize(build);
      this.metadataOpen = true;
    },





    metadataViewsLabel() {
      const views = this.result?.scene?.views;
      return Array.isArray(views) && views.length ? views.join(', ') : 'ΓÇö';
    },





    metadataCheckpoint() {
      return this.result?.sdxl?.checkpoint || {};
    },





    metadataRefineStyleLabel() {
      const raw = this.result?.scene?.refine_style;
      if (raw == null || raw === '' || raw === '_inference') return 'Same as inference';
      return String(raw);
    },





    focusedPreviewPromptId() {
      return this.previewFocusPromptId || this.selectedHistoryId || null;
    },





    canDeleteFocusedPreview() {
      const id = this.focusedPreviewPromptId();
      if (!id || this.deletingPreview) return false;
      return this.historyItems.some((it) => it.prompt_id === id);
    },





    async deleteFocusedPreview() {
      const id = this.focusedPreviewPromptId();
      if (!id || !this.canDeleteFocusedPreview()) return;
      this.deletingPreview = true;
      this.error = '';
      try {
        const r = await fetch(
          '/api/gallery/items/' + encodeURIComponent(id),
          { method: 'DELETE' }
        );
        if (!r.ok) {
          const data = await r.json().catch(() => ({}));
          throw new Error(
            (typeof data.detail === 'string' && data.detail) || 'Delete failed'
          );
        }
        const idx = this.historyItems.findIndex((it) => it.prompt_id === id);
        if (idx >= 0) this.historyItems.splice(idx, 1);
        if (this.selectedHistoryId === id || this.previewFocusPromptId === id) {
          const next = this.historyItems[idx] || this.historyItems[idx - 1] || null;
          if (next) {
            this.selectHistoryItem(next);
          } else {
            this.selectedHistoryId = null;
            this.previewFocusPromptId = null;
            this.outputImage = null;
            this.result = null;
          }
        }
        this.$nextTick(() => this.onViewportResize());
      } catch (e) {
        this.error = e.message || 'Could not delete generation.';
      } finally {
        this.deletingPreview = false;
      }
    },





    closeMetadataModal() {
      this.metadataOpen = false;
    },





    _patchCatalogImagePath(field, imagePath) {
      if (!imagePath) return;
      const val = this.resolvedFieldValue(field);
      switch (field) {
        case 'character': {
          const row = this.characterBySlug(val);
          if (row) row.image_path = imagePath;
          return;
        }
        case 'animation': {
          const row = this.animationBySlug(val);
          if (row) row.image_path = imagePath;
          return;
        }
        case 'place': {
          const row = this.locationByKey(val);
          if (row) row.image_path = imagePath;
          return;
        }
        case 'style':
        case 'refine_style': {
          const row = this.styleBySlug(val);
          if (row) row.image_path = imagePath;
        }
      }
    },





    openPickFieldSettings(field) {
      const url = this.pickFieldSettingsUrl(field);
      if (!url) return;
      window.open(url, '_blank', 'noopener,noreferrer');
    },





    scrollPickerToSelection() {
      this.$nextTick(() => {
        this.$nextTick(() => {
          const scroll = this.$refs.pickerScroll;
          if (!scroll) return;
          const selected = scroll.querySelector('.make-pick-card.selected');
          if (!selected) return;
          const scrollRect = scroll.getBoundingClientRect();
          const selRect = selected.getBoundingClientRect();
          const delta =
            selRect.top -
            scrollRect.top -
            (scroll.clientHeight - selRect.height) / 2;
          scroll.scrollTop += delta;
        });
      });
    },
    };
  }
  global.makeHistoryMethods = makeHistoryMethods;
})(window);

/** Edit Lab — source picker (Make stills + prior edits). */

function editSourcesMethods() {
  return {
    catalog: { animations: [] },
    sourceItems: [],
    selectedSource: null,
    selectedSourceId: null,
    selectedSourceKind: 'make',
    selectedAnimation: null,
    gallery: { open: false, loading: false, tab: 'all' },
    animationPickerOpen: false,
    animationPickerFilter: '',

    async loadCatalog() {
      try {
        const r = await fetch('/api/animations');
        const data = await r.json();
        this.catalog.animations = Array.isArray(data) ? data : data.items || [];
      } catch {
        this.catalog.animations = [];
      }
    },

    async fetchSources() {
      this.gallery.loading = true;
      try {
        const r = await fetch('/api/edit/sources?limit=' + EDIT_LAB_SOURCES_LIMIT);
        const data = await r.json();
        this.sourceItems = Array.isArray(data.items) ? data.items : [];
      } catch {
        this.sourceItems = [];
        this.showError('Could not load source gallery.');
      } finally {
        this.gallery.loading = false;
      }
    },

    filteredSourceItems() {
      const tab = this.gallery.tab || 'all';
      if (tab === 'make') {
        return this.sourceItems.filter((item) => item.source_kind !== 'edit');
      }
      if (tab === 'edit') {
        return this.sourceItems.filter((item) => item.source_kind === 'edit');
      }
      return this.sourceItems;
    },

    openGallery() {
      this.gallery.open = true;
      void this.fetchSources();
    },

    closeGallery() {
      this.gallery.open = false;
    },

    galleryCardTitle(item) {
      const slug = item.animation_slug || '';
      const act = this.catalog.animations.find((a) => a.slug === slug);
      if (item.source_kind === 'edit') return act?.menu_name || slug || 'Edit';
      return act?.menu_name || slug || item.prompt_id;
    },

    galleryCardSubtitle(item) {
      if (item.source_kind === 'edit') return 'Edit output';
      const parts = [item.character_slug, item.background_slug].filter(Boolean);
      return parts.join(' · ') || 'Make still';
    },

    animationLabel(slug) {
      const key = (slug || '').trim();
      if (!key) return '—';
      const row =
        this.selectedAnimation?.slug === key
          ? this.selectedAnimation
          : this.catalog.animations.find((a) => a.slug === key);
      return row?.menu_name || key;
    },

    async fetchAnimationBySlug(slug, { resetLoraStrengths = false } = {}) {
      const key = (slug || '').trim();
      if (!key) {
        this.selectedAnimation = null;
        this.syncLorasForModel({ resetStrengths: true });
        return null;
      }
      try {
        const r = await fetch('/api/animations/' + encodeURIComponent(key));
        if (!r.ok) throw new Error('Animation not found');
        const row = await r.json();
        const idx = this.catalog.animations.findIndex((a) => a.slug === key);
        if (idx >= 0) this.catalog.animations[idx] = row;
        else this.catalog.animations.push(row);
        this.selectedAnimation = row;
        this.syncLorasForModel({ resetStrengths: resetLoraStrengths });
        return row;
      } catch (e) {
        this.selectedAnimation = null;
        this.syncLorasForModel({ resetStrengths: true });
        this.showError(e.message || String(e));
        return null;
      }
    },

    animationPickInitial() {
      if (this.form.animation_slug) {
        return (this.animationLabel(this.form.animation_slug) || '?').charAt(0);
      }
      return '—';
    },

    openAnimationPicker() {
      this.animationPickerFilter = '';
      this.animationPickerOpen = true;
    },

    closeAnimationPicker() {
      this.animationPickerOpen = false;
      this.animationPickerFilter = '';
    },

    filteredAnimationPickerOptions() {
      const q = (this.animationPickerFilter || '').trim().toLowerCase();
      const list = this.catalog.animations || [];
      if (!q) return list;
      return list.filter((a) => {
        const hay = [a.menu_name, a.slug].filter(Boolean).join(' ').toLowerCase();
        return hay.includes(q);
      });
    },

    async selectAnimation(slug) {
      this.form.animation_slug = slug || '';
      this.closeAnimationPicker();
      await this.onAnimationSlugChange();
    },

    async onAnimationSlugChange() {
      this.promptFieldsUserEdited = false;
      await this.fetchAnimationBySlug(this.form.animation_slug, {
        resetLoraStrengths: true,
      });
      await this.loadEditPreview({ force: true });
    },

    applyEditSource(record, { promptId, kind } = {}) {
      const pid = (promptId || record?.prompt_id || '').trim();
      if (!pid) return;
      const sourceKind = (kind || record?.source_kind || 'make').trim() || 'make';
      this.selectedSourceId = pid;
      this.selectedSourceKind = sourceKind;
      this.selectedSource = record
        ? { ...record, prompt_id: pid, source_kind: sourceKind }
        : {
            prompt_id: pid,
            source_kind: sourceKind,
            image_url: '',
          };
    },

    editSourceThumbUrl() {
      return this.selectedSource?.image_url || '';
    },

    editSourceInitial() {
      if (!this.selectedSourceId) return '+';
      return (this.editSourceCardTitle() || '?').charAt(0);
    },

    editSourceCardTitle() {
      if (!this.selectedSourceId) return 'Pick a source image';
      if (this.selectedSource?.image_url) {
        return this.galleryCardTitle(this.selectedSource);
      }
      return this.selectedSourceKind === 'edit' ? 'Edit output' : 'Make still';
    },

    editSourceCardSubtitle() {
      if (!this.selectedSourceId) return 'Make stills or previous edits';
      const kindLabel =
        this.selectedSourceKind === 'edit' ? 'Edit output' : 'Make still';
      if (!this.selectedSource) return kindLabel;
      const detail = this.galleryCardSubtitle(this.selectedSource);
      return detail ? `${kindLabel} · ${detail}` : kindLabel;
    },

    async selectSource(item) {
      if (!item?.prompt_id) return;
      this.applyEditSource(item, {
        promptId: item.prompt_id,
        kind: item.source_kind || 'make',
      });
      this.selectedHistoryId = null;
      this.previewResultUrl = null;
      this.lastEditImageUrl = null;
      this.closeGallery();
      const initialAnim = (item.animation_slug || '').trim();
      this.form.animation_slug = initialAnim;
      this.promptFieldsUserEdited = false;
      await this.fetchAnimationBySlug(initialAnim, { resetLoraStrengths: true });
      await this.loadEditPreview({ force: true });
      this.resetImageEdits?.();
      this.$nextTick(() => this.onViewportResize());
    },

    sourcePreviewImageUrl() {
      if (this.previewResultUrl) return this.previewResultUrl;
      return this.editSourceThumbUrl();
    },

    showSourcePicker() {
      return !this.selectedSourceId && !this.previewResultUrl;
    },

    animationForSource() {
      return this.selectedAnimation;
    },
  };
}

/** Animate Lab — source picker from Make outputs + animation selection. */

function animateSourcesMethods() {
  return {
    catalog: { animations: [] },
    sourceItems: [],
    selectedSource: null,
    selectedSourceId: null,
    selectedAnimation: null,
    gallery: { open: false, loading: false },

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
        const r = await fetch(
          '/api/make/history?limit=' + ANIMATE_LAB_SOURCES_LIMIT
        );
        const data = await r.json();
        this.sourceItems = Array.isArray(data.items) ? data.items : [];
      } catch {
        this.sourceItems = [];
        this.showError('Could not load Make gallery.');
      } finally {
        this.gallery.loading = false;
      }
    },

    openGallery() {
      if (this.previewVideoUrl) return;
      this.gallery.open = true;
      void this.fetchSources();
    },

    closeGallery() {
      this.gallery.open = false;
    },

    galleryCardTitle(item) {
      const slug = item.animation_slug || '';
      const act = this.catalog.animations.find((a) => a.slug === slug);
      return act?.menu_name || slug || item.prompt_id;
    },

    galleryCardSubtitle(item) {
      const parts = [item.character_slug, item.background_slug].filter(Boolean);
      return parts.join(' · ');
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

    async fetchAnimationBySlug(slug) {
      const key = (slug || '').trim();
      if (!key) {
        this.selectedAnimation = null;
        this.syncLorasForModel();
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
        this.syncLorasForModel();
        return row;
      } catch (e) {
        this.selectedAnimation = null;
        this.syncLorasForModel();
        this.showError(e.message || String(e));
        return null;
      }
    },

    async onAnimationSlugChange() {
      this.promptFieldsUserEdited = false;
      await this.fetchAnimationBySlug(this.form.animation_slug);
      await this.loadLtxPreview({ force: true });
    },

    async selectSource(item) {
      if (!item?.prompt_id) return;
      this.selectedSource = item;
      this.selectedSourceId = item.prompt_id;
      this.previewVideoUrl = null;
      this.closeGallery();
      const initialAnim = (item.animation_slug || '').trim();
      this.form.animation_slug = initialAnim;
      this.promptFieldsUserEdited = false;
      await this.fetchAnimationBySlug(initialAnim);
      await this.loadLtxPreview({ force: true });
      this.$nextTick(() => this.onViewportResize());
    },

    sourcePreviewImageUrl() {
      if (this.previewVideoUrl) return '';
      return this.selectedSource?.image_url || '';
    },

    showSourcePicker() {
      return !this.previewVideoUrl;
    },

    animationForSource() {
      return this.selectedAnimation;
    },
  };
}

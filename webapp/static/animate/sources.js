/** Animate Lab — source picker from Make outputs. */

function animateSourcesMethods() {
  return {
    catalog: { animations: [] },
    sourceItems: [],
    selectedSource: null,
    selectedSourceId: null,
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

    async selectSource(item) {
      if (!item?.prompt_id) return;
      this.selectedSource = item;
      this.selectedSourceId = item.prompt_id;
      this.previewVideoUrl = null;
      this.closeGallery();
      this.syncLorasForModel();
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
      const slug = this.selectedSource?.animation_slug || '';
      if (!slug) return null;
      return this.catalog.animations.find((a) => a.slug === slug) || null;
    },
  };
}

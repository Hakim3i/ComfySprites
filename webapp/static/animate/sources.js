/** Animate Lab — source frames (start / end) + animation selection. */

function animateSourcesMethods() {
  return {
    catalog: { animations: [], styles: [] },
    sourceItems: [],
    selectedStartSource: null,
    selectedStartSourceId: null,
    selectedStartSourceKind: 'make',
    selectedEndSource: null,
    selectedEndSourceId: null,
    selectedEndSourceKind: 'make',
    selectedAnimation: null,
    selectedStyle: null,
    gallery: { open: false, loading: false, target: 'start', tab: 'all' },
    animationPickerOpen: false,
    animationPickerFilter: '',
    stylePickerOpen: false,
    stylePickerFilter: '',

    async loadCatalog() {
      try {
        const [animRes, styleRes] = await Promise.all([
          fetch('/api/animations'),
          fetch('/api/styles'),
        ]);
        const animData = await animRes.json();
        const styleData = await styleRes.json();
        this.catalog.animations = Array.isArray(animData) ? animData : animData.items || [];
        this.catalog.styles = Array.isArray(styleData) ? styleData : styleData.items || [];
      } catch {
        this.catalog.animations = [];
        this.catalog.styles = [];
      }
    },

    async fetchSources() {
      this.gallery.loading = true;
      try {
        const r = await fetch('/api/edit/sources?limit=' + ANIMATE_LAB_SOURCES_LIMIT);
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
      if (this.gallery.target === 'end') {
        return this.sourceItems;
      }
      const tab = this.gallery.tab || 'all';
      if (tab === 'make') {
        return this.sourceItems.filter((item) => item.source_kind !== 'edit');
      }
      if (tab === 'edit') {
        return this.sourceItems.filter((item) => item.source_kind === 'edit');
      }
      return this.sourceItems;
    },

    openGallery(target = 'start') {
      this.gallery.target = target === 'end' ? 'end' : 'start';
      if (this.gallery.target === 'start') {
        this.gallery.tab = 'all';
      }
      this.gallery.open = true;
      void this.fetchSources();
    },

    closeGallery() {
      this.gallery.open = false;
    },

    galleryDialogTitle() {
      return this.gallery.target === 'end' ? 'Pick ending frame' : 'Source images';
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
          : this.catalog.animations.find((a) => a.slug === slug);
      return row?.menu_name || key;
    },

    styleLabel(slug) {
      const key = (slug || '').trim();
      if (!key) return '— none —';
      const row =
        this.selectedStyle?.slug === key
          ? this.selectedStyle
          : this.catalog.styles.find((s) => s.slug === key);
      return row?.name || row?.display_name || key;
    },

    async fetchStyleBySlug(slug) {
      const key = (slug || '').trim();
      if (!key) {
        this.selectedStyle = null;
        this.syncLorasForModel();
        return null;
      }
      try {
        const r = await fetch('/api/styles/' + encodeURIComponent(key));
        if (!r.ok) throw new Error('Style not found');
        const row = await r.json();
        const idx = this.catalog.styles.findIndex((s) => s.slug === key);
        if (idx >= 0) this.catalog.styles[idx] = row;
        else this.catalog.styles.push(row);
        this.selectedStyle = row;
        this.syncLorasForModel();
        return row;
      } catch (e) {
        this.selectedStyle = null;
        this.syncLorasForModel();
        this.showError(e.message || String(e));
        return null;
      }
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
      await this.fetchAnimationBySlug(this.form.animation_slug);
      await this.loadAnimatePreview({ force: true });
    },

    stylePickInitial() {
      if (this.form.style_slug) {
        return (this.styleLabel(this.form.style_slug) || '?').charAt(0);
      }
      return '—';
    },

    openStylePicker() {
      this.stylePickerFilter = '';
      this.stylePickerOpen = true;
    },

    closeStylePicker() {
      this.stylePickerOpen = false;
      this.stylePickerFilter = '';
    },

    filteredStylePickerOptions() {
      const q = (this.stylePickerFilter || '').trim().toLowerCase();
      const list = this.catalog.styles || [];
      if (!q) return list;
      return list.filter((s) => {
        const hay = [s.name, s.display_name, s.slug].filter(Boolean).join(' ').toLowerCase();
        return hay.includes(q);
      });
    },

    async selectStyle(slug) {
      this.form.style_slug = slug || '';
      this.closeStylePicker();
      await this.onStyleSlugChange();
    },

    async onStyleSlugChange() {
      this.promptFieldsUserEdited = false;
      await this.fetchStyleBySlug(this.form.style_slug);
      await this.loadAnimatePreview({ force: true });
    },

    applyFrameSource(slot, record, { promptId, kind } = {}) {
      const pid = (promptId || record?.prompt_id || '').trim();
      if (!pid) return;
      const sourceKind = (kind || record?.source_kind || 'make').trim() || 'make';
      const row = record
        ? { ...record, prompt_id: pid, source_kind: sourceKind }
        : { prompt_id: pid, source_kind: sourceKind, image_url: '' };
      if (slot === 'end') {
        this.selectedEndSourceId = pid;
        this.selectedEndSourceKind = sourceKind;
        this.selectedEndSource = row;
        return;
      }
      this.selectedStartSourceId = pid;
      this.selectedStartSourceKind = sourceKind;
      this.selectedStartSource = row;
    },

    applyStartSource(item, opts) {
      this.applyFrameSource('start', item, opts);
    },

    applyEndSource(item, opts) {
      this.applyFrameSource('end', item, opts);
    },

    clearEndSource() {
      this.selectedEndSource = null;
      this.selectedEndSourceId = null;
      this.selectedEndSourceKind = 'make';
    },

    dualFrameSelected() {
      return Boolean(this.selectedStartSourceId && this.selectedEndSourceId);
    },

    frameKind(slot) {
      return slot === 'end' ? this.selectedEndSourceKind : this.selectedStartSourceKind;
    },

    frameThumbUrl(slot) {
      const row = slot === 'end' ? this.selectedEndSource : this.selectedStartSource;
      return row?.image_url || '';
    },

    frameCardTitle(slot) {
      const id = slot === 'end' ? this.selectedEndSourceId : this.selectedStartSourceId;
      const row = slot === 'end' ? this.selectedEndSource : this.selectedStartSource;
      if (!id) {
        return slot === 'end' ? 'Pick ending frame (optional)' : 'Pick a source image';
      }
      if (row?.image_url) return this.galleryCardTitle(row);
      return this.frameKind(slot) === 'edit' ? 'Edit output' : 'Make still';
    },

    frameCardSubtitle(slot) {
      const id = slot === 'end' ? this.selectedEndSourceId : this.selectedStartSourceId;
      const row = slot === 'end' ? this.selectedEndSource : this.selectedStartSource;
      if (!id) {
        return slot === 'end'
          ? 'Optional — anchors the last video frame'
          : 'Make stills or previous edits';
      }
      const kindLabel = this.frameKind(slot) === 'edit' ? 'Edit output' : 'Make still';
      if (!row) return kindLabel;
      const detail = this.galleryCardSubtitle(row);
      return detail ? `${kindLabel} · ${detail}` : kindLabel;
    },

    frameCardInitial(slot) {
      const id = slot === 'end' ? this.selectedEndSourceId : this.selectedStartSourceId;
      if (!id) return '+';
      return (this.frameCardTitle(slot) || '?').charAt(0);
    },

    async selectSource(item) {
      if (!item?.prompt_id) return;
      const target = this.gallery.target === 'end' ? 'end' : 'start';
      this.closeGallery();

      if (target === 'end') {
        this.applyEndSource(item, {
          promptId: item.prompt_id,
          kind: item.source_kind || 'make',
        });
        this.$nextTick(() => this.onViewportResize());
        return;
      }

      this.applyStartSource(item, {
        promptId: item.prompt_id,
        kind: item.source_kind || 'make',
      });
      this.previewVideoUrl = null;
      this.selectedHistoryId = null;
      const initialAnim = (item.animation_slug || '').trim();
      const initialStyle = (item.style_slug || '').trim();
      this.form.animation_slug = initialAnim;
      this.form.style_slug = initialStyle;
      this.promptFieldsUserEdited = false;
      await Promise.all([
        this.fetchAnimationBySlug(initialAnim),
        this.fetchStyleBySlug(initialStyle),
      ]);
      await this.loadAnimatePreview({ force: true });
      this.$nextTick(() => this.onViewportResize());
    },

    sourcePreviewImageUrl() {
      if (this.previewVideoUrl) return '';
      return this.frameThumbUrl('start');
    },

    showSourcePicker() {
      return !this.selectedStartSourceId && !this.previewVideoUrl;
    },

    animationForSource() {
      return this.selectedAnimation;
    },

    styleForSource() {
      return this.selectedStyle;
    },
  };
}

/** Animate Lab — Alpine factory. */

function animateLab() {
  return {
    ...labHistoryScrollMethods(ANIMATE_LAB_BREAKPOINT_NARROW),
    ...animateModelsMethods(),
    ...animateSourcesMethods(),
    ...animateSettingsMethods(),
    ...animatePreviewMethods(),
    ...animateHistoryMethods(),

    loadError: '',
    error: '',
    errorOpen: false,

    comfyuiState: 'offline',
    comfyuiPendingCount: 0,
    comfyuiStatusError: '',

    init() {
      void this.loadAll();
      if (typeof window.startComfyuiStatusPoll === 'function') {
        window.startComfyuiStatusPoll(this, { lab: ANIMATE_LAB_COMFYUI_LAB });
      }
      if (typeof window !== 'undefined') {
        this._boundWindowResize = () => this.onViewportResize();
        window.addEventListener('resize', this._boundWindowResize);
      }
      this.$nextTick(() => this.onViewportResize());
      return () => {
        if (typeof window.stopComfyuiStatusPoll === 'function') {
          window.stopComfyuiStatusPoll();
        }
        if (typeof window !== 'undefined' && this._boundWindowResize) {
          window.removeEventListener('resize', this._boundWindowResize);
        }
      };
    },

    async loadAll() {
      try {
        await Promise.all([
          this.loadDiffusionModels(),
          this.loadCatalog(),
          this.loadHistory(),
        ]);
        this.loadError = '';
      } catch {
        this.loadError = 'Could not load Animate Lab data.';
      }
    },

    showError(message) {
      this.error = message || 'Something went wrong.';
      this.errorOpen = true;
    },

    closeErrorModal() {
      this.errorOpen = false;
    },

    closeTopModal() {
      if (this.errorOpen) {
        this.closeErrorModal();
        return;
      }
      if (this.modelPickerOpen) {
        this.closeModelPicker();
        return;
      }
      if (this.gallery.open) {
        this.closeGallery();
      }
    },

    comfyuiStatusLabel() {
      if (this.comfyuiState === 'idle') return 'Idle';
      if (this.comfyuiState === 'offline') return 'Not connected';
      return this.comfyuiState;
    },

    thumbStyle(image) {
      return image
        ? "background-image:url('" + String(image).replace(/'/g, '%27') + "')"
        : '';
    },
  };
}

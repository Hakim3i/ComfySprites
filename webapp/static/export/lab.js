/** Export Lab — Alpine factory. */

function exportLab() {
  return {
    ...exportLibraryMethods(),
    ...exportFramesMethods(),
    ...exportEditorMethods(),
    ...exportFrameEditMethods(),
    ...exportRmbgMethods(),
    ...exportExportMethods(),

    form: { ...EXPORT_FORM_DEFAULTS },

    loadError: '',
    error: '',
    errorOpen: false,

    comfyuiState: 'offline',
    comfyuiPendingCount: 0,
    comfyuiStatusError: '',
    comfyuiResources: {
      cpu_pct: null,
      ram_pct: null,
      gpu_pct: null,
      vram_pct: null,
    },

    init() {
      void this.loadVideos();
      if (typeof window.startComfyuiStatusPoll === 'function') {
        window.startComfyuiStatusPoll(this, { lab: EXPORT_LAB_COMFYUI_LAB });
      }
      return () => {
        this.stopPlayback();
        if (typeof window.stopComfyuiStatusPoll === 'function') {
          window.stopComfyuiStatusPoll();
        }
      };
    },

    comfyuiAnyJobActive() {
      return this.rmbgRunning;
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
      if (this.confirmDeleteId) {
        this.cancelDeleteVideo();
        return;
      }
      if (this.videoPickerOpen) {
        this.closeVideoPicker();
      }
    },
  };
}

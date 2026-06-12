/** Animate Lab — diffusion model picker. */

function animateModelsMethods() {
  return {
    diffusionModels: [],
    modelPickerOpen: false,

    selectedDiffusionModel() {
      const id = (this.form.model_id || '').trim();
      return this.diffusionModels.find((m) => m.id === id) || null;
    },

    async loadDiffusionModels() {
      try {
        const r = await fetch('/api/diffusion-models');
        const data = await r.json();
        const all = Array.isArray(data.models) ? data.models : [];
        this.diffusionModels = all.filter((m) =>
          ANIMATE_VIDEO_ENGINES.includes(m.engine)
        );
        const cur = (this.form.model_id || '').trim();
        if (cur && !this.diffusionModels.some((m) => m.id === cur)) {
          this.form.model_id = '';
        }
        if (!this.form.model_id) {
          const def = (data.default_id || '').trim();
          const hit =
            this.diffusionModels.find((m) => m.id === 'ltx23_eros') ||
            this.diffusionModels.find((m) => m.id === def) ||
            this.diffusionModels.find((m) => m.is_default) ||
            this.diffusionModels[0];
          if (hit) this.setDiffusionModel(hit.id);
        }
      } catch {
        this.diffusionModels = [];
      }
    },

    setDiffusionModel(modelId) {
      const hit = this.diffusionModels.find((m) => m.id === modelId);
      if (!hit) return;
      this.form.model_id = hit.id;
      const defaults = hit.default_settings || {};
      if (defaults.length_seconds != null) {
        this.form.length_seconds = String(defaults.length_seconds);
      }
      if (defaults.fps != null) this.form.fps = String(defaults.fps);
      if (defaults.cfg != null) this.form.cfg = String(defaults.cfg);
      if (defaults.steps != null) this.form.steps = String(defaults.steps);
      if (defaults.shift != null) this.form.shift = String(defaults.shift);
      this.modelPickerOpen = false;
      this.syncLorasForModel();
      void this.loadAnimatePreview?.();
    },

    openModelPicker() {
      this.modelPickerOpen = true;
    },

    closeModelPicker() {
      this.modelPickerOpen = false;
    },

    modelPickerLabel() {
      return this.selectedDiffusionModel()?.label || 'Select diffusion model';
    },

    selectedEngine() {
      return this.selectedDiffusionModel()?.engine || '';
    },

    isLtxModelSelected() {
      return this.selectedEngine() === 'ltx23';
    },

    isWanModelSelected() {
      return this.selectedEngine() === 'wan22';
    },
  };
}

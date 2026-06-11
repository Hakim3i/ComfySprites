/** Edit Lab — diffusion model picker (Qwen edit only). */

function editModelsMethods() {
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
        this.diffusionModels = all.filter((m) => m.engine === 'qwen_edit');
        if (!this.form.model_id) {
          const def = (data.default_id || '').trim();
          const hit =
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
      if (defaults.steps != null) this.form.steps = String(defaults.steps);
      if (defaults.cfg != null) this.form.cfg = String(defaults.cfg);
      if (defaults.shift != null) this.form.shift = String(defaults.shift);
      if (defaults.image_strength != null) {
        this.form.image_strength = String(defaults.image_strength);
      }
      this.modelPickerOpen = false;
      this.syncLorasForModel();
      void this.loadEditPreview?.({ force: true });
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

    activeLoraRoles() {
      const roles = this.selectedDiffusionModel()?.lora_roles;
      return Array.isArray(roles) ? roles : ['qwen_edit'];
    },

    loraRoleLabel(role) {
      return EDIT_LORA_ROLE_LABELS[role] || role;
    },

    isQwenEditModelSelected() {
      return this.selectedDiffusionModel()?.engine === 'qwen_edit';
    },
  };
}

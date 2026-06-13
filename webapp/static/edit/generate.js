/** Edit Lab — Qwen edit generate. */

function editGenerateMethods() {
  return {
    buildEditPayload() {
      const loras = [];
      for (const role of this.visibleLoraRoles()) {
        const lora = this.resolvedLoras[role];
        if (!lora?.filename) continue;
        loras.push({
          kind: role,
          filename: lora.filename,
          name: lora.name || lora.filename,
          strength: this.loraStrength(role),
          download_url: lora.download_url || null,
          download_fallback_url: lora.download_fallback_url || null,
          version_id: lora.version_id ?? null,
          model_id: lora.model_id ?? null,
        });
      }
      const animationSlug = (this.form.animation_slug || '').trim();
      const source = this.resolveEditJobSource();
      return {
        source_prompt_id: source.source_prompt_id,
        source_kind: source.source_kind,
        animation_slug: animationSlug || null,
        model_id: this.form.model_id,
        seed: parseInt(this.form.seed, 10),
        steps: parseInt(this.form.steps, 10) || 4,
        cfg: parseFloat(this.form.cfg) || 1,
        shift: parseFloat(this.form.shift) || 3.1,
        image_strength: parseFloat(this.form.image_strength) || 1,
        lora_strengths: { ...(this.form.lora_strengths || {}) },
        loras,
        qwen_edit_prompt: this.promptFieldsUserEdited
          ? (this.form.qwen_edit_prompt || '').trim() || null
          : null,
        qwen_edit_negative: this.promptFieldsUserEdited
          ? (this.form.qwen_edit_negative || '').trim() || null
          : null,
      };
    },

    generateButtonLabel() {
      if (this.comfyuiInferenceActive()) return 'Stop';
      if (this.generating) return 'Generating…';
      return 'Generate';
    },

    generateDisabled() {
      if (this.comfyuiInferenceActive()) return false;
      if (!this.selectedSourceId) return true;
      if (!this.isQwenEditModelSelected()) return true;
      return (
        (this.generating && !this.comfyuiAnyJobActive()) ||
        this.comfyuiState === 'offline'
      );
    },

    onGenerateClick() {
      if (this.comfyuiInferenceActive()) {
        void this.stopGeneration();
        return;
      }
      if (this.generateDisabled()) return;
      void this.submitEditGeneration();
    },

    async submitEditGeneration() {
      this.error = '';
      this.generating = true;
      try {
        const payload = this.buildEditPayload();
        const r = await fetch('/api/edit/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await r.json();
        if (!r.ok) {
          throw new Error(
            (data && (data.detail || data.error)) || 'Generate failed (' + r.status + ')'
          );
        }
        const promptId = data.prompt_id;
        if (!promptId) throw new Error('No prompt_id in response');
        this.startComfyuiJobPoll(promptId);
      } catch (e) {
        this.generating = false;
        this.showError(e.message || String(e));
      }
    },
  };
}

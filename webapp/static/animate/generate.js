/** Animate Lab — LTX generate. */

function animateGenerateMethods() {
  return {
    buildAnimatePayload() {
      const strengths = { ...(this.form.lora_strengths || {}) };
      const loras = [];
      for (const role of this.visibleLoraRoles()) {
        const lora = this.resolvedLoras[role];
        if (!lora?.filename) continue;
        loras.push({
          kind: role,
          filename: lora.filename,
          name: lora.name || lora.filename,
          strength: this.loraStrength(role),
        });
      }
      const animationSlug = (this.form.animation_slug || '').trim();
      return {
        source_prompt_id: this.selectedSource?.prompt_id,
        animation_slug: animationSlug || null,
        model_id: this.form.model_id,
        seed: parseInt(this.form.seed, 10),
        length_seconds: parseInt(this.form.length_seconds, 10) || 5,
        fps: parseInt(this.form.fps, 10) || 24,
        cfg: parseFloat(this.form.cfg) || 1,
        lora_strengths: strengths,
        loras,
        ltx_caption: this.promptFieldsUserEdited
          ? (this.form.ltx_caption || '').trim() || null
          : null,
        ltx_video_negative: this.promptFieldsUserEdited
          ? (this.form.ltx_video_negative || '').trim() || null
          : null,
        ltx_audio_negative: this.promptFieldsUserEdited
          ? (this.form.ltx_audio_negative || '').trim() || null
          : null,
        use_sulphur_experimental_lora: true,
      };
    },

    generateButtonLabel() {
      if (this.comfyuiInferenceActive()) return 'Stop';
      if (this.generating) return 'Generating…';
      return 'Generate';
    },

    generateDisabled() {
      if (this.comfyuiInferenceActive()) return false;
      if (!this.selectedSource?.prompt_id) return true;
      if (!this.isLtxModelSelected()) return true;
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
      void this.submitAnimateGeneration();
    },

    async submitAnimateGeneration() {
      this.error = '';
      this.generating = true;
      try {
        const payload = this.buildAnimatePayload();
        const r = await fetch('/api/animate/generate', {
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

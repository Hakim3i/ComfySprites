/** Animate Lab — prompt preview and overrides. */

function animatePromptsMethods() {
  return {
    promptFieldsUserEdited: false,
    inheritedLtx: {
      ltx_caption: '',
    },

    applyLtxPreviewFields(data) {
      const caption = data.ltx_caption || data.positive || '';
      this.form.ltx_caption = caption;
      this.inheritedLtx = { ltx_caption: caption };
    },

    async loadAnimatePreview({ force = false } = {}) {
      const pid = this.selectedStartSource?.prompt_id;
      const modelId = (this.form.model_id || '').trim();
      if (!pid || !modelId) {
        return;
      }
      const params = new URLSearchParams({
        source_prompt_id: pid,
        source_kind: this.selectedStartSourceKind || 'make',
        animation_slug: (this.form.animation_slug || '').trim(),
        model_id: modelId,
      });
      const styleSlug = (this.form.style_slug || '').trim();
      if (styleSlug) params.set('style_slug', styleSlug);
      try {
        const r = await fetch('/api/animate/prompt-preview?' + params.toString());
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || 'Preview failed');
        if (force || !this.promptFieldsUserEdited) {
          this.applyLtxPreviewFields(data);
        } else {
          this.inheritedLtx = {
            ltx_caption: data.ltx_caption || data.positive || '',
          };
        }
      } catch (e) {
        this.showError(e.message || String(e));
      }
    },

    onPromptFieldInput() {
      this.promptFieldsUserEdited = true;
    },

    resetPromptFields() {
      this.promptFieldsUserEdited = false;
      this.form.ltx_caption = this.inheritedLtx.ltx_caption || '';
    },
  };
}

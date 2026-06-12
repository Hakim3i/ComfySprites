/** Edit Lab — Qwen edit prompt preview and overrides. */

function editPromptsMethods() {
  return {
    promptFieldsUserEdited: false,
    inheritedEdit: {
      qwen_edit_prompt: '',
    },

    applyEditPreviewFields(data) {
      const prompt = data.qwen_edit_prompt || '';
      this.form.qwen_edit_prompt = prompt;
      this.inheritedEdit = { qwen_edit_prompt: prompt };
    },

    syncPromptFromAnimation() {
      if (!this.isQwenEditModelSelected()) return;
      const prompt = (this.selectedAnimation?.qwen_edit_prompt || '').trim();
      if (!this.promptFieldsUserEdited) {
        this.form.qwen_edit_prompt = prompt;
        this.inheritedEdit = { qwen_edit_prompt: prompt };
      }
    },

    async loadEditPreview({ force = false } = {}) {
      const pid = this.selectedSourceId;
      if (!this.isQwenEditModelSelected()) return;
      if (!pid) {
        if (force || !this.promptFieldsUserEdited) {
          this.syncPromptFromAnimation();
        }
        return;
      }
      const params = new URLSearchParams({
        source_prompt_id: pid,
        source_kind: this.selectedSourceKind || 'make',
        animation_slug: (this.form.animation_slug || '').trim(),
      });
      try {
        const r = await fetch('/api/edit/preview?' + params.toString());
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || 'Preview failed');
        if (data.build && this.selectedSource) {
          this.selectedSource = { ...this.selectedSource, build: data.build };
        }
        if (force || !this.promptFieldsUserEdited) {
          this.applyEditPreviewFields(data);
        } else {
          this.inheritedEdit = { qwen_edit_prompt: data.qwen_edit_prompt || '' };
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
      this.form.qwen_edit_prompt = this.inheritedEdit.qwen_edit_prompt || '';
    },
  };
}

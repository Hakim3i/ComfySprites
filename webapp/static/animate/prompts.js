/** Animate Lab — LTX prompt preview and overrides. */

function animatePromptsMethods() {
  return {
    promptFieldsUserEdited: false,
    inheritedLtx: {
      ltx_caption: '',
      ltx_video_negative: '',
      ltx_audio_negative: '',
    },

    applyLtxPreviewFields(data) {
      const caption = data.ltx_caption || '';
      const videoNeg = data.ltx_video_negative || '';
      const audioNeg = data.ltx_audio_negative || '';
      this.form.ltx_caption = caption;
      this.form.ltx_video_negative = videoNeg;
      this.form.ltx_audio_negative = audioNeg;
      this.inheritedLtx = {
        ltx_caption: caption,
        ltx_video_negative: videoNeg,
        ltx_audio_negative: audioNeg,
      };
    },

    async loadLtxPreview({ force = false } = {}) {
      const pid = this.selectedSource?.prompt_id;
      if (!pid || !this.isLtxModelSelected()) {
        return;
      }
      const params = new URLSearchParams({
        source_prompt_id: pid,
        animation_slug: (this.form.animation_slug || '').trim(),
      });
      try {
        const r = await fetch('/api/animate/ltx-preview?' + params.toString());
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || 'Preview failed');
        if (force || !this.promptFieldsUserEdited) {
          this.applyLtxPreviewFields(data);
        } else {
          this.inheritedLtx = {
            ltx_caption: data.ltx_caption || '',
            ltx_video_negative: data.ltx_video_negative || '',
            ltx_audio_negative: data.ltx_audio_negative || '',
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
      this.form.ltx_video_negative = this.inheritedLtx.ltx_video_negative || '';
      this.form.ltx_audio_negative = this.inheritedLtx.ltx_audio_negative || '';
    },
  };
}

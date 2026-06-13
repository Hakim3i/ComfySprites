/** Make Lab — ControlNet preprocessor from preview. */

function makeControlnetMethods() {
  const panZoom = typeof panZoomPreviewMethods === 'function'
    ? panZoomPreviewMethods({
        stageRef: 'cnPreprocessStage',
        wrapClass: 'make-cn-preprocess-zoom-wrap',
        imgClass: 'make-cn-preprocess-img',
        exportFill: '#000000',
      })
    : {};

  return {
    ...panZoom,
    cnPreprocessViewportTick: 0,
    controlnetPreprocess: {
      open: false,
      busy: false,
      key: '',
      label: '',
      previewUrl: '',
      previewBlob: null,
    },
    _controlnetPreprocessStartedAt: 0,

    controlnetPreprocessActive() {
      const s = this.controlnetPreprocess;
      return Boolean(s?.busy && !s?.open);
    },

    controlnetPreprocessSaving() {
      const s = this.controlnetPreprocess;
      return Boolean(s?.busy && s?.open);
    },

    controlnetPreprocessBusy() {
      return Boolean(this.controlnetPreprocess?.busy);
    },

    _beginControlnetPreprocessStatus(label) {
      this.comfyuiState = 'generating';
      this.comfyuiPhaseLabel = 'ControlNet — ' + (label || '');
      this.comfyuiProgressPct = 0;
      this.comfyuiProgressActive = true;
      this._controlnetPreprocessStartedAt = Date.now();
      if (typeof window.startComfyuiExecutionClock === 'function') {
        window.startComfyuiExecutionClock(this);
      }
      if (typeof window.bumpComfyuiExecutionTick === 'function') {
        window.bumpComfyuiExecutionTick(this);
      }
    },

    _endControlnetPreprocessStatus() {
      if (this.controlnetPreprocessBusy()) return;
      this.comfyuiPhaseLabel = '';
      this.comfyuiProgressActive = false;
      if (this._controlnetPreprocessStartedAt) {
        this.comfyuiLastExecutionMs = Date.now() - this._controlnetPreprocessStartedAt;
        this._controlnetPreprocessStartedAt = 0;
      }
      if (typeof window.stopComfyuiExecutionClock === 'function') {
        window.stopComfyuiExecutionClock(this);
      }
      if (!this.comfyuiAnyJobActive?.()) {
        void this.refreshComfyuiStatus?.();
      }
    },

    controlnetPreprocessEnabled(key) {
      if (!this.outputImage || this.controlnetPreprocessBusy()) return false;
      if (this.comfyuiInferenceActive?.() && !this.controlnetPreprocessActive()) {
        return false;
      }
      const slug = (this.resolvedFieldValue('animation') || '').trim();
      if (!slug || slug.toLowerCase() === 'none') return false;
      return Boolean(key);
    },

    closeControlnetPreprocessModal() {
      if (this.controlnetPreprocess.busy) return;
      if (this.controlnetPreprocess.previewUrl?.startsWith('blob:')) {
        URL.revokeObjectURL(this.controlnetPreprocess.previewUrl);
      }
      this.controlnetPreprocess = {
        open: false,
        busy: false,
        key: '',
        label: '',
        previewUrl: '',
        previewBlob: null,
      };
      this.resetPanZoomView?.();
      this.panZoomGridVisible = false;
    },

    cnPreprocessStageBox() {
      void this.cnPreprocessViewportTick;
      const img = this.$refs.cnPreprocessStage?.querySelector('.make-cn-preprocess-img');
      let w = 768;
      let h = 1280;
      if (img?.naturalWidth > 0 && img?.naturalHeight > 0) {
        w = img.naturalWidth;
        h = img.naturalHeight;
      }
      const maxW = Math.min(600, (typeof window !== 'undefined' ? window.innerWidth : 800) * 0.88);
      const maxH = Math.min(
        (typeof window !== 'undefined' ? window.innerHeight : 900) * 0.48,
        480
      );
      const scale = Math.min(maxW / w, maxH / h, 1);
      return {
        boxW: Math.max(1, Math.floor(w * scale)),
        boxH: Math.max(1, Math.floor(h * scale)),
      };
    },

    cnPreprocessStageStyle() {
      const { boxW, boxH } = this.cnPreprocessStageBox();
      return {
        width: boxW + 'px',
        height: boxH + 'px',
        maxWidth: '100%',
        margin: '0 auto',
      };
    },

    onCnPreprocessImageLoaded() {
      this.cnPreprocessViewportTick += 1;
      this.$nextTick(() => this.applyPanZoomTransform?.());
    },

    _openControlnetPreprocessModal(key, label, previewUrl, previewBlob) {
      this.controlnetPreprocess = {
        open: true,
        busy: false,
        key,
        label,
        previewUrl,
        previewBlob,
      };
      this.$nextTick(() => {
        this.resetPanZoomView?.();
        this.bindPanZoomView?.();
        this.applyPanZoomTransform?.();
      });
    },

    async runControlnetPreprocess(key) {
      if (!this.controlnetPreprocessEnabled(key)) return;
      const row = this.controlnetRowByKey(key);
      const label = row?.label || key;
      this.controlnetPreprocess.busy = true;
      this.error = '';
      this._beginControlnetPreprocessStatus(label);
      try {
        const blob = await this.resolvePreviewImageBlob();
        const fd = new FormData();
        fd.append('controlnet_type', key);
        fd.append('file', blob, 'source.png');
        const r = await fetch('/api/make/controlnet/preprocess', {
          method: 'POST',
          body: fd,
        });
        const { data } = await parseApiResponse(r);
        if (!r.ok) {
          this.error = apiErrorDetail(data, r.status, 'ControlNet preprocess failed');
          return;
        }
        const dataUrl = data.image_data_url || '';
        if (!dataUrl) {
          this.error = 'Preprocessor returned no image.';
          return;
        }
        const res = await fetch(dataUrl);
        const outBlob = await res.blob();
        if (!outBlob.size) {
          this.error = 'Preprocessor image is empty.';
          return;
        }
        const previewUrl = URL.createObjectURL(outBlob);
        this._openControlnetPreprocessModal(
          key,
          data.label || label,
          previewUrl,
          outBlob
        );
      } catch (e) {
        this.error = 'ControlNet preprocess failed (' + e.message + ').';
      } finally {
        this.controlnetPreprocess.busy = false;
        this._endControlnetPreprocessStatus();
      }
    },

    async confirmControlnetPreprocess() {
      const state = this.controlnetPreprocess;
      if (!state.open || !state.key || !state.previewUrl) return;
      const slug = (this.resolvedFieldValue('animation') || '').trim();
      if (!slug) return;
      state.busy = true;
      this.error = '';
      try {
        const blob = await this.renderPanZoomToBlob?.();
        if (!blob?.size) {
          this.error = 'Could not render ControlNet map.';
          return;
        }
        const fd = new FormData();
        fd.append('file', blob, `controlnet_${state.key}.png`);
        const enc = encodeURIComponent;
        const r = await fetch(
          `/api/animations/${enc(slug)}/controlnet/${enc(state.key)}/image`,
          { method: 'POST', body: fd }
        );
        const { data } = await parseApiResponse(r);
        if (!r.ok) {
          this.error = apiErrorDetail(data, r.status, 'ControlNet upload failed');
          return;
        }
        const anim = this.animationForForm();
        if (anim) {
          anim.controlnets = data.controlnets || anim.controlnets;
        }
        this.loadControlNetFromAnimation();
        this.catalogThumbEpoch = Date.now();
        this.closeControlnetPreprocessModal();
      } catch (e) {
        this.error = 'ControlNet upload failed (' + e.message + ').';
      } finally {
        if (this.controlnetPreprocess.open) {
          this.controlnetPreprocess.busy = false;
        }
      }
    },
  };
}

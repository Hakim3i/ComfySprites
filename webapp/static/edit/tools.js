/** Edit Lab — pan/zoom, filters, overlay, RMBG, canvas save. */

function editToolsMethods() {
  return {
    panOffset: { x: 0, y: 0 },
    isPanning: false,
    panStart: { panX: 0, panY: 0, clientX: 0, clientY: 0 },
    zoomLevel: 1.0,
    panEnabled: false,
    imageEdits: {
      flipX: false,
      flipY: false,
      rotation: 0,
      brightness: 0,
      contrast: 0,
      saturation: 0,
      hue: 0,
    },
    overlayOpacity: 0,
    backgroundMode: 'transparent',
    backgroundColor: '#000000',
    preRmbgImageUrl: null,
    savingCanvas: false,

    initEditTools() {
      this.$nextTick(() => this.bindEditToolEvents());
    },

    bindEditToolEvents() {
      const stage = this.$refs.previewStage;
      if (!stage || stage._editToolsBound) return;
      stage._editToolsBound = true;

      stage.addEventListener('mousedown', (e) => {
        if (!this.panEnabled || !this.lastEditImageUrl) return;
        const img = stage.querySelector('img.edit-preview-img');
        if (!img || (!e.target.closest('.edit-pan-zoom-wrap') && e.target !== img)) return;
        this.isPanning = true;
        this.panStart = {
          panX: this.panOffset.x,
          panY: this.panOffset.y,
          clientX: e.clientX,
          clientY: e.clientY,
        };
        e.preventDefault();
      });

      const onMove = (e) => {
        if (!this.isPanning) return;
        this.panOffset.x = this.panStart.panX + (e.clientX - this.panStart.clientX);
        this.panOffset.y = this.panStart.panY + (e.clientY - this.panStart.clientY);
        this.applyPanTransform();
        e.preventDefault();
      };
      const onUp = () => {
        this.isPanning = false;
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },

    togglePan() {
      this.panEnabled = !this.panEnabled;
    },

    buildFilterCss() {
      const parts = [];
      const e = this.imageEdits;
      if (e.brightness !== 0) parts.push(`brightness(${100 + e.brightness}%)`);
      if (e.contrast !== 0) parts.push(`contrast(${100 + e.contrast}%)`);
      if (e.saturation !== 0) parts.push(`saturate(${100 + e.saturation}%)`);
      if (e.hue !== 0) parts.push(`hue-rotate(${e.hue}deg)`);
      return parts.join(' ');
    },

    applyPanTransform() {
      const stage = this.$refs.previewStage;
      if (!stage) return;
      const wrap = stage.querySelector('.edit-pan-zoom-wrap');
      const mainImg = stage.querySelector('img.edit-preview-img');
      if (!mainImg) return;
      const target = wrap || mainImg;
      let transform = `translate(${this.panOffset.x}px, ${this.panOffset.y}px) scale(${this.zoomLevel})`;
      if (this.imageEdits.flipX) transform += ' scaleX(-1)';
      if (this.imageEdits.flipY) transform += ' scaleY(-1)';
      if (this.imageEdits.rotation !== 0) transform += ` rotate(${this.imageEdits.rotation}deg)`;
      target.style.transform = transform;
      target.style.transformOrigin = 'center center';
      mainImg.style.filter = this.buildFilterCss() || '';
    },

    updatePreviewBackground() {
      const stage = this.$refs.previewStage;
      if (!stage) return;
      stage.style.background =
        this.backgroundMode === 'transparent' ? 'transparent' : this.backgroundColor;
    },

    resetImageEdits() {
      this.imageEdits = {
        flipX: false,
        flipY: false,
        rotation: 0,
        brightness: 0,
        contrast: 0,
        saturation: 0,
        hue: 0,
      };
      this.zoomLevel = 1.0;
      this.panOffset = { x: 0, y: 0 };
      this.panEnabled = false;
      this.applyPanTransform();
    },

    hasVisualEdits() {
      const e = this.imageEdits;
      return (
        e.flipX ||
        e.flipY ||
        e.rotation !== 0 ||
        e.brightness !== 0 ||
        e.contrast !== 0 ||
        e.saturation !== 0 ||
        e.hue !== 0 ||
        this.zoomLevel !== 1.0 ||
        this.panOffset.x !== 0 ||
        this.panOffset.y !== 0
      );
    },

    toggleFlipX() {
      if (!this.lastEditImageUrl) return;
      this.imageEdits.flipX = !this.imageEdits.flipX;
      this.applyPanTransform();
    },

    toggleFlipY() {
      if (!this.lastEditImageUrl) return;
      this.imageEdits.flipY = !this.imageEdits.flipY;
      this.applyPanTransform();
    },

    setRotation(value) {
      if (!this.lastEditImageUrl) return;
      this.imageEdits.rotation = parseInt(value, 10) || 0;
      this.applyPanTransform();
    },

    setFilter(prop, value) {
      if (!this.lastEditImageUrl) return;
      this.imageEdits[prop] = parseInt(value, 10) || 0;
      this.applyPanTransform();
    },

    setZoomPercent(value) {
      if (!this.lastEditImageUrl) return;
      this.zoomLevel = (parseInt(value, 10) || 100) / 100;
      this.applyPanTransform();
    },

    updateSourceOverlay() {
      const stage = this.$refs.previewStage;
      if (!stage) return;
      const opacity = (parseInt(this.overlayOpacity, 10) || 0) / 100;
      const sourceUrl = this.selectedSource?.image_url;
      let overlay = stage.querySelector('.source-overlay');
      if (opacity === 0 || !sourceUrl) {
        if (overlay) overlay.remove();
        return;
      }
      if (!overlay) {
        overlay = document.createElement('img');
        overlay.className = 'source-overlay';
        stage.appendChild(overlay);
      }
      overlay.src = sourceUrl + '?t=' + Date.now();
      overlay.style.opacity = opacity;
    },

    onOverlayInput() {
      this.updateSourceOverlay();
    },

    onBackgroundModeChange() {
      this.updatePreviewBackground();
    },

    async renderEditedImageToCanvas() {
      const stage = this.$refs.previewStage;
      const wrap = stage?.querySelector('.edit-pan-zoom-wrap');
      const previewImg = stage?.querySelector('img.edit-preview-img');
      if (!previewImg || !this.lastEditImageUrl) throw new Error('No image to render');
      await new Promise((resolve, reject) => {
        if (previewImg.complete && previewImg.naturalWidth > 0) resolve();
        else {
          previewImg.onload = resolve;
          previewImg.onerror = reject;
        }
      });
      const width = previewImg.naturalWidth;
      const height = previewImg.naturalHeight;
      const viewEl = wrap || previewImg.parentElement || stage;
      const viewW = viewEl.clientWidth || 1;
      const viewH = viewEl.clientHeight || 1;
      const scaleX = width / viewW;
      const scaleY = height / viewH;
      const panImgX = this.panOffset.x * scaleX;
      const panImgY = this.panOffset.y * scaleY;
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      const bgColor =
        this.backgroundMode === 'transparent' ? null : this.backgroundColor || '#000000';
      if (bgColor) {
        ctx.fillStyle = bgColor;
        ctx.fillRect(0, 0, width, height);
      } else {
        ctx.clearRect(0, 0, width, height);
      }
      ctx.save();
      ctx.translate(width / 2, height / 2);
      if (this.imageEdits.flipX) ctx.scale(-1, 1);
      if (this.imageEdits.flipY) ctx.scale(1, -1);
      if (this.imageEdits.rotation !== 0) {
        ctx.rotate((this.imageEdits.rotation * Math.PI) / 180);
      }
      ctx.scale(this.zoomLevel, this.zoomLevel);
      ctx.translate(panImgX, panImgY);
      const filterCss = this.buildFilterCss();
      if (filterCss) ctx.filter = filterCss;
      ctx.drawImage(previewImg, -width / 2, -height / 2, width, height);
      ctx.restore();
      return canvas.toDataURL('image/png');
    },

    async saveCanvasEdits() {
      if (!this.lastEditImageUrl) {
        this.showError('Generate or pick an image first');
        return;
      }
      if (!this.hasVisualEdits()) {
        this.showError('No visual edits to apply');
        return;
      }
      this.savingCanvas = true;
      try {
        const dataUrl = await this.renderEditedImageToCanvas();
        const r = await fetch('/api/edit/canvas-save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_prompt_id: this.selectedSourceId,
            source_kind: this.selectedSourceKind || 'make',
            image_data_url: dataUrl,
            animation_slug: (this.form.animation_slug || '').trim() || null,
          }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || 'Canvas save failed');
        this.onGenerationComplete?.(data.image_url);
        this.resetImageEdits();
      } catch (e) {
        this.showError(e.message || String(e));
      } finally {
        this.savingCanvas = false;
      }
    },

    async runRemoveBackground() {
      if (!this.lastEditImageUrl) {
        this.showError('No image to process');
        return;
      }
      this.preRmbgImageUrl = this.lastEditImageUrl;
      try {
        let sourcePromptId = this.selectedSourceId;
        let sourceKind = this.selectedSourceKind || 'make';
        if (this.hasVisualEdits()) {
          const dataUrl = await this.renderEditedImageToCanvas();
          const r = await fetch('/api/edit/canvas-save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              source_prompt_id: sourcePromptId,
              source_kind: sourceKind,
              image_data_url: dataUrl,
              animation_slug: (this.form.animation_slug || '').trim() || null,
            }),
          });
          const saved = await r.json();
          if (!r.ok) throw new Error(saved.detail || 'Failed to bake edits before RMBG');
          sourcePromptId = saved.prompt_id;
          sourceKind = 'edit';
          this.resetImageEdits();
        }
        const payload = {
          source_prompt_id: sourcePromptId,
          source_kind: sourceKind,
          animation_slug: (this.form.animation_slug || '').trim() || null,
          background: this.backgroundMode,
          background_color: this.backgroundColor,
        };
        const r = await fetch('/api/edit/rmbg', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || 'RMBG failed');
        this.generating = true;
        this.startComfyuiJobPoll(data.prompt_id);
      } catch (e) {
        this.showError(e.message || String(e));
      }
    },

    restoreBeforeRmbg() {
      if (!this.preRmbgImageUrl) {
        this.showError('Nothing to restore. Run RMBG first.');
        return;
      }
      this.previewResultUrl = this.preRmbgImageUrl;
      this.lastEditImageUrl = this.preRmbgImageUrl;
      this.resetImageEdits();
      this.$nextTick(() => this.updateSourceOverlay());
    },
  };
}

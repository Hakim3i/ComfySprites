/** Shared pan / zoom / rotate preview tools (Edit Lab, Make ControlNet modal). */
(function (global) {
  function panZoomPreviewMethods(options = {}) {
    const stageRef = options.stageRef || 'panZoomStage';
    const wrapClass = options.wrapClass || 'pan-zoom-wrap';
    const imgClass = options.imgClass || 'pan-zoom-img';
    const exportFill = options.exportFill || '#000000';

    return {
      panOffset: { x: 0, y: 0 },
      isPanning: false,
      panStart: { panX: 0, panY: 0, clientX: 0, clientY: 0 },
      zoomLevel: 1.0,
      panEnabled: false,
      rotateEnabled: false,
      isRotating: false,
      rotateStart: { rotation: 0, angle: 0, cx: 0, cy: 0 },
      panZoomFlipX: false,
      panZoomFlipY: false,
      panZoomRotation: 0,
      panZoomGridVisible: false,

      resetPanZoomView() {
        this.panOffset = { x: 0, y: 0 };
        this.zoomLevel = 1.0;
        this.panEnabled = false;
        this.rotateEnabled = false;
        this.isPanning = false;
        this.isRotating = false;
        this.panZoomFlipX = false;
        this.panZoomFlipY = false;
        this.panZoomRotation = 0;
        const stage = this.$refs?.[stageRef];
        const wrap = stage?.querySelector('.' + wrapClass);
        const mainImg = stage?.querySelector('.' + imgClass);
        if (wrap) wrap.style.transform = '';
        if (mainImg) mainImg.style.transform = '';
        this.applyPanZoomTransform();
      },

      togglePanZoomPan() {
        this.panEnabled = !this.panEnabled;
        if (this.panEnabled) this.rotateEnabled = false;
      },

      togglePanZoomRotate() {
        this.rotateEnabled = !this.rotateEnabled;
        if (this.rotateEnabled) this.panEnabled = false;
      },

      togglePanZoomFlipX() {
        this.panZoomFlipX = !this.panZoomFlipX;
        this.applyPanZoomTransform();
      },

      togglePanZoomFlipY() {
        this.panZoomFlipY = !this.panZoomFlipY;
        this.applyPanZoomTransform();
      },

      togglePanZoomGrid() {
        this.panZoomGridVisible = !this.panZoomGridVisible;
      },

      setPanZoomPercent(value) {
        this.zoomLevel = (parseInt(value, 10) || 100) / 100;
        this.applyPanZoomTransform();
      },

      applyPanZoomTransform() {
        const stage = this.$refs?.[stageRef];
        if (!stage) return;
        const wrap = stage.querySelector('.' + wrapClass);
        const mainImg = stage.querySelector('.' + imgClass);
        if (!mainImg) return;
        if (wrap) {
          wrap.style.transform = '';
        }
        let transform = `translate(${this.panOffset.x}px, ${this.panOffset.y}px) scale(${this.zoomLevel})`;
        if (this.panZoomFlipX) transform += ' scaleX(-1)';
        if (this.panZoomFlipY) transform += ' scaleY(-1)';
        if (this.panZoomRotation !== 0) {
          transform += ` rotate(${this.panZoomRotation}deg)`;
        }
        mainImg.style.transform = transform;
        mainImg.style.transformOrigin = 'center center';
      },

      _panZoomFitRect(stageW, stageH, imgW, imgH) {
        const ir = imgW / imgH;
        const cr = stageW / stageH;
        if (ir > cr) {
          const fitW = stageW;
          return { fitW, fitH: stageW / ir };
        }
        const fitH = stageH;
        return { fitW: stageH * ir, fitH };
      },

      bindPanZoomView() {
        const stage = this.$refs?.[stageRef];
        if (!stage || stage._panZoomBound) return;
        stage._panZoomBound = true;

        stage.addEventListener('mousedown', (e) => {
          const img = stage.querySelector('.' + imgClass);
          if (!img || (!e.target.closest('.' + wrapClass) && e.target !== img)) return;

          if (this.rotateEnabled) {
            const rect = img.getBoundingClientRect();
            const cx = rect.left + rect.width / 2;
            const cy = rect.top + rect.height / 2;
            this.isRotating = true;
            this.rotateStart = {
              rotation: this.panZoomRotation,
              angle: (Math.atan2(e.clientY - cy, e.clientX - cx) * 180) / Math.PI,
              cx,
              cy,
            };
            e.preventDefault();
            return;
          }

          if (!this.panEnabled) return;
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
          if (this.isRotating) {
            const { cx, cy, angle, rotation } = this.rotateStart;
            const currentAngle =
              (Math.atan2(e.clientY - cy, e.clientX - cx) * 180) / Math.PI;
            let delta = currentAngle - angle;
            while (delta > 180) delta -= 360;
            while (delta < -180) delta += 360;
            this.panZoomRotation = Math.round(rotation + delta);
            this.applyPanZoomTransform();
            e.preventDefault();
            return;
          }
          if (!this.isPanning) return;
          this.panOffset.x = this.panStart.panX + (e.clientX - this.panStart.clientX);
          this.panOffset.y = this.panStart.panY + (e.clientY - this.panStart.clientY);
          this.applyPanZoomTransform();
          e.preventDefault();
        };
        const onUp = () => {
          this.isPanning = false;
          this.isRotating = false;
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
      },

      async renderPanZoomToBlob() {
        const stage = this.$refs?.[stageRef];
        const previewImg = stage?.querySelector('.' + imgClass);
        if (!previewImg?.src) throw new Error('No image to render');
        await new Promise((resolve, reject) => {
          if (previewImg.complete && previewImg.naturalWidth > 0) resolve();
          else {
            previewImg.onload = resolve;
            previewImg.onerror = () => reject(new Error('Could not load image'));
          }
        });
        const width = previewImg.naturalWidth;
        const height = previewImg.naturalHeight;
        const stageW = stage?.clientWidth || 1;
        const stageH = stage?.clientHeight || 1;
        const scaleX = width / stageW;
        const scaleY = height / stageH;
        const { fitW, fitH } = this._panZoomFitRect(stageW, stageH, width, height);
        const drawW = fitW * scaleX;
        const drawH = fitH * scaleY;
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = exportFill;
        ctx.fillRect(0, 0, width, height);
        ctx.save();
        ctx.translate(width / 2, height / 2);
        const matrixRaw = getComputedStyle(previewImg).transform;
        if (matrixRaw && matrixRaw !== 'none') {
          const m = new DOMMatrixReadOnly(matrixRaw);
          ctx.transform(m.a, m.b, m.c, m.d, m.e * scaleX, m.f * scaleY);
        }
        ctx.drawImage(previewImg, -drawW / 2, -drawH / 2, drawW, drawH);
        ctx.restore();
        return new Promise((resolve, reject) => {
          canvas.toBlob((blob) => {
            if (blob?.size) resolve(blob);
            else reject(new Error('Failed to encode image'));
          }, 'image/png');
        });
      },
    };
  }

  global.panZoomPreviewMethods = panZoomPreviewMethods;
})(window);

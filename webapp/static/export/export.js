/** Export Lab — export settings, layout summary, sprite-sheet / pictures output. */

function exportExportMethods() {
  return {
    exportRunning: false,
    exportProgress: 0,
    exportError: '',
    exportStatus: '',

    columnsValue() {
      const count = this.exportableCount();
      const cols = parseInt(this.form.columns, 10) || 1;
      return Math.max(1, Math.min(cols, Math.max(1, count)));
    },

    summaryRows() {
      const count = this.exportableCount();
      if (count === 0) return 0;
      return Math.ceil(count / this.columnsValue());
    },

    summaryCellSize() {
      let w = 0;
      let h = 0;
      for (const frame of this.exportableFrames()) {
        const size = this.composedFrameSize(frame);
        if (size.w > w) w = size.w;
        if (size.h > h) h = size.h;
      }
      return { w, h };
    },

    summarySheetSize() {
      const cols = this.columnsValue();
      const rows = this.summaryRows();
      const cell = this.summaryCellSize();
      const spacing = Math.max(0, parseInt(this.form.spacing, 10) || 0);
      if (rows === 0) return { w: 0, h: 0 };
      return {
        w: cols * cell.w + (cols - 1) * spacing,
        h: rows * cell.h + (rows - 1) * spacing,
      };
    },

    exportSummaryRows() {
      const count = this.exportableCount();
      if (count === 0) return [];
      const format = exportFormatExt(this.form.format).toUpperCase();
      if (this.form.export_type === 'pictures') {
        return [
          { label: 'Frames', value: String(count) },
          { label: 'Format', value: format },
          { label: 'Output', value: 'ZIP archive' },
        ];
      }
      const cols = this.columnsValue();
      const rows = this.summaryRows();
      const sheet = this.summarySheetSize();
      const cell = this.summaryCellSize();
      const spacing = Math.max(0, parseInt(this.form.spacing, 10) || 0);
      return [
        { label: 'Frames', value: String(count) },
        { label: 'Grid', value: `${cols} × ${rows}` },
        { label: 'Cell', value: `${cell.w} × ${cell.h}px` },
        { label: 'Sheet', value: `${sheet.w} × ${sheet.h}px` },
        { label: 'Spacing', value: `${spacing}px` },
        { label: 'Format', value: format },
      ];
    },

    exportSummaryText() {
      const rows = this.exportSummaryRows();
      if (!rows.length) return 'No exportable frames.';
      return rows.map((r) => `${r.label}: ${r.value}`).join(' · ');
    },

    _canvasToBlob(canvas, format) {
      const mime = exportFormatMime(format);
      const quality = format === 'png' ? undefined : 0.92;
      return new Promise((resolve, reject) => {
        canvas.toBlob(
          (blob) => (blob ? resolve(blob) : reject(new Error('Encode failed'))),
          mime,
          quality
        );
      });
    },

    _downloadBlob(blob, filename) {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },

    _exportBackgroundFill(format) {
      // JPEG cannot be transparent; fall back to the solid color.
      if (this.form.background === 'solid') {
        return (this.form.solid_color || '#222222').trim() || '#222222';
      }
      if (format === 'jpeg') {
        return (this.form.solid_color || '#ffffff').trim() || '#ffffff';
      }
      return null; // transparent
    },

    _exportMetaName(base) {
      return `${base}_meta.json`;
    },

    async runExport() {
      if (this.exportRunning) return;
      if (this.exportableCount() === 0) {
        this.showError('Every frame is deleted — nothing to export.');
        return;
      }
      this.exportRunning = true;
      this.exportError = '';
      this.exportProgress = 0;
      try {
        if (this.form.export_type === 'pictures') {
          await this.exportPictures();
        } else {
          await this.exportSpriteSheet();
        }
      } catch (e) {
        this.exportError = e.message || String(e);
        this.showError(this.exportError);
      } finally {
        this.exportRunning = false;
        this.exportStatus = '';
      }
    },

    async exportSpriteSheet() {
      this.exportStatus = 'Building sprite sheet…';
      const frames = this.exportableFrames();
      const cols = this.columnsValue();
      const rows = Math.ceil(frames.length / cols);
      const cell = this.summaryCellSize();
      const spacing = Math.max(0, parseInt(this.form.spacing, 10) || 0);
      const format = this.form.format;
      const sheetW = cols * cell.w + (cols - 1) * spacing;
      const sheetH = rows * cell.h + (rows - 1) * spacing;

      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, sheetW);
      canvas.height = Math.max(1, sheetH);
      const ctx = canvas.getContext('2d');
      const fill = this._exportBackgroundFill(format);
      if (fill) {
        ctx.fillStyle = fill;
        ctx.fillRect(0, 0, canvas.width, canvas.height);
      }

      const positions = [];
      for (let i = 0; i < frames.length; i++) {
        const frame = frames[i];
        const col = i % cols;
        const row = Math.floor(i / cols);
        const x = col * (cell.w + spacing);
        const y = row * (cell.h + spacing);
        const composed = this.composeFrameCanvas(frame);
        if (composed) {
          const dx = x + Math.floor((cell.w - composed.width) / 2);
          const dy = y + Math.floor((cell.h - composed.height) / 2);
          ctx.drawImage(composed, dx, dy);
        }
        positions.push({
          index: frame.index,
          x,
          y,
          w: cell.w,
          h: cell.h,
        });
        this.exportProgress = (i + 1) / frames.length;
      }

      const base = exportSanitizeFilename(this.form.filename, 'spritesheet');
      const ext = exportFormatExt(format);
      const blob = await this._canvasToBlob(canvas, format);
      this._downloadBlob(blob, `${base}.${ext}`);

      const meta = this.buildSheetMetadata({
        sheetW,
        sheetH,
        cell,
        cols,
        rows,
        spacing,
        positions,
        ext,
      });
      this._downloadBlob(
        new Blob([JSON.stringify(meta, null, 2)], {
          type: 'application/json',
        }),
        this._exportMetaName(base)
      );
    },

    async exportPictures() {
      if (typeof JSZip === 'undefined') {
        throw new Error('JSZip not loaded');
      }
      this.exportStatus = 'Packaging frames…';
      const frames = this.exportableFrames();
      const format = this.form.format;
      const ext = exportFormatExt(format);
      const base = exportSanitizeFilename(this.form.filename, 'frames');
      const zip = new JSZip();
      const folder = zip.folder(base) || zip;
      const width = String(frames.length).length;
      const fileEntries = [];

      for (let i = 0; i < frames.length; i++) {
        const frame = frames[i];
        const fill = this._exportBackgroundFill(format);
        let composed = this.composeFrameCanvas(frame);
        if (fill && composed) {
          const bgCanvas = document.createElement('canvas');
          bgCanvas.width = composed.width;
          bgCanvas.height = composed.height;
          const bctx = bgCanvas.getContext('2d');
          bctx.fillStyle = fill;
          bctx.fillRect(0, 0, bgCanvas.width, bgCanvas.height);
          bctx.drawImage(composed, 0, 0);
          composed = bgCanvas;
        }
        if (!composed) continue;
        const blob = await this._canvasToBlob(composed, format);
        const name = `${base}_${exportPad(i + 1, Math.max(4, width))}.${ext}`;
        folder.file(name, blob);
        fileEntries.push({ file: name, index: frame.index });
        this.exportProgress = (i + 1) / frames.length;
      }

      const meta = this.buildPicturesMetadata(fileEntries);
      folder.file('meta.json', JSON.stringify(meta, null, 2));

      this.exportStatus = 'Compressing…';
      const blob = await zip.generateAsync({ type: 'blob' });
      this._downloadBlob(blob, `${base}.zip`);
    },

    buildSheetMetadata({ sheetW, sheetH, cell, cols, rows, spacing, positions, ext }) {
      return {
        type: 'spritesheet',
        created_at: new Date().toISOString(),
        fps: this.sourceFps,
        frame_count: positions.length,
        format: ext,
        source: {
          name: this.videoTitle(this.openVideo),
          prompt_id: this.openVideo?.prompt_id || null,
        },
        image: { width: sheetW, height: sheetH },
        frame: { width: cell.w, height: cell.h },
        columns: cols,
        rows,
        spacing,
        frames: positions,
      };
    },

    buildPicturesMetadata(fileEntries) {
      return {
        type: 'pictures',
        created_at: new Date().toISOString(),
        fps: this.sourceFps,
        frame_count: fileEntries.length,
        format: exportFormatExt(this.form.format),
        source: {
          name: this.videoTitle(this.openVideo),
          prompt_id: this.openVideo?.prompt_id || null,
        },
        frames: fileEntries,
      };
    },

    exportProgressPercent() {
      return Math.round((this.exportProgress || 0) * 100);
    },
  };
}

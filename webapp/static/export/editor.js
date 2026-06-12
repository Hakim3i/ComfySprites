/** Export Lab — frame navigation, timeline, playback, keyboard shortcuts. */

function exportEditorMethods() {
  return {
    playing: false,
    _playTimer: null,

    currentFrame() {
      return this.frames[this.currentIndex] || null;
    },

    exportableFrames() {
      return this.frames.filter((f) => !f.deleted);
    },

    exportableCount() {
      return this.frames.reduce((n, f) => n + (f.deleted ? 0 : 1), 0);
    },

    deletedCount() {
      return this.frames.reduce((n, f) => n + (f.deleted ? 1 : 0), 0);
    },

    rmbgCount() {
      return this.frames.reduce((n, f) => n + (f.hasRmbg ? 1 : 0), 0);
    },

    exportablePositionLabel() {
      const cur = this.currentFrame();
      if (!cur) return '0 / 0';
      if (cur.deleted) return 'deleted';
      let pos = 0;
      for (const f of this.frames) {
        if (f.deleted) continue;
        pos += 1;
        if (f.id === cur.id) break;
      }
      return `${pos} / ${this.exportableCount()}`;
    },

    goToFrame(index) {
      if (index < 0 || index >= this.frames.length) return;
      this.currentIndex = index;
      this.renderCurrentFrame();
      this.scrollCurrentTickIntoView();
    },

    scrollCurrentTickIntoView() {
      this.$nextTick(() => {
        const track = this.$refs.frameTrack;
        if (!track) return;
        const tick = track.children[this.currentIndex];
        if (tick?.scrollIntoView) {
          tick.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        }
      });
    },

    firstFrame() {
      this.goToFrame(0);
    },

    lastFrame() {
      this.goToFrame(this.frames.length - 1);
    },

    prevFrame() {
      this.goToFrame(Math.max(0, this.currentIndex - 1));
    },

    nextFrame() {
      this.goToFrame(Math.min(this.frames.length - 1, this.currentIndex + 1));
    },

    _nextExportableIndex(fromIndex) {
      const n = this.frames.length;
      if (n === 0) return -1;
      for (let step = 1; step <= n; step++) {
        const idx = (fromIndex + step) % n;
        if (!this.frames[idx].deleted) return idx;
      }
      return -1;
    },

    togglePlayback() {
      if (this.playing) {
        this.stopPlayback();
      } else {
        this.startPlayback();
      }
    },

    startPlayback() {
      if (this.exportableCount() === 0) return;
      this.stopPlayback();
      this.playing = true;
      // Ensure we start on an exportable frame.
      if (this.currentFrame()?.deleted) {
        const first = this._nextExportableIndex(this.currentIndex);
        if (first >= 0) this.goToFrame(first);
      }
      const interval = 1000 / Math.max(1, this.sourceFps);
      this._playTimer = setInterval(() => {
        const next = this._nextExportableIndex(this.currentIndex);
        if (next < 0) {
          this.stopPlayback();
          return;
        }
        this.goToFrame(next);
      }, interval);
    },

    stopPlayback() {
      this.playing = false;
      if (this._playTimer) {
        clearInterval(this._playTimer);
        this._playTimer = null;
      }
    },

    renderCurrentFrame() {
      const frame = this.currentFrame();
      const canvas = this.$refs.stageCanvas;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!frame) {
        canvas.width = 1;
        canvas.height = 1;
        ctx.clearRect(0, 0, 1, 1);
        return;
      }
      const composed = this.composeFrameCanvas(frame);
      if (!composed) return;
      canvas.width = composed.width;
      canvas.height = composed.height;
      ctx.clearRect(0, 0, composed.width, composed.height);
      ctx.drawImage(composed, 0, 0);
    },

    _editorTypingTarget(el) {
      if (!el?.closest) return false;
      if (el.isContentEditable || el.closest('[contenteditable="true"]')) return true;
      if (el.closest('.export-modal')) return true;
      if (!el.closest('.export-settings-col')) return false;
      const tag = (el.tagName || '').toUpperCase();
      if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
      if (tag === 'INPUT') {
        const type = (el.type || 'text').toLowerCase();
        return !['button', 'submit', 'reset', 'checkbox', 'radio', 'range', 'file', 'color'].includes(
          type
        );
      }
      return false;
    },

    onEditorKeydown(event) {
      if (!this.openVideo || this.errorOpen || this.videoPickerOpen) return;
      if (this._editorTypingTarget(event.target)) return;
      switch (event.key) {
        case ' ':
        case 'Spacebar':
          event.preventDefault();
          this.togglePlayback();
          break;
        case 'ArrowLeft':
          event.preventDefault();
          this.prevFrame();
          break;
        case 'ArrowRight':
          event.preventDefault();
          this.nextFrame();
          break;
        case 'Home':
          event.preventDefault();
          this.firstFrame();
          break;
        case 'End':
          event.preventDefault();
          this.lastFrame();
          break;
        case 'Delete':
        case 'Backspace':
          event.preventDefault();
          this.toggleDeleteCurrent();
          break;
        case 'f':
        case 'F':
          event.preventDefault();
          this.flipCurrentX();
          break;
        case 'v':
        case 'V':
          event.preventDefault();
          this.flipCurrentY();
          break;
        case 'r':
        case 'R':
          event.preventDefault();
          this.cycleRotateCurrent();
          break;
        default:
          break;
      }
    },
  };
}

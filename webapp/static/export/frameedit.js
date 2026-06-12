/** Export Lab — per-frame delete/restore and flip/rotate transforms. */

function exportFrameEditMethods() {
  return {
    toggleDeleteCurrent() {
      const frame = this.currentFrame();
      if (!frame) return;
      frame.deleted = !frame.deleted;
      this.renderCurrentFrame();
    },

    setFrameDeleted(frame, deleted) {
      if (!frame) return;
      frame.deleted = deleted;
      this.renderCurrentFrame();
    },

    flipCurrentX() {
      const frame = this.currentFrame();
      if (!frame) return;
      frame.flipX = !frame.flipX;
      this.renderCurrentFrame();
    },

    flipCurrentY() {
      const frame = this.currentFrame();
      if (!frame) return;
      frame.flipY = !frame.flipY;
      this.renderCurrentFrame();
    },

    rotateCurrent(deg) {
      const frame = this.currentFrame();
      if (!frame) return;
      frame.rotation = ((parseInt(deg, 10) % 360) + 360) % 360;
      this.renderCurrentFrame();
    },

    cycleRotateCurrent() {
      const frame = this.currentFrame();
      if (!frame) return;
      frame.rotation = (frame.rotation + 90) % 360;
      this.renderCurrentFrame();
    },

    currentRotation() {
      return this.currentFrame()?.rotation ?? 0;
    },

    currentIsDeleted() {
      return !!this.currentFrame()?.deleted;
    },

    currentFlipX() {
      return !!this.currentFrame()?.flipX;
    },

    currentFlipY() {
      return !!this.currentFrame()?.flipY;
    },

    restoreAllFrames() {
      for (const frame of this.frames) frame.deleted = false;
      this.renderCurrentFrame();
    },

    /** Evenly keep `target` frames across the whole strip; delete the rest. */
    reduceFramesTo(target) {
      const n = this.frames.length;
      if (n === 0) return;
      const k = Math.max(1, Math.min(parseInt(target, 10) || 1, n));
      this.reduceTarget = k;
      if (k >= n) {
        this.restoreAllFrames();
        return;
      }
      const keep = new Set();
      const step = n / k;
      for (let i = 0; i < k; i++) {
        keep.add(Math.floor(i * step + step / 2));
      }
      this.frames.forEach((frame, idx) => {
        frame.deleted = !keep.has(idx);
      });
      if (this.currentFrame()?.deleted) {
        const firstKept = this.frames.findIndex((f) => !f.deleted);
        if (firstKept >= 0) this.currentIndex = firstKept;
      }
      this.renderCurrentFrame();
    },

    onReduceTargetInput() {
      if (!this.frames.length) return;
      const raw = parseInt(this.reduceTarget, 10);
      if (!Number.isFinite(raw) || raw < 1) return;
      this.reduceFramesTo(raw);
    },
  };
}

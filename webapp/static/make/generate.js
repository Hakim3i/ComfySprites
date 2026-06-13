(function (global) {
  function makeGenerateMethods() {
    return {

    generateButtonLabel() {
      if (this.comfyuiInferenceActive() && !this.controlnetPreprocessActive?.()) {
        return 'Stop';
      }
      if (this.generating) return 'Generating…';
      if (this.controlnetPreprocessActive?.()) return 'Preprocessing…';
      return 'Generate';
    },

    generateDisabled() {
      return (
        (this.busy && !this.comfyuiAnyJobActive()) ||
        (!this.comfyuiAnyJobActive() && this.comfyuiState === 'offline') ||
        this.controlnetPreprocessBusy?.()
      );
    },

    onGenerateClick() {
      if (this.comfyuiInferenceActive() && !this.controlnetPreprocessActive?.()) {
        void this.stopGeneration();
        return;
      }
      if (this.generateDisabled()) return;
      void this.generateMake();
    },

    _keyboardTypingTarget(el) {
      if (!el?.closest) return false;
      if (el.isContentEditable || el.closest('[contenteditable="true"]')) return true;
      if (el.closest('.make-picker-panel, .make-metadata-panel')) return true;
      const tag = el.tagName;
      if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
      if (tag === 'INPUT') {
        const type = (el.type || 'text').toLowerCase();
        return !['button', 'submit', 'reset', 'checkbox', 'radio', 'range', 'file'].includes(type);
      }
      return false;
    },

    _labModalOpen() {
      return !!(this.picker?.open || this.metadataOpen);
    },

    onGenerateKeydown(event) {
      if (event.code !== 'Space' && event.key !== ' ') return;
      if (this._keyboardTypingTarget(event.target)) return;
      if (this._labModalOpen()) return;
      event.preventDefault();
      event.stopPropagation();
      this.onGenerateClick();
    },

    clearClientGenerationQueue() {
      this.clientGenerationQueue = null;
      this.clientGenSubmitting = false;
    },

    plannedGenerationCount() {
      let n = parseInt(this.form.generation_count, 10);
      if (Number.isNaN(n) || n < MAKE_LAB_GENERATION_COUNT_MIN) {
        n = MAKE_LAB_GENERATION_COUNT_MIN;
      }
      return Math.min(
        MAKE_LAB_GENERATION_COUNT_MAX,
        Math.max(MAKE_LAB_GENERATION_COUNT_MIN, n)
      );
    },

    syncClientBatchTracking() {
      const q = this.clientGenerationQueue;
      if (!q || q.promptIds.length < 2) return;
      const ids = q.promptIds.slice();
      for (const tracked of this.trackedJobs) {
        if (!ids.includes(tracked.promptId)) continue;
        tracked.batchPromptIds = ids;
        tracked.batchIndex = ids.indexOf(tracked.promptId);
        tracked.batchTotal = q.total;
      }
      this.syncClientBatchSlotVisibility();
    },

    drainClientGenerationQueue() {
      const q = this.clientGenerationQueue;
      if (!q || q.nextIndex >= q.total) {
        if (q && q.nextIndex >= q.total && !this.comfyuiAnyJobActive()) {
          this.clearClientGenerationQueue();
        }
        return;
      }
      if (this.comfyuiInferenceActive() || this.clientGenSubmitting) return;
      void this.submitOneGeneration();
    },

    async stopGeneration() {
      const promptId = this.primaryInferencePromptId();
      const tracked = promptId
        ? this.trackedJobs.find((t) => t.promptId === promptId)
        : null;
      const batchIds = new Set([
        ...(tracked?.batchPromptIds || []),
        ...(this.clientGenerationQueue?.promptIds || []),
        ...(promptId ? [promptId] : []),
      ]);
      this.clearClientGenerationQueue();
      if (!batchIds.size) return;
      let failed = false;
      for (const pid of batchIds) {
        try {
          const r = await fetch(
            '/api/comfyui/job/' + encodeURIComponent(pid) + '/cancel',
            { method: 'POST' }
          );
          if (!r.ok) failed = true;
        } catch {
          failed = true;
        }
        this.removeTrackedJob(pid);
      }
      if (failed) {
        this.error = 'Stop failed for one or more jobs.';
      } else {
        this.error = '';
      }
      void this.refreshComfyuiStatus();
      await this.pollAllComfyuiJobs();
    },

    async generateMake() {
      const total = this.plannedGenerationCount();
      const queueDuringDownload =
        this.comfyuiAnyJobActive() && !this.comfyuiInferenceActive();
      if (!queueDuringDownload) {
        this.clearClientGenerationQueue();
      }
      if (total > 1) {
        if (!this.clientGenerationQueue) {
          this.clientGenerationQueue = {
            total,
            nextIndex: 0,
            promptIds: [],
          };
        } else if (queueDuringDownload) {
          this.clientGenerationQueue.total += total;
        }
      }
      await this.submitOneGeneration();
    },

    async submitOneGeneration() {
      const q = this.clientGenerationQueue;
      const isMulti = q && q.total > 1;
      if (isMulti && (q.nextIndex >= q.total || this.clientGenSubmitting)) {
        return;
      }
      if (isMulti && this.comfyuiInferenceActive()) {
        return;
      }

      this.busy = true;
      this.error = '';
      const queueDuringDownload =
        this.comfyuiAnyJobActive() && !this.comfyuiInferenceActive();
      if (!queueDuringDownload) {
        this.generating = true;
        if (!isMulti || (isMulti && q.nextIndex === 0)) this.stopComfyuiJobPoll();
      }
      if (isMulti) this.clientGenSubmitting = true;

      const payload = this.buildPayload();
      payload.generation_count = 1;
      if (isMulti && q.nextIndex > 0) {
        const seed = payload.seed;
        if (typeof seed === 'number' && seed >= 0) {
          payload.seed = seed + q.nextIndex;
        }
      }

      try {
        const r = await fetch('/api/make/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const { data } = await parseApiResponse(r);
        if (!r.ok) {
          this.error = apiErrorDetail(data, r.status, 'Generate failed');
          if (isMulti) this.clearClientGenerationQueue();
          return;
        }
        if (data.build) {
          this.result = data.build;
          this.applyBuildPreviewSize(data.build);
          if (this.shouldPinResolvedBuildToForm()) {
            this.runWithDetailerSyncSuppressed(() => {
              this.pinResolvedSceneDisplay(data.build);
              this.applyRequestToForm(data.build.request, data.build);
            });
          } else {
            this.pinResolvedSceneDisplay(data.build);
          }
        }
        const qAfter = this.clientGenerationQueue;
        if (!qAfter || qAfter.nextIndex >= qAfter.total) {
          this.resetOrientationToDefault();
        }
        if (data.prompt_id) {
          const sceneSnap = this.sceneSnapshotForJob(data.build);
          if (isMulti) {
            q.promptIds.push(data.prompt_id);
            q.nextIndex += 1;
            const batchIndex = q.promptIds.length - 1;
            this.registerClientBatchJob(data.prompt_id, sceneSnap, q, {
              autoFocus: !queueDuringDownload && batchIndex === 0,
            });
            if (q.nextIndex >= q.total && !this.comfyuiAnyJobActive()) {
              this.clearClientGenerationQueue();
            }
          } else if (queueDuringDownload) {
            this.registerTrackedJobs(data.prompt_id, data.prompt_ids, sceneSnap, {
              autoFocus: false,
            });
          } else {
            this.startComfyuiJobPoll(data.prompt_id, data.prompt_ids, sceneSnap);
          }
        }
      } catch (e) {
        this.error = 'Generate failed (' + e.message + ').';
        if (isMulti) this.clearClientGenerationQueue();
        if (!queueDuringDownload && !isMulti) this.stopComfyuiJobPoll();
      } finally {
        if (isMulti) this.clientGenSubmitting = false;
        this.busy = false;
        if (!this.comfyuiAnyJobActive()) this.generating = false;
      }
    },
    };
  }
  global.makeGenerateMethods = makeGenerateMethods;
})(window);

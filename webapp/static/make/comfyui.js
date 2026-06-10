(function (global) {
  function makeComfyuiMethods() {
    return {

    _comfyuiJobPollResumeOptions() {
      return {
        pollOnce: () => this.pollAllComfyuiJobs(),
        jobPollOptions: {
          intervalMs: 500,
          pollOnce: () => this.pollAllComfyuiJobs(),
          onStart: () => {
            this.comfyuiState = 'generating';
          },
        },
      };
    },

    _persistTrackedJob(job) {
      if (!job?.promptId || typeof window.persistLabJob !== 'function') return;
      window.persistLabJob(MAKE_LAB_COMFYUI_LAB, {
        promptId: job.promptId,
        animationSlug: job.animationSlug || '',
        placeKey: job.placeKey || '',
        batchPromptIds: job.batchPromptIds || null,
        batchIndex: job.batchIndex ?? null,
        batchTotal: job.batchTotal ?? null,
        startedAt: job.startedAt || Date.now(),
        status: job.status || 'queued',
      });
    },

    async reconcilePersistedJob(promptId) {
      if (typeof window.removePersistedLabJob === 'function') {
        window.removePersistedLabJob(MAKE_LAB_COMFYUI_LAB, promptId);
      }
      if (this.trackedJobs.some((t) => t.promptId === promptId)) {
        this.removeTrackedJob(promptId);
      }
      await this.loadHistory();
      const hit = this.historyItems.find((i) => i.prompt_id === promptId);
      if (hit?.image_url) {
        this.pinPreviewToCompletedJob(promptId, promptId, hit.image_url);
      }
    },

    readPersistedMakeLabJobs() {
      if (typeof window.readPersistedLabJobs !== 'function') return [];
      return window.readPersistedLabJobs(MAKE_LAB_COMFYUI_LAB);
    },

    async restorePersistedComfyuiJobs() {
      const stored = this.readPersistedMakeLabJobs();
      if (!stored.length) return;
      for (const entry of stored) {
        const promptId = (entry?.promptId || '').trim();
        if (!promptId) continue;
        if (this.trackedJobs.some((t) => t.promptId === promptId)) continue;
        const result =
          typeof window.fetchComfyuiJob === 'function'
            ? await window.fetchComfyuiJob(promptId)
            : { ok: false, status: 0, data: null };
        if (result.ok && result.data) {
          const status = result.data.status || entry.status || 'queued';
          if (this.isTerminalJobStatus(status)) {
            if (typeof window.removePersistedLabJob === 'function') {
              window.removePersistedLabJob(MAKE_LAB_COMFYUI_LAB, promptId);
            }
            if (status === 'complete') {
              await this.loadHistory();
              const previewUrl =
                (Array.isArray(result.data.preview_urls) &&
                  result.data.preview_urls[0]) ||
                result.data.preview_url;
              const imageId =
                (Array.isArray(result.data.image_ids) &&
                  result.data.image_ids[0]) ||
                promptId;
              if (previewUrl) {
                this.pinPreviewToCompletedJob(promptId, imageId, previewUrl);
              } else {
                const hit = this.historyItems.find(
                  (i) => i.prompt_id === promptId
                );
                if (hit?.image_url) {
                  this.pinPreviewToCompletedJob(
                    promptId,
                    promptId,
                    hit.image_url
                  );
                }
              }
            }
            continue;
          }
          const scene = {
            animationSlug: entry.animationSlug || '',
            placeKey: entry.placeKey || '',
            outfitName: entry.outfitName || '',
          };
          if (entry.batchPromptIds?.length) {
            this.registerTrackedJobs(
              promptId,
              entry.batchPromptIds,
              scene,
              { autoFocus: false }
            );
          } else {
            this.registerTrackedJobs(promptId, [promptId], scene, {
              autoFocus: false,
            });
          }
          const tracked = this.trackedJobs.find((t) => t.promptId === promptId);
          if (tracked) {
            tracked.status = status;
            this.updateTrackedJobFromPoll(tracked, result.data);
          }
          continue;
        }
        await this.reconcilePersistedJob(promptId);
      }
      if (this.comfyuiAnyJobActive()) {
        this.ensureComfyuiJobPoll();
      }
    },

    startComfyuiStatusPoll() {
      if (typeof window.startComfyuiStatusPoll === 'function') {
        window.startComfyuiStatusPoll(this, { lab: MAKE_LAB_COMFYUI_LAB });
      }
    },

    stopComfyuiStatusPoll() {
      if (typeof window.stopComfyuiStatusPoll === 'function') {
        window.stopComfyuiStatusPoll();
      }
    },

    applyComfyuiStatus(data) {
      if (typeof window.applyComfyuiServerStatus === 'function') {
        window.applyComfyuiServerStatus(this, data);
      }
    },

    comfyuiMetricDisplay(pct) {
      return typeof window.comfyuiMetricDisplay === 'function'
        ? window.comfyuiMetricDisplay(pct)
        : '—%';
    },

    comfyuiMetricLevelClass(pct) {
      return typeof window.comfyuiMetricLevelClass === 'function'
        ? window.comfyuiMetricLevelClass(pct)
        : '';
    },

    comfyuiExecutionTimeDisplay() {
      void this.comfyuiExecutionTick;
      return typeof window.comfyuiExecutionTimeDisplay === 'function'
        ? window.comfyuiExecutionTimeDisplay(this)
        : '00:00';
    },

    startComfyuiExecutionClock() {
      if (typeof window.startComfyuiExecutionClock === 'function') {
        window.startComfyuiExecutionClock(this);
      }
    },

    stopComfyuiExecutionClock() {
      if (typeof window.stopComfyuiExecutionClock === 'function') {
        window.stopComfyuiExecutionClock(this);
      }
    },

    comfyuiBadgeClass() {
      if (this.comfyuiInferenceActive()) return 'accent';
      if (this.comfyuiAnyJobActive()) return 'warn';
      const map = window.COMFYUI_BADGE_CLASS || {};
      return map[this.comfyuiState] || 'muted';
    },

    isTerminalJobStatus(status) {
      return status === 'complete' || status === 'error' || status === 'cancelled';
    },

    isInferenceJobStatus(status) {
      return (
        status === 'running' ||
        status === 'queued' ||
        status === 'fetching_assets'
      );
    },

    comfyuiInferenceActive() {
      return this.trackedJobs.some((t) => this.isInferenceJobStatus(t.status));
    },

    comfyuiAnyJobActive() {
      return this.trackedJobs.some((t) => !this.isTerminalJobStatus(t.status));
    },

    primaryInferencePromptId() {
      const running = this.trackedJobs
        .filter((t) => this.isInferenceJobStatus(t.status))
        .sort((a, b) => a.startedAt - b.startedAt);
      return running[0]?.promptId || null;
    },

    stopComfyuiJobPoll(clearTracked = true) {
      if (typeof window.stopComfyuiJobPollLoop === 'function') {
        window.stopComfyuiJobPollLoop(this);
      }
      if (clearTracked) {
        for (const t of this.trackedJobs) this.revokeTrackedPreviewBlob(t);
        this.trackedJobs = [];
        this.previewFocusPromptId = null;
        this.previewAutoFollowInference = true;
      }
      this.comfyuiJobPromptId = null;
      this.comfyuiProgressActive = false;
      this.comfyuiProgressPct = 0;
      this.comfyuiPhaseLabel = '';
      this.comfyuiJobWsWarning = '';
      this.comfyuiJobStartedAt = 0;
      if (!this.comfyuiAnyJobActive()) {
        this.generating = false;
        this.previewLiveSampling = true;
      }
    },

    syncPrimaryProgressDisplay() {
      const pid = this.primaryInferencePromptId();
      const job = pid
        ? this.trackedJobs.find((t) => t.promptId === pid)
        : null;
      this.comfyuiJobPromptId = pid;
      this.comfyuiProgressActive = this.comfyuiInferenceActive();
      if (job) {
        this.comfyuiProgressPct = job.progressPct;
        this.comfyuiPhaseLabel = job.phaseLabel;
        this.comfyuiJobWsWarning = job.wsWarning;
        this.comfyuiJobStartedAt = job.startedAt;
      } else {
        this.comfyuiProgressPct = 0;
        this.comfyuiPhaseLabel = '';
        this.comfyuiJobWsWarning = '';
      }
    },

    ensureComfyuiJobPoll() {
      if (typeof window.runComfyuiJobPollLoop !== 'function') return;
      window.runComfyuiJobPollLoop(
        this,
        this._comfyuiJobPollResumeOptions().jobPollOptions
      );
    },

    registerTrackedJobs(promptId, promptIds, sceneOrAct, { autoFocus = true } = {}) {
      const ids =
        Array.isArray(promptIds) && promptIds.length
          ? promptIds
          : promptId
            ? [promptId]
            : [];
      if (!ids.length) return;
      this.comfyuiLastExecutionMs = null;
      if (typeof window.bumpComfyuiExecutionTick === 'function') {
        window.bumpComfyuiExecutionTick(this);
      }
      const now = Date.now();
      const isBatch = ids.length > 1;
      const scene = this._normalizeSceneSnapshot(sceneOrAct);
      for (let i = 0; i < ids.length; i++) {
        if (this.trackedJobs.some((t) => t.promptId === ids[i])) continue;
        const trackedEntry = {
          promptId: ids[i],
          animationSlug: scene.animationSlug,
          placeKey: scene.placeKey,
          outfitName: scene.outfitName,
          slotVisible: !isBatch || i === 0,
          batchPromptIds: isBatch ? ids : null,
          batchIndex: isBatch ? i : null,
          batchTotal: isBatch ? ids.length : null,
          status: 'queued',
          progressPct: 0,
          downloadPct: 0,
          phaseLabel: '',
          startedAt: now + i,
          finishedAt: null,
          wsWarning: '',
          lastLivePreviewUrl: null,
        };
        this.trackedJobs.push(trackedEntry);
        this._persistTrackedJob(trackedEntry);
      }
      this.previewLiveSampling = true;
      if (autoFocus) {
        this.previewAutoFollowInference = true;
        this.previewFocusPromptId = null;
        this.selectedHistoryId = ids[0];
      }
      this.syncSelectedHistoryFromPreview();
      this.ensureComfyuiJobPoll();
      this.syncPrimaryProgressDisplay();
      this.$nextTick(() => this.updateHistoryScrollState());
    },

    revealNextBatchSlot(tracked) {
      if (this.clientGenerationQueue?.total > 1) {
        this.syncClientBatchSlotVisibility();
        return;
      }
      if (!tracked?.batchPromptIds || tracked.batchIndex == null) return;
      const nextIndex = tracked.batchIndex + 1;
      if (nextIndex >= tracked.batchPromptIds.length) return;
      const nextId = tracked.batchPromptIds[nextIndex];
      const next = this.trackedJobs.find((t) => t.promptId === nextId);
      if (next) next.slotVisible = true;
    },

    syncClientBatchSlotVisibility() {
      const q = this.clientGenerationQueue;
      if (!q || q.total <= 1) return;
      const batchJobs = this.trackedJobs.filter(
        (t) => t.batchTotal != null && t.batchTotal > 1
      );
      if (!batchJobs.length) return;
      const active = batchJobs.filter((t) => !this.isTerminalJobStatus(t.status));
      if (!active.length) {
        for (const t of batchJobs) t.slotVisible = false;
        return;
      }
      const downloading = active
        .filter((t) => t.status === 'downloading')
        .sort((a, b) => a.startedAt - b.startedAt)[0];
      const inference = active
        .filter((t) => this.isInferenceJobStatus(t.status))
        .sort((a, b) => a.startedAt - b.startedAt)[0];
      const show =
        downloading ||
        inference ||
        active.sort((a, b) => a.startedAt - b.startedAt)[0];
      for (const t of batchJobs) {
        t.slotVisible = show ? t.promptId === show.promptId : false;
      }
    },

    registerClientBatchJob(promptId, sceneSnap, q, { autoFocus = false } = {}) {
      if (!promptId || !q) return;
      if (this.trackedJobs.some((t) => t.promptId === promptId)) {
        this.syncClientBatchTracking();
        this.syncClientBatchSlotVisibility();
        return;
      }
      const scene = this._normalizeSceneSnapshot(sceneSnap);
      const batchIndex = q.promptIds.indexOf(promptId);
      const trackedEntry = {
        promptId,
        animationSlug: scene.animationSlug,
        placeKey: scene.placeKey,
        outfitName: scene.outfitName,
        slotVisible: false,
        batchPromptIds: q.promptIds.slice(),
        batchIndex: batchIndex >= 0 ? batchIndex : q.promptIds.length - 1,
        batchTotal: q.total,
        status: 'queued',
        progressPct: 0,
        downloadPct: 0,
        phaseLabel: '',
        startedAt: Date.now() + Math.max(0, batchIndex),
        finishedAt: null,
        wsWarning: '',
        lastLivePreviewUrl: null,
      };
      this.trackedJobs.push(trackedEntry);
      this._persistTrackedJob(trackedEntry);
      this.syncClientBatchTracking();
      this.syncClientBatchSlotVisibility();
      this.previewLiveSampling = true;
      if (autoFocus) {
        this.previewAutoFollowInference = true;
        this.previewFocusPromptId = null;
        this.selectedHistoryId = promptId;
      }
      this.syncSelectedHistoryFromPreview();
      this.ensureComfyuiJobPoll();
      this.syncPrimaryProgressDisplay();
      this.$nextTick(() => this.updateHistoryScrollState());
    },

    removeTrackedJob(promptId) {
      const job = this.trackedJobs.find((t) => t.promptId === promptId);
      if (job && typeof window.captureExecutionOnRemove === 'function') {
        window.captureExecutionOnRemove(this, job);
      }
      if (typeof window.removePersistedLabJob === 'function') {
        window.removePersistedLabJob(MAKE_LAB_COMFYUI_LAB, promptId);
      }
      if (job) this.revokeTrackedPreviewBlob(job);
      this.trackedJobs = this.trackedJobs.filter((t) => t.promptId !== promptId);
      this.syncPrimaryProgressDisplay();
      if (!this.comfyuiAnyJobActive()) {
        this.stopComfyuiJobPoll(false);
        void this.refreshComfyuiStatus();
      }
    },

    updateTrackedJobFromPoll(tracked, data) {
      const prevStatus = tracked.status;
      tracked.status = data.status || tracked.status;
      tracked.progressPct = Number(data.progress_pct) || 0;
      tracked.downloadPct = Number(data.download_pct) || 0;
      tracked.phaseLabel =
        data.executing_label || data.phase_label || data.phase || '';
      if (data.animation_slug) tracked.animationSlug = data.animation_slug;
      if (data.background) tracked.placeKey = data.background;
      if (
        this.isTerminalJobStatus(tracked.status) &&
        prevStatus !== tracked.status &&
        typeof window.noteJobFinished === 'function'
      ) {
        window.noteJobFinished(this, tracked);
      }

      if (
        data.ws_error &&
        tracked.startedAt &&
        Date.now() - tracked.startedAt > 2000
      ) {
        tracked.wsWarning = data.ws_error;
      } else if (data.ws_connected) {
        tracked.wsWarning = '';
      } else if (
        tracked.startedAt &&
        Date.now() - tracked.startedAt > 2000 &&
        !data.ws_connected &&
        this.isInferenceJobStatus(tracked.status)
      ) {
        tracked.wsWarning =
          'Progress stream disconnected — check WebSocket to ComfyUI';
      }

      const focusId = this.activePreviewPromptId();
      if (data.live_preview_url && this.isInferenceJobStatus(tracked.status)) {
        tracked.lastLivePreviewUrl = data.live_preview_url;
        if (this.shouldUpdateLivePreviewFor(tracked)) {
          this.outputImage = this.cacheBustUrl(data.live_preview_url);
          this.$nextTick(() => this.onViewportResize());
        }
      }

      if (
        tracked.status === 'downloading' &&
        prevStatus !== 'downloading' &&
        prevStatus !== 'complete'
      ) {
        if (data.live_preview_url) {
          tracked.lastLivePreviewUrl = data.live_preview_url;
        }
        const shouldPin =
          this.previewAutoFollowInference || focusId === tracked.promptId;
        if (shouldPin) {
          this.previewAutoFollowInference = false;
          this.previewFocusPromptId = tracked.promptId;
          this.syncSelectedHistoryFromPreview();
        }
        void this.snapshotTrackedPreview(tracked).then((url) => {
          if (this.previewFocusPromptId === tracked.promptId && url) {
            this.outputImage = url;
            this.$nextTick(() => this.onViewportResize());
          }
        });
        this.revealNextBatchSlot(tracked);
        this.syncPrimaryProgressDisplay();
        this.drainClientGenerationQueue();
      }

      if (tracked.status === 'complete') {
        const inferenceJustEnded = this.isInferenceJobStatus(prevStatus);
        if (inferenceJustEnded) {
          this.revealNextBatchSlot(tracked);
        }
        const previewUrl =
          (Array.isArray(data.preview_urls) && data.preview_urls[0]) ||
          data.preview_url;
        const firstImageId =
          Array.isArray(data.image_ids) && data.image_ids.length
            ? data.image_ids[0]
            : tracked.promptId;
        const focusId = this.previewFocusPromptId;
        const userManuallyWatchingOther =
          !this.previewAutoFollowInference &&
          focusId &&
          focusId !== tracked.promptId &&
          focusId !== firstImageId &&
          this.trackedJobs.some(
            (t) => t.promptId === focusId && !this.isTerminalJobStatus(t.status)
          );
        const viewingOtherCompleted =
          this.isPreviewPinnedToCompleted() &&
          focusId &&
          focusId !== tracked.promptId &&
          focusId !== firstImageId;
        const adoptCompletedJob =
          !userManuallyWatchingOther && !viewingOtherCompleted;
        if (data.build && adoptCompletedJob) {
          this.result = data.build;
          this.applyBuildPreviewSize(data.build);
          this.runWithDetailerSyncSuppressed(() => {
            this.pinResolvedSceneDisplay(data.build);
            this.applyRequestToForm(data.build.request, data.build);
          });
        }
        if (adoptCompletedJob) {
          this.pinPreviewToCompletedJob(tracked.promptId, firstImageId, previewUrl);
        }
        void this.loadHistory();
        this.removeTrackedJob(tracked.promptId);
        if (inferenceJustEnded) {
          this.drainClientGenerationQueue();
        }
        return;
      }

      this.syncSelectedHistoryFromPreview();

      if (tracked.status === 'cancelled' || tracked.status === 'error') {
        if (tracked.status === 'error') {
          this.error = data.error || 'Generation failed';
          this.clearClientGenerationQueue();
        }
        if (this.previewFocusPromptId === tracked.promptId) {
          this.previewFocusPromptId = null;
        }
        this.removeTrackedJob(tracked.promptId);
      }
    },

    async pollOneComfyuiJob(promptId) {
      try {
        const r = await fetch(
          '/api/comfyui/job/' + encodeURIComponent(promptId),
          { cache: 'no-store' }
        );
        if (!r.ok) {
          if (r.status === 404) {
            await this.reconcilePersistedJob(promptId);
          }
          return;
        }
        const data = await r.json();
        const tracked = this.trackedJobs.find((t) => t.promptId === promptId);
        if (!tracked) return;
        this.updateTrackedJobFromPoll(tracked, data);
        this.syncClientBatchSlotVisibility();
        if (!this.isTerminalJobStatus(tracked.status)) {
          this._persistTrackedJob(tracked);
        }
      } catch {
        /* keep polling until job endpoint responds */
      }
    },

    async pollAllComfyuiJobs() {
      const active = this.trackedJobs.filter(
        (t) => !this.isTerminalJobStatus(t.status)
      );
      if (!active.length) {
        this.stopComfyuiJobPoll(false);
        return;
      }
      await Promise.all(active.map((t) => this.pollOneComfyuiJob(t.promptId)));
      this.syncPrimaryProgressDisplay();
      this.drainClientGenerationQueue();
      this.$nextTick(() => this.updateHistoryScrollState());
    },

    startComfyuiJobPoll(promptId, promptIds, sceneOrAct) {
      this.previewMagnifierLeave();
      this.stopComfyuiJobPoll();
      const snap =
        sceneOrAct && typeof sceneOrAct === 'object'
          ? sceneOrAct
          : this.sceneSnapshotForJob(this.result);
      if (sceneOrAct && typeof sceneOrAct !== 'object') {
        snap.animationSlug = sceneOrAct;
      }
      this.registerTrackedJobs(promptId, promptIds, snap, { autoFocus: true });
    },

    comfyuiQueueLabel() {
      const pid = this.primaryInferencePromptId();
      if (!pid) return '';
      const job = this.trackedJobs.find((t) => t.promptId === pid);
      if (job.batchIndex == null) return '';
      const total = job.batchTotal || job.batchPromptIds?.length;
      if (!total) return '';
      return ` (${job.batchIndex + 1}/${total})`;
    },

    comfyuiStatusLabel() {
      if (this.comfyuiInferenceActive()) {
        return `${this.comfyuiProgressPct}%${this.comfyuiQueueLabel()}`;
      }
      if (this.comfyuiAnyJobActive()) {
        const n = this.trackedJobs.filter((t) => t.status === 'downloading').length;
        return n > 1 ? `Downloading ${n} images…` : 'Downloading…';
      }
      const pending = this.comfyuiPendingCount;
      switch (this.comfyuiState) {
        case 'generating':
          return pending > 0 ? `Generating · ${pending} queued` : 'Generating';
        case 'queued':
          return pending === 1 ? 'Queued' : `Queued (${pending})`;
        case 'idle':
          return 'Idle';
        default:
          return 'Not connected';
      }
    },

    comfyuiStatusTitle() {
      if (this.comfyuiJobWsWarning) return this.comfyuiJobWsWarning;
      if (this.comfyuiStatusError) return this.comfyuiStatusError;
      if (this.comfyuiState === 'offline') return 'Set server URL in Settings';
      return '';
    },

    async refreshComfyuiStatus() {
      if (typeof window.refreshComfyuiServerStatus === 'function') {
        await window.refreshComfyuiServerStatus(this);
      }
    },
    };
  }
  global.makeComfyuiMethods = makeComfyuiMethods;
})(window);

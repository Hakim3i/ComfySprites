/** Edit Lab — ComfyUI job polling and status display. */



function editComfyuiMethods() {

  return {

    trackedJobs: [],

    generating: false,

    comfyuiLab: EDIT_LAB_COMFYUI_LAB,



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



    syncPrimaryProgressDisplay() {

      const pid = this.primaryInferencePromptId();

      const job = pid ? this.trackedJobs.find((t) => t.promptId === pid) : null;

      this.comfyuiJobPromptId = pid;

      this.comfyuiProgressActive = this.comfyuiInferenceActive();

      if (job) {

        this.comfyuiProgressPct = job.progressPct;

        this.comfyuiPhaseLabel = job.phaseLabel;

        this.comfyuiJobWsWarning = job.wsWarning;

        this.comfyuiJobStartedAt = job.startedAt;

      } else {

        const downloading = this.trackedJobs.find((t) => t.status === 'downloading');

        if (downloading) {

          this.comfyuiProgressPct = downloading.progressPct;

          this.comfyuiPhaseLabel = downloading.phaseLabel;

          this.comfyuiJobWsWarning = downloading.wsWarning;

          this.comfyuiJobStartedAt = downloading.startedAt;

        } else {

          this.comfyuiProgressPct = 0;

          this.comfyuiPhaseLabel = '';

          this.comfyuiJobWsWarning = '';

        }

      }

    },



    registerTrackedJob(promptId) {

      if (!promptId) return;

      if (this.trackedJobs.some((t) => t.promptId === promptId)) return;

      this.comfyuiLastExecutionMs = null;

      if (typeof window.bumpComfyuiExecutionTick === 'function') {

        window.bumpComfyuiExecutionTick(this);

      }

      const now = Date.now();

      const trackedEntry = {

        promptId,

        status: 'queued',

        progressPct: 0,

        downloadPct: 0,

        phaseLabel: '',

        startedAt: now,

        finishedAt: null,

        wsWarning: '',

      };

      this.trackedJobs.push(trackedEntry);

      if (typeof window.persistLabJob === 'function') {

        window.persistLabJob(EDIT_LAB_COMFYUI_LAB, {

          promptId,

          startedAt: now,

          status: 'queued',

        });

      }

      this.syncPrimaryProgressDisplay();

    },



    removeTrackedJob(promptId) {

      const job = this.trackedJobs.find((t) => t.promptId === promptId);

      if (job && typeof window.captureExecutionOnRemove === 'function') {

        window.captureExecutionOnRemove(this, job);

      }

      this.trackedJobs = this.trackedJobs.filter((t) => t.promptId !== promptId);

      if (typeof window.removePersistedLabJob === 'function') {

        window.removePersistedLabJob(EDIT_LAB_COMFYUI_LAB, promptId);

      }

      this.syncPrimaryProgressDisplay();

      if (!this.comfyuiAnyJobActive()) {

        this.stopComfyuiJobPoll(false);

        this.generating = false;

        void this.refreshComfyuiStatus();

      }

    },



    stopComfyuiJobPoll(clearState) {

      if (typeof window.stopComfyuiJobPollLoop === 'function') {

        window.stopComfyuiJobPollLoop(this);

      }

      if (clearState !== false && !this.comfyuiAnyJobActive()) {

        this.comfyuiState = 'idle';

      }

      if (!this.comfyuiAnyJobActive()) {

        this.comfyuiJobPromptId = null;

        this.comfyuiProgressActive = false;

        this.comfyuiProgressPct = 0;

        this.comfyuiPhaseLabel = '';

        this.comfyuiJobWsWarning = '';

        this.comfyuiJobStartedAt = 0;

        this.generating = false;

      }

    },



    ensureComfyuiJobPoll() {

      if (typeof window.runComfyuiJobPollLoop !== 'function') return;

      window.runComfyuiJobPollLoop(

        this,

        this._comfyuiJobPollResumeOptions().jobPollOptions

      );

    },



    startComfyuiJobPoll(promptId) {

      this.stopComfyuiJobPoll(false);

      this.registerTrackedJob(promptId);

      this.generating = true;

      this.ensureComfyuiJobPoll();

    },



    updateTrackedJobFromPoll(tracked, data) {

      const prevStatus = tracked.status;

      tracked.status = data.status || tracked.status;

      tracked.progressPct = Number(data.progress_pct) || 0;

      tracked.downloadPct = Number(data.download_pct) || 0;

      tracked.phaseLabel =

        data.executing_label || data.phase_label || data.phase || '';



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



      if (tracked.status === 'complete') {

        const previewUrl =

          (Array.isArray(data.preview_urls) && data.preview_urls[0]) ||

          data.preview_url;

        if (previewUrl) {

          this.onGenerationComplete?.(previewUrl);

          this.selectedHistoryId = tracked.promptId;

        } else {

          void this.loadHistory();

        }

        this.removeTrackedJob(tracked.promptId);

        return;

      }



      if (tracked.status === 'cancelled' || tracked.status === 'error') {

        if (tracked.status === 'error') {

          this.showError(data.error || 'Edit generation failed');

        }

        this.removeTrackedJob(tracked.promptId);

      }

    },



    async pollOneComfyuiJob(promptId) {

      const result =

        typeof window.fetchComfyuiJob === 'function'

          ? await window.fetchComfyuiJob(promptId)

          : { ok: false, data: null };

      if (!result.ok || !result.data) return;

      const tracked = this.trackedJobs.find((t) => t.promptId === promptId);

      if (!tracked) return;

      this.updateTrackedJobFromPoll(tracked, result.data);

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

    },



    async stopGeneration() {

      const promptId = this.primaryInferencePromptId();

      if (!promptId) return;

      try {

        await fetch('/api/comfyui/job/' + encodeURIComponent(promptId) + '/cancel', {

          method: 'POST',

        });

      } catch {

        /* best effort */

      }

      this.removeTrackedJob(promptId);

    },



    comfyuiStatusLabel() {

      if (this.comfyuiInferenceActive()) {

        return `${this.comfyuiProgressPct}%`;

      }

      if (this.comfyuiAnyJobActive()) {

        const n = this.trackedJobs.filter((t) => t.status === 'downloading').length;

        return n > 1 ? `Downloading ${n} videos…` : 'Downloading…';

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

        await window.refreshComfyuiServerStatus(this, {

          lab: EDIT_LAB_COMFYUI_LAB,

        });

      }

    },

  };

}



/** Shared ComfyUI status resource metrics for Make and Video Lab. */
(function (global) {
  const EMPTY = { cpu_pct: null, ram_pct: null, gpu_pct: null, vram_pct: null };
  const EXECUTION_CLOCK_MS = 1000;
  const COMFYUI_STATUS_URL_DEFAULT = '/api/comfyui/status';
  const COMFYUI_STATUS_POLL_MS = 2500;
  const COMFYUI_STATUS_MIN_GAP_MS = 1500;

  let statusPollIntervalId = null;
  let statusRefreshInFlight = false;
  let statusLastRefreshAt = 0;

  const COMFYUI_BADGE_CLASS = {
    generating: 'accent',
    queued: 'warn',
    idle: 'good',
    offline: 'muted',
  };

  function comfyuiMetricDisplay(pct) {
    if (pct == null || pct === '' || Number.isNaN(Number(pct))) {
      return '—%';
    }
    const n = Math.round(Math.max(0, Math.min(100, Number(pct))));
    return `${n}%`;
  }

  function applyComfyuiResources(ctx, data) {
    const r = data && data.resources ? data.resources : EMPTY;
    ctx.comfyuiResources = {
      cpu_pct: r.cpu_pct ?? null,
      ram_pct: r.ram_pct ?? null,
      gpu_pct: r.gpu_pct ?? null,
      vram_pct: r.vram_pct ?? null,
    };
  }

  function applyComfyuiServerStatus(ctx, data) {
    if (!ctx.comfyuiAnyJobActive?.()) {
      ctx.comfyuiState = data.state || (data.connected ? 'idle' : 'offline');
    }
    ctx.comfyuiPendingCount = Number(data.pending_count) || 0;
    applyComfyuiResources(ctx, data);
    if (!data.connected) {
      ctx.comfyuiStatusError = data.error || '';
    } else if (!ctx.comfyuiAnyJobActive?.()) {
      ctx.comfyuiStatusError = data.error || '';
    }
  }

  function comfyuiStatusUrl(lab) {
    const base = COMFYUI_STATUS_URL_DEFAULT;
    if (lab === 'make' || lab === 'photo' || lab === 'video') {
      return `${base}?lab=${encodeURIComponent(lab)}`;
    }
    return base;
  }

  async function refreshComfyuiServerStatus(ctx, options = {}) {
    const minGapMs = options.minGapMs ?? 0;
    if (statusRefreshInFlight) return;
    if (minGapMs > 0 && Date.now() - statusLastRefreshAt < minGapMs) return;
    statusRefreshInFlight = true;
    const lab = options.lab ?? ctx.comfyuiLab ?? 'make';
    try {
      const r = await fetch(comfyuiStatusUrl(lab), { cache: 'no-store' });
      applyComfyuiServerStatus(ctx, await r.json());
      statusLastRefreshAt = Date.now();
    } catch {
      ctx.comfyuiState = 'offline';
      ctx.comfyuiPendingCount = 0;
      ctx.comfyuiStatusError = 'Could not reach ComfySprites API';
      applyComfyuiResources(ctx, null);
      statusLastRefreshAt = Date.now();
    } finally {
      statusRefreshInFlight = false;
    }
  }

  function startComfyuiStatusPoll(ctx, options = {}) {
    const lab = options.lab ?? ctx.comfyuiLab ?? 'make';
    ctx.comfyuiLab = lab;
    stopComfyuiStatusPoll();
    void refreshComfyuiServerStatus(ctx, { lab });
    statusPollIntervalId = setInterval(
      () =>
        refreshComfyuiServerStatus(ctx, {
          lab,
          minGapMs: COMFYUI_STATUS_MIN_GAP_MS,
        }),
      COMFYUI_STATUS_POLL_MS
    );
  }

  function stopComfyuiStatusPoll() {
    if (statusPollIntervalId) {
      clearInterval(statusPollIntervalId);
      statusPollIntervalId = null;
    }
  }

  function labJobsStorageKey(lab) {
    return `coomfy:activeJobs:${lab}`;
  }

  function readPersistedLabJobs(lab) {
    if (typeof sessionStorage === 'undefined') return [];
    try {
      const raw = sessionStorage.getItem(labJobsStorageKey(lab));
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function writePersistedLabJobs(lab, jobs) {
    if (typeof sessionStorage === 'undefined') return;
    try {
      const key = labJobsStorageKey(lab);
      if (!jobs.length) sessionStorage.removeItem(key);
      else sessionStorage.setItem(key, JSON.stringify(jobs));
    } catch {
      /* quota / private mode */
    }
  }

  function persistLabJob(lab, entry) {
    if (!lab || !entry?.promptId) return;
    const jobs = readPersistedLabJobs(lab).filter(
      (j) => j.promptId !== entry.promptId
    );
    jobs.push(entry);
    writePersistedLabJobs(lab, jobs);
  }

  function removePersistedLabJob(lab, promptId) {
    if (!lab || !promptId) return;
    writePersistedLabJobs(
      lab,
      readPersistedLabJobs(lab).filter((j) => j.promptId !== promptId)
    );
  }

  async function fetchComfyuiJob(promptId) {
    try {
      const r = await fetch(
        '/api/comfyui/job/' + encodeURIComponent(promptId),
        { cache: 'no-store' }
      );
      if (!r.ok) return { ok: false, status: r.status, data: null };
      return { ok: true, status: r.status, data: await r.json() };
    } catch {
      return { ok: false, status: 0, data: null };
    }
  }

  /**
   * Non-overlapping job poll loop — avoids stacking fetches that starve
   * /api/comfyui/status (browser ~6 connections per host).
   */
  function runComfyuiJobPollLoop(ctx, { intervalMs, pollOnce, onStart }) {
    stopComfyuiJobPollLoop(ctx);
    ctx._comfyuiJobPollRunning = true;
    ctx._comfyuiJobPollGen = (ctx._comfyuiJobPollGen || 0) + 1;
    const gen = ctx._comfyuiJobPollGen;
    if (typeof onStart === 'function') onStart();
    let statusEvery = 0;

    void (async () => {
      while (ctx._comfyuiJobPollRunning && gen === ctx._comfyuiJobPollGen) {
        await pollOnce();
        if (ctx.comfyuiAnyJobActive?.()) {
          bumpComfyuiExecutionTick(ctx);
        }
        if (!ctx._comfyuiJobPollRunning || gen !== ctx._comfyuiJobPollGen) break;
        statusEvery += 1;
        if (statusEvery >= 2 && ctx.comfyuiAnyJobActive?.()) {
          statusEvery = 0;
          void refreshComfyuiServerStatus(ctx, {
            lab: ctx.comfyuiLab ?? 'make',
            minGapMs: COMFYUI_STATUS_MIN_GAP_MS,
          });
        }
        await new Promise((resolve) => setTimeout(resolve, intervalMs));
      }
    })();
  }

  function stopComfyuiJobPollLoop(ctx) {
    ctx._comfyuiJobPollRunning = false;
    ctx._comfyuiJobPollGen = (ctx._comfyuiJobPollGen || 0) + 1;
  }

  /** Restart job polling after tab focus, bfcache restore, or a stalled loop. */
  function resumeComfyuiJobPolling(ctx, { pollOnce, jobPollOptions } = {}) {
    if (document.hidden) return;
    void refreshComfyuiServerStatus(ctx, {
      lab: ctx.comfyuiLab ?? 'make',
      minGapMs: 0,
    });
    if (!ctx.comfyuiAnyJobActive?.()) return;
    if (typeof pollOnce === 'function') {
      void pollOnce();
    }
    if (jobPollOptions) {
      runComfyuiJobPollLoop(ctx, jobPollOptions);
    }
  }

  function bindComfyuiLabResume(ctx, options) {
    const onResume = () => resumeComfyuiJobPolling(ctx, options);
    const onPageShow = (event) => {
      if (event.persisted) onResume();
    };
    document.addEventListener('visibilitychange', onResume);
    window.addEventListener('pageshow', onPageShow);
    window.addEventListener('focus', onResume);
    return () => {
      document.removeEventListener('visibilitychange', onResume);
      window.removeEventListener('pageshow', onPageShow);
      window.removeEventListener('focus', onResume);
    };
  }

  /** 0–50 white, 51–89 orange, 90–100 red. */
  function comfyuiMetricLevelClass(pct) {
    if (pct == null || pct === '' || Number.isNaN(Number(pct))) {
      return 'make-comfyui-metric-val--na';
    }
    const n = Math.round(Math.max(0, Math.min(100, Number(pct))));
    if (n <= 50) return 'make-comfyui-metric-val--ok';
    if (n >= 90) return 'make-comfyui-metric-val--crit';
    return 'make-comfyui-metric-val--warn';
  }

  function formatDurationMmSs(ms) {
    if (ms == null || !Number.isFinite(ms) || ms < 0) {
      return '—:—';
    }
    const totalSec = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSec / 60);
    const seconds = totalSec % 60;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }

  function jobExecutionStartedAt(tracked, trackedJobs) {
    if (!tracked) {
      return null;
    }
    if (Array.isArray(tracked.batchPromptIds) && tracked.batchPromptIds.length) {
      const peers = trackedJobs.filter(
        (t) => t.batchPromptIds === tracked.batchPromptIds
      );
      const times = peers.map((t) => t.startedAt).filter((n) => n > 0);
      return times.length ? Math.min(...times) : tracked.startedAt;
    }
    return tracked.startedAt;
  }

  function noteJobFinished(ctx, tracked) {
    if (!tracked || !ctx.isTerminalJobStatus?.(tracked.status)) {
      return;
    }
    const batchIds = tracked.batchPromptIds;
    if (Array.isArray(batchIds) && batchIds.length && ctx.trackedJobs) {
      if (!tracked.finishedAt) {
        tracked.finishedAt = Date.now();
      }
      const peers = ctx.trackedJobs.filter((t) => t.batchPromptIds === batchIds);
      const stillRunning = peers.some((t) => !ctx.isTerminalJobStatus(t.status));
      if (stillRunning) {
        return;
      }
      const started = jobExecutionStartedAt(tracked, ctx.trackedJobs);
      if (started) {
        const finishedAt = Math.max(
          ...peers.map((t) => t.finishedAt || Date.now())
        );
        ctx.comfyuiLastExecutionMs = finishedAt - started;
        for (const t of peers) {
          if (!t.finishedAt) {
            t.finishedAt = finishedAt;
          }
        }
      }
      return;
    }
    if (tracked.finishedAt) {
      return;
    }
    tracked.finishedAt = Date.now();
    if (tracked.startedAt) {
      ctx.comfyuiLastExecutionMs = tracked.finishedAt - tracked.startedAt;
    }
  }

  function activeJobForExecutionTime(ctx) {
    if (!ctx.trackedJobs || !ctx.isTerminalJobStatus) {
      return null;
    }
    const active = ctx.trackedJobs
      .filter((t) => !ctx.isTerminalJobStatus(t.status))
      .sort((a, b) => (a.startedAt || 0) - (b.startedAt || 0));
    return active[0] || null;
  }

  function bumpComfyuiExecutionTick(ctx) {
    if (!ctx || !('comfyuiExecutionTick' in ctx)) return;
    ctx.comfyuiExecutionTick = (ctx.comfyuiExecutionTick || 0) + 1;
  }

  function executionTimeMs(ctx) {
    void ctx.comfyuiExecutionTick;
    const active = activeJobForExecutionTime(ctx);
    if (active) {
      const started = jobExecutionStartedAt(active, ctx.trackedJobs);
      if (started) {
        return Date.now() - started;
      }
    }
    if (ctx.comfyuiLastExecutionMs != null) {
      return ctx.comfyuiLastExecutionMs;
    }
    return 0;
  }

  function startComfyuiExecutionClock(ctx) {
    if (!ctx) return;
    stopComfyuiExecutionClock(ctx);
    bumpComfyuiExecutionTick(ctx);
    ctx.comfyuiExecutionClockId = setInterval(() => {
      bumpComfyuiExecutionTick(ctx);
    }, EXECUTION_CLOCK_MS);
  }

  function stopComfyuiExecutionClock(ctx) {
    if (!ctx?.comfyuiExecutionClockId) {
      return;
    }
    clearInterval(ctx.comfyuiExecutionClockId);
    ctx.comfyuiExecutionClockId = null;
  }

  function comfyuiExecutionTimeDisplay(ctx) {
    return formatDurationMmSs(executionTimeMs(ctx));
  }

  /** Preserve elapsed time when a job row is removed before a terminal poll. */
  function captureExecutionOnRemove(ctx, job) {
    if (!job?.startedAt || !ctx.trackedJobs || !ctx.isTerminalJobStatus) {
      return;
    }
    const othersActive = ctx.trackedJobs.some(
      (t) =>
        t.promptId !== job.promptId && !ctx.isTerminalJobStatus(t.status)
    );
    if (othersActive) {
      return;
    }
    if (ctx.comfyuiLastExecutionMs != null && ctx.isTerminalJobStatus(job.status)) {
      return;
    }
    const started = jobExecutionStartedAt(job, ctx.trackedJobs);
    if (started) {
      ctx.comfyuiLastExecutionMs = Date.now() - started;
    }
  }

  global.COMFYUI_BADGE_CLASS = COMFYUI_BADGE_CLASS;
  global.comfyuiMetricDisplay = comfyuiMetricDisplay;
  global.applyComfyuiResources = applyComfyuiResources;
  global.applyComfyuiServerStatus = applyComfyuiServerStatus;
  global.refreshComfyuiServerStatus = refreshComfyuiServerStatus;
  global.startComfyuiStatusPoll = startComfyuiStatusPoll;
  global.stopComfyuiStatusPoll = stopComfyuiStatusPoll;
  global.runComfyuiJobPollLoop = runComfyuiJobPollLoop;
  global.stopComfyuiJobPollLoop = stopComfyuiJobPollLoop;
  global.resumeComfyuiJobPolling = resumeComfyuiJobPolling;
  global.bindComfyuiLabResume = bindComfyuiLabResume;
  global.readPersistedLabJobs = readPersistedLabJobs;
  global.persistLabJob = persistLabJob;
  global.removePersistedLabJob = removePersistedLabJob;
  global.fetchComfyuiJob = fetchComfyuiJob;
  global.comfyuiMetricLevelClass = comfyuiMetricLevelClass;
  global.noteJobFinished = noteJobFinished;
  global.captureExecutionOnRemove = captureExecutionOnRemove;
  global.bumpComfyuiExecutionTick = bumpComfyuiExecutionTick;
  global.startComfyuiExecutionClock = startComfyuiExecutionClock;
  global.stopComfyuiExecutionClock = stopComfyuiExecutionClock;
  global.comfyuiExecutionTimeDisplay = comfyuiExecutionTimeDisplay;
})(typeof window !== 'undefined' ? window : globalThis);

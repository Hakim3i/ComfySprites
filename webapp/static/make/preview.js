(function (global) {
  function makePreviewMethods() {
    return {

    pendingHistorySlots() {
      return this.trackedJobs
        .filter((t) => t.slotVisible && !this.isTerminalJobStatus(t.status))
        .slice()
        .reverse();
    },

    sceneSnapshotForJob(build) {
      const scene = build?.scene;
      if (scene && typeof scene === 'object') {
        return {
          animationSlug: scene.animation || this.displayValueForField('animation'),
          placeKey: scene.background || this.displayValueForField('place'),
        };
      }
      return {
        animationSlug: this.displayValueForField('animation'),
        placeKey: this.displayValueForField('place'),
      };
    },

    _normalizeSceneSnapshot(sceneOrAct) {
      if (sceneOrAct && typeof sceneOrAct === 'object') {
        return {
          animationSlug: sceneOrAct.animationSlug || this.displayValueForField('animation'),
          placeKey: sceneOrAct.placeKey || this.displayValueForField('place'),
        };
      }
      return {
        animationSlug: sceneOrAct || this.displayValueForField('animation'),
        placeKey: this.displayValueForField('place'),
      };
    },

    pendingSlotSceneLabel(slot) {
      const parts = [];
      const act = this.actLabelForSlug(slot?.animationSlug);
      if (act && act !== '—') parts.push(act);
      const place = this.locationLabelForKey(slot?.placeKey);
      if (place) parts.push(place);
      return parts.length ? parts.join(' · ') : '—';
    },

    isNarrowViewport() {
      return (
        typeof window !== 'undefined' &&
        window.innerWidth <= MAKE_LAB_BREAKPOINT_NARROW
      );
    },

    pendingSlotDetail(slot) {
      if (slot.status === 'fetching_assets') return 'Fetching models';
      if (slot.status === 'downloading') return 'Downloading';
      if (slot.status === 'queued') return 'Queued';
      return (slot.phaseLabel || 'Generating').trim();
    },

    activePreviewPromptId() {
      if (this.previewFocusPromptId) return this.previewFocusPromptId;
      if (this.previewAutoFollowInference) {
        return this.primaryInferencePromptId();
      }
      return null;
    },

    isPendingSlotSelected(slot) {
      if (!slot?.promptId) return false;
      return this.activePreviewPromptId() === slot.promptId;
    },

    syncSelectedHistoryFromPreview() {
      if (this.isPreviewPinnedToCompleted()) return;
      const active = this.activePreviewPromptId();
      if (!active) return;
      const pending = this.trackedJobs.find((t) => t.promptId === active);
      if (pending && !this.isTerminalJobStatus(pending.status)) {
        this.selectedHistoryId = active;
      }
    },

    isPreviewPinnedToCompleted() {
      const id = this.previewFocusPromptId;
      if (!id || this.previewAutoFollowInference) return false;
      return !this.trackedJobs.some((t) => t.promptId === id);
    },

    shouldUpdateLivePreviewFor(tracked) {
      if (!tracked) return false;
      return (
        this.previewFollowLiveSampling() &&
        this.activePreviewPromptId() === tracked.promptId
      );
    },

    revokeTrackedPreviewBlob(tracked) {
      if (!tracked?._previewBlobUrl) return;
      URL.revokeObjectURL(tracked._previewBlobUrl);
      tracked._previewBlobUrl = null;
    },

    async snapshotTrackedPreview(tracked) {
      if (!tracked) return null;
      if (tracked._previewBlobUrl) return tracked._previewBlobUrl;
      const source = tracked.lastLivePreviewUrl;
      if (!source) return null;
      try {
        const r = await fetch(this.cacheBustUrl(source));
        if (!r.ok) return null;
        const blob = await r.blob();
        if (!blob.size) return null;
        this.revokeTrackedPreviewBlob(tracked);
        tracked._previewBlobUrl = URL.createObjectURL(blob);
        return tracked._previewBlobUrl;
      } catch {
        return null;
      }
    },

    focusPreviewJob(promptId) {
      if (!promptId) return;
      this.previewFocusPromptId = promptId;
      this.previewAutoFollowInference = false;
      this.previewLiveSampling = true;
      this.selectedHistoryId = promptId;
      const tracked = this.trackedJobs.find((t) => t.promptId === promptId);
      if (tracked?.status === 'downloading') {
        void this.snapshotTrackedPreview(tracked).then((url) => {
          if (this.previewFocusPromptId === promptId) {
            this.outputImage = url || null;
            this.$nextTick(() => this.onViewportResize());
          }
        });
        return;
      }
      if (
        tracked &&
        this.isInferenceJobStatus(tracked.status) &&
        tracked.lastLivePreviewUrl
      ) {
        this.outputImage = this.cacheBustUrl(tracked.lastLivePreviewUrl);
        this.$nextTick(() => this.onViewportResize());
      }
    },

    pinPreviewToCompletedJob(promptId, imageId, previewUrl) {
      this.previewAutoFollowInference = false;
      this.previewLiveSampling = false;
      const id = imageId || promptId;
      this.previewFocusPromptId = id;
      this.selectedHistoryId = id;
      if (previewUrl) {
        this.outputImage = this.cacheBustUrl(previewUrl);
        this.$nextTick(() => this.onViewportResize());
      }
    },

    focusedTrackedJob() {
      const id = this.activePreviewPromptId();
      if (!id) return null;
      return this.trackedJobs.find((t) => t.promptId === id) || null;
    },

    previewShowDownloadOverlay() {
      const job = this.focusedTrackedJob();
      return job?.status === 'downloading';
    },

    previewFocusedDownloadPct() {
      const job = this.focusedTrackedJob();
      return job?.downloadPct ?? 0;
    },

    selectPendingSlot(slot) {
      if (!slot?.promptId) return;
      this.focusPreviewJob(slot.promptId);
    },

    previewFollowLiveSampling() {
      if (!this.previewLiveSampling || this.isPreviewPinnedToCompleted()) {
        return false;
      }
      const focusId = this.activePreviewPromptId();
      if (!focusId) return false;
      const focused = this.trackedJobs.find((t) => t.promptId === focusId);
      return focused ? this.isInferenceJobStatus(focused.status) : false;
    },

    async resolvePreviewImageBlob() {
      const url = this.outputImage;
      if (!url) throw new Error('No preview image');

      if (String(url).startsWith('blob:')) {
        const r = await fetch(url);
        if (!r.ok) throw new Error('Could not load preview image');
        const blob = await r.blob();
        if (!blob.size) throw new Error('Preview image is empty');
        return blob;
      }

      const hist = this.historyItemForFocusedPreview();
      if (hist?.image_url) {
        const r = await fetch(this.cacheBustUrl(hist.image_url));
        if (r.ok) {
          const blob = await r.blob();
          if (blob.size) return blob;
        }
      }

      const tracked = this.focusedTrackedJob();
      if (tracked?._previewBlobUrl) {
        const r = await fetch(tracked._previewBlobUrl);
        if (r.ok) {
          const blob = await r.blob();
          if (blob.size) return blob;
        }
      }

      const base = String(url).split('?')[0];
      const r = await fetch(this.cacheBustUrl(base));
      if (!r.ok) throw new Error('Could not load preview image');
      const blob = await r.blob();
      if (!blob.size) throw new Error('Preview image is empty');
      return blob;
    },

    async setPickFieldCoverFromPreview(field) {
      const uploadUrl = this.pickFieldCoverUploadUrl(field);
      if (!uploadUrl || !this.outputImage) return;
      const label = this.pickFieldCoverTargetLabel(field);
      const ok = confirm(
        `Use the current preview as the reference image for "${label}"?\n\nThis replaces the existing cover photo.`
      );
      if (!ok) return;
      this.coverUploadBusy = true;
      this.error = '';
      try {
        const blob = await this.resolvePreviewImageBlob();
        const fd = new FormData();
        fd.append('file', blob, 'cover.png');
        const up = await fetch(uploadUrl, { method: 'POST', body: fd });
        const { data } = await parseApiResponse(up);
        if (!up.ok) {
          this.error = apiErrorDetail(data, up.status, 'Cover upload failed');
          return;
        }
        if (!data.image_path) {
          this.error = 'Cover upload succeeded but no image path was returned.';
          return;
        }
        this._patchCatalogImagePath(field, data.image_path);
        this.catalogThumbEpoch = Date.now();
      } catch (e) {
        this.error = 'Cover upload failed (' + e.message + ').';
      } finally {
        this.coverUploadBusy = false;
      }
    },

    normalizePreviewUrl(url) {
      return String(url || '').split('?')[0];
    },

    historyItemForFocusedPreview() {
      const id = this.focusedPreviewPromptId();
      if (id) {
        const byId = this.historyItems.find((it) => it.prompt_id === id);
        if (byId) return byId;
      }
      if (this.outputImage) {
        const cur = this.normalizePreviewUrl(this.outputImage);
        return (
          this.historyItems.find(
            (it) => this.normalizePreviewUrl(it.image_url) === cur
          ) || null
        );
      }
      return null;
    },

    onPreviewInferenceChanged() {
      this.previewBuildSizeStale = true;
      this.$nextTick(() => this.onViewportResize());
    },

    cacheBustUrl(url) {
      if (!url) return '';
      const s = String(url);
      if (s.startsWith('blob:')) return s;
      const sep = s.includes('?') ? '&' : '?';
      return s + sep + '_=' + Date.now();
    },

    effectivePreviewOrientation() {
      const choice = (this.form.orientation || '').trim().toLowerCase();
      if (choice === 'portrait' || choice === 'landscape') return choice;
      const built = (this.result?.scene?.orientation || '').trim().toLowerCase();
      if (built === 'portrait' || built === 'landscape') return built;
      const dimKey =
        this.canonicalDimensionKeyFromKey(this.form.dimension) ||
        this.defaultDimension();
      const dim = this.parseDimension(dimKey);
      const fromDim = () =>
        dim && dim.width > dim.height ? 'landscape' : 'portrait';
      if (choice === 'both') return fromDim();
      if (!this.animationIsRandom() && this.form.animation) {
        const act = this.animationBySlug(this.form.animation);
        const ao = (act?.orientation || '').trim().toLowerCase();
        if (ao === 'portrait' || ao === 'landscape') return ao;
        if (ao === 'both') return fromDim();
      }
      if (!this.styleIsRandom() && this.form.style) {
        const style = this.styleBySlug(this.form.style);
        if (style?.width && style?.height) {
          return style.width <= style.height ? 'portrait' : 'landscape';
        }
      }
      return fromDim();
    },

    expectedPreviewDimensions() {
      const sdxl = this.result?.sdxl;
      if (
        !this.previewBuildSizeStale &&
        sdxl?.width &&
        sdxl?.height
      ) {
        return {
          width: Number(sdxl.width),
          height: Number(sdxl.height),
        };
      }
      const o = this.effectivePreviewOrientation();
      const dimKey =
        this.canonicalDimensionKeyFromKey(this.form.dimension) ||
        this.defaultDimension();
      const dim = this.parseDimension(dimKey);
      if (!dim) return { width: 1024, height: 1024 };
      let w = dim.width;
      let h = dim.height;
      if (o === 'landscape' && h > w) {
        const t = w;
        w = h;
        h = t;
      } else if (o === 'portrait' && w > h) {
        const t = w;
        w = h;
        h = t;
      }
      return { width: w, height: h };
    },

    previewSizeLabel() {
      const { width, height } = this.expectedPreviewDimensions();
      return width + 'x' + height;
    },

    syncHistoryHeight() {
      const history = this.$refs.historyPanel;
      const controls = this.$refs.controlsColumn;
      const locationCard = this.$refs.locationCard;
      if (!history || !controls || !locationCard) return;
      if (this.isNarrowViewport()) {
        history.style.height = '';
        history.style.maxHeight = '';
        return;
      }
      const top = controls.getBoundingClientRect().top;
      const bottom = locationCard.getBoundingClientRect().bottom;
      const h = Math.max(120, Math.ceil(bottom - top));
      history.style.height = h + 'px';
      history.style.maxHeight = h + 'px';
    },

    onViewportResize() {
      this.syncHistoryHeight();
      this.viewportTick += 1;
      this.$nextTick(() => this.updateHistoryScrollState());
    },

    previewBounds() {
      void this.viewportTick;
      const bottomPad = 24;
      const vw = typeof window !== 'undefined' ? window.innerWidth : 1200;
      const vh = typeof window !== 'undefined' ? window.innerHeight : 900;
      const narrow = vw <= MAKE_LAB_BREAKPOINT_NARROW;
      const historyInset = 0;
      const rootStyle =
        typeof getComputedStyle !== 'undefined'
          ? getComputedStyle(document.documentElement)
          : null;
      const colLeft = rootStyle
        ? parseInt(rootStyle.getPropertyValue('--make-col-left'), 10) || 425
        : 425;
      const colRight = rootStyle
        ? parseInt(rootStyle.getPropertyValue('--make-col-right'), 10) || 320
        : 320;
      const center = this.$refs.studioCenter;
      const wrap = this.$refs.previewWrap;
      let maxW = 320;
      let maxH = 240;
      if (wrap?.clientWidth > 0) {
        maxW = wrap.clientWidth;
      } else if (center?.clientWidth) {
        maxW = Math.max(160, center.clientWidth - historyInset);
      } else {
        const mainPad = 48;
        const studioGaps = narrow ? 0 : 12 * 2;
        const colHistory = rootStyle
          ? parseInt(rootStyle.getPropertyValue('--make-history-w'), 10) || 132
          : 132;
        const sideW = narrow ? 0 : colLeft + colRight + colHistory;
        maxW = Math.max(
          160,
          Math.floor(vw - mainPad - sideW - studioGaps - historyInset)
        );
      }
      if (wrap && typeof wrap.getBoundingClientRect === 'function') {
        const top = wrap.getBoundingClientRect().top;
        maxH = Math.max(160, Math.floor(vh - top - bottomPad));
      } else {
        const chromeH = narrow ? 240 : 220;
        maxH = Math.max(160, Math.floor(vh - chromeH));
      }
      return { maxW, maxH };
    },

    previewStageBox() {
      const { width: w, height: h } = this.expectedPreviewDimensions();
      const { maxW, maxH } = this.previewBounds();
      const scale = Math.min(maxW / w, maxH / h, 1);
      const boxW = Math.max(1, Math.floor(w * scale));
      const boxH = Math.max(1, Math.floor(h * scale));
      return { w, h, boxW, boxH };
    },

    previewStageStyle() {
      const { boxW, boxH } = this.previewStageBox();
      return {
        width: boxW + 'px',
        height: boxH + 'px',
        maxWidth: '100%',
        maxHeight: '100%',
        flexShrink: 0,
      };
    },

    previewMagnifierReady() {
      return (
        Boolean(this.outputImage) &&
        !this.previewShowDownloadOverlay() &&
        (!this.comfyuiInferenceActive() || !this.previewLiveSampling)
      );
    },

    previewMagnifierMove(event) {
      if (!this.previewMagnifierReady()) {
        this.previewMagnifier.active = false;
        return;
      }
      const el = event.currentTarget;
      const rect = el.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) return;
      const x = (event.clientX - rect.left) / rect.width;
      const y = (event.clientY - rect.top) / rect.height;
      this.previewMagnifier = {
        active: true,
        x: Math.min(1, Math.max(0, x)),
        y: Math.min(1, Math.max(0, y)),
      };
    },

    previewMagnifierLeave() {
      this.previewMagnifier.active = false;
    },

    previewMagnifierImgStyle() {
      if (!this.previewMagnifier.active || !this.previewMagnifierReady()) {
        return {};
      }
      const x = this.previewMagnifier.x * 100;
      const y = this.previewMagnifier.y * 100;
      return {
        transform: `scale(${MAKE_LAB_PREVIEW_MAGNIFIER_ZOOM})`,
        transformOrigin: `${x}% ${y}%`,
      };
    },

    async previewMetadata() {
      this.busy = true;
      this.error = '';
      try {
        const stored = await this.resolveMetadataBuild();
        if (stored) {
          this.openMetadataWithBuild(stored);
          return;
        }

        const payload = this.buildPayload();
        const r = await fetch('/api/build', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await r.json();
        if (!r.ok) {
          this.error = data.detail || 'HTTP ' + r.status;
          this.result = null;
          this.metadataOpen = false;
        } else {
          this.result = data;
          this.applyBuildPreviewSize(data);
          const styleWasRandom = this.formRandom.style;
          this.runWithDetailerSyncSuppressed(() => {
            this.pinResolvedSceneDisplay(data);
            this.applyRequestToForm(data.request, data);
          });
          const rolledStyle = data.scene?.style;
          if (rolledStyle && styleWasRandom) {
            this.applyInferenceFromStyle(rolledStyle, { dimension: false });
          }
          this.metadataOpen = true;
        }
      } catch (e) {
        this.error = 'Request failed (' + e.message + ').';
        this.result = null;
      } finally {
        this.busy = false;
      }
    },

    promptSegTooltip(idx, seg) {
      return window.coomfyPromptSegments.segTooltip(idx, seg);
    },

    sdxlJoined(side) {
      return window.coomfyPromptSegments.sdxlJoined(this.result, side);
    },

    refineJoined(side) {
      return window.coomfyPromptSegments.refineJoined(this.result, side);
    },

    copyPrompt(side, evt) {
      const text = this.sdxlJoined(side) || this.result?.sdxl?.[side] || '';
      window.coomfyPromptSegments.copyText(text, evt);
    },

    copyRefinePrompt(side, evt) {
      const text = this.refineJoined(side) || this.result?.refine_sdxl?.[side] || '';
      window.coomfyPromptSegments.copyText(text, evt);
    }
    };
  }
  global.makePreviewMethods = makePreviewMethods;
})(window);

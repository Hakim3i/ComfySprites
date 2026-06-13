(function (global) {
  function makePipelineMethods() {
    return {

    defaultDetailerTiming() {
      if (!this.form.refine_enabled) return 'after';
      return this.refineStyleSameAsInference() ? 'after' : 'before';
    },

    detailerRunEnabled() {
      return this.form.detailer_timing !== 'disabled';
    },

    upscaleRunEnabled() {
      return this.form.upscale_timing !== 'disabled';
    },

    normalizePipelineTimingWithoutRefine() {
      if (this.form.refine_enabled) return;
      if (this.form.upscale_timing === 'before') {
        this.form.upscale_timing = 'after';
      }
      if (this.form.detailer_timing === 'before') {
        this.form.detailer_timing = 'after';
      }
      this.form.upscale_enabled = this.form.upscale_timing !== 'disabled';
    },

    syncDetailerTimingDefault() {
      if (!this.detailerTimingTouched && this.form.detailer_timing !== 'disabled') {
        this.form.detailer_timing = this.defaultDetailerTiming();
      }
    },

    setDetailerRun(value) {
      if (value === 'disabled' || value === 'before' || value === 'after') {
        this.form.detailer_timing = value;
        this.detailerTimingTouched = true;
      }
    },

    setDetailerEnabled(enabled) {
      if (enabled) {
        this.form.detailer_timing = this.form.refine_enabled
          ? this.defaultDetailerTiming()
          : 'after';
      } else {
        this.form.detailer_timing = 'disabled';
      }
      this.detailerTimingTouched = true;
    },

    setRmbgRun(enabled) {
      this.rmbg.enabled = !!enabled;
    },

    setRefineEnabled(enabled) {
      this.form.refine_enabled = !!enabled;
      if (!enabled) {
        this.normalizePipelineTimingWithoutRefine();
      }
      this.form.upscale_enabled = this.form.upscale_timing !== 'disabled';
    },

    setUpscaleEnabled(enabled) {
      this.form.upscale_timing = enabled ? 'after' : 'disabled';
      this.form.upscale_enabled = enabled;
    },

    setUpscaleTiming(value) {
      if (value !== 'disabled' && value !== 'before' && value !== 'after') return;
      if (value === 'before' && !this.form.refine_enabled) return;
      this.form.upscale_timing = value;
      this.form.upscale_enabled = value !== 'disabled';
    },

    rmbgColorLabel() {
      return String(this.rmbg.background_color || '#000000').toUpperCase();
    },

    normalizeRmbgProcessRes(value) {
      const raw = String(value ?? '').trim();
      return MAKE_LAB_RMBG_PROCESS_RES_OPTIONS.includes(raw)
        ? raw
        : MAKE_LAB_RMBG_PROCESS_RES_OPTIONS[1];
    },

    clampRmbgMaskBlur(event) {
      let raw = this.rmbg.mask_blur;
      if (event?.target?.value != null) raw = event.target.value;
      let n = parseInt(String(raw), 10);
      if (Number.isNaN(n) || n < 0) n = 0;
      if (n > MAKE_LAB_RMBG_MASK_BLUR_MAX) n = MAKE_LAB_RMBG_MASK_BLUR_MAX;
      this.rmbg.mask_blur = String(n);
    },

    stepRmbgMaskBlur(delta) {
      let n = parseInt(this.rmbg.mask_blur, 10);
      if (Number.isNaN(n)) n = 0;
      n = Math.min(MAKE_LAB_RMBG_MASK_BLUR_MAX, Math.max(0, n + delta));
      this.rmbg.mask_blur = String(n);
    },

    clampRmbgMaskOffset(event) {
      let raw = this.rmbg.mask_offset;
      if (event?.target?.value != null) raw = event.target.value;
      let n = parseInt(String(raw), 10);
      if (Number.isNaN(n)) n = 0;
      if (n < MAKE_LAB_RMBG_MASK_OFFSET_MIN) n = MAKE_LAB_RMBG_MASK_OFFSET_MIN;
      if (n > MAKE_LAB_RMBG_MASK_OFFSET_MAX) n = MAKE_LAB_RMBG_MASK_OFFSET_MAX;
      this.rmbg.mask_offset = String(n);
    },

    stepRmbgMaskOffset(delta) {
      let n = parseInt(this.rmbg.mask_offset, 10);
      if (Number.isNaN(n)) n = 0;
      n = Math.min(
        MAKE_LAB_RMBG_MASK_OFFSET_MAX,
        Math.max(MAKE_LAB_RMBG_MASK_OFFSET_MIN, n + delta)
      );
      this.rmbg.mask_offset = String(n);
    },

    detailerSyncBlocked() {
      return this._detailerSyncSuppress > 0;
    },

    runWithDetailerSyncSuppressed(fn) {
      this._detailerSyncSuppress += 1;
      try {
        return fn();
      } finally {
        this._detailerSyncSuppress = Math.max(0, this._detailerSyncSuppress - 1);
      }
    },

    detailerLabel(id) {
      const d = this.detailerRegions.find((r) => r.id === id);
      if (d?.label) return d.label;
      return id.charAt(0).toUpperCase() + id.slice(1);
    },

    toggleDetailer(id) {
      const list = [...(this.form.detailers || [])];
      const i = list.indexOf(id);
      if (i >= 0) list.splice(i, 1);
      else list.push(id);
      this.form.detailers = list;
    },

    detailerOrder() {
      return (this.detailerRegions || []).map((d) => d.id);
    },

    filterDetailersToOrder(ids) {
      const order = this.detailerOrder();
      const normalized = this.normalizeDetailerIds(ids);
      if (!order.length) {
        if (normalized.length) this._pendingDetailerIds = normalized;
        return [];
      }
      const enabled = new Set(normalized.filter((id) => order.includes(id)));
      return order.filter((id) => enabled.has(id));
    },

    applyDetailerSettingsFromRequest(request) {
      const raw = request?.detailers;
      if (Array.isArray(raw)) {
        const ordered = this.filterDetailersToOrder(raw);
        this.form.detailers = ordered;
        if (ordered.length === 0 && raw.length > 0) {
          this._pendingDetailerIds = this.normalizeDetailerIds(raw);
        }
      } else {
        this.form.detailers = [];
      }
      const timing = String(request?.detailer_timing || '').trim().toLowerCase();
      if (timing === 'disabled' || timing === 'before' || timing === 'after') {
        this.form.detailer_timing = timing;
        this.detailerTimingTouched = true;
      } else {
        this.detailerTimingTouched = false;
        this.syncDetailerTimingDefault();
      }
    },

    applyRmbgSettingsFromRequest(request) {
      const raw = request?.rmbg;
      if (!raw || typeof raw !== 'object') {
        this.rmbg.enabled = false;
        return;
      }
      this.rmbg.enabled = !!raw.enabled;
      if (raw.model) {
        const model = String(raw.model);
        this.rmbg.model = MAKE_LAB_RMBG_MODELS.includes(model) ? model : MAKE_LAB_RMBG_MODELS[0];
      }
      if (raw.sensitivity != null && raw.sensitivity !== '') {
        this.rmbg.sensitivity = String(raw.sensitivity);
      }
      if (raw.process_res != null && raw.process_res !== '') {
        this.rmbg.process_res = this.normalizeRmbgProcessRes(raw.process_res);
      }
      if (raw.mask_blur != null && raw.mask_blur !== '') {
        this.rmbg.mask_blur = String(raw.mask_blur);
        this.clampRmbgMaskBlur();
      }
      if (raw.mask_offset != null && raw.mask_offset !== '') {
        this.rmbg.mask_offset = String(raw.mask_offset);
        this.clampRmbgMaskOffset();
      }
      if (typeof raw.invert_output === 'boolean') {
        this.rmbg.invert_output = raw.invert_output;
      }
      if (typeof raw.refine_foreground === 'boolean') {
        this.rmbg.refine_foreground = raw.refine_foreground;
      }
      if (raw.background === 'Alpha' || raw.background === 'Color') {
        this.rmbg.background = raw.background;
      }
      if (raw.background_color) {
        this.rmbg.background_color = String(raw.background_color);
      }
    },

    controlnetTypeLabel(key) {
      const labels = { openpose: 'OpenPose', depth: 'Depth', canny: 'Canny' };
      return (labels[key] || String(key || '')).toUpperCase();
    },

    controlnetDefaults(key) {
      return (
        CONTROLNET_TYPE_DEFAULTS[key] || {
          strength: 0.9,
          start_percent: 0,
          end_percent: 1,
        }
      );
    },

    controlnetRowByKey(key) {
      return (this.controlnetRows || []).find((r) => r.key === key) || null;
    },

    controlnetEnabled(key) {
      return Boolean(this.form.controlnet?.[key]?.enabled);
    },

    buildControlNetPayload() {
      if (global.usesIllustriousRefine?.(this.form.engine)) return null;
      const out = {};
      const toggles = this.form.controlnet || {};
      for (const row of this.controlnetRows || []) {
        if (!row.hasImage) continue;
        const toggle = toggles[row.key];
        if (!toggle || !toggle.enabled) continue;
        const strength = parseFloat(toggle.strength);
        const start = parseFloat(toggle.start_percent);
        const end = parseFloat(toggle.end_percent);
        out[row.key] = {
          enabled: true,
          strength: Number.isNaN(strength) ? null : strength,
          start_percent: Number.isNaN(start) ? null : start,
          end_percent: Number.isNaN(end) ? null : end,
        };
      }
      return Object.keys(out).length ? out : null;
    },

    buildRmbgPayload() {
      if (!this.rmbg.enabled) return null;
      const sensitivity = parseFloat(this.rmbg.sensitivity);
      const processRes = parseInt(this.rmbg.process_res, 10);
      const maskBlur = parseInt(this.rmbg.mask_blur, 10);
      const maskOffset = parseInt(this.rmbg.mask_offset, 10);
      return {
        enabled: true,
        model: (this.rmbg.model || 'RMBG-2.0').trim() || 'RMBG-2.0',
        sensitivity: Number.isNaN(sensitivity) ? 1 : sensitivity,
        process_res: parseInt(this.normalizeRmbgProcessRes(this.rmbg.process_res), 10),
        mask_blur: Number.isNaN(maskBlur)
          ? 0
          : Math.min(MAKE_LAB_RMBG_MASK_BLUR_MAX, Math.max(0, maskBlur)),
        mask_offset: Number.isNaN(maskOffset)
          ? 0
          : Math.min(
              MAKE_LAB_RMBG_MASK_OFFSET_MAX,
              Math.max(MAKE_LAB_RMBG_MASK_OFFSET_MIN, maskOffset)
            ),
        invert_output: !!this.rmbg.invert_output,
        refine_foreground: !!this.rmbg.refine_foreground,
        background: this.rmbg.background === 'Color' ? 'Color' : 'Alpha',
        background_color: (this.rmbg.background_color || '#000000').trim() || '#000000',
      };
    },

    loraStrengthVisible(kind) {
      return this._loraStrengthSaved(kind) != null;
    },

    loraStrengthEffective(kind) {
      const saved = this._loraStrengthSaved(kind);
      if (saved == null) return 1;
      const o = this.form.loraStrengthOverrides || {};
      if (Object.prototype.hasOwnProperty.call(o, kind)) {
        const n = Number(o[kind]);
        if (Number.isFinite(n)) return n;
      }
      return saved;
    },

    hasAdetailerMetadata() {
      const ad = this.result?.character_adetailer;
      if (!ad || typeof ad !== 'object') return false;
      return Object.values(ad).some((t) => t && String(t).trim());
    },

    adetailerEntries() {
      const ad = this.result?.character_adetailer || {};
      return Object.entries(ad).filter(([, v]) => v && String(v).trim());
    }
    };
  }
  global.makePipelineMethods = makePipelineMethods;
})(window);

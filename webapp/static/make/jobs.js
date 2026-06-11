(function (global) {
  function makeJobsMethods() {
    return {

    async init() {
      await this.loadAll();
      this.ensureDefaultPicks();
      this.loadControlNetFromAnimation();
      this.applySceneConstraints();
      this.applyInferenceFromStyle(this.form.style, { dimension: false });
      this.form.dimension = '1024x1024';
      if (this.form.orientation === 'both') this.form.orientation = '';
      await Promise.all([
        this.loadHistory(),
        this.loadUpscaleModels(),
        this.loadDetailerRegions(),
      ]);
      await this.applyGalleryHandoff();
      await this.restorePersistedComfyuiJobs();
      this.syncDetailerTimingDefault();
      this.$nextTick(() => {
        this.$nextTick(() => this.onViewportResize());
      });
      this.startComfyuiStatusPoll();
      this.startComfyuiExecutionClock();
      this.startCatalogRevisionPoll();
      const onInferenceFormChange = () => this.onPreviewInferenceChanged();
      this.$watch('form.dimension', onInferenceFormChange);
      this.$watch('form.orientation', (val) => {
        const v = String(val || '').trim().toLowerCase();
        this.orientationTouched = v === 'portrait' || v === 'landscape';
        onInferenceFormChange();
      });
      this.$watch('form.style', () => {
        this.clearLoraStrengthOverride('style');
        onInferenceFormChange();
      });
      this.$watch('form.character', () => {
        this.clearLoraStrengthOverride('character');
        if (this.animationIsRandom()) this.ensureDisplayValue('animation');
        if (this.placeIsRandom()) this.ensureDisplayValue('place');
      });
      this.$watch('form.animation', () => {
        this.clearLoraStrengthOverride('animation');
        this.applySceneConstraints();
        this.loadControlNetFromAnimation();
        onInferenceFormChange();
        this.$nextTick(() => this.syncHistoryHeight());
      });
      this.$watch('form.refine_style', () => {
        this.clearLoraStrengthOverride('refine_style');
        if (!this.detailerSyncBlocked()) this.syncDetailerTimingDefault();
      });
      this.$watch('form.place', () => {
        this.applySceneConstraints();
      });
      const onVisibilityChange = () => {
        if (document.hidden) return;
        void this.checkCatalogRevision();
        if (!this.comfyuiAnyJobActive()) {
          this.drainClientGenerationQueue();
        }
      };
      const onWindowFocus = () => void this.checkCatalogRevision();
      document.addEventListener('visibilitychange', onVisibilityChange);
      window.addEventListener('focus', onWindowFocus);
      const unbindComfyuiResume =
        typeof window.bindComfyuiLabResume === 'function'
          ? window.bindComfyuiLabResume(this, this._comfyuiJobPollResumeOptions())
          : null;
      return () => {
        unbindComfyuiResume?.();
        document.removeEventListener('visibilitychange', onVisibilityChange);
        window.removeEventListener('focus', onWindowFocus);
        this.stopCatalogRevisionPoll();
        this.stopComfyuiStatusPoll();
        this.stopComfyuiJobPoll(false);
        this.stopComfyuiExecutionClock();
      };
    },

    _loraStrengthSaved(kind) {
      const lora = this.resolvedLoraForKind(kind);
      if (!lora || !(lora.filename || '').trim()) return null;
      const n = Number(lora.strength);
      return Number.isFinite(n) ? n : 1;
    },

    _patchCatalogLoraStrength(kind, strength) {
      const lora = this.resolvedLoraForKind(kind);
      if (!lora?.id) return;
      const s = Number(strength);
      if (kind === 'style') {
        const slug = (this.form.style || '').trim();
        const st = this.styleBySlug(slug);
        if (st?.lora) st.lora.strength = s;
      } else if (kind === 'refine_style') {
        const slug = (this.form.refine_style || '').trim();
        const st = this.styleBySlug(slug);
        if (st?.lora) st.lora.strength = s;
      } else if (kind === 'character') {
        const slug = (this.form.character || '').trim();
        const c = this.characterBySlug(slug);
        if (c?.lora) c.lora.strength = s;
      } else if (kind === 'animation') {
        const slug = (this.form.animation || '').trim();
        const a = this.animationBySlug(slug);
        if (!a) return;
        const lora = a.sdxl_lora || a.lora;
        if (lora) lora.strength = s;
        if (a.sdxl_lora && a.lora && a.sdxl_lora !== a.lora) {
          a.lora.strength = s;
        }
      }
    },

    actOrientationDirty() {
      const orient = this.selectedOrientationForSave();
      if (!orient || this.animationIsRandom()) return false;
      const act = this.animationBySlug(this.form.animation);
      if (!act) return false;
      const saved = (act.orientation || '').trim().toLowerCase();
      return orient !== saved;
    },

    actOrientationSaveDisabled() {
      if (this.animationOrientationSaveBusy) return true;
      if (this.animationIsRandom()) return true;
      if (!this.form.animation) return true;
      if (!this.selectedOrientationForSave()) return true;
      return !this.actOrientationDirty();
    },

    actOrientationSaving() {
      return this.animationOrientationSaveBusy;
    },

    clearLoraStrengthOverride(kind) {
      const o = { ...(this.form.loraStrengthOverrides || {}) };
      if (!Object.prototype.hasOwnProperty.call(o, kind)) return;
      delete o[kind];
      this.form.loraStrengthOverrides = o;
    },

    dimensionSelectOptions() {
      const out = [];
      const seen = new Set();
      const add = (key, label) => {
        if (!key || seen.has(key)) return;
        seen.add(key);
        out.push({ key, label: label || key });
      };
      for (const key of this.dropdowns.dimension_hints || []) {
        add(key, key);
      }
      const style =
        !this.styleIsRandom() && this.form.style
          ? this.styleBySlug(this.form.style)
          : null;
      if (style?.width && style?.height) {
        const key = this.canonicalDimensionKey(style.width, style.height);
        const label = key + ' (model)';
        if (seen.has(key)) {
          const hit = out.find((o) => o.key === key);
          if (hit) hit.label = label;
        } else {
          add(key, label);
        }
      }
      return out;
    },

    isDetailerEnabled(id) {
      return (this.form.detailers || []).includes(id);
    },

    loadControlNetFromAnimation() {
      const animation = this.animationForForm();
      const stored =
        animation && typeof animation.controlnets === 'object'
          ? animation.controlnets
          : {};
      const rows = [];
      const next = {};
      for (const key of CONTROLNET_TYPE_KEYS) {
        const entry =
          stored[key] && typeof stored[key] === 'object' ? stored[key] : null;
        const hasImage = Boolean(entry?.image_path);
        const defaults = this.controlnetDefaults(key);
        rows.push({
          key,
          label: this.controlnetTypeLabel(key),
          image_path: hasImage ? entry.image_path : null,
          hasImage,
          initial: this.controlnetTypeLabel(key).charAt(0),
        });
        next[key] = {
          enabled: false,
          strength: entry?.strength ?? defaults.strength,
          start_percent: entry?.start_percent ?? defaults.start_percent,
          end_percent: entry?.end_percent ?? defaults.end_percent,
        };
      }
      this.controlnetRows = rows;
      this.form.controlnet = next;
    },

    async loadDetailerRegions() {
      try {
        const r = await fetch('/api/make/detailers');
        if (!r.ok) return;
        const { data } = await parseApiResponse(r);
        this.detailerRegions = Array.isArray(data.regions) ? data.regions : [];
        this.detailerUiRows = detailerUiRowsFromOrder(data.order);
        if (this._pendingDetailerIds) {
          this.form.detailers = this.filterDetailersToOrder(this._pendingDetailerIds);
          this._pendingDetailerIds = null;
        }
      } catch {
        this.detailerRegions = [];
        this.detailerUiRows = [];
      }
    },

    async loadUpscaleModels() {
      try {
        const r = await fetch('/api/comfyui/upscale-models');
        if (!r.ok) return;
        const data = await r.json();
        const options = Array.isArray(data.options) ? data.options : [];
        if (options.length) {
          this.upscaleModels = options.map((row) => row.filename).filter(Boolean);
          this.upscaleModelLabels = Object.fromEntries(
            options
              .filter((row) => row.filename)
              .map((row) => [row.filename, row.label || row.filename]),
          );
        } else {
          this.upscaleModels = Array.isArray(data.models) ? data.models : [];
          this.upscaleModelLabels = {};
        }
        this.ensureUpscaleModelSelection();
      } catch {
        /* ComfyUI may be offline; keep form defaults */
      }
    },

    loraStrengthDirty(kind) {
      const saved = this._loraStrengthSaved(kind);
      if (saved == null) return false;
      return Math.abs(this.loraStrengthEffective(kind) - saved) > 0.001;
    },

    loraStrengthDisabled(kind) {
      return !this.loraStrengthVisible(kind) || !!this.loraStrengthSaveBusy[kind];
    },

    loraStrengthSaveDisabled(kind) {
      return (
        this.loraStrengthDisabled(kind) ||
        !this.loraStrengthDirty(kind) ||
        !this.resolvedLoraForKind(kind)?.id
      );
    },

    loraStrengthSaving(kind) {
      return !!this.loraStrengthSaveBusy[kind];
    },

    normalizeDetailerIds(ids) {
      const out = new Set();
      for (const raw of ids || []) {
        const id = String(raw || '').trim().toLowerCase();
        if (!id) continue;
        if (id === 'genitals') {
          out.add('penis');
          out.add('pussy');
        } else {
          out.add(id);
        }
      }
      return [...out];
    },

    orientationSelectOptions() {
      return (this.dropdowns.orientations || []).filter((o) => o !== 'both');
    },

    pickFieldCoverEnabled(field) {
      if (!this.outputImage || this.coverUploadBusy) return false;
      return !!this.pickFieldCoverUploadUrl(field);
    },

    pickFieldCoverTargetLabel(field) {
      const summary = this.pickSummary(field);
      return summary?.title || field || 'entity';
    },

    pickFieldCoverUploadUrl(field) {
      const enc = encodeURIComponent;
      switch (field) {
        case 'character': {
          const slug = this.resolvedFieldValue('character');
          if (!slug || this.spriteType !== 'character') return '';
          return `/api/characters/${enc(slug)}/image`;
        }
        case 'animation': {
          const slug = this.resolvedFieldValue('animation');
          if (!slug || slug.toLowerCase() === 'none') return '';
          return `/api/animations/${enc(slug)}/image`;
        }
        case 'place': {
          const key = this.resolvedFieldValue('place');
          return key ? `/api/backgrounds/${enc(key)}/image` : '';
        }
        case 'style': {
          const slug = this.resolvedFieldValue('style');
          return slug ? `/api/styles/${enc(slug)}/image` : '';
        }
        case 'refine_style': {
          if (this.refineStyleSameAsInference()) return '';
          const slug = this.resolvedFieldValue('refine_style');
          return slug ? `/api/styles/${enc(slug)}/image` : '';
        }
        default:
          return '';
      }
    },

    pickFieldSettingsEnabled(field) {
      return !!this.pickFieldSettingsUrl(field);
    },

    pickFieldSettingsUrl(field) {
      const enc = encodeURIComponent;
      switch (field) {
        case 'character': {
          const slug = this.resolvedFieldValue('character');
          if (!slug) return '';
          if (this.spriteType === 'monster') return `/design/monsters/${enc(slug)}`;
          if (this.spriteType === 'object') return `/design/objects/${enc(slug)}`;
          return `/characters/${enc(slug)}`;
        }
        case 'animation': {
          const slug = this.resolvedFieldValue('animation');
          if (!slug || slug.toLowerCase() === 'none') return '';
          return `/animations/${enc(slug)}?tab=lora`;
        }
        case 'place': {
          const key = this.resolvedFieldValue('place');
          return key ? `/backgrounds/${enc(key)}` : '';
        }
        case 'style': {
          const slug = this.resolvedFieldValue('style');
          return slug ? `/styles/${enc(slug)}` : '';
        }
        case 'refine_style': {
          if (this.refineStyleSameAsInference()) return '';
          const slug = this.resolvedFieldValue('refine_style');
          return slug ? `/styles/${enc(slug)}` : '';
        }
        default:
          return '';
      }
    },

    pickSlotClick(field) {
      this.openPicker(field);
    },

    resolvedFieldValue(field) {
      if (!field) return '';
      return String(this.displayValueForField(field) || '').trim();
    },

    resolvedLoraForKind(kind) {
      if (kind === 'style') {
        const slug = this.resolvedFieldValue('style');
        if (!slug) return null;
        return this.styleBySlug(slug)?.lora || null;
      }
      if (kind === 'refine_style') {
        if (this.refineStyleSameAsInference()) return null;
        const slug = this.resolvedFieldValue('refine_style');
        if (!slug) return null;
        return this.styleBySlug(slug)?.lora || null;
      }
      if (kind === 'character') {
        const slug = this.resolvedFieldValue('character');
        if (!slug) return null;
        return this.characterBySlug(slug)?.lora || null;
      }
      if (kind === 'animation') {
        const slug = this.resolvedFieldValue('animation');
        if (!slug) return null;
        const act = this.animationBySlug(slug);
        return act?.sdxl_lora || act?.lora || null;
      }
      return null;
    },

    samplerSelectOptions() {
      const hints = [...(this.dropdowns.sampler_hints || [])];
      const cur = (this.form.sampler || '').trim();
      if (cur && !hints.includes(cur)) hints.unshift(cur);
      return hints;
    },

    async saveAnimationOrientation() {
      if (this.actOrientationSaveDisabled()) return;
      const slug = (this.form.animation || '').trim();
      const orient = this.selectedOrientationForSave();
      if (!slug || !orient) return;
      this.animationOrientationSaveBusy = true;
      this.error = '';
      try {
        const r = await fetch(
          '/api/animations/' + encodeURIComponent(slug) + '/orientation',
          {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ orientation: orient }),
          }
        );
        const { data } = await parseApiResponse(r);
        if (!r.ok) {
          throw new Error(apiErrorDetail(data, r.status, 'Could not save orientation'));
        }
        const act = this.animationBySlug(slug);
        if (act && data.orientation) act.orientation = data.orientation;
      } catch (e) {
        this.error = e.message || String(e);
      } finally {
        this.animationOrientationSaveBusy = false;
      }
    },

    async saveLoraStrength(kind) {
      const lora = this.resolvedLoraForKind(kind);
      if (!lora?.id || !this.loraStrengthDirty(kind)) return;
      const strength = this.loraStrengthEffective(kind);
      this.loraStrengthSaveBusy = { ...this.loraStrengthSaveBusy, [kind]: true };
      try {
        const data = await patchLoraStrength(lora.id, strength);
        const saved = Number(data.strength);
        this._patchCatalogLoraStrength(kind, saved);
        this.clearLoraStrengthOverride(kind);
      } catch (e) {
        this.error = e.message || String(e);
      } finally {
        const next = { ...this.loraStrengthSaveBusy };
        delete next[kind];
        this.loraStrengthSaveBusy = next;
      }
    },

    schedulerSelectOptions() {
      const hints = [...(this.dropdowns.scheduler_hints || [])];
      const cur = (this.form.scheduler || '').trim();
      if (cur && !hints.includes(cur)) hints.unshift(cur);
      return hints;
    },

    setControlNetEnabled(key, on) {
      const row = this.controlnetRowByKey(key);
      if (!row?.hasImage) {
        if (this.form.controlnet?.[key]) {
          this.form.controlnet[key].enabled = false;
        }
        return;
      }
      if (!this.form.controlnet[key]) {
        const d = this.controlnetDefaults(key);
        this.form.controlnet[key] = {
          enabled: false,
          strength: d.strength,
          start_percent: d.start_percent,
          end_percent: d.end_percent,
        };
      }
      this.form.controlnet[key].enabled = Boolean(on);
    },

    setLoraStrengthOverride(kind, raw) {
      const saved = this._loraStrengthSaved(kind);
      if (saved == null) return;
      const n = clampLoraStrength(parseFloat(raw));
      if (n == null) return;
      const o = { ...(this.form.loraStrengthOverrides || {}) };
      if (Math.abs(n - saved) <= 0.001) {
        delete o[kind];
      } else {
        o[kind] = n;
      }
      this.form.loraStrengthOverrides = o;
    },

    stepLoraStrength(kind, delta) {
      const cur = this.loraStrengthEffective(kind);
      this.setLoraStrengthOverride(kind, String(cur + delta * 0.05));
    },

    upscaleModelLabel(filename) {
      const key = String(filename || '').trim();
      return (this.upscaleModelLabels && this.upscaleModelLabels[key]) || key;
    },
    };
  }
  global.makeJobsMethods = makeJobsMethods;
})(window);

(function (global) {
  function makePayloadMethods() {
    return {


    recordScenePin(field) {
      if (!MAKE_LAB_SCENE_PIN_FIELDS.includes(field)) return;
      if (!this.scenePinOrder.includes(field)) this.scenePinOrder.push(field);
    },



    clearScenePin(field) {
      this.scenePinOrder = this.scenePinOrder.filter((f) => f !== field);
    },


    syncScenePinOrder() {
      this.scenePinOrder = this.scenePinOrder.filter((f) => !this.isFieldRandom(f));
    },


    rebuildScenePinOrderFromForm() {
      this.scenePinOrder = MAKE_LAB_SCENE_PIN_FIELDS.filter(
        (f) => !this.isFieldRandom(f) && this.form[f]
      );
    },



    resolvedPlaceKey() {
      const p = this.form.place;
      if (!p) return null;
      return p;
    },



    defaultActSlug() {
      return 'none';
    },



    defaultPlaceKey() {
      const locs = this.pickerLocations();
      return locs[0]?.key || this.catalog.backgrounds[0]?.key || '';
    },


    displayValueForField(field) {
      const raw = this.form[field];
      if (this.isFieldRandom(field)) {
        if (raw != null && raw !== '') return raw;
        if (MAKE_LAB_SCENE_PIN_FIELDS.includes(field)) {
          switch (field) {
            case 'animation':
              return this.defaultActSlug();
            case 'place':
              return this.defaultPlaceKey();
          }
        }
      }
      if (raw != null && raw !== '') return raw;
      switch (field) {
        case 'character':
          return this.defaultSubjectSlug();
        case 'animation':
          return this.defaultActSlug();
        case 'place':
          return this.defaultPlaceKey();
        case 'style':
          return this.defaultStyleSlug();
        case 'refine_style':
          return this.form.refine_style || '_inference';
        default:
          return '';
      }
    },



    ensureDisplayValue(field) {
      if (!this.fieldUsesDice(field)) return;
      const v = this.displayValueForField(field);
      if (v) this.form[field] = v;
    },



    defaultStyleSlug() {
      return this.catalog.styles[0]?.slug || '';
    },



    ensureDefaultPicks() {
      const migrateDiceField = (field, pickDefault) => {
        const raw = String(this.form[field] || '').toLowerCase();
        if (raw === 'random') {
          this.formRandom[field] = true;
        }
        if (!raw || raw === 'random') {
          const value = pickDefault();
          if (value) this.form[field] = value;
        }
      };
      migrateDiceField('character', () => this.defaultSubjectSlug());
      migrateDiceField('style', () => this.defaultStyleSlug());
      const actRaw = String(this.form.animation || '').toLowerCase();
      if (actRaw === 'random') {
        this.formRandom.animation = true;
      } else if (!actRaw) {
        this.form.animation = 'none';
        this.formRandom.animation = false;
      }
      const placeRaw = String(this.form.place || '').toLowerCase();
      if (placeRaw === 'random') {
        this.formRandom.place = true;
      } else if (!placeRaw) {
        this.form.place = this.defaultPlaceKey();
        this.formRandom.place = false;
      }
      this.rebuildScenePinOrderFromForm();
      const refineRaw = String(this.form.refine_style || '').toLowerCase();
      if (refineRaw === 'random') {
        this.formRandom.refine_style = true;
        this.form.refine_style = '_inference';
      } else if (!refineRaw) {
        this.form.refine_style = '_inference';
      }
    },


    coerceSceneFieldToValid(field) {
      if (!MAKE_LAB_SCENE_PIN_FIELDS.includes(field) || this.isFieldRandom(field)) {
        return;
      }
      switch (field) {
        case 'animation': {
          const cur = this.form.animation;
          if (cur === 'none') return;
          const animations = this.pickerAnimations();
          if (!animations.length) {
            this.form.animation = 'none';
            this.formRandom.animation = false;
            return;
          }
          if (!cur || !animations.some((a) => a.slug === cur)) {
            this.form.animation = animations[0].slug;
          }
          return;
        }
        case 'place': {
          const locs = this.pickerLocations();
          const cur = this.form.place;
          if (!locs.length) {
            if (cur) this.setFieldRandom('place');
            return;
          }
          if (!cur || !locs.some((l) => l.key === cur)) {
            this.form.place = locs[0].key;
          }
          return;
        }
      }
    },



    applySceneConstraints() {
      const pinned = this.scenePinOrder.filter((f) => !this.isFieldRandom(f));
      this.syncScenePinOrder();
      for (let pass = 0; pass < MAKE_LAB_SCENE_PIN_FIELDS.length; pass++) {
        for (const field of MAKE_LAB_SCENE_PIN_FIELDS) {
          this.coerceSceneFieldToValid(field);
        }
      }
      for (const field of MAKE_LAB_SCENE_PIN_FIELDS) {
        if (this.isFieldRandom(field)) this.ensureDisplayValue(field);
      }
    },



    fieldUsesDice(field) {
      return MAKE_LAB_DICE_FIELDS.has(field);
    },



    isFieldRandom(field) {
      return Boolean(this.formRandom[field]);
    },



    pinResolvedSceneDisplay(build) {
      const scene = build?.scene;
      if (!scene || typeof scene !== 'object') return;
      const pin = (field, sceneKey = field) => {
        const v = scene[sceneKey];
        if (v == null || v === '') return;
        this.setFormField(field, v);
      };
      pin('character');
      pin('animation');
      pin('place', 'location');
      pin('style');
      if (scene.refine_style != null && scene.refine_style !== '') {
        this.form.refine_style = scene.refine_style;
      }
    },



    toggleFieldRandom(field) {
      if (!this.fieldUsesDice(field)) return;
      this.formRandom[field] = !this.formRandom[field];
      if (MAKE_LAB_SCENE_PIN_FIELDS.includes(field)) {
        if (this.formRandom[field]) {
          this.clearScenePin(field);
          this.ensureDisplayValue(field);
        } else {
          if (!this.form[field]) this.ensureDisplayValue(field);
          this.coerceSceneFieldToValid(field);
          if (this.form[field]) {
            this.recordScenePin(field);
          } else {
            this.clearScenePin(field);
          }
        }
        this.applySceneConstraints();
      } else if (this.formRandom[field]) {
        this.ensureDisplayValue(field);
      }
    },



    characterIsRandom() {
      return this.isFieldRandom('character');
    },



    animationIsRandom() {
      return this.isFieldRandom('animation');
    },



    styleIsRandom() {
      return this.isFieldRandom('style');
    },



    setFieldRandom(field) {
      if (!this.fieldUsesDice(field)) return;
      this.formRandom[field] = true;
      if (MAKE_LAB_SCENE_PIN_FIELDS.includes(field)) {
        this.clearScenePin(field);
      }
      this.ensureDisplayValue(field);
    },



    setFormField(field, value) {
      if (value === undefined || value === null) return;
      this.form[field] = value;
    },



    refineStyleSameAsInference() {
      const v = String(this.form.refine_style || '').trim().toLowerCase();
      return !v || v === '_inference';
    },



    resolvedSeedFromHistory(request, build) {
      const sceneSeed = build?.scene?.seed;
      if (sceneSeed != null && sceneSeed !== '') return Number(sceneSeed);
      const reqSeed = request?.seed;
      if (reqSeed == null || reqSeed === '') return null;
      const n = Number(reqSeed);
      if (!Number.isNaN(n) && n >= 0) return n;
      return null;
    },



    _requestSlotNeedsResolution(value) {
      if (value == null || value === '') return true;
      return String(value).toLowerCase() === 'random';
    },


    shouldPinResolvedBuildToForm() {
      const q = this.clientGenerationQueue;
      return !(q && q.total > 1);
    },


    requestWithResolvedScene(request, build) {
      if (!request || typeof request !== 'object') return request;
      const scene = build?.scene;
      if (!scene || typeof scene !== 'object') return request;
      const out = { ...request };
      const fill = (reqKey, sceneKey = reqKey) => {
        const sceneVal = scene[sceneKey];
        if (sceneVal == null || sceneVal === '') return;
        if (this._requestSlotNeedsResolution(out[reqKey])) {
          out[reqKey] = sceneVal;
        }
      };
      fill('character');
      fill('animation');
      fill('style');
      fill('location', 'location');
      fill('orientation');
      if (
        scene.refine_style != null &&
        this._requestSlotNeedsResolution(out.refine_style)
      ) {
        out.refine_style = scene.refine_style;
      }
      return out;
    },



    applyRequestToForm(request, build, opts = {}) {
      if (!request || typeof request !== 'object') return;
      const { restoreDice = false } = opts;
      const r = this.requestWithResolvedScene(request, build);
      const set = (field, value) => this.setFormField(field, value);
      this.runWithDetailerSyncSuppressed(() => {
      const applyDiceField = (field, reqKey, resolveKey = reqKey) => {
        const raw = request[reqKey];
        let resolved = r[reqKey];
        if (resolveKey === 'location') {
          resolved = r.location;
        }
        if (resolved == null && raw == null) return;
        if (restoreDice) {
          const wasRandom =
            field === 'refine_style'
              ? String(raw || '').toLowerCase() === 'random'
              : this._requestSlotNeedsResolution(raw);
          this.formRandom[field] = wasRandom;
        }
        if (resolved != null && resolved !== '') set(field, resolved);
      };
      applyDiceField('character', 'character');
      applyDiceField('animation', 'animation');
      applyDiceField('place', 'location', 'location');
      if (r.subject_type) {
        this.spriteType = String(r.subject_type).toLowerCase();
      }
      applyDiceField('style', 'style');
      applyDiceField('refine_style', 'refine_style');
      if (restoreDice && this.seedIsMinusOne()) {
        this.setSeedMinusOne();
      }
      if (this.seedIsMinusOne()) {
        this.form.seed = '-1';
      } else if (restoreDice) {
        const reqSeed = request?.seed;
        if (reqSeed != null && reqSeed !== '') {
          const n = Number(reqSeed);
          if (!Number.isNaN(n) && n === -1) {
            this.form.seed = '-1';
          } else {
            const seed = this.resolvedSeedFromHistory(r, build);
            if (seed != null) set('seed', String(seed));
          }
        }
      } else {
        const seed = this.resolvedSeedFromHistory(r, build);
        if (seed != null) set('seed', String(seed));
      }
      if (r.width && r.height) {
        const key = this.canonicalDimensionKey(Number(r.width), Number(r.height));
        if (key) this.form.dimension = key;
      }
      if (r.images != null && r.images !== '') {
        const n = parseInt(r.images, 10);
        if (!Number.isNaN(n)) {
          this.form.images = String(
            Math.min(MAKE_LAB_IMAGES_MAX, Math.max(MAKE_LAB_IMAGES_MIN, n))
          );
        }
      }
      if (r.generation_count != null && r.generation_count !== '') {
        const n = parseInt(r.generation_count, 10);
        if (!Number.isNaN(n)) {
          this.form.generation_count = String(
            Math.min(
              MAKE_LAB_GENERATION_COUNT_MAX,
              Math.max(MAKE_LAB_GENERATION_COUNT_MIN, n)
            )
          );
        }
      }
      this.rebuildScenePinOrderFromForm();
      this.applySceneConstraints();
      this.applyInferenceFromStyle(this.form.style, { dimension: false });
      const ckpt = build?.sdxl?.checkpoint || {};
      if (r.sampler) this.form.sampler = r.sampler;
      else if (ckpt.sampler) this.form.sampler = ckpt.sampler;
      if (r.scheduler) this.form.scheduler = r.scheduler;
      else if (ckpt.scheduler) this.form.scheduler = ckpt.scheduler;
      if (r.steps != null && r.steps !== '') {
        this.form.steps = String(r.steps);
      } else if (ckpt.steps != null) {
        this.form.steps = String(ckpt.steps);
      }
      if (r.cfg_scale != null && r.cfg_scale !== '') {
        this.form.cfg_scale = String(r.cfg_scale);
      } else if (ckpt.cfg_scale != null) {
        this.form.cfg_scale = String(ckpt.cfg_scale);
      }
      if (!this.form.sampler) this.form.sampler = this.defaultSampler();
      if (!this.form.scheduler) this.form.scheduler = this.defaultScheduler();
      if (r.upscale_model) this.form.upscale_model = r.upscale_model;
      if (r.upscale_by != null && r.upscale_by !== '') {
        this.form.upscale_by = String(r.upscale_by);
      }
      if (r.refine_steps != null && r.refine_steps !== '') {
        this.form.refine_steps = String(r.refine_steps);
      } else if (r.upscale_steps != null && r.upscale_steps !== '') {
        this.form.refine_steps = String(r.upscale_steps);
      }
      if (r.refine_denoise != null && r.refine_denoise !== '') {
        this.form.refine_denoise = String(r.refine_denoise);
      } else if (r.upscale_denoise != null && r.upscale_denoise !== '') {
        this.form.refine_denoise = String(r.upscale_denoise);
      }
      if (typeof r.refine_enabled === 'boolean') {
        this.form.refine_enabled = r.refine_enabled;
      }
      if (typeof r.upscale_timing === 'string') {
        const t = String(r.upscale_timing).trim().toLowerCase();
        if (t === 'disabled' || t === 'before' || t === 'after') {
          this.form.upscale_timing = t;
          this.form.upscale_enabled = t !== 'disabled';
        }
      } else if (typeof r.upscale_enabled === 'boolean') {
        this.form.upscale_enabled = r.upscale_enabled;
        this.form.upscale_timing = r.upscale_enabled ? 'after' : 'disabled';
      }
      this.ensureUpscaleModelSelection();
      this.normalizePipelineTimingWithoutRefine();
      });
      this.applyDetailerSettingsFromRequest(request);
      this.normalizePipelineTimingWithoutRefine();
      this.applyRmbgSettingsFromRequest(request);
      this.$nextTick(() => {
        this.applyDetailerSettingsFromRequest(request);
        this.normalizePipelineTimingWithoutRefine();
        this.applyRmbgSettingsFromRequest(request);
      });
    },

    ensureUpscaleModelSelection() {
      const current = (this.form.upscale_model || '').trim();
      if (current && this.upscaleModels.includes(current)) return;
      if (this.upscaleModels.includes(MAKE_LAB_UPSCALE_MODEL_DEFAULT)) {
        this.form.upscale_model = MAKE_LAB_UPSCALE_MODEL_DEFAULT;
      } else if (this.upscaleModels.length) {
        this.form.upscale_model = this.upscaleModels[0];
      } else if (!current) {
        this.form.upscale_model = MAKE_LAB_UPSCALE_MODEL_DEFAULT;
      }
    },



    defaultSampler() {
      const d = this.dropdowns.style_defaults || {};
      return d.sampler || this.dropdowns.sampler_hints?.[0] || 'Euler a';
    },



    defaultScheduler() {
      const d = this.dropdowns.style_defaults || {};
      return d.scheduler || 'normal';
    },


    canonicalDimensionKey(width, height) {
      const w = parseInt(width, 10);
      const h = parseInt(height, 10);
      if (!w || !h) return '';
      if (w === h) return w + 'x' + h;
      const lo = Math.min(w, h);
      const hi = Math.max(w, h);
      return lo + 'x' + hi;
    },



    canonicalDimensionKeyFromKey(key) {
      const parsed = this.parseDimension(key);
      return parsed
        ? this.canonicalDimensionKey(parsed.width, parsed.height)
        : '';
    },



    parseDimension(key) {
      const m = String(key || '')
        .trim()
        .match(/^(\d+)\s*[x├ù]\s*(\d+)$/i);
      if (!m) return null;
      return { width: parseInt(m[1], 10), height: parseInt(m[2], 10) };
    },



    defaultDimension() {
      const d = this.dropdowns.style_defaults || {};
      const key = this.canonicalDimensionKey(d.width, d.height);
      return key || this.dropdowns.dimension_hints?.[0] || '1024x1024';
    },



    applyInferenceFromStyle(slug, opts = {}) {
      const { dimension = true } = opts;
      const defaults = this.dropdowns.style_defaults || {};
      const style =
        slug && !this.styleIsRandom() ? this.styleBySlug(slug) : null;
      const src = style || defaults;
      if (!src || typeof src !== 'object') return;
      this.form.sampler = src.sampler || defaults.sampler || this.defaultSampler();
      this.form.scheduler =
        src.scheduler || defaults.scheduler || this.defaultScheduler();
      this.form.steps = String(src.steps ?? defaults.steps ?? '');
      this.form.cfg_scale = String(src.cfg_scale ?? defaults.cfg_scale ?? '');
      if (dimension) {
        const w = src.width ?? defaults.width;
        const h = src.height ?? defaults.height;
        this.form.dimension =
          this.canonicalDimensionKey(w, h) || this.defaultDimension();
      }
    },

    resetOrientationToDefault() {
      this.form.orientation = '';
      this.orientationTouched = false;
    },



    selectedOrientationForSave() {
      const v = (this.form.orientation || '').trim().toLowerCase();
      return v === 'portrait' || v === 'landscape' ? v : null;
    },



    applyBuildPreviewSize(build) {
      if (build?.sdxl?.width && build?.sdxl?.height) {
        this.previewBuildSizeStale = false;
        this.$nextTick(() => this.onViewportResize());
      }
    },



    buildPayload() {
      const payload = {};
      const apiKeys = { place: 'location' };
      const skip = new Set([
        'dimension',
        'detailers',
        'loraStrengthOverrides',
        'orientation',
        'controlnet',
      ]);
      const intFields = new Set([
        'seed',
        'steps',
        'images',
        'generation_count',
        'refine_steps',
      ]);
      const floatFields = new Set([
        'cfg_scale',
        'upscale_by',
        'refine_denoise',
      ]);
      for (const [k, v] of Object.entries(this.form)) {
        if (skip.has(k) || v === '' || v === null || v === undefined) continue;
        const outKey = apiKeys[k] || k;
        if (intFields.has(k)) {
          const n = parseInt(v, 10);
          if (k === 'seed') {
            if (!Number.isNaN(n) && n >= -1) payload.seed = n;
            continue;
          }
          if (k === 'images') {
            if (!Number.isNaN(n)) {
              payload.images = Math.min(
                MAKE_LAB_IMAGES_MAX,
                Math.max(MAKE_LAB_IMAGES_MIN, n)
              );
            }
            continue;
          }
          if (k === 'generation_count') {
            if (!Number.isNaN(n)) {
              payload.generation_count = Math.min(
                MAKE_LAB_GENERATION_COUNT_MAX,
                Math.max(MAKE_LAB_GENERATION_COUNT_MIN, n)
              );
            }
            continue;
          }
          if (!Number.isNaN(n)) {
            payload[outKey] = n;
          }
        } else if (floatFields.has(k)) {
          const n = parseFloat(v);
          if (!Number.isNaN(n)) payload[outKey] = n;
        } else {
          payload[outKey] = v;
        }
      }
      const dimKey =
        this.canonicalDimensionKeyFromKey(this.form.dimension) ||
        this.defaultDimension();
      if (dimKey !== this.form.dimension) this.form.dimension = dimKey;
      const dim = this.parseDimension(dimKey);
      if (dim) {
        payload.width = dim.width;
        payload.height = dim.height;
      }
      if (this.form.detailer_timing !== 'disabled') {
        const detailers = this.filterDetailersToOrder(this.form.detailers || []);
        if (detailers.length) {
          payload.detailers = detailers;
          payload.detailer_timing = !this.form.refine_enabled
            ? 'after'
            : this.form.detailer_timing === 'before'
              ? 'before'
              : 'after';
        }
      }
      const rmbg = this.buildRmbgPayload();
      if (rmbg) payload.rmbg = rmbg;
      const controlnet = this.buildControlNetPayload();
      if (controlnet) payload.controlnet = controlnet;
      if (this.form.upscale_timing && this.form.upscale_timing !== 'disabled') {
        payload.upscale_timing = this.form.upscale_timing;
        payload.upscale_enabled = true;
      } else {
        payload.upscale_enabled = false;
      }
      payload.subject_type = this.spriteType;
      if (this.formRandom.character) payload.character = 'random';
      if (this.formRandom.animation) payload.animation = 'random';
      else if ((this.form.animation || '').trim().toLowerCase() === 'none') payload.animation = 'none';
      if (this.formRandom.place) payload.location = 'random';
      if (this.formRandom.style) payload.style = 'random';
      if (this.formRandom.refine_style) payload.refine_style = 'random';
      const orientOverride = this.selectedOrientationForSave();
      if (orientOverride) payload.orientation = orientOverride;
      // Random style: only send sampler/scheduler when the user changed them
      // away from workspace defaults (otherwise the rolled style wins).
      if (this.formRandom.style) {
        if (payload.sampler === this.defaultSampler()) delete payload.sampler;
        if (payload.scheduler === this.defaultScheduler()) delete payload.scheduler;
      }
      const loraOverrides = {};
      for (const kind of ['style', 'refine_style', 'character', 'animation']) {
        if (!this.loraStrengthVisible(kind)) continue;
        const n = this.loraStrengthEffective(kind);
        if (Number.isFinite(n)) loraOverrides[kind] = n;
      }
      if (Object.keys(loraOverrides).length) {
        payload.lora_strength_overrides = loraOverrides;
      }
      return payload;
    },



    clampFormImages(event) {
      let raw = this.form.images;
      if (event?.target?.value != null) raw = event.target.value;
      let digits = String(raw).replace(/\D/g, '');
      if (digits.length > 1) digits = digits.slice(0, 1);
      let n = digits === '' ? MAKE_LAB_IMAGES_MIN : parseInt(digits, 10);
      if (Number.isNaN(n) || n < MAKE_LAB_IMAGES_MIN) n = MAKE_LAB_IMAGES_MIN;
      if (n > MAKE_LAB_IMAGES_MAX) n = MAKE_LAB_IMAGES_MAX;
      this.form.images = String(n);
    },



    stepFormImages(delta) {
      let n = parseInt(this.form.images, 10);
      if (Number.isNaN(n)) n = MAKE_LAB_IMAGES_MIN;
      n = Math.min(
        MAKE_LAB_IMAGES_MAX,
        Math.max(MAKE_LAB_IMAGES_MIN, n + delta)
      );
      this.form.images = String(n);
    },



    clampFormGenerationCount(event) {
      let raw = this.form.generation_count;
      if (event?.target?.value != null) raw = event.target.value;
      let digits = String(raw).replace(/\D/g, '');
      if (digits.length > 3) digits = digits.slice(0, 3);
      let n =
        digits === '' ? MAKE_LAB_GENERATION_COUNT_MIN : parseInt(digits, 10);
      if (Number.isNaN(n) || n < MAKE_LAB_GENERATION_COUNT_MIN) {
        n = MAKE_LAB_GENERATION_COUNT_MIN;
      }
      if (n > MAKE_LAB_GENERATION_COUNT_MAX) n = MAKE_LAB_GENERATION_COUNT_MAX;
      this.form.generation_count = String(n);
    },



    stepFormGenerationCount(delta) {
      let n = parseInt(this.form.generation_count, 10);
      if (Number.isNaN(n)) n = MAKE_LAB_GENERATION_COUNT_MIN;
      n = Math.min(
        MAKE_LAB_GENERATION_COUNT_MAX,
        Math.max(MAKE_LAB_GENERATION_COUNT_MIN, n + delta)
      );
      this.form.generation_count = String(n);
    },



    setSeedMinusOne() {
      if (this.seedIsMinusOne()) {
        const restore = this._seedBeforeMinusOne;
        this.form.seed =
          restore != null && restore !== ''
            ? String(restore)
            : String(Math.floor(Math.random() * 2 ** 31));
        this._seedBeforeMinusOne = null;
        return;
      }
      this._seedBeforeMinusOne = this.form.seed;
      this.form.seed = '-1';
    },



    seedIsMinusOne() {
      return String(this.form.seed).trim() === '-1';
    },



    randomizeSeed() {
      if (this.seedIsMinusOne()) return;
      this.form.seed = String(Math.floor(Math.random() * 2 ** 31));
    }
    };
  }
  global.makePayloadMethods = makePayloadMethods;
})(window);

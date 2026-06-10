/** Make — entity pickers + /api/build preview. */

const MAKE_LAB_HISTORY_LIMIT = 25;
const MAKE_LAB_IMAGES_MIN = 1;
const MAKE_LAB_IMAGES_MAX = 5;
const MAKE_LAB_GENERATION_COUNT_MIN = 1;
const MAKE_LAB_GENERATION_COUNT_MAX = 999;
const MAKE_LAB_BREAKPOINT_NARROW = LAB_HISTORY_BREAKPOINT_NARROW;
const MAKE_LAB_UPSCALE_MODEL_DEFAULT = 'RealESRGAN_x2.pth';
const MAKE_LAB_UPSCALE_BY_DEFAULT = '1.5';
const MAKE_LAB_REFINE_STEPS_DEFAULT = '15';
const MAKE_LAB_REFINE_DENOISE_DEFAULT = '0.35';
const MAKE_LAB_RMBG_MODELS = ['RMBG-2.0', 'INSPYRENET', 'BEN', 'BEN2'];
const MAKE_LAB_RMBG_PROCESS_RES_OPTIONS = ['512', '1024', '2048'];
const MAKE_LAB_RMBG_MASK_BLUR_MAX = 64;
const MAKE_LAB_RMBG_MASK_OFFSET_MIN = -64;
const MAKE_LAB_RMBG_MASK_OFFSET_MAX = 64;
/** Hover magnifier zoom inside the output preview (when idle). */
const MAKE_LAB_PREVIEW_MAGNIFIER_ZOOM = 2.0;
/** Poll dataset revision so catalog pickers stay current across tabs. */
const MAKE_LAB_CATALOG_REVISION_POLL_MS = 5000;
const MAKE_LAB_COMFYUI_LAB = 'make';
const MAKE_LAB_COMFYUI_LAB_LEGACY = 'photo';
function countActPhases(phases) {
  if (!phases || typeof phases !== 'object') return 0;
  return Object.keys(phases).filter((p) => String(phases[p] || '').trim()).length;
}
/** Scene slots that constrain each other; pin order = user selection order. */
const MAKE_LAB_SCENE_PIN_FIELDS = ['animation', 'place'];
const MAKE_LAB_SPRITE_TYPES = [
  { id: 'character', label: 'Character', icon: 'character' },
  { id: 'monster', label: 'Monster', icon: 'flame' },
  { id: 'object', label: 'Object', icon: 'category' },
];
const ANIMATION_TYPE_LABELS = {
  character: 'Character animation',
  monster: 'Monster animation',
  object: 'Object animation',
};
const MAKE_LAB_DICE_FIELDS = new Set([
  'character',
  'animation',
  'place',
  'style',
  'refine_style',
]);
const CONTROLNET_TYPE_KEYS = ['openpose', 'depth', 'canny'];
const CONTROLNET_TYPE_DEFAULTS = {
  openpose: { strength: 0.9, start_percent: 0, end_percent: 1 },
  depth: { strength: 0.75, start_percent: 0, end_percent: 1 },
  canny: { strength: 0.8, start_percent: 0, end_percent: 1 },
};

/** Chunk detailer region ids into rows of four for the settings grid. */
function detailerUiRowsFromOrder(order) {
  const ids = Array.isArray(order) ? order.filter(Boolean) : [];
  if (!ids.length) return [];
  const rows = [];
  for (let i = 0; i < ids.length; i += 4) {
    rows.push(ids.slice(i, i + 4));
  }
  return rows;
}

function makeLab() {
  const tagPreview = (tags, max = 4) => {
    const list = (tags || []).filter(Boolean);
    if (!list.length) return '';
    const head = list.slice(0, max).join(', ');
    return list.length > max ? head + '…' : head;
  };

  return {
    ...labHistoryScrollMethods(MAKE_LAB_BREAKPOINT_NARROW),
    dropdowns: {
      orientations: [],
      sampler_hints: [],
      scheduler_hints: [],
      dimension_hints: [],
      style_defaults: {},
    },
    catalog: {
      characters: [],
      monsters: [],
      objects: [],
      animations: [],
      styles: [],
      backgrounds: [],
    },
    spriteType: 'character',
    leftPipelineTab: 'inference',
    rmbgModels: MAKE_LAB_RMBG_MODELS,
    rmbgProcessResOptions: MAKE_LAB_RMBG_PROCESS_RES_OPTIONS,
    rmbgMaskBlurMax: MAKE_LAB_RMBG_MASK_BLUR_MAX,
    rmbgMaskOffsetMin: MAKE_LAB_RMBG_MASK_OFFSET_MIN,
    rmbgMaskOffsetMax: MAKE_LAB_RMBG_MASK_OFFSET_MAX,
    rmbg: {
      enabled: false,
      model: 'RMBG-2.0',
      sensitivity: '1',
      process_res: '1024',
      mask_blur: '0',
      mask_offset: '0',
      invert_output: false,
      refine_foreground: false,
      background: 'Alpha',
      background_color: '#222222',
    },
    outputImage: null,
    /** Bumped after cover upload so pick-card thumbs bypass browser cache. */
    catalogThumbEpoch: 0,
    catalogRevision: 0,
    catalogRevisionPollId: null,
    catalogRefreshInFlight: false,
    previewMagnifier: { active: false, x: 0.5, y: 0.5 },
    /** When false during a job, preview shows a history pick instead of live sampling. */
    previewLiveSampling: true,
    /** When true, preview size follows form hints instead of last build sdxl. */
    previewBuildSizeStale: true,
    comfyuiState: 'offline',
    comfyuiPendingCount: 0,
    comfyuiStatusError: '',
    comfyuiResources: {
      cpu_pct: null,
      ram_pct: null,
      gpu_pct: null,
      vram_pct: null,
    },
    comfyuiProgressActive: false,
    comfyuiProgressPct: 0,
    comfyuiPhaseLabel: '',
    comfyuiJobWsWarning: '',
    comfyuiJobStartedAt: 0,
    comfyuiJobPromptId: null,
    /** FIFO tracked ComfyUI jobs (inference + download). */
    trackedJobs: [],
    /** Client-side multi-generation queue (one ComfyUI job per HTTP request). */
    clientGenerationQueue: null,
    clientGenSubmitting: false,
    /**
     * Main preview focus: auto-follow FIFO inference until download pins a job;
     * completed jobs pin by image_id. Manual history-slot click sets focus + clears autoFollow.
     */
    previewFocusPromptId: null,
    /** When true, main preview follows the FIFO inferencing job; cleared once a job downloads. */
    previewAutoFollowInference: true,
    /** Last finished run duration (ms); kept after job is removed from trackedJobs. */
    comfyuiLastExecutionMs: null,
    comfyuiExecutionTick: 0,
    comfyuiExecutionClockId: null,
    loadError: '',
    picker: { open: false, field: '', title: '', filter: '' },
    metadataOpen: false,
    viewportTick: 0,
    form: {
      character: '',
      animation: '',
      controlnet: {},
      place: '',
      style: '',
      refine_style: '_inference',
      orientation: '',
      seed: '-1',
      images: '1',
      generation_count: '1',
      sampler: 'Euler a',
      scheduler: 'normal',
      steps: '',
      cfg_scale: '',
      dimension: '1024x1024',
      upscale_model: MAKE_LAB_UPSCALE_MODEL_DEFAULT,
      upscale_by: MAKE_LAB_UPSCALE_BY_DEFAULT,
      refine_steps: MAKE_LAB_REFINE_STEPS_DEFAULT,
      refine_denoise: MAKE_LAB_REFINE_DENOISE_DEFAULT,
      refine_enabled: false,
      upscale_enabled: false,
      upscale_timing: 'disabled',
      detailers: [],
      detailer_timing: 'disabled',
      loraStrengthOverrides: {},
    },
    detailerTimingTouched: false,
    /** True after user picks portrait/landscape (not act default). */
    orientationTouched: false,
    /** Blocks act/refine watchers from clobbering detailers during form restore. */
    _detailerSyncSuppress: 0,
    _pendingDetailerIds: null,
    /** When true, the slot rolls at job time (dice toggle). */
    formRandom: {
      character: false,
      animation: false,
      place: false,
      style: false,
      refine_style: false,
    },
    /** Restored when toggling seed off −1 lock. */
    _seedBeforeMinusOne: null,
    /** First-pinned scene field wins when filtering sibling pickers (act / place / skin). */
    scenePinOrder: [],
    animationOrientationSaveBusy: false,
    loraStrengthSaveBusy: {},
    busy: false,
    generating: false,
    error: '',
    result: null,
    historyItems: [],
    selectedHistoryId: null,
    historyLoading: false,
    deletingPreview: false,
    coverUploadBusy: false,
    upscaleModels: [],
    upscaleModelLabels: {},
    detailerRegions: [],
    detailerUiRows: [],
    controlnetRows: [],

    spriteTypes: MAKE_LAB_SPRITE_TYPES,
    pickFieldsRender: [
      { field: 'style', label: 'Inference model' },
      { field: 'refine_style', label: 'Refine model' },
    ],

    subjectPickLabel() {
      const hit = MAKE_LAB_SPRITE_TYPES.find((t) => t.id === this.spriteType);
      return hit?.label || 'Subject';
    },

    visibleSceneFields() {
      const fields = [
        { field: 'animation', label: 'Animation' },
        { field: 'place', label: 'Background' },
      ];
      return fields;
    },

    animationMatchesSpriteType(act) {
      if (!act) return false;
      const t = String(act.subject_type || 'character').toLowerCase();
      return t === this.spriteType;
    },

    animationsCatalog() {
      return (this.catalog.animations || []).filter((a) => this.animationMatchesSpriteType(a));
    },

    activeSubjects() {
      switch (this.spriteType) {
        case 'monster':
          return this.catalog.monsters || [];
        case 'object':
          return this.catalog.objects || [];
        default:
          return this.catalog.characters || [];
      }
    },

    defaultSubjectSlug() {
      return this.activeSubjects()[0]?.slug || '';
    },

    setSpriteType(type) {
      const next = String(type || '').trim().toLowerCase();
      if (!MAKE_LAB_SPRITE_TYPES.some((t) => t.id === next)) return;
      if (this.spriteType === next) return;
      this.spriteType = next;
      const subjects = this.activeSubjects();
      const cur = (this.form.character || '').trim();
      const valid = subjects.some((s) => s.slug === cur);
      if (!valid) {
        this.form.character = this.defaultSubjectSlug();
        this.formRandom.character = false;
      }
      this.coerceSceneFieldToValid('animation');
      this.applySceneConstraints();
    },

    animationForForm() {
      const v = this.form.animation;
      if (!v) return null;
      return this.animationBySlug(v) || null;
    },

    locationByKey(key) {
      if (!key) return null;
      const target = String(key).toLowerCase();
      return (
        (this.catalog.backgrounds || []).find(
          (l) => String(l.key || '').toLowerCase() === target
        ) || null
      );
    },

    locationForForm() {
      return this.locationByKey(this.resolvedPlaceKey());
    },

    placeIsRandom() {
      return this.isFieldRandom('place');
    },

    locationsForAct(_act) {
      return this.catalog.backgrounds || [];
    },

    animationsForPlace(_loc) {
      return this.animationsCatalog();
    },

    pickerAnimations() {
      let animations = this.animationsCatalog();
      for (const field of this.scenePinOrder) {
        if (this.isFieldRandom(field)) continue;
        if (field === 'place') {
          const loc = this.locationForForm();
          if (loc) animations = this.animationsForPlace(loc);
        }
      }
      return animations;
    },

    pickerLocations() {
      let locs = this.catalog.backgrounds || [];
      for (const field of this.scenePinOrder) {
        if (this.isFieldRandom(field)) continue;
        if (field === 'animation') {
          const act = this.animationForForm();
          if (act) locs = this.locationsForAct(act);
        }
      }
      return locs;
    },

    recordScenePin(field) {
      if (!MAKE_LAB_SCENE_PIN_FIELDS.includes(field)) return;
      if (!this.scenePinOrder.includes(field)) this.scenePinOrder.push(field);
    },

    clearScenePin(field) {
      this.scenePinOrder = this.scenePinOrder.filter((f) => f !== field);
    },

    /** Drop unpinned fields; keep first-selected order for picker filtering. */
    syncScenePinOrder() {
      this.scenePinOrder = this.scenePinOrder.filter((f) => !this.isFieldRandom(f));
    },

    /** History restore: no pin timestamps — stable act → place → skin order. */
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

    /** Value shown in pick cards; dice-on uses form when set (last roll), else first eligible. */
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

    /** Keep a pinned scene slot on a valid catalog value (first match), not random. */
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
      return (
        !v ||
        v === '_inference' ||
        v === 'same_as_inference' ||
        v === 'same as inference'
      );
    },

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
      return String(this.rmbg.background_color || '#222222').toUpperCase();
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
      const current = window.readPersistedLabJobs(MAKE_LAB_COMFYUI_LAB);
      const legacy = window.readPersistedLabJobs(MAKE_LAB_COMFYUI_LAB_LEGACY);
      const seen = new Set(
        current.map((entry) => String(entry?.promptId || '').trim()).filter(Boolean)
      );
      const merged = [...current];
      for (const entry of legacy) {
        const promptId = String(entry?.promptId || '').trim();
        if (promptId && !seen.has(promptId)) merged.push(entry);
      }
      return merged;
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

    startCatalogRevisionPoll() {
      this.stopCatalogRevisionPoll();
      this.catalogRevisionPollId = setInterval(
        () => void this.checkCatalogRevision(),
        MAKE_LAB_CATALOG_REVISION_POLL_MS
      );
    },

    stopCatalogRevisionPoll() {
      if (this.catalogRevisionPollId != null) {
        clearInterval(this.catalogRevisionPollId);
        this.catalogRevisionPollId = null;
      }
    },

    async checkCatalogRevision() {
      if (this.catalogRefreshInFlight) return;
      try {
        const r = await fetch('/api/health', { cache: 'no-store' });
        if (!r.ok) return;
        const data = await r.json();
        const rev = Number(data.revision) || 0;
        if (rev > 0 && rev !== this.catalogRevision) {
          await this.refreshCatalog();
        }
      } catch {
        /* best-effort */
      }
    },

    async refreshCatalog() {
      if (this.catalogRefreshInFlight) return;
      this.catalogRefreshInFlight = true;
      try {
        await this.loadAll();
        if (this.loadError) return;
        this.applySceneConstraints();
        this.coerceCatalogFormPicks();
        this.$nextTick(() => {
          this.onViewportResize();
          this.updateHistoryScrollState();
        });
      } finally {
        this.catalogRefreshInFlight = false;
      }
    },

    coerceCatalogFormPicks() {
      if (
        this.form.character &&
        !this.isFieldRandom('character') &&
        !this.characterBySlug(this.form.character)
      ) {
        this.form.character = this.defaultSubjectSlug();
      }
      if (
        this.form.style &&
        !this.isFieldRandom('style') &&
        !this.styleBySlug(this.form.style)
      ) {
        this.form.style = this.defaultStyleSlug();
      }
      if (
        this.form.refine_style &&
        !this.isFieldRandom('refine_style') &&
        !this.refineStyleSameAsInference() &&
        !this.styleBySlug(this.form.refine_style)
      ) {
        this.form.refine_style = '_inference';
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

    pendingSlotActLabel(slot) {
      return this.pendingSlotSceneLabel(slot);
    },

    actLabelForSlug(slug) {
      if (!slug) return '—';
      const act = this.animationBySlug(slug);
      return act?.menu_name || act?.slug || slug;
    },

    locationLabelForKey(key) {
      if (!key) return '';
      const loc = this.locationByKey(key);
      return loc ? this._locationLabel(loc) : String(key).replace(/_/g, ' ');
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

    /** One visible history slot for client-side multi-generation batches. */
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

    previewFollowLiveSampling() {
      if (!this.previewLiveSampling || this.isPreviewPinnedToCompleted()) {
        return false;
      }
      const focusId = this.activePreviewPromptId();
      if (!focusId) return false;
      const focused = this.trackedJobs.find((t) => t.promptId === focusId);
      return focused ? this.isInferenceJobStatus(focused.status) : false;
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

    async loadHistory() {
      this.historyLoading = true;
      try {
        const r = await fetch(
          '/api/make/history?limit=' + MAKE_LAB_HISTORY_LIMIT
        );
        if (!r.ok) return;
        const data = await r.json();
        this.historyItems = Array.isArray(data.items) ? data.items : [];
        this.syncHistorySelectionFromPreview();
      } catch {
        /* keep previous list */
      } finally {
        this.historyLoading = false;
        this.$nextTick(() => {
          this.onViewportResize();
          this.updateHistoryScrollState();
        });
      }
    },

    syncHistorySelectionFromPreview() {
      if (this.comfyuiAnyJobActive()) return;
      const id = this.focusedPreviewPromptId();
      if (!id) return;
      const hit = this.historyItems.find((it) => it.prompt_id === id);
      if (hit) {
        this.selectedHistoryId = hit.prompt_id;
      }
    },

    historySceneLabel(item) {
      const parts = [];
      const charSlug = item?.character_slug;
      if (charSlug) {
        const subj =
          this.subjectEntityBySlug(charSlug) || this.characterBySlug(charSlug);
        const name = subj?.menu_name || subj?.slug || charSlug;
        if (name) parts.push(name);
      }
      const animationSlug = item?.animation_slug;
      if (animationSlug && String(animationSlug).toLowerCase() !== 'none') {
        const act = this.actLabelForSlug(animationSlug);
        if (act && act !== '—') parts.push(act);
      }
      const place = this.locationLabelForKey(item?.location_slug);
      if (place) parts.push(place);
      return parts.length ? parts.join(' · ') : '—';
    },

    historyActLabel(item) {
      return this.historySceneLabel(item);
    },

    isHistoryItemSelected(item) {
      const id = item?.prompt_id;
      if (!id) return false;
      return (
        this.selectedHistoryId === id ||
        this.previewFocusPromptId === id ||
        this.focusedPreviewPromptId() === id
      );
    },

    formatHistoryDate(iso) {
      if (!iso) return '';
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return '';
      return d.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
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

    /** True when a finished build should update entity pickers (not mid multi-queue). */
    shouldPinResolvedBuildToForm() {
      const q = this.clientGenerationQueue;
      return !(q && q.total > 1);
    },

    /** Merge rolled scene slugs into request when slots were random or omitted. */
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
      fill('background', 'location');
      fill('orientation');
      if (
        scene.refine_style != null &&
        this._requestSlotNeedsResolution(out.refine_style)
      ) {
        out.refine_style = scene.refine_style;
      }
      return out;
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
          resolved = r.location ?? r.background;
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

    async applyGalleryHandoff() {
      const params = new URLSearchParams(window.location.search);
      const restoreId = (params.get('restore') || '').trim();
      if (!restoreId) return;
      try {
        const r = await fetch(
          '/api/gallery/items/' + encodeURIComponent(restoreId)
        );
        if (!r.ok) return;
        const item = await r.json();
        this.selectHistoryItem(item);
        params.delete('restore');
        const qs = params.toString();
        window.history.replaceState(
          null,
          '',
          window.location.pathname + (qs ? '?' + qs : '')
        );
      } catch {
        /* handoff is best-effort */
      }
    },

    selectHistoryItem(item) {
      if (!item?.image_url) return;
      if (this.comfyuiAnyJobActive()) {
        this.previewLiveSampling = false;
      }
      this.previewFocusPromptId = null;
      this.previewAutoFollowInference = false;
      this.selectedHistoryId = item.prompt_id;
      this.outputImage = this.cacheBustUrl(item.image_url);
      this.resetOrientationToDefault();
      this.applyRequestToForm(item.request, item.build, { restoreDice: true });
      if (item.build) {
        this.result = item.build;
        this.applyBuildPreviewSize(item.build);
      } else {
        this.previewBuildSizeStale = true;
      }
      this.$nextTick(() => this.onViewportResize());
    },

    async loadAll() {
      this.loadError = '';
      try {
        const [dd, chars, monsters, objects, animations, styles, locs] = await Promise.all([
          fetch('/api/dropdowns'),
          fetch('/api/characters'),
          fetch('/api/monsters'),
          fetch('/api/objects'),
          fetch('/api/animations'),
          fetch('/api/styles'),
          fetch('/api/backgrounds'),
        ]);
        const bodies = await Promise.all([
          dd.json(),
          chars.json(),
          monsters.json(),
          objects.json(),
          animations.json(),
          styles.json(),
          locs.json(),
        ]);
        if (!dd.ok) throw new Error('dropdowns HTTP ' + dd.status);
        if (!chars.ok) throw new Error('characters HTTP ' + chars.status);
        if (!monsters.ok) throw new Error('monsters HTTP ' + monsters.status);
        if (!objects.ok) throw new Error('objects HTTP ' + objects.status);
        if (!animations.ok) throw new Error('animations HTTP ' + animations.status);
        if (!styles.ok) throw new Error('styles HTTP ' + styles.status);
        if (!locs.ok) throw new Error('backgrounds HTTP ' + locs.status);

        this.dropdowns = {
          orientations: bodies[0].orientations || [],
          sampler_hints: bodies[0].sampler_hints || [],
          scheduler_hints: bodies[0].scheduler_hints || [],
          dimension_hints: bodies[0].dimension_hints || [],
          style_defaults: bodies[0].style_defaults || {},
        };
        this.catalog = {
          characters: bodies[1],
          monsters: bodies[2],
          objects: bodies[3],
          animations: bodies[4],
          styles: bodies[5],
          backgrounds: bodies[6],
        };
        this.catalogRevision = Number(bodies[0].revision) || this.catalogRevision || 0;
      } catch (e) {
        this.loadError = 'Could not load dataset (' + e.message + ').';
      }
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

    detailerLabel(id) {
      const d = this.detailerRegions.find((r) => r.id === id);
      if (d?.label) return d.label;
      return id.charAt(0).toUpperCase() + id.slice(1);
    },

    isDetailerEnabled(id) {
      return (this.form.detailers || []).includes(id);
    },

    toggleDetailer(id) {
      const list = [...(this.form.detailers || [])];
      const i = list.indexOf(id);
      if (i >= 0) list.splice(i, 1);
      else list.push(id);
      this.form.detailers = list;
    },

    /** Canonical detailer order from the catalog API. */
    detailerOrder() {
      return (this.detailerRegions || []).map((d) => d.id);
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

    buildControlNetPayload() {
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
        background_color: (this.rmbg.background_color || '#222222').trim() || '#222222',
      };
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

    upscaleModelLabel(filename) {
      const key = String(filename || '').trim();
      return (this.upscaleModelLabels && this.upscaleModelLabels[key]) || key;
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

    characterBySlug(slug) {
      if (!slug) return null;
      const target = String(slug).trim();
      return (
        this.catalog.characters.find((c) => c.slug === target) ||
        this.catalog.monsters.find((c) => c.slug === target) ||
        this.catalog.objects.find((c) => c.slug === target) ||
        null
      );
    },

    subjectEntityBySlug(slug) {
      if (!slug) return null;
      const target = String(slug).trim();
      return this.activeSubjects().find((c) => c.slug === target) || null;
    },

    animationBySlug(slug) {
      return this.catalog.animations.find((a) => a.slug === slug);
    },

    styleBySlug(slug) {
      return this.catalog.styles.find((s) => s.slug === slug);
    },

    _loraStrengthSaved(kind) {
      const lora = this.resolvedLoraForKind(kind);
      if (!lora || !(lora.filename || '').trim()) return null;
      const n = Number(lora.strength);
      return Number.isFinite(n) ? n : 1;
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

    loraStrengthVisible(kind) {
      return this._loraStrengthSaved(kind) != null;
    },

    loraStrengthDisabled(kind) {
      return !this.loraStrengthVisible(kind) || !!this.loraStrengthSaveBusy[kind];
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

    loraStrengthDirty(kind) {
      const saved = this._loraStrengthSaved(kind);
      if (saved == null) return false;
      return Math.abs(this.loraStrengthEffective(kind) - saved) > 0.001;
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

    clearLoraStrengthOverride(kind) {
      const o = { ...(this.form.loraStrengthOverrides || {}) };
      if (!Object.prototype.hasOwnProperty.call(o, kind)) return;
      delete o[kind];
      this.form.loraStrengthOverrides = o;
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

    pickSlotClick(field) {
      this.openPicker(field);
    },

    resolvedFieldValue(field) {
      if (!field) return '';
      return String(this.displayValueForField(field) || '').trim();
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

    pickFieldCoverTargetLabel(field) {
      const summary = this.pickSummary(field);
      return summary?.title || field || 'entity';
    },

    pickFieldSettingsEnabled(field) {
      return !!this.pickFieldSettingsUrl(field);
    },

    pickFieldCoverEnabled(field) {
      if (!this.outputImage || this.coverUploadBusy) return false;
      return !!this.pickFieldCoverUploadUrl(field);
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

    _patchCatalogImagePath(field, imagePath) {
      if (!imagePath) return;
      const val = this.resolvedFieldValue(field);
      switch (field) {
        case 'character': {
          const row = this.characterBySlug(val);
          if (row) row.image_path = imagePath;
          return;
        }
        case 'animation': {
          const row = this.animationBySlug(val);
          if (row) row.image_path = imagePath;
          return;
        }
        case 'place': {
          const row = this.locationByKey(val);
          if (row) row.image_path = imagePath;
          return;
        }
        case 'style':
        case 'refine_style': {
          const row = this.styleBySlug(val);
          if (row) row.image_path = imagePath;
        }
      }
    },

    async setPickFieldCoverFromPreview(field) {
      const uploadUrl = this.pickFieldCoverUploadUrl(field);
      if (!uploadUrl || !this.outputImage) return;
      const label = this.pickFieldCoverTargetLabel(field);
      const ok = confirm(
        `Use the current preview as the reference image for “${label}”?\n\nThis replaces the existing cover photo.`
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

    openPickFieldSettings(field) {
      const url = this.pickFieldSettingsUrl(field);
      if (!url) return;
      window.open(url, '_blank', 'noopener,noreferrer');
    },

    scrollPickerToSelection() {
      this.$nextTick(() => {
        this.$nextTick(() => {
          const scroll = this.$refs.pickerScroll;
          if (!scroll) return;
          const selected = scroll.querySelector('.make-pick-card.selected');
          if (!selected) return;
          const scrollRect = scroll.getBoundingClientRect();
          const selRect = selected.getBoundingClientRect();
          const delta =
            selRect.top -
            scrollRect.top -
            (scroll.clientHeight - selRect.height) / 2;
          scroll.scrollTop += delta;
        });
      });
    },

    async openPicker(field) {
      await this.checkCatalogRevision();
      const titles = {
        character: `Choose ${this.subjectPickLabel().toLowerCase()}`,
        act: 'Choose animation',
        place: 'Choose background',
        style: 'Choose inference model',
        refine_style: 'Choose refine model',
      };
      this.picker = { open: true, field, title: titles[field] || 'Choose', filter: '' };
      this.scrollPickerToSelection();
    },

    closePicker() {
      this.picker.open = false;
      this.picker.filter = '';
    },

    closeMetadataModal() {
      this.metadataOpen = false;
    },

    focusedPreviewPromptId() {
      return this.previewFocusPromptId || this.selectedHistoryId || null;
    },

    canDeleteFocusedPreview() {
      const id = this.focusedPreviewPromptId();
      if (!id || this.deletingPreview) return false;
      return this.historyItems.some((it) => it.prompt_id === id);
    },

    async deleteFocusedPreview() {
      const id = this.focusedPreviewPromptId();
      if (!id || !this.canDeleteFocusedPreview()) return;
      this.deletingPreview = true;
      this.error = '';
      try {
        const r = await fetch(
          '/api/gallery/items/' + encodeURIComponent(id),
          { method: 'DELETE' }
        );
        if (!r.ok) {
          const data = await r.json().catch(() => ({}));
          throw new Error(
            (typeof data.detail === 'string' && data.detail) || 'Delete failed'
          );
        }
        const idx = this.historyItems.findIndex((it) => it.prompt_id === id);
        if (idx >= 0) this.historyItems.splice(idx, 1);
        if (this.selectedHistoryId === id || this.previewFocusPromptId === id) {
          const next = this.historyItems[idx] || this.historyItems[idx - 1] || null;
          if (next) {
            this.selectHistoryItem(next);
          } else {
            this.selectedHistoryId = null;
            this.previewFocusPromptId = null;
            this.outputImage = null;
            this.result = null;
          }
        }
        this.$nextTick(() => this.onViewportResize());
      } catch (e) {
        this.error = e.message || 'Could not delete generation.';
      } finally {
        this.deletingPreview = false;
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


    async fetchBuildForPromptId(promptId) {
      if (!promptId) return null;
      try {
        const r = await fetch(
          '/api/gallery/items/' + encodeURIComponent(promptId)
        );
        if (!r.ok) return null;
        const item = await r.json();
        return item.build || null;
      } catch {
        return null;
      }
    },

    async resolveMetadataBuild() {
      const focused = this.historyItemForFocusedPreview();
      if (focused?.build) return focused.build;

      if (this.outputImage && this.isPreviewPinnedToCompleted() && this.result) {
        return this.result;
      }

      const active = this.activePreviewPromptId();
      if (
        active &&
        this.trackedJobs.some((t) => t.promptId === active) &&
        this.result
      ) {
        return this.result;
      }

      const id = this.focusedPreviewPromptId();
      if (id) return this.fetchBuildForPromptId(id);

      return null;
    },

    openMetadataWithBuild(build) {
      this.result = build;
      this.applyBuildPreviewSize(build);
      this.metadataOpen = true;
    },

    metadataViewsLabel() {
      const views = this.result?.scene?.views;
      return Array.isArray(views) && views.length ? views.join(', ') : '—';
    },

    metadataCheckpoint() {
      return this.result?.sdxl?.checkpoint || {};
    },

    metadataRefineStyleLabel() {
      const raw = this.result?.scene?.refine_style;
      if (raw == null || raw === '' || raw === '_inference') return 'Same as inference';
      return String(raw);
    },

    hasAdetailerMetadata() {
      const ad = this.result?.character_adetailer;
      if (!ad || typeof ad !== 'object') return false;
      return Object.values(ad).some((t) => t && String(t).trim());
    },

    adetailerEntries() {
      const ad = this.result?.character_adetailer || {};
      return Object.entries(ad).filter(([, v]) => v && String(v).trim());
    },

    selectPick(value) {
      const field = this.picker.field;
      const prevChar = this.form.character;
      this.form[field] = value;
      if (MAKE_LAB_SCENE_PIN_FIELDS.includes(field)) {
        this.formRandom[field] = false;
        this.recordScenePin(field);
        this.applySceneConstraints();
      }
      if (field === 'character' && value !== prevChar) {
        this.applySceneConstraints();
      }
      if (field === 'style') {
        this.applyInferenceFromStyle(value, { dimension: true });
      }
      this.closePicker();
    },

    defaultSampler() {
      const d = this.dropdowns.style_defaults || {};
      return d.sampler || this.dropdowns.sampler_hints?.[0] || 'Euler a';
    },

    defaultScheduler() {
      const d = this.dropdowns.style_defaults || {};
      return d.scheduler || 'normal';
    },

    samplerSelectOptions() {
      const hints = [...(this.dropdowns.sampler_hints || [])];
      const cur = (this.form.sampler || '').trim();
      if (cur && !hints.includes(cur)) hints.unshift(cur);
      return hints;
    },

    schedulerSelectOptions() {
      const hints = [...(this.dropdowns.scheduler_hints || [])];
      const cur = (this.form.scheduler || '').trim();
      if (cur && !hints.includes(cur)) hints.unshift(cur);
      return hints;
    },

    /** One canonical size per aspect ratio; orientation swaps at build time. */
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
        .match(/^(\d+)\s*[x×]\s*(\d+)$/i);
      if (!m) return null;
      return { width: parseInt(m[1], 10), height: parseInt(m[2], 10) };
    },

    defaultDimension() {
      const d = this.dropdowns.style_defaults || {};
      const key = this.canonicalDimensionKey(d.width, d.height);
      return key || this.dropdowns.dimension_hints?.[0] || '1024x1024';
    },

    dimensionSelectOptions() {
      const out = [];
      const seen = new Set();
      const add = (key, label) => {
        if (!key || seen.has(key)) return;
        seen.add(key);
        out.push({ key, label: label || key.replace(/x/i, '×') });
      };
      for (const key of this.dropdowns.dimension_hints || []) {
        add(key, key.replace(/x/i, '×'));
      }
      const style =
        !this.styleIsRandom() && this.form.style
          ? this.styleBySlug(this.form.style)
          : null;
      if (style?.width && style?.height) {
        const key = this.canonicalDimensionKey(style.width, style.height);
        const label = key.replace(/x/i, '×') + ' (model)';
        if (seen.has(key)) {
          const hit = out.find((o) => o.key === key);
          if (hit) hit.label = label;
        } else {
          add(key, label);
        }
      }
      return out;
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

    filteredPickerOptions() {
      const opts = this.pickerOptions(this.picker.field);
      const q = (this.picker.filter || '').trim().toLowerCase();
      if (!q) return opts;
      return opts.filter((o) => {
        const hay = [o.title, o.slug, ...(o.lines || []), ...(o.badges || []).map((b) => b.label)]
          .join(' ')
          .toLowerCase();
        return hay.includes(q);
      });
    },

    pickerOptions(field) {
      const f = field || this.picker.field;
      switch (f) {
        case 'character':
          return this.activeSubjects().map((c) => this._characterOption(c));
        case 'animation':
          return [
            this._specialOption('none', 'None', 'No animation tags', 'animation'),
            ...this.pickerAnimations().map((a) => this._actOption(a)),
          ];
        case 'place':
          return this.pickerLocations().map((l) => this._locationOption(l));
        case 'style':
          return this.catalog.styles.map((s) => this._styleOption(s));
        case 'refine_style':
          return [
            this._specialOption(
              '_inference',
              'Same as inference',
              'Use the inference checkpoint for refine and detailers',
              f
            ),
            ...this.catalog.styles.map((s) => this._styleOption(s)),
          ];
        default:
          return [];
      }
    },

    _specialOption(value, title, line, field) {
      const pickKey =
        'special-' +
        (field || 'pick') +
        '-' +
        title +
        '-' +
        (value === '' ? 'empty' : String(value));
      return {
        value,
        title,
        slug: value || '—',
        image: null,
        initial: title.charAt(0).toUpperCase(),
        lines: [line],
        badges: [{ label: 'special', kind: 'muted' }],
        pickKey,
      };
    },

    _loraTriggerBadge(lora) {
      if (!lora) return null;
      const key = (lora.trigger || lora.caption_trigger || '').trim();
      return key ? { label: key, kind: 'accent' } : { label: 'LoRA', kind: 'accent' };
    },

    _characterOption(c) {
      const title = c.display_name || c.slug;
      const badges = [];
      const loraBadge = this._loraTriggerBadge(c.lora);
      if (loraBadge) badges.push(loraBadge);
      const lines = [];
      if (c.language) lines.push('Voice: ' + c.language);
      return {
        value: c.slug,
        title,
        slug: c.slug,
        image: c.image_path || null,
        initial: title.charAt(0).toUpperCase(),
        lines,
        badges,
        pickKey: 'char-' + c.slug,
      };
    },

    _actOption(a) {
      const title = a.menu_name || a.slug;
      const phaseCount = a.phase_count ?? countActPhases(a.phases);
      const badges = [];
      const animType = ANIMATION_TYPE_LABELS[a.subject_type || 'character'];
      if (animType) badges.push({ label: animType, kind: 'muted' });
      badges.push({
        label: phaseCount + (phaseCount === 1 ? ' phase' : ' phases'),
        kind: phaseCount >= 1 ? 'good' : 'warn',
      });
      if (a.sdxl_lora || a.lora) badges.push({ label: 'LoRA', kind: 'accent' });
      return {
        value: a.slug,
        title,
        slug: a.slug,
        image: a.image_path || null,
        initial: title.charAt(0).toUpperCase(),
        lines: [],
        badges,
        pickKey: 'act-' + a.slug,
      };
    },

    _styleOption(s) {
      const title = s.name || s.slug;
      return {
        value: s.slug,
        title,
        slug: s.slug,
        image: s.image_path || null,
        initial: title.charAt(0).toUpperCase(),
        lines: [],
        badges: s.lora ? [{ label: 'LoRA', kind: 'accent' }] : [],
      };
    },

    _locationLabel(loc) {
      return String(loc?.key || 'background').replace(/_/g, ' ');
    },

    _locationOption(loc) {
      const label = this._locationLabel(loc);
      const tags = tagPreview(loc.tags, 4);
      const lines = [];
      if (tags) lines.push(tags);
      const badges = [];
      const key = String(loc?.key || '');
      return {
        value: key,
        title: label,
        slug: key,
        image: loc?.image_path || null,
        initial: (label.charAt(0) || '?').toUpperCase(),
        lines,
        badges,
        pickKey: 'loc-' + key,
      };
    },

    formValue(field) {
      return field ? this.form[field] : '';
    },

    pickLineSummary(pick) {
      return (pick?.lines || []).filter(Boolean).join(' · ');
    },

    orientationSelectOptions() {
      return (this.dropdowns.orientations || []).filter((o) => o !== 'both');
    },

    resetOrientationToDefault() {
      this.form.orientation = '';
      this.orientationTouched = false;
    },

    selectedOrientationForSave() {
      const v = (this.form.orientation || '').trim().toLowerCase();
      return v === 'portrait' || v === 'landscape' ? v : null;
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

    applyBuildPreviewSize(build) {
      if (build?.sdxl?.width && build?.sdxl?.height) {
        this.previewBuildSizeStale = false;
        this.$nextTick(() => this.onViewportResize());
      }
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
      return width + '×' + height;
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

    /** Max preview box from measured center column + viewport (no page scroll). */
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

    _pickSummaryForValue(field, value) {
      if (value == null || value === '') {
        const fallback = this.displayValueForField(field);
        if (fallback) return this._pickSummaryForValue(field, fallback);
        return this._fallbackPickSummary('?');
      }
      switch (field) {
        case 'character': {
          const c = this.subjectEntityBySlug(value) || this.characterBySlug(value);
          return c ? this._characterOption(c) : this._fallbackPickSummary(value);
        }
        case 'animation': {
          if (String(value).toLowerCase() === 'none') {
            return this._specialOption('none', 'None', 'No animation tags', 'animation');
          }
          const a = this.animationBySlug(value);
          return a ? this._actOption(a) : this._fallbackPickSummary(value);
        }
        case 'place': {
          const l = this.locationByKey(value);
          return l ? this._locationOption(l) : this._fallbackPickSummary(value);
        }
        case 'style': {
          const s = this.styleBySlug(value);
          return s ? this._styleOption(s) : this._fallbackPickSummary(value);
        }
        case 'refine_style':
          if (
            String(value).toLowerCase() === '_inference' ||
            String(value).toLowerCase() === 'same_as_inference'
          ) {
            return this._specialOption(
              '_inference',
              'Same as inference',
              'Use the inference checkpoint for refine and detailers',
              field
            );
          }
          return this._pickSummaryForValue('style', value);
        default:
          return this._fallbackPickSummary(value);
      }
    },

    _fallbackPickSummary(value) {
      const label = String(value);
      return {
        value: label,
        title: label,
        slug: label,
        image: null,
        initial: label.charAt(0).toUpperCase() || '?',
        lines: [],
        badges: [],
      };
    },

    pickSummary(field) {
      return this._pickSummaryForValue(field, this.displayValueForField(field));
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

    generateButtonLabel() {
      if (this.comfyuiInferenceActive()) return 'Stop';
      if (this.generating) return 'Generating…';
      return 'Generate';
    },

    generateDisabled() {
      return (
        (this.busy && !this.comfyuiAnyJobActive()) ||
        (!this.comfyuiAnyJobActive() && this.comfyuiState === 'offline')
      );
    },

    onGenerateClick() {
      if (this.comfyuiInferenceActive()) {
        void this.stopGeneration();
        return;
      }
      if (this.generateDisabled()) return;
      void this.generatePhoto();
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

    async generatePhoto() {
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

    randomizeSeed() {
      if (this.seedIsMinusOne()) return;
      this.form.seed = String(Math.floor(Math.random() * 2 ** 31));
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
    },

    thumbStyle(image) {
      if (!image) return '';
      void this.catalogThumbEpoch;
      const base = String(image).split('?')[0];
      const src = base + '?_=' + this.catalogThumbEpoch;
      return "background-image:url('" + src.replace(/'/g, '%27') + "')";
    },
  };
}

window.makeLab = makeLab;

/** Make Lab — diffusion engine picker (Illustrious + Qwen Image 2512). */

(function (global) {
  const MAKE_ENGINE_IDS = global.MAKE_ENGINE_IDS || [
    global.MAKE_ENGINE_ILLUSTRIOUS || 'illustrious',
    global.MAKE_ENGINE_QWEN || 'qwen_image_2512',
  ];

  function makeEngineMethods() {
    return {
      diffusionModels: [],
      modelPickerOpen: false,

      selectedDiffusionModel() {
        const id = (this.form.engine || '').trim();
        return (
          this.diffusionModels.find((m) => m.id === id) ||
          this.diffusionModels.find((m) => m.id === 'illustrious') ||
          null
        );
      },

      async loadDiffusionModels() {
        try {
          const r = await fetch('/api/diffusion-models');
          const data = await r.json();
          const all = Array.isArray(data.models) ? data.models : [];
          this.diffusionModels = all.filter((m) =>
            MAKE_ENGINE_IDS.includes(m.id)
          );
          if (!this.form.engine) {
            this.form.engine = global.MAKE_ENGINE_ILLUSTRIOUS || 'illustrious';
          }
          const hit = this.selectedDiffusionModel();
          if (!hit && this.diffusionModels[0]) {
            this.setEngine(this.diffusionModels[0].id, { coerce: true });
          }
        } catch {
          this.diffusionModels = [];
          if (!this.form.engine) {
            this.form.engine = global.MAKE_ENGINE_ILLUSTRIOUS || 'illustrious';
          }
        }
      },

      isQwenEngineSelected() {
        return global.isQwenEngine(this.form.engine);
      },

      isIllustriousEngineSelected() {
        return !this.isQwenEngineSelected();
      },

      engineDimensionPresetKeys() {
        const presets = this.dropdowns.dimension_presets || {};
        const engine = (
          this.form.engine || global.MAKE_ENGINE_ILLUSTRIOUS || 'illustrious'
        ).trim();
        const rows = presets[engine];
        return Array.isArray(rows) ? rows.filter(Boolean) : [];
      },

      applyEngineCatalogDefaults(model) {
        if (!model) return;
        const defaults = model.default_settings || {};
        if (defaults.steps != null) this.form.steps = String(defaults.steps);
        if (defaults.cfg != null) this.form.cfg_scale = String(defaults.cfg);
        if (defaults.cfg_scale != null) {
          this.form.cfg_scale = String(defaults.cfg_scale);
        }
        if (defaults.shift != null) this.form.shift = String(defaults.shift);
        if (defaults.sampler != null) this.form.sampler = String(defaults.sampler);
        if (defaults.scheduler != null) {
          this.form.scheduler = String(defaults.scheduler);
        }
      },

      coercePicksForEngine() {
        const styles = this.stylesForEngine(this.form.engine);
        if (
          this.form.style &&
          !this.isFieldRandom('style') &&
          !styles.some((s) => s.slug === this.form.style)
        ) {
          this.form.style = styles[0]?.slug || '';
          this.formRandom.style = false;
        }
        const refineStyles = this.refineStylesForEngine(this.form.engine);
        const refine = (this.form.refine_style || '').trim();
        if (
          this.isQwenEngineSelected() &&
          refine === global.REFINE_STYLE_SAME &&
          !this.isFieldRandom('refine_style')
        ) {
          this.form.refine_style = global.REFINE_STYLE_NONE;
          this.formRandom.refine_style = false;
        }
        if (
          refine &&
          refine !== global.REFINE_STYLE_SAME &&
          refine !== global.REFINE_STYLE_NONE &&
          !this.isFieldRandom('refine_style') &&
          !refineStyles.some((s) => s.slug === refine)
        ) {
          this.form.refine_style = global.defaultRefineStyleForEngine(
            this.form.engine
          );
          this.formRandom.refine_style = false;
        }
        this.coerceDimensionForEngine();
      },

      coerceDimensionForEngine() {
        const opts = this.dimensionSelectOptions().map((o) => o.key);
        const cur =
          this.canonicalDimensionKeyFromKey(this.form.dimension) ||
          this.form.dimension;
        if (opts.length && !opts.includes(cur)) {
          this.form.dimension = opts[0];
        }
      },

      disableControlNetForQwen() {
        if (!this.isQwenEngineSelected()) return;
        const next = { ...(this.form.controlnet || {}) };
        for (const key of global.CONTROLNET_TYPE_KEYS || []) {
          if (next[key]) next[key] = { ...next[key], enabled: false };
        }
        this.form.controlnet = next;
        if (this.leftPipelineTab === 'controlnet') {
          this.leftPipelineTab = 'inference';
        }
      },

      setEngine(engineId, opts = {}) {
        const { coerce = true, fromStyle = false } = opts;
        const hit = this.diffusionModels.find((m) => m.id === engineId);
        if (!hit) return;
        const prev = this.form.engine;
        this.form.engine = hit.id;
        if (!fromStyle) {
          this.applyEngineCatalogDefaults(hit);
        }
        if (coerce) {
          this.coercePicksForEngine();
        }
        this.disableControlNetForQwen();
        if (prev !== hit.id) {
          this.onPreviewInferenceChanged?.();
        }
        this.modelPickerOpen = false;
      },

      syncEngineFromStyle(slug) {
        const style =
          slug && !this.styleIsRandom?.()
            ? this.styleBySlug(slug)
            : this.styleBySlug(this.form.style);
        const base = (style?.base_model || global.MAKE_ENGINE_ILLUSTRIOUS || 'illustrious')
          .trim()
          .toLowerCase();
        const engine =
          base === (global.MAKE_ENGINE_QWEN || 'qwen_image_2512')
            ? global.MAKE_ENGINE_QWEN || 'qwen_image_2512'
            : global.MAKE_ENGINE_ILLUSTRIOUS || 'illustrious';
        if (engine !== this.form.engine) {
          this.setEngine(engine, { coerce: false, fromStyle: true });
        }
      },

      openModelPicker() {
        this.modelPickerOpen = true;
      },

      closeModelPicker() {
        this.modelPickerOpen = false;
      },

      modelPickerLabel() {
        return this.selectedDiffusionModel()?.label || 'Select diffusion model';
      },

      metadataEngineLabel() {
        const e =
          this.result?.scene?.engine ||
          this.result?.qwen_make?.engine ||
          this.form.engine;
        if (e === (global.MAKE_ENGINE_QWEN || 'qwen_image_2512')) {
          return 'Qwen Image 2512';
        }
        if (e === (global.MAKE_ENGINE_ILLUSTRIOUS || 'illustrious')) {
          return 'Illustrious (SDXL)';
        }
        return e || '—';
      },

      metadataUsesQwenMake() {
        return Boolean(this.result?.qwen_make);
      },
    };
  }

  global.makeEngineMethods = makeEngineMethods;
})(window);

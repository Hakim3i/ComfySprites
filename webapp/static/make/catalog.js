(function (global) {
  function makeCatalogMethods() {
    return {

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
        !this.stylesForEngine(this.form.engine).some(
          (s) => s.slug === this.form.style
        )
      ) {
        this.form.style = this.defaultStyleSlug();
      }
      if (
        this.form.refine_style &&
        !this.isFieldRandom('refine_style') &&
        !this.refineStyleSameAsInference() &&
        !this.refineStyleIsNone() &&
        !this.refineStylesForEngine(this.form.engine).some(
          (s) => s.slug === this.form.refine_style
        )
      ) {
        this.form.refine_style = global.defaultRefineStyleForEngine(
          this.form.engine
        );
      }
      if (
        this.isQwenEngineSelected() &&
        this.refineStyleSameAsInference() &&
        !this.isFieldRandom('refine_style')
      ) {
        this.form.refine_style = global.REFINE_STYLE_NONE;
      }
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

        if (typeof applyMakeLabLimitsFromDropdowns === 'function') {
          applyMakeLabLimitsFromDropdowns(bodies[0]);
        }
        this.dropdowns = {
          orientations: bodies[0].orientations || [],
          sampler_hints: bodies[0].sampler_hints || [],
          scheduler_hints: bodies[0].scheduler_hints || [],
          dimension_hints: bodies[0].dimension_hints || [],
          dimension_presets: bodies[0].dimension_presets || {},
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

    async openPicker(field) {
      await this.checkCatalogRevision();
      const titles = {
        character: `Choose ${this.subjectPickLabel().toLowerCase()}`,
        act: 'Choose animation',
        place: 'Choose background',
        style: 'Choose inference style',
        refine_style: 'Choose refine style',
      };
      this.picker = { open: true, field, title: titles[field] || 'Choose', filter: '' };
      this.scrollPickerToSelection();
    },

    closePicker() {
      this.picker.open = false;
      this.picker.filter = '';
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
        this.syncEngineFromStyle(value);
        this.applyInferenceFromStyle(value, { dimension: true });
      }
      this.closePicker();
    },

    stylesForEngine(engine) {
      const target = String(engine || this.form.engine || 'illustrious')
        .trim()
        .toLowerCase();
      return (this.catalog.styles || []).filter((s) => {
        const base = String(s.base_model || 'illustrious').trim().toLowerCase();
        return base === target;
      });
    },

    refineStylesForEngine(engine) {
      const inf = String(engine || this.form.engine || 'illustrious')
        .trim()
        .toLowerCase();
      const refineEngine =
        inf === 'qwen_image_2512' ? 'illustrious' : inf;
      return this.stylesForEngine(refineEngine);
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
          return this.stylesForEngine(this.form.engine).map((s) =>
            this._styleOption(s)
          );
        case 'refine_style':
          if (this.isQwenEngineSelected()) {
            return [
              this._specialOption(
                'none',
                'None',
                'Random Illustrious SDXL style when refine runs',
                f
              ),
              ...this.refineStylesForEngine(this.form.engine).map((s) =>
                this._styleOption(s)
              ),
            ];
          }
          return [
            this._specialOption(
              '_inference',
              'Same as inference',
              'Use the inference checkpoint for refine and detailers',
              f
            ),
            ...this.refineStylesForEngine(this.form.engine).map((s) =>
              this._styleOption(s)
            ),
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

    formValue(field) {
      return field ? this.form[field] : '';
    },

    pickLineSummary(pick) {
      return (pick?.lines || []).filter(Boolean).join(' · ');
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
          if (String(value).toLowerCase() === '_inference') {
            return this._specialOption(
              '_inference',
              'Same as inference',
              'Use the inference checkpoint for refine and detailers',
              field
            );
          }
          if (String(value).toLowerCase() === 'none') {
            return this._specialOption(
              'none',
              'None',
              'Random Illustrious SDXL style when refine runs',
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

    animationBySlug(slug) {
      return this.catalog.animations.find((a) => a.slug === slug);
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

    styleBySlug(slug) {
      return this.catalog.styles.find((s) => s.slug === slug);
    },

    subjectEntityBySlug(slug) {
      if (!slug) return null;
      const target = String(slug).trim();
      return this.activeSubjects().find((c) => c.slug === target) || null;
    },

    _loraTriggerBadge(lora) {
      if (!lora) return null;
      const key = (lora.trigger || lora.caption_trigger || '').trim();
      return key ? { label: key, kind: 'accent' } : { label: 'LoRA', kind: 'accent' };
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

    thumbStyle(image) {
      if (!image) return '';
      void this.catalogThumbEpoch;
      const base = String(image).split('?')[0];
      const src = base + '?_=' + this.catalogThumbEpoch;
      return "background-image:url('" + src.replace(/'/g, '%27') + "')";
    }
    };
  }
  global.makeCatalogMethods = makeCatalogMethods;
})(window);

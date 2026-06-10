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



    actLabelForSlug(slug) {
      if (!slug) return 'ΓÇö';
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
        slug: value || 'ΓÇö',
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
      return (pick?.lines || []).filter(Boolean).join(' ┬╖ ');
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

/** Animate Lab — generation settings and LoRA strengths. */

function animateSettingsMethods() {
  return {
    form: {
      ...ANIMATE_FORM_DEFAULTS,
      lora_strengths: {},
      ltx_caption: '',
    },
    resolvedLoras: {},
    loraStrengthSaveBusy: {},
    _seedBeforeMinusOne: null,

    activeVideoLoraRoles() {
      const configured = this.selectedDiffusionModel()?.lora_roles;
      const roles = Array.isArray(configured) ? configured : [];
      return ANIMATE_VIDEO_LORA_ROLES.filter((role) => roles.includes(role));
    },

    resolveVideoLora(source, role) {
      const style = this.styleForSource?.() || null;
      const act = this.animationForSource();
      if (source === 'style') {
        if (role === 'ltx') return style?.ltx_lora || null;
        if (role === 'wan_high') return style?.wan_high_lora || null;
        if (role === 'wan_low') return style?.wan_low_lora || null;
        return null;
      }
      if (source === 'animation') {
        if (role === 'ltx') return act?.ltx_lora || null;
        if (role === 'wan_high') return act?.wan_high_lora || null;
        if (role === 'wan_low') return act?.wan_low_lora || null;
      }
      return null;
    },

    syncLorasForModel() {
      const roles = this.activeVideoLoraRoles();
      const next = {};
      const strengths = { ...this.form.lora_strengths };
      for (const source of ['style', 'animation']) {
        for (const role of roles) {
          const slot = animateLoraSlotKey(source, role);
          const lora = this.resolveVideoLora(source, role);
          if (lora?.filename) {
            next[slot] = animateCloneLora(lora);
            if (strengths[slot] == null) {
              strengths[slot] = Number(lora.strength) || 1;
            }
          }
        }
      }
      this.resolvedLoras = next;
      this.form.lora_strengths = strengths;
    },

    visibleStyleLoraSlots() {
      return this.activeVideoLoraRoles()
        .map((role) => animateLoraSlotKey('style', role))
        .filter((slot) => this.resolvedLoras[slot]);
    },

    visibleAnimationLoraSlots() {
      return this.activeVideoLoraRoles()
        .map((role) => animateLoraSlotKey('animation', role))
        .filter((slot) => this.resolvedLoras[slot]);
    },

    visibleLoraSlots() {
      return [...this.visibleStyleLoraSlots(), ...this.visibleAnimationLoraSlots()];
    },

    loraStrength(slot) {
      const n = Number(this.form.lora_strengths?.[slot]);
      return Number.isFinite(n) ? n : 1;
    },

    setLoraStrength(slot, value) {
      const n = clampLoraStrength(value);
      if (n == null) return;
      this.form.lora_strengths = {
        ...this.form.lora_strengths,
        [slot]: n,
      };
    },

    stepLoraStrength(slot, delta) {
      this.setLoraStrength(slot, stepLoraStrengthValue(this.loraStrength(slot), delta));
    },

    loraDisplayName(slot) {
      const lora = this.resolvedLoras[slot];
      return (lora?.name || '').trim() || lora?.filename || animateLoraSlotLabel(slot);
    },

    loraPersistId(slot) {
      const lora = this.resolvedLoras[slot];
      return lora?.id || null;
    },

    _loraStrengthSaved(slot) {
      const lora = this.resolvedLoras[slot];
      if (lora?.strength == null) return null;
      return Number(lora.strength);
    },

    loraStrengthDirty(slot) {
      const saved = this._loraStrengthSaved(slot);
      if (saved == null) return false;
      return Math.abs(this.loraStrength(slot) - saved) > 0.001;
    },

    loraStrengthSaveDisabled(slot) {
      return (
        !this.loraPersistId(slot) ||
        !this.loraStrengthDirty(slot) ||
        !!this.loraStrengthSaveBusy[slot]
      );
    },

    loraStrengthSaving(slot) {
      return !!this.loraStrengthSaveBusy[slot];
    },

    async saveLoraStrength(slot) {
      const loraId = this.loraPersistId(slot);
      if (!loraId || !this.loraStrengthDirty(slot)) return;
      this.loraStrengthSaveBusy = { ...this.loraStrengthSaveBusy, [slot]: true };
      try {
        const data = await patchLoraStrength(loraId, this.loraStrength(slot));
        const saved = Number(data.strength);
        const lora = this.resolvedLoras[slot];
        if (lora) lora.strength = saved;
        const style = this.styleForSource?.() || null;
        const act = this.animationForSource();
        const idx = slot.indexOf('_');
        const source = idx >= 0 ? slot.slice(0, idx) : '';
        const role = idx >= 0 ? slot.slice(idx + 1) : slot;
        if (source === 'style') {
          if (role === 'ltx' && style?.ltx_lora) style.ltx_lora.strength = saved;
          if (role === 'wan_high' && style?.wan_high_lora) style.wan_high_lora.strength = saved;
          if (role === 'wan_low' && style?.wan_low_lora) style.wan_low_lora.strength = saved;
        }
        if (source === 'animation') {
          if (role === 'ltx' && act?.ltx_lora) act.ltx_lora.strength = saved;
          if (role === 'wan_high' && act?.wan_high_lora) act.wan_high_lora.strength = saved;
          if (role === 'wan_low' && act?.wan_low_lora) act.wan_low_lora.strength = saved;
        }
      } catch (e) {
        this.showError(e.message || String(e));
      } finally {
        const next = { ...this.loraStrengthSaveBusy };
        delete next[slot];
        this.loraStrengthSaveBusy = next;
      }
    },

    styleCardTitle() {
      if (this.form.style_slug) {
        return this.styleLabel(this.form.style_slug);
      }
      return '— none —';
    },

    styleCardInitial() {
      return this.stylePickInitial();
    },

    seedIsMinusOne() {
      return String(this.form.seed).trim() === '-1';
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

    randomizeSeed() {
      if (this.seedIsMinusOne()) return;
      this.form.seed = String(Math.floor(Math.random() * 2 ** 31));
    },
  };
}

/** Animate Lab — generation settings and LoRA strengths. */

function animateSettingsMethods() {
  return {
    form: { ...ANIMATE_FORM_DEFAULTS, lora_strengths: {} },
    resolvedLoras: {},
    _seedBeforeMinusOne: null,

    syncLorasForModel() {
      const act = this.animationForSource();
      const roles = this.activeLoraRoles();
      const next = {};
      const strengths = { ...this.form.lora_strengths };
      for (const role of roles) {
        let lora = null;
        if (role === 'sdxl') lora = act?.sdxl_lora || act?.lora;
        else if (role === 'ltx') lora = act?.ltx_lora;
        else if (role === 'wan_high') lora = act?.wan_high_lora;
        else if (role === 'wan_low') lora = act?.wan_low_lora;
        if (lora?.filename) {
          next[role] = animateCloneLora(lora);
          if (strengths[role] == null) {
            strengths[role] = Number(lora.strength) || 1;
          }
        }
      }
      this.resolvedLoras = next;
      this.form.lora_strengths = strengths;
    },

    visibleLoraRoles() {
      return this.activeLoraRoles().filter((role) => this.resolvedLoras[role]);
    },

    loraStrength(role) {
      const n = Number(this.form.lora_strengths?.[role]);
      return Number.isFinite(n) ? n : 1;
    },

    setLoraStrength(role, value) {
      const n = clampLoraStrength(value);
      if (n == null) return;
      this.form.lora_strengths = {
        ...this.form.lora_strengths,
        [role]: n,
      };
    },

    stepLoraStrength(role, delta) {
      this.setLoraStrength(role, stepLoraStrengthValue(this.loraStrength(role), delta));
    },

    loraDisplayName(role) {
      const lora = this.resolvedLoras[role];
      return (lora?.name || '').trim() || lora?.filename || this.loraRoleLabel(role);
    },

    loraPersistId(role) {
      const lora = this.resolvedLoras[role];
      return lora?.id || null;
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

    generateDisabled() {
      return true;
    },

    generateButtonLabel() {
      return 'Generate';
    },

    onGenerateClick() {
      /* scaffold — workflows not wired */
    },
  };
}

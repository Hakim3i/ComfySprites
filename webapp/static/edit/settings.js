/** Edit Lab — generation settings and LoRA strengths. */

function editSettingsMethods() {
  return {
    form: {
      ...EDIT_FORM_DEFAULTS,
      lora_strengths: {},
    },
    resolvedLoras: {},
    loraStrengthSaveBusy: {},
    _seedBeforeMinusOne: null,

    syncLorasForModel({ resetStrengths = false } = {}) {
      const act = this.animationForSource();
      const roles = this.activeLoraRoles();
      const next = {};
      const strengths = { ...this.form.lora_strengths };
      for (const role of roles) {
        let lora = null;
        if (role === 'qwen_edit') lora = act?.qwen_edit_lora;
        if (lora?.filename) {
          next[role] = editCloneLora(lora);
          if (resetStrengths || strengths[role] == null) {
            strengths[role] = Number(lora.strength) || 1;
          }
        } else if (resetStrengths) {
          delete strengths[role];
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
      this.form.lora_strengths = { ...this.form.lora_strengths, [role]: n };
    },

    stepLoraStrength(role, delta) {
      this.setLoraStrength(role, stepLoraStrengthValue(this.loraStrength(role), delta));
    },

    loraDisplayName(role) {
      const lora = this.resolvedLoras[role];
      return (lora?.name || '').trim() || lora?.filename || this.loraRoleLabel(role);
    },

    loraPersistId(role) {
      return this.resolvedLoras[role]?.id || null;
    },

    _loraStrengthSaved(role) {
      const lora = this.resolvedLoras[role];
      if (lora?.strength == null) return null;
      return Number(lora.strength);
    },

    loraStrengthDirty(role) {
      const saved = this._loraStrengthSaved(role);
      if (saved == null) return false;
      return Math.abs(this.loraStrength(role) - saved) > 0.001;
    },

    loraStrengthSaveDisabled(role) {
      return (
        !this.loraPersistId(role) ||
        !this.loraStrengthDirty(role) ||
        !!this.loraStrengthSaveBusy[role]
      );
    },

    loraStrengthSaving(role) {
      return !!this.loraStrengthSaveBusy[role];
    },

    // Make Lab macro compatibility (`lora_strength_spin_save` in templates).
    loraStrengthVisible(kind) {
      return this.visibleLoraRoles().includes(kind) && !!this.resolvedLoras[kind];
    },

    loraStrengthEffective(kind) {
      return this.loraStrength(kind);
    },

    setLoraStrengthOverride(kind, value) {
      this.setLoraStrength(kind, value);
    },

    loraStrengthDisabled(kind) {
      return !this.loraStrengthVisible(kind);
    },

    async saveLoraStrength(role) {
      const loraId = this.loraPersistId(role);
      if (!loraId || !this.loraStrengthDirty(role)) return;
      this.loraStrengthSaveBusy = { ...this.loraStrengthSaveBusy, [role]: true };
      try {
        const data = await patchLoraStrength(loraId, this.loraStrength(role));
        const saved = Number(data.strength);
        const lora = this.resolvedLoras[role];
        if (lora) lora.strength = saved;
        const act = this.animationForSource();
        if (role === 'qwen_edit' && act?.qwen_edit_lora) {
          act.qwen_edit_lora.strength = saved;
        }
      } catch (e) {
        this.showError(e.message || String(e));
      } finally {
        const next = { ...this.loraStrengthSaveBusy };
        delete next[role];
        this.loraStrengthSaveBusy = next;
      }
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

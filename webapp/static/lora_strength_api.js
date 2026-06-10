/** PATCH /api/loras/{id} strength — shared by Make and Video Lab. */
(function (global) {
  const LORA_STRENGTH_MAX = 2;
  const LORA_STRENGTH_STEP = 0.05;

  function roundLoraStrength(n) {
    return Math.round(n * 100) / 100;
  }

  /** Cap high end only; negative strengths are allowed. */
  function clampLoraStrength(n) {
    let v = roundLoraStrength(Number(n));
    if (!Number.isFinite(v)) return null;
    if (v > LORA_STRENGTH_MAX) v = LORA_STRENGTH_MAX;
    return v;
  }

  function stepLoraStrengthValue(current, deltaSteps) {
    const cur = Number(current);
    const base = Number.isFinite(cur) ? cur : 1;
    return clampLoraStrength(base + deltaSteps * LORA_STRENGTH_STEP);
  }

  async function patchLoraStrength(loraId, strength) {
    const r = await fetch(`/api/loras/${loraId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ strength }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      throw new Error(data.detail || r.statusText || 'Save failed');
    }
    return data;
  }

  global.LORA_STRENGTH_MAX = LORA_STRENGTH_MAX;
  global.LORA_STRENGTH_STEP = LORA_STRENGTH_STEP;
  global.roundLoraStrength = roundLoraStrength;
  global.clampLoraStrength = clampLoraStrength;
  global.stepLoraStrengthValue = stepLoraStrengthValue;
  global.patchLoraStrength = patchLoraStrength;
})(window);

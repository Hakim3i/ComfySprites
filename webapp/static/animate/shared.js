/** Animate Lab — shared constants. */

const ANIMATE_LAB_HISTORY_LIMIT = 25;
const ANIMATE_LAB_SOURCES_LIMIT = 60;
const ANIMATE_LAB_BREAKPOINT_NARROW = 1100;
const ANIMATE_LAB_COMFYUI_LAB = 'animate';

const ANIMATE_LORA_ROLE_LABELS = {
  sdxl: 'SDXL LoRA',
  ltx: 'LTX 2.3 LoRA',
  wan_high: 'Wan High Noise',
  wan_low: 'Wan Low Noise',
};

const ANIMATE_FORM_DEFAULTS = {
  model_id: '',
  length_seconds: '5',
  fps: '24',
  seed: '-1',
  cfg: '1',
  lora_strengths: {},
};

function animateCloneLora(lora) {
  if (!lora) return null;
  return {
    id: lora.id ?? null,
    kind: lora.kind || '',
    filename: lora.filename || '',
    name: lora.name || '',
    trigger: lora.trigger || '',
    caption_trigger: lora.caption_trigger || '',
    strength: lora.strength != null ? Number(lora.strength) : 1,
    comment: lora.comment || '',
    url: lora.url || '',
    model_id: lora.model_id ?? null,
    version_id: lora.version_id ?? null,
  };
}

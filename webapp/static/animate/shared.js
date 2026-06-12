/** Animate Lab — shared constants. */

const ANIMATE_LAB_HISTORY_LIMIT = 25;
const ANIMATE_LAB_SOURCES_LIMIT = 60;
const ANIMATE_LAB_BREAKPOINT_NARROW = 1100;
const ANIMATE_LAB_COMFYUI_LAB = 'animate';
const ANIMATE_VIDEO_ENGINES = ['wan22', 'ltx23'];

const ANIMATE_VIDEO_LORA_ROLES = ['ltx', 'wan_high', 'wan_low'];

const ANIMATE_LORA_ROLE_LABELS = {
  ltx: 'LTX 2.3 LoRA',
  wan_high: 'Wan High Noise',
  wan_low: 'Wan Low Noise',
};

function animateLoraSlotKey(source, role) {
  return `${source}_${role}`;
}

function animateLoraSlotLabel(slot) {
  const idx = slot.indexOf('_');
  if (idx < 0) return slot;
  const source = slot.slice(0, idx);
  const role = slot.slice(idx + 1);
  const roleLabel = ANIMATE_LORA_ROLE_LABELS[role] || role;
  if (source === 'style') return `Style ${roleLabel}`;
  if (source === 'animation') return `Animation ${roleLabel}`;
  return `${source} ${roleLabel}`;
}

const ANIMATE_FORM_DEFAULTS = {
  model_id: '',
  style_slug: '',
  animation_slug: '',
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

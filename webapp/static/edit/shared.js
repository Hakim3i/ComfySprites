/** Edit Lab — shared constants. */

const EDIT_LAB_HISTORY_LIMIT = 25;
const EDIT_LAB_SOURCES_LIMIT = 60;
const EDIT_LAB_BREAKPOINT_NARROW = 1100;
const EDIT_LAB_COMFYUI_LAB = 'edit';

const EDIT_LORA_ROLE_LABELS = {
  qwen_edit: 'Edit LoRA',
};

const EDIT_FORM_DEFAULTS = {
  model_id: '',
  animation_slug: '',
  seed: '-1',
  steps: '4',
  cfg: '1',
  shift: '3.1',
  image_strength: '1',
  qwen_edit_prompt: '',
  qwen_edit_negative: '',
  lora_strengths: {},
};

function editCloneLora(lora) {
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
    download_url: lora.download_url || '',
    download_fallback_url: lora.download_fallback_url || '',
    model_id: lora.model_id ?? null,
    version_id: lora.version_id ?? null,
  };
}

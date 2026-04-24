const path = require('path');

const rootDir = path.join(__dirname, '..');

const sizePresets = {
  small: { width: 640, height: 1024 },
  medium: { width: 704, height: 1152 },
  large: { width: 768, height: 1280 },
};

const sizeLabels = {
  small: `${sizePresets.small.width} × ${sizePresets.small.height}`,
  medium: `${sizePresets.medium.width} × ${sizePresets.medium.height}`,
  large: `${sizePresets.large.width} × ${sizePresets.large.height}`,
};

const sizeLabelLandscape = {
  small: `${sizePresets.small.height} × ${sizePresets.small.width}`,
  medium: `${sizePresets.medium.height} × ${sizePresets.medium.width}`,
  large: `${sizePresets.large.height} × ${sizePresets.large.width}`,
};

const genderPrompts = {
  male: process.env.DEFAULT_GENDER_PROMPT_MALE || 'solo, 1boy',
  female: process.env.DEFAULT_GENDER_PROMPT_FEMALE || 'solo, 1girl',
};

const defaultPromptTags =
  process.env.DEFAULT_PROMPT_TAGS ||
  'standing, full_body, side_view, looking_away, simple_background';

const defaultPromptTagsObject =
  process.env.DEFAULT_PROMPT_TAGS_OBJECT ||
  'no_humans, simple_background, centered, game_assets';

const defaultNegativePrompt =
  process.env.DEFAULT_NEGATIVE_PROMPT ||
  'lowres, (worst quality, low quality, bad anatomy, bad hands:1.3), abstract, signature';

/** Available sprite types */
const spriteTypes = [
  { value: 'character', label: 'Character' },
  { value: 'object', label: 'Object' },
];

const defaultSpriteType = 'character';

/** LoRA options for sprite creation/make workflow (Power Lora Loader node 1168). value = lora_name for workflow, label = display name. */
const makeLoras = [
  { value: '', label: 'None' },
  { value: 'ILLUSTRIOUS\\cm2.safetensors', label: 'CloudMeadow' },
  { value: 'ILLUSTRIOUS\\CounterSide_Sprites.safetensors', label: 'CounterSide' },
];

/** LoRA options for edit workflow (Power Lora Loader node 110). value = lora_name for workflow, label = display name. */
const editLoras = [
  { value: '', label: 'None' },
  { value: 'QWEN\\2D_Mouvement.safetensors', label: '2D Mouvement' },
  { value: 'QWEN\\2D_Combat.safetensors', label: '2D Combat' },
];

/** LoRA options for animate HIGH NOISE only (Power Lora Loader HIGH NOISE). */
const animateLorasHigh = [
  { value: '', label: 'None' },
  { value: 'WAN2.2\\I2V\\cloudmeadow3_i2v_high.safetensors', label: 'CloudMeadow' },
  { value: 'WAN2.2\\I2V\\counter_side_attack_i2v_high.safetensors', label: 'CounterSide Attack' },
  { value: 'WAN2.2\\I2V\\counter_side_defeated_i2v_high.safetensors', label: 'CounterSide Defeated' },
  { value: 'WAN2.2\\I2V\\counter_side_hit_i2v_high.safetensors', label: 'CounterSide Hit' },
  { value: 'WAN2.2\\I2V\\counter_side_idle_i2v_high.safetensors', label: 'CounterSide Idle' },
  { value: 'WAN2.2\\I2V\\counter_side_run_i2v_high.safetensors', label: 'CounterSide Run' },
  { value: 'WAN2.2\\I2V\\counter_side_walk_i2v_high.safetensors', label: 'CounterSide Walk' },
];

/** LoRA options for animate LOW NOISE only (Power Lora Loader LOW NOISE). */
const animateLorasLow = [
  { value: '', label: 'None' },
  { value: 'WAN2.2\\I2V\\cloudmeadow3_i2v_low.safetensors', label: 'CloudMeadow' },
  { value: 'WAN2.2\\I2V\\counter_side_attack_i2v_low.safetensors', label: 'CounterSide Attack' },
  { value: 'WAN2.2\\I2V\\counter_side_defeated_i2v_low.safetensors', label: 'CounterSide Defeated' },
  { value: 'WAN2.2\\I2V\\counter_side_hit_i2v_low.safetensors', label: 'CounterSide Hit' },
  { value: 'WAN2.2\\I2V\\counter_side_idle_i2v_low.safetensors', label: 'CounterSide Idle' },
  { value: 'WAN2.2\\I2V\\counter_side_run_i2v_low.safetensors', label: 'CounterSide Run' },
  { value: 'WAN2.2\\I2V\\counter_side_walk_i2v_low.safetensors', label: 'CounterSide Walk' },
];

module.exports = {
  PORT: Number(process.env.PORT) || 3000,
  COMFY_URL: process.env.COMFY_URL || 'http://127.0.0.1:8188',
  outputsDir: path.join(rootDir, 'outputs'),
  spritesDir: path.join(rootDir, 'data', 'sprites'),
  videosDir: path.join(rootDir, 'data', 'videos'),
  makeWorkflowPath: path.join(rootDir, 'workflows', 'Make.json'),
  editWorkflowPath: path.join(rootDir, 'workflows', 'Edit.json'),
  animateWorkflowPath: path.join(rootDir, 'workflows', 'Animate.json'),
  animateFFLFWorkflowPath: path.join(rootDir, 'workflows', 'AnimateFFLF.json'),
  animatePPWorkflowPath: path.join(rootDir, 'workflows', 'AnimatePP.json'),
  rmbgWorkflowPath: path.join(rootDir, 'workflows', 'RMBG.json'),
  rmbgImagesWorkflowPath: path.join(rootDir, 'workflows', 'RMBG_IMAGES.json'),
  rmbgVideoWorkflowPath: path.join(rootDir, 'workflows', 'RMBG_VIDEO.json'),
  tempExportDir: path.join(rootDir, 'temp_export'),
  defaultAnimateFrames: 81,
  generationTtlMs: 10 * 60 * 1000,
  cleanupIntervalMs: 60 * 1000,

  defaultBackgroundColor: process.env.DEFAULT_BACKGROUND_COLOR || '#000000',
  defaultGender: process.env.DEFAULT_GENDER || 'female',
  defaultSize: process.env.DEFAULT_SIZE || 'large',
  defaultSpriteType,
  spriteTypes,
  genderPrompts,
  sizePresets,
  sizeLabels,
  sizeLabelLandscape,
  defaultPromptTags,
  defaultPromptTagsObject,
  defaultNegativePrompt,
  makeLoras,
  editLoras,
  animateLorasHigh,
  animateLorasLow,
};

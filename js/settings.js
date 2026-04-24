/* Settings tab: load and save config via data/config.json */

import { getConfig, putConfig } from './api.js';

function get(id) {
  return document.getElementById(id);
}

function lorasToJson(arr) {
  try {
    return JSON.stringify(Array.isArray(arr) && arr.length ? arr : [{ value: '', label: 'None' }], null, 2);
  } catch {
    return '[{"value":"","label":"None"}]';
  }
}

function updateSizeSelectLabels(presets, labels) {
  const sel = get('settings-default-size');
  if (!sel) return;
  const lbl = labels || (presets ? { small: `${presets.small?.width ?? 0} × ${presets.small?.height ?? 0}`, medium: `${presets.medium?.width ?? 0} × ${presets.medium?.height ?? 0}`, large: `${presets.large?.width ?? 0} × ${presets.large?.height ?? 0}` } : {});
  ['small', 'medium', 'large'].forEach(k => {
    const opt = sel.querySelector(`option[value="${k}"]`);
    if (opt) opt.textContent = `${k.charAt(0).toUpperCase() + k.slice(1)} (${lbl[k] || '—'})`;
  });
}

function parseLorasJson(str) {
  if (!str || !String(str).trim()) return [{ value: '', label: 'None' }];
  try {
    const parsed = JSON.parse(str);
    return Array.isArray(parsed) ? parsed : [{ value: '', label: 'None' }];
  } catch {
    return null;
  }
}

export function loadSettingsForm(config) {
  const c = config || {};
  const color = c.defaultBackgroundColor || '#000000';
  const colorInput = get('settings-bg-color');
  const colorText = get('settings-bg-color-text');
  if (colorInput) colorInput.value = color;
  if (colorText) colorText.value = color;

  const genderSelect = get('settings-default-gender');
  if (genderSelect) genderSelect.value = c.defaultGender || 'female';

  const sizeSelect = get('settings-default-size');
  if (sizeSelect) sizeSelect.value = c.defaultSize || 'large';
  updateSizeSelectLabels(c.sizePresets, c.sizeLabels);

  const presets = c.sizePresets || { small: { width: 640, height: 1024 }, medium: { width: 704, height: 1152 }, large: { width: 768, height: 1280 } };
  const setNum = (id, val) => { const el = get(id); if (el) el.value = val != null ? String(val) : ''; };
  setNum('settings-size-small-w', presets.small?.width);
  setNum('settings-size-small-h', presets.small?.height);
  setNum('settings-size-medium-w', presets.medium?.width);
  setNum('settings-size-medium-h', presets.medium?.height);
  setNum('settings-size-large-w', presets.large?.width);
  setNum('settings-size-large-h', presets.large?.height);

  const typeSelect = get('settings-default-sprite-type');
  if (typeSelect) typeSelect.value = c.defaultSpriteType || 'character';

  const promptTags = get('settings-prompt-tags');
  if (promptTags) promptTags.value = c.defaultPromptTags || '';

  const promptTagsObject = get('settings-prompt-tags-object');
  if (promptTagsObject) promptTagsObject.value = c.defaultPromptTagsObject || '';

  const negativePrompt = get('settings-negative-prompt');
  if (negativePrompt) negativePrompt.value = c.defaultNegativePrompt || '';

  const gp = c.genderPrompts || {};
  const maleInput = get('settings-gender-prompt-male');
  if (maleInput) maleInput.value = gp.male || '';
  const femaleInput = get('settings-gender-prompt-female');
  if (femaleInput) femaleInput.value = gp.female || '';

  const makeLorasEl = get('settings-make-loras');
  if (makeLorasEl) makeLorasEl.value = lorasToJson(c.makeLoras);
  const editLorasEl = get('settings-edit-loras');
  if (editLorasEl) editLorasEl.value = lorasToJson(c.editLoras);
  const animateHighEl = get('settings-animate-loras-high');
  if (animateHighEl) animateHighEl.value = lorasToJson(c.animateLorasHigh);
  const animateLowEl = get('settings-animate-loras-low');
  if (animateLowEl) animateLowEl.value = lorasToJson(c.animateLorasLow);
}

function showStatus(message, isError = false) {
  const el = get('settings-status');
  if (!el) return;
  el.textContent = message;
  el.className = 'settings-status' + (isError ? ' settings-status-error' : '');
}

export async function setupSettingsTab(onConfigSaved) {
  const form = get('settings-form');
  const saveBtn = get('settings-save-btn');

  const colorInput = get('settings-bg-color');
  const colorText = get('settings-bg-color-text');
  if (colorInput && colorText) {
    colorInput.addEventListener('input', () => { colorText.value = colorInput.value; });
    colorText.addEventListener('input', (e) => {
      const v = e.target.value?.trim();
      if (/^#[0-9A-Fa-f]{6}$/.test(v)) colorInput.value = v;
    });
  }

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const makeLoras = parseLorasJson(get('settings-make-loras')?.value);
      const editLoras = parseLorasJson(get('settings-edit-loras')?.value);
      const animateHigh = parseLorasJson(get('settings-animate-loras-high')?.value);
      const animateLow = parseLorasJson(get('settings-animate-loras-low')?.value);
      if (makeLoras === null || editLoras === null || animateHigh === null || animateLow === null) {
        showStatus('Invalid JSON in one or more LoRA fields.', true);
        return;
      }

      const num = (id) => { const v = parseInt(get(id)?.value, 10); return Number.isFinite(v) ? v : undefined; };
      const sizePresets = {
        small: { width: num('settings-size-small-w') ?? 640, height: num('settings-size-small-h') ?? 1024 },
        medium: { width: num('settings-size-medium-w') ?? 704, height: num('settings-size-medium-h') ?? 1152 },
        large: { width: num('settings-size-large-w') ?? 768, height: num('settings-size-large-h') ?? 1280 },
      };

      const payload = {
        defaultBackgroundColor: get('settings-bg-color')?.value || '#000000',
        defaultGender: get('settings-default-gender')?.value || 'female',
        defaultSize: get('settings-default-size')?.value || 'large',
        defaultSpriteType: get('settings-default-sprite-type')?.value || 'character',
        sizePresets,
        defaultPromptTags: get('settings-prompt-tags')?.value?.trim() ?? '',
        defaultPromptTagsObject: get('settings-prompt-tags-object')?.value?.trim() ?? '',
        defaultNegativePrompt: get('settings-negative-prompt')?.value?.trim() ?? '',
        genderPrompts: {
          male: get('settings-gender-prompt-male')?.value?.trim() ?? '',
          female: get('settings-gender-prompt-female')?.value?.trim() ?? '',
        },
        makeLoras,
        editLoras,
        animateLorasHigh: animateHigh,
        animateLorasLow: animateLow,
      };

      try {
        if (saveBtn) saveBtn.disabled = true;
        showStatus('Saving…');
        const updated = await putConfig(payload);
        showStatus('Saved. Settings applied.');
        if (typeof onConfigSaved === 'function') onConfigSaved(updated);
      } catch (err) {
        showStatus(err.message || 'Failed to save.', true);
      } finally {
        if (saveBtn) saveBtn.disabled = false;
      }
    });
  }
}

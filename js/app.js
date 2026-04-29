/* Main application entry: initializes tabs, renders views, wires up event handlers */

import { setupTabs, escapeHtml } from './ui.js';
import { renderCards, handleCreateSubmit, handleGenerateClick, setupRandomSeed, resetModal, setAppConfig, hideMakePanel } from './make.js';
import { renderEditRows, setupEditTab } from './edit.js';
import { renderAnimateList, setupAnimateTab } from './animate.js';
import { renderSavedVideosList, setupVideosTab } from './export.js';
import { loadSettingsForm, setupSettingsTab } from './settings.js';
import { getConfig, getModels } from './api.js';

/** Last filename segment without extension. Used to render human-friendly labels for models/LoRAs discovered from ComfyUI (which returns full relative paths). */
function prettyLabelFromPath(p) {
    if (!p) return '';
    const parts = String(p).replace(/\\/g, '/').split('/');
    const last = parts[parts.length - 1] || p;
    return last.replace(/\.[a-zA-Z0-9]+$/, '');
}

function optionHtml(value, label, { selected = false } = {}) {
    const sel = selected ? ' selected' : '';
    return `<option value="${escapeHtml(value)}"${sel}>${escapeHtml(label)}</option>`;
}

function fillSelect(el, items, { includeNone = false, noneLabel = 'None' } = {}) {
    if (!el) return;
    const parts = [];
    if (includeNone) parts.push(optionHtml('', noneLabel));
    for (const val of items) parts.push(optionHtml(val, prettyLabelFromPath(val)));
    el.innerHTML = parts.join('');
}

function normalizeModelPath(value) {
    return String(value || '').replace(/\\/g, '/').toLowerCase();
}

function filterLorasByFolder(loras, folderName) {
    const name = String(folderName || '').toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`(^|/)${name}(/|$)`);
    return loras.filter((l) => re.test(normalizeModelPath(l)));
}

function filterByFolder(items, folderName) {
    const name = String(folderName || '').toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`(^|/)${name}(/|$)`);
    return items.filter((item) => re.test(normalizeModelPath(item)));
}

function filterByTag(items, tag) {
    const needle = String(tag || '').toLowerCase();
    return items.filter((item) => normalizeModelPath(item).includes(needle));
}

/**
 * Populate every model and LoRA selector from values discovered via `/api/models`.
 * LoRA selectors are filtered by model folder:
 * - Make   -> loras/sdxl
 * - Edit   -> loras/qwen
 * - Animate -> loras/wan
 * If a scoped bucket is empty, we gracefully fall back to the full LoRA list.
 */
function populateModelsAndLoras(models) {
    const checkpoints = Array.isArray(models?.checkpoints) ? models.checkpoints : [];
    const diffusionModels = Array.isArray(models?.diffusionModels) ? models.diffusionModels : [];
    const loras = Array.isArray(models?.loras) ? models.loras : [];
    const qwenModels = filterByFolder(diffusionModels, 'qwen');
    const wanModels = filterByFolder(diffusionModels, 'wan');
    const wanHighModels = filterByTag(wanModels, 'high');
    const wanLowModels = filterByTag(wanModels, 'low');

    fillSelect(document.getElementById('make-model'), checkpoints);
    fillSelect(document.getElementById('edit-model'), qwenModels);
    fillSelect(document.getElementById('animate-model-high'), wanHighModels.length ? wanHighModels : wanModels);
    fillSelect(document.getElementById('animate-model-low'), wanLowModels.length ? wanLowModels : wanModels);

    const sdxlLoras = filterLorasByFolder(loras, 'sdxl');
    const qwenLoras = filterLorasByFolder(loras, 'qwen');
    const wanLoras = filterLorasByFolder(loras, 'wan');
    const wanHighLoras = filterByTag(wanLoras, 'high');
    const wanLowLoras = filterByTag(wanLoras, 'low');

    fillSelect(document.getElementById('make-lora'), sdxlLoras.length ? sdxlLoras : loras, { includeNone: true });
    fillSelect(document.getElementById('edit-lora'), qwenLoras.length ? qwenLoras : loras, { includeNone: true });
    fillSelect(document.getElementById('animate-lora-high'), wanHighLoras.length ? wanHighLoras : wanLoras, { includeNone: true });
    fillSelect(document.getElementById('animate-lora-low'), wanLowLoras.length ? wanLowLoras : wanLoras, { includeNone: true });

    return { checkpoints: checkpoints.length, diffusionModels: diffusionModels.length, loras: loras.length };
}

/** Force a fresh discovery from the backend (bypasses cache) and repopulate every select. Exposed to settings.js via the `reloadModels` export. */
export async function reloadModels() {
    const models = await getModels({ refresh: true });
    return { counts: populateModelsAndLoras(models), comfyUrl: models?.comfyUrl };
}

function refreshAppConfig(config) {
    setAppConfig(config);
}

document.addEventListener('DOMContentLoaded', async () => {
    const [config, models] = await Promise.all([getConfig(), getModels()]);
    refreshAppConfig(config);
    populateModelsAndLoras(models);
    loadSettingsForm(config);
    setupTabs();
    setupSettingsTab(refreshAppConfig);
    renderCards();
    renderEditRows();
    renderAnimateList();
    setupRandomSeed();
    setupEditTab();
    setupAnimateTab();
    setupVideosTab();

    const generateBtn = document.getElementById('generate-btn');
    if (generateBtn) generateBtn.addEventListener('click', handleGenerateClick);

    const form = document.getElementById('make-sprite-form');
    if (form) form.addEventListener('submit', handleCreateSubmit);

    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', async () => {
            if (tab.dataset.tab === 'make') renderCards();
            if (tab.dataset.tab === 'edit') renderEditRows();
            if (tab.dataset.tab === 'animate') renderAnimateList();
            if (tab.dataset.tab === 'videos') renderSavedVideosList();
            if (tab.dataset.tab === 'settings') {
                const config = await getConfig();
                loadSettingsForm(config);
            }
        });
    });
});

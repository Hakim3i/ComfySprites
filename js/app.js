/* Main application entry: initializes tabs, renders views, wires up event handlers */

import { setupTabs, escapeHtml } from './ui.js';
import { renderCards, handleCreateSubmit, handleGenerateClick, setupRandomSeed, resetModal, setAppConfig, hideMakePanel } from './make.js';
import { renderEditRows, setupEditTab } from './edit.js';
import { renderAnimateList, setupAnimateTab } from './animate.js';
import { renderSavedVideosList, setupVideosTab } from './export.js';
import { loadSettingsForm, setupSettingsTab } from './settings.js';
import { getConfig } from './api.js';

function populateLoraDropdowns(config) {
    const makeSelect = document.querySelector('#make-sprite-form select[name="lora"]');
    if (makeSelect && config.makeLoras?.length) {
        makeSelect.innerHTML = config.makeLoras.map(o => `<option value="${escapeHtml(o.value)}">${escapeHtml(o.label)}</option>`).join('');
    }
    const editSelect = document.getElementById('edit-lora');
    if (editSelect && config.editLoras?.length) {
        editSelect.innerHTML = config.editLoras.map(o => `<option value="${escapeHtml(o.value)}">${escapeHtml(o.label)}</option>`).join('');
    }
    const highOptions = config.animateLorasHigh?.length
        ? config.animateLorasHigh.map(o => `<option value="${escapeHtml(o.value)}">${escapeHtml(o.label)}</option>`).join('')
        : '<option value="">None</option>';
    const lowOptions = config.animateLorasLow?.length
        ? config.animateLorasLow.map(o => `<option value="${escapeHtml(o.value)}">${escapeHtml(o.label)}</option>`).join('')
        : '<option value="">None</option>';
    const animateHigh = document.getElementById('animate-lora-high');
    const animateLow = document.getElementById('animate-lora-low');
    if (animateHigh) animateHigh.innerHTML = highOptions;
    if (animateLow) animateLow.innerHTML = lowOptions;
}

function refreshAppConfig(config) {
    setAppConfig(config);
    populateLoraDropdowns(config);
}

document.addEventListener('DOMContentLoaded', async () => {
    const config = await getConfig();
    refreshAppConfig(config);
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

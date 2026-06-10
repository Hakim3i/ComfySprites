/** Make Lab shared constants and helpers. */
(function (global) {
  global.MAKE_LAB_HISTORY_LIMIT = 25;
  global.MAKE_LAB_BREAKPOINT_NARROW = global.LAB_HISTORY_BREAKPOINT_NARROW;
  global.MAKE_LAB_RMBG_MODELS = ['RMBG-2.0', 'INSPYRENET', 'BEN', 'BEN2'];
  global.MAKE_LAB_RMBG_PROCESS_RES_OPTIONS = ['512', '1024', '2048'];
  global.MAKE_LAB_RMBG_MASK_BLUR_MAX = 64;
  global.MAKE_LAB_RMBG_MASK_OFFSET_MIN = -64;
  global.MAKE_LAB_RMBG_MASK_OFFSET_MAX = 64;
  global.MAKE_LAB_PREVIEW_MAGNIFIER_ZOOM = 2.0;
  global.MAKE_LAB_CATALOG_REVISION_POLL_MS = 5000;
  global.MAKE_LAB_COMFYUI_LAB = 'make';
  global.MAKE_LAB_SCENE_PIN_FIELDS = ['animation', 'place'];
  global.MAKE_LAB_SPRITE_TYPES = [
    { id: 'character', label: 'Character', icon: 'character' },
    { id: 'monster', label: 'Monster', icon: 'flame' },
    { id: 'object', label: 'Object', icon: 'category' },
  ];
  global.ANIMATION_TYPE_LABELS = {
    character: 'Character animation',
    monster: 'Monster animation',
    object: 'Object animation',
  };
  global.MAKE_LAB_DICE_FIELDS = new Set([
    'character',
    'animation',
    'place',
    'style',
    'refine_style',
  ]);
  global.CONTROLNET_TYPE_KEYS = ['openpose', 'depth', 'canny'];
  global.CONTROLNET_TYPE_DEFAULTS = {
    openpose: { strength: 0.9, start_percent: 0, end_percent: 1 },
    depth: { strength: 0.75, start_percent: 0, end_percent: 1 },
    canny: { strength: 0.8, start_percent: 0, end_percent: 1 },
  };

  global.tagPreview = function tagPreview(tags, max = 4) {
    const list = (tags || []).filter(Boolean);
    if (!list.length) return '';
    const head = list.slice(0, max).join(', ');
    return list.length > max ? head + '…' : head;
  };

  global.countActPhases = function countActPhases(phases) {
    if (!phases || typeof phases !== 'object') return 0;
    return Object.keys(phases).filter((p) => String(phases[p] || '').trim()).length;
  };

  global.detailerUiRowsFromOrder = function detailerUiRowsFromOrder(order) {
    const ids = Array.isArray(order) ? order.filter(Boolean) : [];
    if (!ids.length) return [];
    const rows = [];
    for (let i = 0; i < ids.length; i += 4) {
      rows.push(ids.slice(i, i + 4));
    }
    return rows;
  };
})(window);

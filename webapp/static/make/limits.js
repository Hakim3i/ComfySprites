/** Make Lab limits — defaults; overridden from GET /api/dropdowns in init(). */
(function (global) {
  global.MAKE_LAB_IMAGES_MIN = 1;
  global.MAKE_LAB_IMAGES_MAX = 5;
  global.MAKE_LAB_GENERATION_COUNT_MIN = 1;
  global.MAKE_LAB_GENERATION_COUNT_MAX = 999;
  global.MAKE_LAB_UPSCALE_MODEL_DEFAULT = 'RealESRGAN_x2.pth';
  global.MAKE_LAB_UPSCALE_BY_DEFAULT = '1.5';
  global.MAKE_LAB_REFINE_STEPS_DEFAULT = '15';
  global.MAKE_LAB_REFINE_DENOISE_DEFAULT = '0.35';

  function applyMakeLabLimitsFromDropdowns(data) {
    const lim = data && data.make_limits;
    if (!lim || typeof lim !== 'object') return;
    const assign = (key, prop) => {
      if (lim[prop] != null) global[key] = lim[prop];
    };
    assign('MAKE_LAB_IMAGES_MIN', 'images_min');
    assign('MAKE_LAB_IMAGES_MAX', 'images_max');
    assign('MAKE_LAB_GENERATION_COUNT_MIN', 'generation_count_min');
    assign('MAKE_LAB_GENERATION_COUNT_MAX', 'generation_count_max');
    assign('MAKE_LAB_UPSCALE_MODEL_DEFAULT', 'upscale_model_default');
    assign('MAKE_LAB_UPSCALE_BY_DEFAULT', 'upscale_by_default');
    assign('MAKE_LAB_REFINE_STEPS_DEFAULT', 'refine_steps_default');
    assign('MAKE_LAB_REFINE_DENOISE_DEFAULT', 'refine_denoise_default');
  }
  global.applyMakeLabLimitsFromDropdowns = applyMakeLabLimitsFromDropdowns;
})(window);

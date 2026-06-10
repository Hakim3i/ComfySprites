/** Shared SDXL prompt-segment helpers for Validate and Make. */

window.coomfyPromptSegments = {
  segTooltip(idx, seg) {
    const n = idx + 1;
    const cat = seg?.label || seg?.source || '';
    const from = seg?.origin || seg?.source || '';
    return n + '. ' + cat + ' - ' + from;
  },

  sdxlJoined(result, side) {
    const segs = result?.sdxl?.[side + '_segments'] || [];
    const parts = segs.filter((s) => s.tags?.length).map((s) => s.tags.join(', '));
    return parts.join(', ');
  },

  refineJoined(result, side) {
    const segs = result?.refine_sdxl?.[side + '_segments'] || [];
    const parts = segs.filter((s) => s.tags?.length).map((s) => s.tags.join(', '));
    return parts.join(', ');
  },

  copyText(text, evt) {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      const btn = evt?.target;
      if (!btn) return;
      const orig = btn.textContent;
      btn.textContent = 'copied';
      setTimeout(() => {
        btn.textContent = orig;
      }, 1100);
    });
  },
};

/** Wide vs portrait image handling (detail hero layout + card thumbs). */
(function () {
  "use strict";

  /** Wide only when clearly wider than 4:3 (square and 3:4 stay portrait). */
  const LANDSCAPE_MIN_RATIO = 4 / 3;

  function isWide(w, h) {
    return h > 0 && w / h > LANDSCAPE_MIN_RATIO;
  }

  function applyOrientation(img) {
    if (!img?.naturalWidth) return;
    const wide = isWide(img.naturalWidth, img.naturalHeight);
    img.classList.toggle("wide", wide);
    const layout = img.closest(".detail-layout");
    if (layout) {
      layout.classList.toggle("landscape", wide);
      layout.classList.toggle("portrait", !wide);
    }
  }

  function scan(root) {
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll("[data-orient-img]").forEach((img) => {
      if (img.complete && img.naturalWidth > 0) applyOrientation(img);
    });
  }

  window.detailHeroOrient = applyOrientation;

  function init() {
    scan(document);
    document.addEventListener(
      "load",
      (e) => {
        if (e.target?.matches?.("[data-orient-img]")) applyOrientation(e.target);
      },
      true
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

/** Grow <textarea> height to fit content (forms + readonly build output). */
(function () {
  "use strict";

  function minHeightPx(el) {
    const style = getComputedStyle(el);
    const lineHeight = parseFloat(style.lineHeight);
    const lh = Number.isFinite(lineHeight) ? lineHeight : 20;
    const pad =
      parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    const border =
      parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
    const rows = parseInt(el.getAttribute("rows"), 10);
    const rowCount = Number.isFinite(rows) && rows > 0 ? rows : 2;
    return Math.ceil(lh * rowCount + pad + border);
  }

  function isDisplayed(el) {
    return el.getClientRects().length > 0;
  }

  /** Measure scroll height even when the field sits in a hidden Alpine tab. */
  function contentHeight(el) {
    if (isDisplayed(el)) {
      el.style.overflowY = "hidden";
      el.style.height = "auto";
      return el.scrollHeight;
    }
    const style = getComputedStyle(el);
    const clone = el.cloneNode(true);
    clone.removeAttribute("id");
    clone.style.cssText = [
      "visibility:hidden",
      "position:absolute",
      "top:-9999px",
      "left:0",
      "height:auto",
      "min-height:0",
      "overflow:hidden",
      "display:block",
      "width:" + style.width,
    ].join(";");
    document.body.appendChild(clone);
    const h = clone.scrollHeight;
    clone.remove();
    return h;
  }

  function resizeTextarea(el) {
    if (!(el instanceof HTMLTextAreaElement)) return;
    if (el.dataset.noAutogrow !== undefined) return;
    const floor = minHeightPx(el);
    const h = Math.max(contentHeight(el), floor);
    el.style.overflowY = "hidden";
    el.style.height = h + "px";
  }

  function resizeAll(root) {
    if (root instanceof HTMLTextAreaElement) {
      resizeTextarea(root);
      return;
    }
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll("textarea").forEach(resizeTextarea);
  }

  function bindTextarea(el) {
    if (!(el instanceof HTMLTextAreaElement)) return;
    if (el.dataset.autoTextareaBound) return;
    el.dataset.autoTextareaBound = "1";
    el.addEventListener("input", () => resizeTextarea(el));
    resizeTextarea(el);
  }

  function scan(root) {
    if (root instanceof HTMLTextAreaElement) {
      bindTextarea(root);
      return;
    }
    if (!(root && root.querySelectorAll)) return;
    root.querySelectorAll("textarea").forEach(bindTextarea);
  }

  function scheduleResize(root) {
    requestAnimationFrame(() => requestAnimationFrame(() => resizeAll(root || document)));
  }

  function init() {
    scan(document);
    const obs = new MutationObserver((mutations) => {
      for (const m of mutations) {
        m.addedNodes.forEach((node) => {
          if (node.nodeType !== 1) return;
          scan(node);
        });
      }
    });
    obs.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("click", (e) => {
      if (e.target.closest(".tabs button, .video-lab-prompts-tab")) scheduleResize(document);
    });
    document.addEventListener("alpine:initialized", () => scheduleResize(document));
    window.addEventListener("resize", () => resizeAll(document));
    window.addEventListener("load", () => scheduleResize(document));
  }

  window.coomfyResizeTextareas = resizeAll;
  window.coomfyScheduleTextareaResize = scheduleResize;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

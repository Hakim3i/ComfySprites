/** Themed up/down controls for ``input[type=number]`` (replaces native spinners). */
(function () {
  "use strict";

  /* Spin markup from <template id="number-stepper-spin"> in base.html. */
  const SPIN_TEMPLATE = document.getElementById("number-stepper-spin");

  function shouldSkip(input) {
    if (!input || input.type !== "number") return true;
    if (input.closest(".number-stepper")) return true;
    if (input.closest(".seed-row")) return true;
    if (input.dataset.numberStepper === "skip") return true;
    return false;
  }

  function parseBound(raw) {
    if (raw === "" || raw == null) return null;
    const n = parseFloat(raw);
    return Number.isFinite(n) ? n : null;
  }

  function stepDecimals(step) {
    const parts = String(step).split(".");
    return parts.length > 1 ? parts[1].length : 0;
  }

  function stepInputValue(input, delta) {
    const step = parseFloat(input.step);
    const stepVal = Number.isFinite(step) && step > 0 ? step : 1;
    const min = parseBound(input.min);
    const max = parseBound(input.max);
    let v = parseBound(input.value);
    if (v === null) v = min !== null ? min : 0;
    const decimals = stepDecimals(stepVal);
    v = Number((v + delta * stepVal).toFixed(decimals));
    if (min !== null) v = Math.max(min, v);
    if (max !== null) v = Math.min(max, v);
    input.value = String(v);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function syncButtons(wrap, input) {
    const up = wrap.querySelector('[data-number-stepper="up"]');
    const down = wrap.querySelector('[data-number-stepper="down"]');
    if (!up || !down) return;
    const min = parseBound(input.min);
    const max = parseBound(input.max);
    const v = parseBound(input.value);
    const disabled = input.disabled;
    up.disabled =
      disabled || (max !== null && v !== null && v >= max);
    down.disabled =
      disabled || (min !== null && v !== null && v <= min);
  }

  function bindNumberStepper(wrap) {
    if (wrap.dataset.stepperBound === "1") return;
    if (wrap.dataset.stepper === "alpine") return;

    const input = wrap.querySelector('input[type="number"]');
    if (!input) return;

    input.classList.add("number-stepper-input");

    const up = wrap.querySelector('[data-number-stepper="up"]');
    const down = wrap.querySelector('[data-number-stepper="down"]');
    if (!up || !down) return;

    up.addEventListener("click", (e) => {
      e.preventDefault();
      stepInputValue(input, 1);
      syncButtons(wrap, input);
    });
    down.addEventListener("click", (e) => {
      e.preventDefault();
      stepInputValue(input, -1);
      syncButtons(wrap, input);
    });

    input.addEventListener("input", () => syncButtons(wrap, input));
    input.addEventListener("change", () => syncButtons(wrap, input));
    new MutationObserver(() => syncButtons(wrap, input)).observe(input, {
      attributes: true,
      attributeFilter: ["disabled", "value", "min", "max"],
    });

    wrap.dataset.stepperBound = "1";
    syncButtons(wrap, input);
  }

  function appendSpinMarkup(wrap) {
    if (!SPIN_TEMPLATE?.content) return;
    wrap.appendChild(SPIN_TEMPLATE.content.cloneNode(true));
  }

  function wrapNumberInput(input) {
    if (shouldSkip(input)) return;

    const wrap = document.createElement("div");
    wrap.className = "number-stepper";
    if (input.parentNode) {
      input.parentNode.insertBefore(wrap, input);
    }
    wrap.appendChild(input);
    input.classList.add("number-stepper-input");
    appendSpinMarkup(wrap);
    bindNumberStepper(wrap);
  }

  function scan(root) {
    const el = root && root.nodeType === 1 ? root : document;
    el.querySelectorAll(".number-stepper").forEach(bindNumberStepper);
    el.querySelectorAll('input[type="number"]').forEach((input) => {
      if (!shouldSkip(input)) wrapNumberInput(input);
    });
  }

  document.addEventListener("DOMContentLoaded", () => scan(document));
  document.addEventListener("alpine:initialized", () => scan(document));

  const mo = new MutationObserver((records) => {
    for (const rec of records) {
      rec.addedNodes.forEach((node) => {
        if (node.nodeType !== 1) return;
        if (node.matches?.('input[type="number"]')) wrapNumberInput(node);
        else scan(node);
      });
    }
  });
  if (document.body) {
    mo.observe(document.body, { childList: true, subtree: true });
  }
})();

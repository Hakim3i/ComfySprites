/** Act camera framing chips — click a selected radio again to clear that kind. */
(function () {
  "use strict";

  function framingRadio(target) {
    return target.closest?.(".view-picker .view-chip input[type='radio']");
  }

  document.addEventListener("pointerdown", (e) => {
    const input = framingRadio(e.target);
    if (!input) return;
    input.dataset.viewPickerWasChecked = input.checked ? "1" : "0";
  });

  document.addEventListener("click", (e) => {
    const input = framingRadio(e.target);
    if (!input) return;
    if (input.dataset.viewPickerWasChecked === "1") {
      input.checked = false;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
    delete input.dataset.viewPickerWasChecked;
  });
})();

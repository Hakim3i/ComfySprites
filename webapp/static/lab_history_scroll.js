/** Shared history list scroll helpers for Make and Video Lab. */
(function (global) {
  const LAB_HISTORY_BREAKPOINT_NARROW = 1100;

  function isLabHistoryNarrow(breakpoint) {
    return (
      typeof window !== 'undefined' && window.innerWidth <= breakpoint
    );
  }

  function labHistoryScrollMethods(
    breakpoint = LAB_HISTORY_BREAKPOINT_NARROW
  ) {
    return {
      historyScrollCanUp: false,
      historyScrollCanDown: false,

      historyListEl() {
        return this.$refs.historyList || null;
      },

      historyScrollStepPx() {
        const el = this.historyListEl();
        if (!el) return 80;
        const item = el.querySelector('li');
        if (!item) return 80;
        const style = getComputedStyle(el);
        const gap =
          parseFloat(style.rowGap || style.columnGap || style.gap) || 4;
        const narrow = isLabHistoryNarrow(breakpoint);
        return (narrow ? item.offsetWidth : item.offsetHeight) + gap;
      },

      updateHistoryScrollState() {
        const el = this.historyListEl();
        if (!el) {
          this.historyScrollCanUp = false;
          this.historyScrollCanDown = false;
          return;
        }
        const narrow = isLabHistoryNarrow(breakpoint);
        const pos = narrow ? el.scrollLeft : el.scrollTop;
        const maxScroll = narrow
          ? el.scrollWidth - el.clientWidth
          : el.scrollHeight - el.clientHeight;
        if (maxScroll <= 1) {
          this.historyScrollCanUp = false;
          this.historyScrollCanDown = false;
          return;
        }
        this.historyScrollCanUp = pos > 1;
        this.historyScrollCanDown = pos < maxScroll - 1;
      },

      onHistoryWheel(event) {
        const el = this.historyListEl();
        if (!el) return;
        event.preventDefault();
        const narrow = isLabHistoryNarrow(breakpoint);
        if (narrow) {
          el.scrollLeft += event.deltaY;
        } else {
          el.scrollTop += event.deltaY;
        }
        this.updateHistoryScrollState();
      },

      scrollHistoryBy(direction) {
        const el = this.historyListEl();
        if (!el) return;
        const step = direction * this.historyScrollStepPx();
        const narrow = isLabHistoryNarrow(breakpoint);
        if (narrow) {
          el.scrollLeft += step;
        } else {
          el.scrollTop += step;
        }
        this.updateHistoryScrollState();
      },
    };
  }

  global.LAB_HISTORY_BREAKPOINT_NARROW = LAB_HISTORY_BREAKPOINT_NARROW;
  global.labHistoryScrollMethods = labHistoryScrollMethods;
})(window);

// Clamp dialog windows to stay within the viewport.
(function () {
  const MARGIN = 12;          // minimum margin from viewport edges
  const HEADER_HEIGHT = 48;   // reserve space so header stays visible
  const MIN_WIDTH = 120;      // minimal width allowance when clamping left

  function clampDialog(el) {
    if (!el || !el.getBoundingClientRect) return;
    const rect = el.getBoundingClientRect();

    // Use inline top/left if present, else fall back to current rect
    let top = parseFloat(el.style.top) || rect.top;
    let left = parseFloat(el.style.left) || rect.left;

    const maxTop = window.innerHeight - HEADER_HEIGHT;
    const maxLeft = window.innerWidth - MIN_WIDTH;

    // Clamp values
    top = Math.min(Math.max(top, MARGIN), Math.max(MARGIN, maxTop));
    left = Math.min(Math.max(left, MARGIN), Math.max(MARGIN, maxLeft));

    // Apply only if changed to avoid layout thrash
    if (el.style.top !== `${top}px`) el.style.top = `${top}px`;
    if (el.style.left !== `${left}px`) el.style.left = `${left}px`;
  }

  function clampAll() {
    document.querySelectorAll('.dialog-card').forEach(clampDialog);
  }

  // Initial clamp and on resize
  window.addEventListener('load', clampAll);
  window.addEventListener('resize', clampAll);

  // Observe style changes (e.g., when a dialog is shown/restored)
  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.type === 'attributes' && m.attributeName === 'style') {
        const el = m.target;
        if (el.classList && el.classList.contains('dialog-card')) {
          clampDialog(el);
        }
      }
      (m.addedNodes || []).forEach((node) => {
        if (node.nodeType === 1 && node.classList && node.classList.contains('dialog-card')) {
          clampDialog(node);
        }
      });
    }
  });

  observer.observe(document.body, {
    attributes: true,
    subtree: true,
    attributeFilter: ['style'],
    childList: true,
  });
})();

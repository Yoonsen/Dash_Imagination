// Clamp dialog windows within the viewport (lightweight, no observers).
(function () {
  const MARGIN = 12;          // minimum margin from viewport edges
  const HEADER_HEIGHT = 48;   // reserve space so header stays visible
  const MIN_WIDTH = 160;      // minimal width allowance when clamping left

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

    // Apply only if changed
    if (el.style.top !== `${top}px`) el.style.top = `${top}px`;
    if (el.style.left !== `${left}px`) el.style.left = `${left}px`;
  }

  function clampAll() {
    document.querySelectorAll('.dialog-card').forEach(clampDialog);
  }

  // Initial clamp and on resize
  window.addEventListener('load', clampAll);
  window.addEventListener('resize', clampAll);
})();

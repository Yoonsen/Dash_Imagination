// Minimal z-index bump: bring clicked dialog/modal to front. No observers.
(function () {
  let zCounter = 2000;

  function bump(el) {
    if (!el || !el.style) return;
    zCounter += 1;
    el.style.zIndex = zCounter;
  }

  function handle(evt) {
    const card = evt.target.closest && evt.target.closest('.dialog-card');
    if (card) bump(card);
    const modal = evt.target.closest && evt.target.closest('#image-gallery-modal');
    if (modal) bump(modal);
  }

  document.addEventListener('mousedown', handle, true);
  document.addEventListener('touchstart', handle, true);
})();

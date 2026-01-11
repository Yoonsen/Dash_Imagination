// Bring clicked dialog cards to front by incrementing z-index.
(function () {
  let zCounter = 2000;

  function bringToFront(el) {
    if (!el || !el.style) return;
    zCounter += 1;
    el.style.zIndex = zCounter;
  }

  function handleEvent(evt) {
    const card = evt.target.closest && evt.target.closest('.dialog-card');
    if (card) {
      bringToFront(card);
    }
    const modal = evt.target.closest && evt.target.closest('#image-gallery-modal');
    if (modal) {
      bringToFront(modal);
    }
  }

  document.addEventListener('mousedown', handleEvent, true);
  document.addEventListener('touchstart', handleEvent, true);

  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.type === 'attributes' && m.attributeName === 'style') {
        const el = m.target;
        if (el.classList && el.classList.contains('dialog-card')) {
          const disp = window.getComputedStyle(el).display;
          if (disp && disp !== 'none') {
            bringToFront(el);
          }
        }
        if (el.id === 'image-gallery-modal') {
            const isOpen = !el.classList.contains('modal') || el.classList.contains('show');
            if (isOpen) bringToFront(el);
        }
      }
      (m.addedNodes || []).forEach((node) => {
        if (node.nodeType === 1 && node.classList) {
          if (node.classList.contains('dialog-card')) bringToFront(node);
          if (node.id === 'image-gallery-modal') bringToFront(node);
        }
      });
    }
  });

  observer.observe(document.body, {
    attributes: true,
    subtree: true,
    attributeFilter: ['style', 'class'],
    childList: true,
  });
})();

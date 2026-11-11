// Small enhancements; every page works without this file.

// Filters: apply as soon as a radio changes, collapse on narrow screens.
document.querySelectorAll('[data-autosubmit]').forEach((form) => {
  form.addEventListener('change', (e) => {
    if (e.target.type === 'radio') form.requestSubmit();
  });
});
document.querySelectorAll('[data-submit-on-change]').forEach((el) => {
  el.addEventListener('change', () => el.form.requestSubmit());
});
const filters = document.querySelector('[data-filters]');
if (filters && window.matchMedia('(max-width: 860px)').matches) filters.open = false;

// Gallery thumbnails
const mainImage = document.getElementById('gallery-main');
document.querySelectorAll('[data-thumb]').forEach((btn) => {
  btn.addEventListener('click', () => {
    mainImage.src = btn.dataset.thumb;
    document.querySelectorAll('[data-thumb]').forEach((b) => b.removeAttribute('aria-current'));
    btn.setAttribute('aria-current', 'true');
  });
});

// Tabs (Details / Review)
document.querySelectorAll('[data-tabs]').forEach((root) => {
  const tabs = [...root.querySelectorAll('[role=tab]')];
  const show = (id) => {
    tabs.forEach((tab) => {
      const on = tab.getAttribute('aria-controls') === id;
      tab.setAttribute('aria-selected', on);
      tab.tabIndex = on ? 0 : -1;
      document.getElementById(tab.getAttribute('aria-controls')).hidden = !on;
    });
  };
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => show(tab.getAttribute('aria-controls')));
    tab.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
      next.focus();
      next.click();
    });
  });
  document.querySelectorAll('[data-open-tab]').forEach((link) => {
    link.addEventListener('click', () => show(link.dataset.openTab));
  });
  show(location.hash === '#review' ? 'review' : 'details');
});

// Review dialog
document.querySelectorAll('[data-open-dialog]').forEach((btn) => {
  btn.addEventListener('click', () => document.getElementById(btn.dataset.openDialog).showModal());
});
document.querySelectorAll('dialog').forEach((dialog) => {
  dialog.querySelectorAll('[data-close-dialog]').forEach((b) => b.addEventListener('click', () => dialog.close()));
  dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });
});

// Some product photos on the API point to files that no longer exist.
const useFallback = (img) => {
  if (img.dataset.fallback) return;
  const thumbs = img.closest(".gallery__thumbs");
  if (thumbs) { thumbs.remove(); return; }
  img.dataset.fallback = "1";
  img.src = window.NO_IMAGE;
  img.classList.add("noimage");
};
document.querySelectorAll("main img").forEach((img) => {
  if (img.complete && img.naturalWidth === 0 && img.getAttribute("src")) useFallback(img);
  img.addEventListener("error", () => useFallback(img));
});

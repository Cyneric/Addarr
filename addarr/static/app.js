/**
 * @file app.js
 * @author Christian Blank
 * Created Date: 2026-09-11
 * Description: Service tabs, mobile navigation and form controls for the web interface.
 */
"use strict";

/** Ask before removing or cancelling a request; the server still validates every action. */
document.addEventListener("submit", event => {
  const message = event.target.dataset.confirm;
  if (message && !window.confirm(message)) event.preventDefault();
});

const menu = document.querySelector(".menu-toggle");
const scrim = document.querySelector(".nav-scrim");
const sidebar = document.querySelector(".sidebar");
const servicePanels = document.querySelector(".service-panels");
/**
 * Show the service named by the URL fragment, falling back to the server-selected tab.
 * Updates aria-current alongside panel visibility so navigation stays accessible.
 * @returns {void}
 */
function selectService() {
  if (!servicePanels) return;
  const hash = window.location.hash.slice(1);
  const kind = ["radarr", "sonarr", "lidarr"].includes(hash) ? hash : servicePanels.dataset.activeService;
  servicePanels.querySelectorAll(".service-config").forEach(panel => { panel.hidden = panel.id !== kind; });
  document.querySelectorAll(".service-picker a").forEach(link => {
    if (link.dataset.service === kind) link.setAttribute("aria-current", "true");
    else link.removeAttribute("aria-current");
  });
}
selectService();
window.addEventListener("hashchange", selectService);
/**
 * Close mobile navigation and reset its overlay and expanded state.
 * Callers restore focus when closing from the keyboard or overlay.
 * @returns {void}
 */
function closeMenu() {
  document.body.classList.remove("nav-open");
  menu?.setAttribute("aria-expanded", "false");
  if (scrim) scrim.hidden = true;
}
menu?.addEventListener("click", () => {
  const open = !document.body.classList.contains("nav-open");
  document.body.classList.toggle("nav-open", open);
  menu.setAttribute("aria-expanded", String(open));
  scrim.hidden = !open;
  if (open) sidebar.querySelector("nav a")?.focus();
});
scrim?.addEventListener("click", () => { closeMenu(); menu?.focus(); });
document.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    if (document.body.classList.contains("nav-open")) { closeMenu(); menu?.focus(); }
    document.querySelectorAll(".language[open]").forEach(item => {
      item.open = false;
      item.querySelector("summary").focus();
    });
  }
  if (event.key === "Tab" && document.body.classList.contains("nav-open")) {
    // Keep keyboard focus inside the open mobile navigation until it is dismissed.
    const focusable = [...sidebar.querySelectorAll("a, button")];
    const first = focusable[0], last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
});
window.matchMedia("(max-width: 760px)").addEventListener("change", closeMenu);
document.querySelectorAll(".password-toggle").forEach(button => {
  button.addEventListener("click", () => {
    const input = button.parentElement.querySelector("input");
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    button.setAttribute("aria-pressed", String(show));
  });
});
document.addEventListener("click", event => {
  document.querySelectorAll(".language[open]").forEach(item => {
    if (!item.contains(event.target)) item.open = false;
  });
});


/** Show one update action and keep this document alive while the container restarts. */
(() => {
  const panels = [...document.querySelectorAll('[data-update-view]')];
  if (!panels.length) return;
  let posting = false;
  let startFailed = false;
  let timer;
  let polling = false;
  let generation = 0;
  let busy = panels.some(panel => panel.dataset.state === 'updating');

  /** Apply the server's display state without replacing focused controls or exposing job internals. */
  function render(view) {
    busy = view.state === 'updating';
    if (busy || view.state === 'updated') startFailed = false;
    for (const panel of panels) {
      const failed = startFailed && !busy;
      panel.hidden = panel.dataset.standalone !== 'true' && !view.visible && !failed;
      panel.dataset.state = failed ? 'error' : view.state;
      const message = panel.querySelector('.update-message');
      const text = failed ? panel.dataset.failed : view.message;
      if (message.textContent !== text) message.textContent = text;
      const form = panel.querySelector('[data-update-install]');
      form.hidden = !view.can_install;
      form.querySelector('button').disabled = !view.can_install || posting;
      form.elements.revision.value = view.revision || '';
      panel.querySelector('[data-update-details]').hidden = !view.details && !failed;
    }
  }

  /** Poll quickly during an update; a lost connection leaves the last confirmed state visible. */
  async function poll() {
    if (polling || posting) return;
    polling = true;
    const startedAt = generation;
    try {
      const response = await fetch('/updates/status', {cache: 'no-store', signal: AbortSignal.timeout(10000)});
      if (response.redirected) { window.location.assign('/login'); return; }
      if (response.ok && response.headers.get('content-type')?.includes('application/json')) {
        const data = await response.json();
        if (!posting && startedAt === generation) render(data.view);
        const detail = document.querySelector('[data-update-detail]');
        if (detail && data.detail_message) detail.textContent = data.detail_message;
      }
    } catch (_) {
      // Restarting the server is expected; keep polling rather than navigating to an error page.
    } finally {
      polling = false;
      window.clearTimeout(timer);
      timer = window.setTimeout(poll, busy ? 3000 : 15000);
    }
  }

  document.addEventListener('submit', async event => {
    const form = event.target;
    if (!form.matches('[data-update-install]')) return;
    event.preventDefault();
    if (posting || busy || form.querySelector('button').disabled) return;
    const data = new FormData(form);
    posting = true;
    generation += 1;
    startFailed = false;
    window.clearTimeout(timer);
    render({state: 'updating', message: panels[0].dataset.busy, can_install: false, visible: true, details: false});
    try {
      const response = await fetch(form.action, {
        method: 'POST', body: data, headers: {'Accept': 'application/json'}, signal: AbortSignal.timeout(60000)
      });
      if (response.redirected) { window.location.assign('/login'); return; }
      if (!response.ok) startFailed = true;
    } catch (_) {
      // The request may have been accepted before the connection closed. Read status before retrying.
    } finally {
      posting = false;
      await poll();
    }
  });
  poll();
})();

/** Refresh request cards without interrupting keyboard focus or a form submission. */
(() => {
  if (!document.querySelector('.request-list')) return;
  let submitting = false;
  document.addEventListener('submit', event => { if (!event.defaultPrevented) submitting = true; });
  window.setInterval(async () => {
    const list = document.querySelector('.request-list');
    if (!list || document.hidden || submitting || list.contains(document.activeElement)) return;
    try {
      const response = await fetch(window.location.href, {cache: 'no-store'});
      if (!response.ok || response.redirected) return;
      const documentCopy = new DOMParser().parseFromString(await response.text(), 'text/html');
      const next = documentCopy.querySelector('.request-list');
      if (next && !submitting && !list.contains(document.activeElement)) list.replaceWith(next);
    } catch (_) {
      // A later poll will recover; the last confirmed status remains visible.
    }
  }, 15000);
})();

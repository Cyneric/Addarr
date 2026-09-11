/**
 * @file app.js
 * @author Christian Blank
 * Created Date: 2026-09-11
 * Description: Service tabs, mobile navigation and form controls for the web interface.
 */
"use strict";

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

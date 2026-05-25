/* VidFlow — utils.js: shared state and utility functions */

/* ── Shared State ─────────────────────────────────────────────────────────── */
var currentJobId   = null;
var pollTimer      = null;
var selectedKey    = '1';
var cfgKey         = '1';
var currentTheme   = 'dark';
var detectedInfo   = null;
var infoDebounce   = null;

/* ── Toast ────────────────────────────────────────────────────────────────── */
function showToast(message, type) {
  type = type || 'success';
  var container = document.getElementById('toast-container');
  if (!container) return;
  var icons = { success: 'check-circle-2', error: 'alert-circle', info: 'info' };
  var el = document.createElement('div');
  el.className = 'toast toast-' + type;
  el.innerHTML = '<i data-lucide="' + (icons[type] || 'info') + '"></i><span>' + message + '</span>';
  container.appendChild(el);
  if (window.lucide) lucide.createIcons({ nodes: [el] });
  setTimeout(function () {
    el.classList.add('toast-out');
    setTimeout(function () { el.remove(); }, 400);
  }, 4000);
}

/* ── HTML escape ──────────────────────────────────────────────────────────── */
function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* ── YouTube search fallback ──────────────────────────────────────────────── */
function historySearch(encodedTitle) {
  window.open('https://www.youtube.com/results?search_query=' + encodedTitle, '_blank');
}

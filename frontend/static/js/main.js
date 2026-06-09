/* VidFlow — main.js: init, UI helpers, settings, navbar, FAQ */

/* ── Entry point ──────────────────────────────────────────────────────────── */
function initVidFlow() {
  selectedKey  = window.DEFAULT_QUALITY  || '1';
  cfgKey       = window.DEFAULT_QUALITY  || '1';
  currentTheme = window.CURRENT_THEME    || 'dark';

  refreshThemeButtons(currentTheme);
  renderHistory();
  setupScrollReveal();
  setupNavbarScroll();

  var urlEl = document.getElementById('url');
  if (urlEl) {
    urlEl.addEventListener('input',   function (e) { scheduleDetect(e.target.value.trim()); });
    urlEl.addEventListener('paste',   function () { setTimeout(function () { scheduleDetect(document.getElementById('url').value.trim()); }, 0); });
    urlEl.addEventListener('keydown', function (e) { if (e.key === 'Enter') startDownload(); });
  }

  var dlPlaylist = document.getElementById('dl-playlist');
  if (dlPlaylist) {
    dlPlaylist.addEventListener('change', function () {
      if (detectedInfo) updateDlButton(detectedInfo.type === 'playlist', detectedInfo.count);
    });
  }
}

/* ── Scroll reveal ────────────────────────────────────────────────────────── */
function setupScrollReveal() {
  var obs = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        obs.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });
  document.querySelectorAll('.reveal').forEach(function (el) { obs.observe(el); });
}

/* ── Navbar scroll ────────────────────────────────────────────────────────── */
function setupNavbarScroll() {
  var navbar = document.getElementById('navbar');
  if (!navbar) return;
  window.addEventListener('scroll', function () {
    navbar.style.borderBottomColor = window.scrollY > 10
      ? 'var(--border)'
      : 'transparent';
  }, { passive: true });
}

/* ── Mobile menu ──────────────────────────────────────────────────────────── */
function toggleMenu() {
  var links = document.getElementById('nav-links');
  var ham   = document.getElementById('hamburger');
  if (links) links.classList.toggle('open');
  if (ham)   ham.classList.toggle('open');
}

/* ── User dropdown ────────────────────────────────────────────────────────── */
function toggleUserMenu() {
  var dropdown = document.getElementById('nav-user-dropdown');
  var btn      = document.getElementById('nav-user-btn');
  if (!dropdown) return;
  var isOpen = dropdown.classList.toggle('show');
  if (btn) btn.classList.toggle('open', isOpen);
}

function closeUserMenu() {
  var dropdown = document.getElementById('nav-user-dropdown');
  var btn      = document.getElementById('nav-user-btn');
  if (dropdown) dropdown.classList.remove('show');
  if (btn)      btn.classList.remove('open');
}

document.addEventListener('click', function (e) {
  var navUser = document.getElementById('nav-user');
  if (navUser && !navUser.contains(e.target)) closeUserMenu();
});

/* ── Quality pills ────────────────────────────────────────────────────────── */
function selectQuality(btn) {
  document.querySelectorAll('#quality-grid .q-pill').forEach(function (b) { b.classList.remove('active'); });
  btn.classList.add('active');
  selectedKey = btn.dataset.key;
}

/* ── Settings modal ───────────────────────────────────────────────────────── */
function openSettings() {
  refreshThemeButtons(currentTheme);
  var overlay = document.getElementById('overlay');
  if (overlay) overlay.classList.add('show');
}
function closeSettings() {
  var overlay = document.getElementById('overlay');
  if (overlay) overlay.classList.remove('show');
}
function closeIfBackdrop(e) {
  var overlay = document.getElementById('overlay');
  if (e.target === overlay) closeSettings();
}
function setTheme(t) {
  currentTheme = t;
  document.documentElement.setAttribute('data-theme', t);
  refreshThemeButtons(t);
}
function refreshThemeButtons(t) {
  var dark  = document.getElementById('theme-dark');
  var light = document.getElementById('theme-light');
  if (dark)  dark.classList.toggle('active',  t === 'dark');
  if (light) light.classList.toggle('active', t === 'light');
}
function setCfgQuality(btn) {
  document.querySelectorAll('#cfg-quality-grid .q-pill').forEach(function (b) { b.classList.remove('active'); });
  btn.classList.add('active');
  cfgKey = btn.dataset.key;
}
async function saveSettings() {
  var dirEl = document.getElementById('cfg-dir');
  var dir   = dirEl ? dirEl.value.trim() : '';
  var note  = document.getElementById('save-note');
  if (note) note.textContent = '';
  try {
    var res  = await csrfFetch('/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme: currentTheme, default_quality: cfgKey, download_dir: dir }),
    });
    var data = await res.json();
    if (data.error) throw new Error(data.error);
    selectedKey = cfgKey;
    document.querySelectorAll('#quality-grid .q-pill').forEach(function (b) {
      b.classList.toggle('active', b.dataset.key === cfgKey);
    });
    if (note) { note.style.color = 'var(--success)'; note.textContent = '✓ Settings saved'; }
    showToast('Settings saved', 'success');
    setTimeout(closeSettings, 1200);
  } catch (err) {
    if (note) { note.style.color = 'var(--error)'; note.textContent = 'Error: ' + err.message; }
  }
}

/* ── FAQ accordion ────────────────────────────────────────────────────────── */
function toggleFaq(btn) {
  var item   = btn.closest('.faq-item');
  var isOpen = item.classList.contains('open');
  document.querySelectorAll('.faq-item.open').forEach(function (i) { i.classList.remove('open'); });
  if (!isOpen) item.classList.add('open');
}

/* ── UI helpers ───────────────────────────────────────────────────────────── */
var BADGES = {
  starting:    ['badge-starting',    'Starting…'],
  downloading: ['badge-downloading', 'Downloading'],
  processing:  ['badge-processing',  'Processing'],
  done:        ['badge-done',        'Complete'],
  error:       ['badge-error',       'Error'],
};

function setBadge(s) {
  var pair  = BADGES[s] || ['badge-starting', s];
  var cls   = pair[0], label = pair[1];
  var el    = document.getElementById('badge');
  if (el) el.className = 'badge ' + cls;
  var textEl = document.getElementById('badge-text');
  if (textEl) textEl.textContent = label;
}
function setBar(pct, done) {
  var b = document.getElementById('bar');
  if (!b) return;
  b.style.width = pct + '%';
  b.classList.toggle('complete', done);
}
function indeterminate(on) {
  var b = document.getElementById('bar');
  if (b) b.classList.toggle('indeterminate', on);
}
function setText(id, v) {
  var el = document.getElementById(id);
  if (el) el.textContent = v;
}
function setBtn(off) {
  var btn = document.getElementById('dl-btn');
  if (btn) btn.disabled = off;
}
function showError(msg) {
  setBadge('error');
  var errText = document.getElementById('err-text');
  var msgErr  = document.getElementById('msg-error');
  if (errText) errText.textContent = msg;
  if (msgErr)  msgErr.style.display = 'flex';
}

function resetProgress(isPlaylist, count) {
  setBadge('starting');
  setText('vid-title', '');
  setText('s-speed', '—');
  setText('s-eta', '—');
  setText('s-size', '—');
  setText('s-pct', '0%');
  indeterminate(true);
  setBar(0, false);

  var bar        = document.getElementById('bar');
  var msgDone    = document.getElementById('msg-done');
  var msgError   = document.getElementById('msg-error');
  var doneText   = document.getElementById('done-text');
  var doneAction = document.getElementById('done-action');
  var plCounter  = document.getElementById('pl-counter');
  var overallWrap= document.getElementById('overall-wrap');
  var barLabel   = document.getElementById('bar-label');

  if (bar)        bar.classList.remove('complete');
  if (msgDone)    msgDone.style.display  = 'none';
  if (msgError)   msgError.style.display = 'none';
  if (doneText)   doneText.textContent   = 'Downloaded successfully!';
  if (doneAction) doneAction.style.display = '';

  if (isPlaylist) {
    if (plCounter)  plCounter.classList.remove('show');
    setText('pl-index', '1');
    setText('pl-total', count > 0 ? String(count) : '?');
    if (overallWrap) { overallWrap.classList.add('show'); setOverallBar(0); }
    if (barLabel)    barLabel.style.display = 'block';
  } else {
    if (plCounter)   plCounter.classList.remove('show');
    if (overallWrap) overallWrap.classList.remove('show');
    if (barLabel)    barLabel.style.display = 'none';
  }
}

function shake(el) {
  if (!el) return;
  el.style.animation = 'none';
  el.offsetHeight;
  el.style.animation = 'shake .35s ease';
}

/* VidFlow — script.js */

/* ── State ────────────────────────────────────────────────────────────────── */
let currentJobId   = null;
let pollTimer      = null;
let selectedKey    = '1';
let cfgKey         = '1';
let currentTheme   = 'dark';
let detectedInfo   = null;
let infoDebounce   = null;

/* ── Entry point ──────────────────────────────────────────────────────────── */
function initVidFlow() {
  selectedKey  = window.DEFAULT_QUALITY  || '1';
  cfgKey       = window.DEFAULT_QUALITY  || '1';
  currentTheme = window.CURRENT_THEME    || 'dark';

  refreshThemeButtons(currentTheme);
  renderHistory();
  setupScrollReveal();
  setupNavbarScroll();

  const urlEl = document.getElementById('url');
  if (urlEl) {
    urlEl.addEventListener('input',   e => scheduleDetect(e.target.value.trim()));
    urlEl.addEventListener('paste',   () => setTimeout(() => scheduleDetect(document.getElementById('url').value.trim()), 0));
    urlEl.addEventListener('keydown', e => { if (e.key === 'Enter') startDownload(); });
  }

  const dlPlaylist = document.getElementById('dl-playlist');
  if (dlPlaylist) {
    dlPlaylist.addEventListener('change', () => {
      if (detectedInfo) updateDlButton(detectedInfo.type === 'playlist', detectedInfo.count);
    });
  }
}

/* ── Scroll reveal ────────────────────────────────────────────────────────── */
function setupScrollReveal() {
  const obs = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        obs.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });
  document.querySelectorAll('.reveal').forEach(el => obs.observe(el));
}

/* ── Navbar scroll ────────────────────────────────────────────────────────── */
function setupNavbarScroll() {
  const navbar = document.getElementById('navbar');
  if (!navbar) return;
  window.addEventListener('scroll', () => {
    navbar.style.borderBottomColor = window.scrollY > 10
      ? 'var(--border)'
      : 'transparent';
  }, { passive: true });
}

/* ── Mobile menu ──────────────────────────────────────────────────────────── */
function toggleMenu() {
  const links = document.getElementById('nav-links');
  const ham   = document.getElementById('hamburger');
  if (links) links.classList.toggle('open');
  if (ham)   ham.classList.toggle('open');
}

/* ── User dropdown (auth) ─────────────────────────────────────────────────── */
function toggleUserMenu() {
  const dropdown = document.getElementById('nav-user-dropdown');
  const btn      = document.getElementById('nav-user-btn');
  if (!dropdown) return;
  const isOpen = dropdown.classList.toggle('show');
  if (btn) btn.classList.toggle('open', isOpen);
}

function closeUserMenu() {
  const dropdown = document.getElementById('nav-user-dropdown');
  const btn      = document.getElementById('nav-user-btn');
  if (dropdown) dropdown.classList.remove('show');
  if (btn)      btn.classList.remove('open');
}

// Close dropdown when clicking anywhere outside the nav-user element
document.addEventListener('click', function (e) {
  const navUser = document.getElementById('nav-user');
  if (navUser && !navUser.contains(e.target)) closeUserMenu();
});

/* ── Quality pills ────────────────────────────────────────────────────────── */
function selectQuality(btn) {
  document.querySelectorAll('#quality-grid .q-pill').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  selectedKey = btn.dataset.key;
}

/* ── URL info detection ───────────────────────────────────────────────────── */
function scheduleDetect(url) {
  clearTimeout(infoDebounce);
  if (!url) { hideInfo(); return; }
  showInfoLoading();
  infoDebounce = setTimeout(() => detectInfo(url), 700);
}

function showInfoLoading() {
  const strip = document.getElementById('info-strip');
  if (strip) strip.classList.add('show');
  const loading = document.getElementById('info-loading');
  if (loading) loading.style.display = 'flex';
  const content = document.getElementById('info-content');
  if (content) content.style.display = 'none';
}

function hideInfo() {
  const strip = document.getElementById('info-strip');
  if (strip) strip.classList.remove('show');
  detectedInfo = null;
  updateDlButton(false, 0);
}

async function detectInfo(url) {
  try {
    const res  = await fetch('/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (data.error) { hideInfo(); return; }
    detectedInfo = data;
    renderInfo(data);
  } catch (_) {
    hideInfo();
  }
}

function renderInfo(d) {
  const loading = document.getElementById('info-loading');
  const content = document.getElementById('info-content');
  if (loading) loading.style.display = 'none';
  if (content) content.style.display = 'block';

  const isPlaylist = d.type === 'playlist';

  // Thumbnail
  const thumbRow = document.getElementById('info-thumb-row');
  const thumbImg = document.getElementById('info-thumb');
  if (thumbRow && thumbImg) {
    if (!isPlaylist && d.thumbnail) {
      thumbImg.src     = d.thumbnail;
      thumbImg.onerror = () => { thumbRow.style.display = 'none'; };
      thumbImg.onload  = () => { thumbRow.style.display = 'block'; };
    } else if (!isPlaylist) {
      const vid = extractVideoId(document.getElementById('url').value);
      if (vid) {
        thumbImg.src     = `https://img.youtube.com/vi/${vid}/mqdefault.jpg`;
        thumbImg.onerror = () => { thumbRow.style.display = 'none'; };
        thumbImg.onload  = () => { thumbRow.style.display = 'block'; };
      } else {
        thumbRow.style.display = 'none';
      }
    } else {
      thumbRow.style.display = 'none';
    }
  }

  // Type badge
  const badge = document.getElementById('info-type-badge');
  if (badge) {
    badge.textContent = isPlaylist ? '▶ Playlist' : '▶ Video';
    badge.className   = 'info-type-badge ' + (isPlaylist ? 'badge-playlist' : 'badge-video');
  }

  // Title
  const titleEl = document.getElementById('info-title');
  if (titleEl) titleEl.textContent = d.title || 'Unknown';

  // Sub-line
  let sub = d.uploader || '';
  if (isPlaylist)     sub += (sub ? ' · ' : '') + d.count + ' videos';
  else if (d.duration) {
    const m = Math.floor(d.duration / 60), s = d.duration % 60;
    sub += (sub ? ' · ' : '') + m + ':' + String(s).padStart(2, '0');
  }
  const subEl = document.getElementById('info-sub');
  if (subEl) subEl.textContent = sub;

  // Playlist toggle
  const toggle = document.getElementById('pl-toggle-wrap');
  if (toggle) toggle.style.display = isPlaylist ? 'flex' : 'none';

  updateDlButton(isPlaylist, d.count);
}

function updateDlButton(isPlaylist, count) {
  const btn  = document.getElementById('dl-btn-text');
  const dlEl = document.getElementById('dl-playlist');
  if (!btn) return;
  const dlAll = isPlaylist && dlEl && dlEl.checked;
  if (dlAll)        btn.textContent = `Download All ${count > 0 ? '(' + count + ')' : ''}`.trim();
  else if (isPlaylist) btn.textContent = 'Download Video';
  else              btn.textContent = 'Download';
}

function extractVideoId(url) {
  const m = url.match(/[?&]v=([^&#]{11})/) || url.match(/youtu\.be\/([^?&#]{11})/);
  return m ? m[1] : null;
}

/* ── Start download ───────────────────────────────────────────────────────── */
async function startDownload() {
  const urlEl = document.getElementById('url');
  const url   = urlEl ? urlEl.value.trim() : '';
  if (!url) { if (urlEl) shake(urlEl.closest('.search-bar') || urlEl); return; }

  const dlEl          = document.getElementById('dl-playlist');
  const isPlaylist    = detectedInfo && detectedInfo.type === 'playlist' && dlEl && dlEl.checked;
  const playlistCount = isPlaylist ? (detectedInfo.count || 0) : 0;

  currentJobId = null;
  clearTimeout(pollTimer);
  resetProgress(isPlaylist, playlistCount);

  const progCard = document.getElementById('prog-card');
  if (progCard) {
    progCard.classList.add('show');
    setTimeout(() => progCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100);
  }
  setBtn(true);

  try {
    const res  = await fetch('/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, quality: selectedKey, is_playlist: isPlaylist, playlist_count: playlistCount }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    currentJobId = data.job_id;
    schedulePoll();
  } catch (err) {
    showError(err.message);
    setBtn(false);
  }
}

/* ── Polling ──────────────────────────────────────────────────────────────── */
function schedulePoll() { pollTimer = setTimeout(doPoll, 600); }

async function doPoll() {
  if (!currentJobId) return;
  try {
    const data = await fetch('/progress/' + currentJobId).then(r => r.json());
    applyUpdate(data);
    if (data.status !== 'done' && data.status !== 'error') schedulePoll();
  } catch (_) {
    schedulePoll();
  }
}

/* ── Apply update ─────────────────────────────────────────────────────────── */
function applyUpdate(d) {
  setBadge(d.status);
  const isPlaylist = d.is_playlist;

  const vidTitle = document.getElementById('vid-title');
  if (d.title && vidTitle) vidTitle.textContent = d.title;

  if (d.status === 'starting') {
    indeterminate(true);

  } else if (d.status === 'downloading') {
    indeterminate(false);
    setBar(d.percent || 0, false);
    setText('s-speed', d.speed || '—');
    setText('s-eta',   d.eta   || '—');
    setText('s-size',  d.size  || '—');
    setText('s-pct',   (d.percent || 0).toFixed(1) + '%');

    if (isPlaylist) {
      const idx   = d.playlist_index || 0;
      const total = d.playlist_count || 0;
      if (idx) {
        setText('pl-index', idx);
        if (total) setText('pl-total', total);
        const plCounter = document.getElementById('pl-counter');
        if (plCounter) plCounter.classList.add('show');
      }
      setOverallBar(d.overall_percent || 0);
    }

  } else if (d.status === 'processing') {
    indeterminate(true);
    setText('s-pct', '…');

  } else if (d.status === 'done') {
    indeterminate(false);
    setBar(100, true);
    setText('s-pct', '100%');

    if (isPlaylist) {
      setOverallBar(100);
      const files = d.files || [];
      const total = d.playlist_count || files.length;
      const doneText = document.getElementById('done-text');
      if (doneText) doneText.textContent = `Playlist downloaded — ${files.length} of ${total} videos saved`;
      const doneAction = document.getElementById('done-action');
      if (doneAction) doneAction.style.display = 'none';
    }

    const msgDone = document.getElementById('msg-done');
    if (msgDone) msgDone.style.display = 'flex';
    setBtn(false);

    // Save to history
    const qPill = document.querySelector('#quality-grid .q-pill.active');
    const qName = qPill ? qPill.textContent.trim() : '';
    const title = (detectedInfo && detectedInfo.title) ? detectedInfo.title : (d.title || 'Unknown');
    saveToHistory(title, qName);
    showToast('Download complete!', 'success');

    if (!isPlaylist) triggerDownload(currentJobId);

    // Bump the stat counters live so the user sees the update without a reload
    if (window.USER_LOGGED_IN) {
      const incEl = id => {
        const el = document.getElementById(id);
        if (el) el.textContent = (parseInt(el.textContent, 10) || 0) + 1;
      };
      incEl('stat-total');
      incEl('stat-month');
    }

  } else if (d.status === 'error') {
    indeterminate(false);
    showError(d.error || 'Download failed.');
    showToast('Download failed', 'error');
    setBtn(false);
  }
}

function setOverallBar(pct) {
  const bar = document.getElementById('overall-bar');
  if (bar) bar.style.width = pct + '%';
}

/* ── Trigger file save ────────────────────────────────────────────────────── */
function triggerDownload(id) {
  const a = Object.assign(document.createElement('a'), { href: '/download/' + id, style: 'display:none' });
  document.body.appendChild(a);
  a.click();
  setTimeout(() => a.remove(), 1000);
}
function retryDownload() { if (currentJobId) triggerDownload(currentJobId); }

/* ── Settings modal ───────────────────────────────────────────────────────── */
function openSettings() {
  refreshThemeButtons(currentTheme);
  const overlay = document.getElementById('overlay');
  if (overlay) overlay.classList.add('show');
}
function closeSettings() {
  const overlay = document.getElementById('overlay');
  if (overlay) overlay.classList.remove('show');
}
function closeIfBackdrop(e) {
  const overlay = document.getElementById('overlay');
  if (e.target === overlay) closeSettings();
}
function setTheme(t) {
  currentTheme = t;
  document.documentElement.setAttribute('data-theme', t);
  refreshThemeButtons(t);
}
function refreshThemeButtons(t) {
  const dark  = document.getElementById('theme-dark');
  const light = document.getElementById('theme-light');
  if (dark)  dark.classList.toggle('active',  t === 'dark');
  if (light) light.classList.toggle('active', t === 'light');
}
function setCfgQuality(btn) {
  document.querySelectorAll('#cfg-quality-grid .q-pill').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  cfgKey = btn.dataset.key;
}
async function saveSettings() {
  const dirEl = document.getElementById('cfg-dir');
  const dir   = dirEl ? dirEl.value.trim() : '';
  const note  = document.getElementById('save-note');
  if (note) note.textContent = '';
  try {
    const res  = await fetch('/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme: currentTheme, default_quality: cfgKey, download_dir: dir }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    selectedKey = cfgKey;
    document.querySelectorAll('#quality-grid .q-pill').forEach(b => {
      b.classList.toggle('active', b.dataset.key === cfgKey);
    });
    if (note) { note.style.color = 'var(--success)'; note.textContent = '✓ Settings saved'; }
    showToast('Settings saved', 'success');
    setTimeout(closeSettings, 1200);
  } catch (err) {
    if (note) { note.style.color = 'var(--error)'; note.textContent = 'Error: ' + err.message; }
  }
}

/* ── Toast ────────────────────────────────────────────────────────────────── */
function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const icons = { success: 'check-circle-2', error: 'alert-circle', info: 'info' };
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.innerHTML = `<i data-lucide="${icons[type] || 'info'}"></i><span>${message}</span>`;
  container.appendChild(el);
  if (window.lucide) lucide.createIcons({ nodes: [el] });
  setTimeout(() => {
    el.classList.add('toast-out');
    setTimeout(() => el.remove(), 400);
  }, 4000);
}

/* ── FAQ accordion ────────────────────────────────────────────────────────── */
function toggleFaq(btn) {
  const item   = btn.closest('.faq-item');
  const isOpen = item.classList.contains('open');
  document.querySelectorAll('.faq-item.open').forEach(i => i.classList.remove('open'));
  if (!isOpen) item.classList.add('open');
}

/* ── History ──────────────────────────────────────────────────────────────── */
const HISTORY_KEY = 'vidflow_history';
const HISTORY_MAX = 20;

function saveToHistory(title, quality) {
  if (!window.USER_LOGGED_IN) {
    // Guest: persist to localStorage only
    const history = loadHistory();
    history.unshift({ title, quality, date: new Date().toISOString() });
    if (history.length > HISTORY_MAX) history.length = HISTORY_MAX;
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  }
  // For logged-in users the server already saved the record in the worker;
  // re-render so the new entry appears immediately.
  renderHistory();
}

function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
  } catch (_) {
    return [];
  }
}

/* Dispatch to the correct renderer based on auth state */
function renderHistory() {
  if (window.USER_LOGGED_IN) {
    renderDbHistory();
  } else {
    renderLocalHistory();
  }
}

/* Fetch history from the server DB (logged-in users) */
async function renderDbHistory() {
  const emptyEl  = document.getElementById('history-empty');
  const tableEl  = document.getElementById('history-table-wrap');
  const tbody    = document.getElementById('history-tbody');
  const clearBtn = document.getElementById('clear-history-btn');
  if (!emptyEl || !tableEl || !tbody) return;

  try {
    const res = await fetch('/api/history');
    if (!res.ok) { renderLocalHistory(); return; }
    const history = await res.json();

    if (history.length === 0) {
      emptyEl.style.display = '';
      tableEl.style.display = 'none';
      if (clearBtn) clearBtn.style.display = 'none';
      return;
    }

    emptyEl.style.display = 'none';
    tableEl.style.display = '';
    // Logged-in users manage history server-side; hide the client-side clear button
    if (clearBtn) clearBtn.style.display = 'none';

    tbody.innerHTML = history.map(item => {
      const date    = new Date(item.date);
      const dateStr = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
      const enc     = encodeURIComponent(item.title || '');
      return `<tr>
        <td class="history-title" title="${escHtml(item.title || '')}">${escHtml(item.title || 'Unknown')}</td>
        <td class="history-quality">${escHtml(item.quality || '—')}</td>
        <td class="history-date">${dateStr}</td>
        <td>
          <button class="history-retry-btn" onclick="historySearch('${enc}')">↗ Search</button>
        </td>
      </tr>`;
    }).join('');
  } catch (_) {
    renderLocalHistory();
  }
}

/* Render history from localStorage (guest users) */
function renderLocalHistory() {
  const history  = loadHistory();
  const emptyEl  = document.getElementById('history-empty');
  const tableEl  = document.getElementById('history-table-wrap');
  const tbody    = document.getElementById('history-tbody');
  const clearBtn = document.getElementById('clear-history-btn');

  if (!emptyEl || !tableEl || !tbody) return;

  if (history.length === 0) {
    emptyEl.style.display = '';
    tableEl.style.display = 'none';
    if (clearBtn) clearBtn.style.display = 'none';
    return;
  }

  emptyEl.style.display = 'none';
  tableEl.style.display = '';
  if (clearBtn) clearBtn.style.display = '';

  tbody.innerHTML = history.map(item => {
    const date    = new Date(item.date);
    const dateStr = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    const enc     = encodeURIComponent(item.title || '');
    return `<tr>
      <td class="history-title" title="${escHtml(item.title || '')}">${escHtml(item.title || 'Unknown')}</td>
      <td class="history-quality">${escHtml(item.quality || '—')}</td>
      <td class="history-date">${dateStr}</td>
      <td><button class="history-retry-btn" onclick="historySearch('${enc}')">↗ Search</button></td>
    </tr>`;
  }).join('');
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function historySearch(encodedTitle) {
  window.open('https://www.youtube.com/results?search_query=' + encodedTitle, '_blank');
}

function clearHistory() {
  localStorage.removeItem(HISTORY_KEY);
  renderHistory();
  showToast('History cleared', 'info');
}

/* ── UI helpers ───────────────────────────────────────────────────────────── */
const BADGES = {
  starting:    ['badge-starting',    'Starting…'],
  downloading: ['badge-downloading', 'Downloading'],
  processing:  ['badge-processing',  'Processing'],
  done:        ['badge-done',        'Complete'],
  error:       ['badge-error',       'Error'],
};
function setBadge(s) {
  const [cls, label] = BADGES[s] || ['badge-starting', s];
  const el = document.getElementById('badge');
  if (el) el.className = 'badge ' + cls;
  const textEl = document.getElementById('badge-text');
  if (textEl) textEl.textContent = label;
}
function setBar(pct, done) {
  const b = document.getElementById('bar');
  if (!b) return;
  b.style.width = pct + '%';
  b.classList.toggle('complete', done);
}
function indeterminate(on) {
  const b = document.getElementById('bar');
  if (b) b.classList.toggle('indeterminate', on);
}
function setText(id, v) {
  const el = document.getElementById(id);
  if (el) el.textContent = v;
}
function setBtn(off) {
  const btn = document.getElementById('dl-btn');
  if (btn) btn.disabled = off;
}
function showError(msg) {
  setBadge('error');
  const errText = document.getElementById('err-text');
  const msgErr  = document.getElementById('msg-error');
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

  const bar       = document.getElementById('bar');
  const msgDone   = document.getElementById('msg-done');
  const msgError  = document.getElementById('msg-error');
  const doneText  = document.getElementById('done-text');
  const doneAction= document.getElementById('done-action');
  const plCounter = document.getElementById('pl-counter');
  const overallWrap= document.getElementById('overall-wrap');
  const barLabel  = document.getElementById('bar-label');

  if (bar)        bar.classList.remove('complete');
  if (msgDone)    msgDone.style.display  = 'none';
  if (msgError)   msgError.style.display = 'none';
  if (doneText)   doneText.textContent   = 'Downloaded successfully!';
  if (doneAction) doneAction.style.display = '';

  if (isPlaylist) {
    if (plCounter)   { plCounter.classList.remove('show'); }
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

/* VidFlow — downloader.js: URL detection, download flow, history */

/* ── URL info detection ───────────────────────────────────────────────────── */
function scheduleDetect(url) {
  clearTimeout(infoDebounce);
  if (!url) { hideInfo(); return; }
  showInfoLoading();
  infoDebounce = setTimeout(function () { detectInfo(url); }, 700);
}

function showInfoLoading() {
  var strip = document.getElementById('info-strip');
  if (strip) strip.classList.add('show');
  var loading = document.getElementById('info-loading');
  if (loading) loading.style.display = 'flex';
  var content = document.getElementById('info-content');
  if (content) content.style.display = 'none';
}

function hideInfo() {
  var strip = document.getElementById('info-strip');
  if (strip) strip.classList.remove('show');
  detectedInfo = null;
  updateDlButton(false, 0);
}

async function detectInfo(url) {
  try {
    var res  = await fetch('/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: url }),
    });
    var data = await res.json();
    if (data.error) { hideInfo(); return; }
    detectedInfo = data;
    renderInfo(data);
  } catch (_) {
    hideInfo();
  }
}

function renderInfo(d) {
  var loading = document.getElementById('info-loading');
  var content = document.getElementById('info-content');
  if (loading) loading.style.display = 'none';
  if (content) content.style.display = 'block';

  var isPlaylist = d.type === 'playlist';

  var thumbRow = document.getElementById('info-thumb-row');
  var thumbImg = document.getElementById('info-thumb');
  if (thumbRow && thumbImg) {
    if (!isPlaylist && d.thumbnail) {
      thumbImg.src     = d.thumbnail;
      thumbImg.onerror = function () { thumbRow.style.display = 'none'; };
      thumbImg.onload  = function () { thumbRow.style.display = 'block'; };
    } else if (!isPlaylist) {
      var vid = extractVideoId(document.getElementById('url').value);
      if (vid) {
        thumbImg.src     = 'https://img.youtube.com/vi/' + vid + '/mqdefault.jpg';
        thumbImg.onerror = function () { thumbRow.style.display = 'none'; };
        thumbImg.onload  = function () { thumbRow.style.display = 'block'; };
      } else {
        thumbRow.style.display = 'none';
      }
    } else {
      thumbRow.style.display = 'none';
    }
  }

  var badge = document.getElementById('info-type-badge');
  if (badge) {
    badge.textContent = isPlaylist ? '▶ Playlist' : '▶ Video';
    badge.className   = 'info-type-badge ' + (isPlaylist ? 'badge-playlist' : 'badge-video');
  }

  var titleEl = document.getElementById('info-title');
  if (titleEl) titleEl.textContent = d.title || 'Unknown';

  var sub = d.uploader || '';
  if (isPlaylist) {
    sub += (sub ? ' · ' : '') + d.count + ' videos';
  } else if (d.duration) {
    var m = Math.floor(d.duration / 60), s = d.duration % 60;
    sub += (sub ? ' · ' : '') + m + ':' + String(s).padStart(2, '0');
  }
  var subEl = document.getElementById('info-sub');
  if (subEl) subEl.textContent = sub;

  var toggle = document.getElementById('pl-toggle-wrap');
  if (toggle) toggle.style.display = isPlaylist ? 'flex' : 'none';

  updateDlButton(isPlaylist, d.count);
}

function updateDlButton(isPlaylist, count) {
  var btn  = document.getElementById('dl-btn-text');
  var dlEl = document.getElementById('dl-playlist');
  if (!btn) return;
  var dlAll = isPlaylist && dlEl && dlEl.checked;
  if (dlAll)           btn.textContent = ('Download All ' + (count > 0 ? '(' + count + ')' : '')).trim();
  else if (isPlaylist) btn.textContent = 'Download Video';
  else                 btn.textContent = 'Download';
}

function extractVideoId(url) {
  var m = url.match(/[?&]v=([^&#]{11})/) || url.match(/youtu\.be\/([^?&#]{11})/);
  return m ? m[1] : null;
}

/* ── Start download ───────────────────────────────────────────────────────── */
async function startDownload() {
  if (!window.USER_LOGGED_IN) {
    showSignupPrompt();
    return;
  }

  var urlEl = document.getElementById('url');
  var url   = urlEl ? urlEl.value.trim() : '';
  if (!url) { if (urlEl) shake(urlEl.closest('.search-bar') || urlEl); return; }

  var dlEl          = document.getElementById('dl-playlist');
  var isPlaylist    = detectedInfo && detectedInfo.type === 'playlist' && dlEl && dlEl.checked;
  var playlistCount = isPlaylist ? (detectedInfo.count || 0) : 0;

  currentJobId = null;
  clearTimeout(pollTimer);
  resetProgress(isPlaylist, playlistCount);

  var progCard = document.getElementById('prog-card');
  if (progCard) {
    progCard.classList.add('show');
    setTimeout(function () { progCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, 100);
  }
  setBtn(true);

  try {
    var res  = await fetch('/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: url, quality: selectedKey, is_playlist: isPlaylist, playlist_count: playlistCount }),
    });
    var data = await res.json();
    if (res.status === 429 && data.error === 'limit_reached') {
      showLimitReached(data.hours, data.minutes);
      setBtn(false);
      var progCard = document.getElementById('prog-card');
      if (progCard) progCard.classList.remove('show');
      return;
    }
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
    var data = await fetch('/progress/' + currentJobId).then(function (r) { return r.json(); });
    applyUpdate(data);
    if (data.status !== 'done' && data.status !== 'error') schedulePoll();
  } catch (_) {
    schedulePoll();
  }
}

/* ── Apply update ─────────────────────────────────────────────────────────── */
function applyUpdate(d) {
  setBadge(d.status);
  var isPlaylist = d.is_playlist;

  var vidTitle = document.getElementById('vid-title');
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
      var idx   = d.playlist_index || 0;
      var total = d.playlist_count || 0;
      if (idx) {
        setText('pl-index', idx);
        if (total) setText('pl-total', total);
        var plCounter = document.getElementById('pl-counter');
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
      var files = d.files || [];
      var tot   = d.playlist_count || files.length;
      var doneText = document.getElementById('done-text');
      if (doneText) doneText.textContent = 'Playlist downloaded — ' + files.length + ' of ' + tot + ' videos saved';
      var doneAction = document.getElementById('done-action');
      if (doneAction) doneAction.style.display = 'none';
    }

    var msgDone = document.getElementById('msg-done');
    if (msgDone) msgDone.style.display = 'flex';
    setBtn(false);

    var qPill = document.querySelector('#quality-grid .q-pill.active');
    var qName = qPill ? qPill.textContent.trim() : '';
    var title = (detectedInfo && detectedInfo.title) ? detectedInfo.title : (d.title || 'Unknown');
    saveToHistory(title, qName);
    showToast('Download complete!', 'success');

    if (!isPlaylist) triggerDownload(currentJobId);

    if (window.USER_LOGGED_IN) {
      var incEl = function (id) {
        var el = document.getElementById(id);
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
  var bar = document.getElementById('overall-bar');
  if (bar) bar.style.width = pct + '%';
}

/* ── Trigger file save ────────────────────────────────────────────────────── */
function triggerDownload(id) {
  var a = document.createElement('a');
  a.href = '/download/' + id;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  setTimeout(function () { a.remove(); }, 1000);
}
function retryDownload() { if (currentJobId) triggerDownload(currentJobId); }

/* ── History ──────────────────────────────────────────────────────────────── */
var HISTORY_KEY = 'vidflow_history';
var HISTORY_MAX = 20;

function saveToHistory(title, quality) {
  if (!window.USER_LOGGED_IN) {
    var history = loadHistory();
    history.unshift({ title: title, quality: quality, date: new Date().toISOString() });
    if (history.length > HISTORY_MAX) history.length = HISTORY_MAX;
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  }
  renderHistory();
}

function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
  } catch (_) {
    return [];
  }
}

function renderHistory() {
  if (window.USER_LOGGED_IN) {
    renderDbHistory();
  } else {
    renderLocalHistory();
  }
}

async function renderDbHistory() {
  var emptyEl  = document.getElementById('history-empty');
  var tableEl  = document.getElementById('history-table-wrap');
  var tbody    = document.getElementById('history-tbody');
  var clearBtn = document.getElementById('clear-history-btn');
  if (!emptyEl || !tableEl || !tbody) return;

  try {
    var res = await fetch('/api/history');
    if (!res.ok) { renderLocalHistory(); return; }
    var history = await res.json();

    if (history.length === 0) {
      emptyEl.style.display = '';
      tableEl.style.display = 'none';
      if (clearBtn) clearBtn.style.display = 'none';
      return;
    }

    emptyEl.style.display = 'none';
    tableEl.style.display = '';
    if (clearBtn) clearBtn.style.display = 'none';

    tbody.innerHTML = history.map(function (item) {
      var date    = new Date(item.date);
      var dateStr = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
      var enc     = encodeURIComponent(item.title || '');
      return '<tr>' +
        '<td class="history-title" title="' + escHtml(item.title || '') + '">' + escHtml(item.title || 'Unknown') + '</td>' +
        '<td class="history-quality">' + escHtml(item.quality || '—') + '</td>' +
        '<td class="history-date">' + dateStr + '</td>' +
        '<td><button class="history-retry-btn" onclick="historySearch(\'' + enc + '\')">↗ Search</button></td>' +
        '</tr>';
    }).join('');
  } catch (_) {
    renderLocalHistory();
  }
}

function renderLocalHistory() {
  var history  = loadHistory();
  var emptyEl  = document.getElementById('history-empty');
  var tableEl  = document.getElementById('history-table-wrap');
  var tbody    = document.getElementById('history-tbody');
  var clearBtn = document.getElementById('clear-history-btn');

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

  tbody.innerHTML = history.map(function (item) {
    var date    = new Date(item.date);
    var dateStr = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    var enc     = encodeURIComponent(item.title || '');
    return '<tr>' +
      '<td class="history-title" title="' + escHtml(item.title || '') + '">' + escHtml(item.title || 'Unknown') + '</td>' +
      '<td class="history-quality">' + escHtml(item.quality || '—') + '</td>' +
      '<td class="history-date">' + dateStr + '</td>' +
      '<td><button class="history-retry-btn" onclick="historySearch(\'' + enc + '\')">↗ Search</button></td>' +
      '</tr>';
  }).join('');
}

function clearHistory() {
  localStorage.removeItem(HISTORY_KEY);
  renderHistory();
  showToast('History cleared', 'info');
}

/* ── Daily limit modal ───────────────────────────────────────────────────── */
function showLimitReached(hours, minutes) {
  var existing = document.getElementById('limit-overlay');
  if (existing) { existing.classList.add('show'); return; }

  var timeStr = hours > 0
    ? hours + 'h ' + minutes + 'm'
    : minutes + ' minutes';

  var overlay = document.createElement('div');
  overlay.id = 'limit-overlay';
  overlay.innerHTML =
    '<div class="limit-box">' +
      '<button class="signup-prompt-close" onclick="closeLimitOverlay()" aria-label="Close">' +
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>' +
      '</button>' +
      '<div class="limit-icon">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>' +
      '</div>' +
      '<h3 class="limit-title">Daily limit reached</h3>' +
      '<p class="limit-text">You\'ve used all <strong>3 free downloads</strong> for today.</p>' +
      '<div class="limit-timer">Resets in <strong>' + timeStr + '</strong></div>' +
      '<a href="/pricing" class="limit-upgrade-btn">Upgrade for more downloads</a>' +
    '</div>';
  overlay.addEventListener('click', function (e) {
    if (e.target === overlay) closeLimitOverlay();
  });
  document.body.appendChild(overlay);
  requestAnimationFrame(function () { overlay.classList.add('show'); });
}

function closeLimitOverlay() {
  var overlay = document.getElementById('limit-overlay');
  if (overlay) {
    overlay.classList.remove('show');
    setTimeout(function () { overlay.remove(); }, 300);
  }
}

/* ── Signup prompt ────────────────────────────────────────────────────────── */
function showSignupPrompt() {
  var existing = document.getElementById('signup-prompt-overlay');
  if (existing) { existing.classList.add('show'); return; }

  var overlay = document.createElement('div');
  overlay.id = 'signup-prompt-overlay';
  overlay.innerHTML =
    '<div class="signup-prompt-box">' +
      '<button class="signup-prompt-close" onclick="closeSignupPrompt()" aria-label="Close">' +
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>' +
      '</button>' +
      '<div class="signup-prompt-logo">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round"><path d="M3 5 Q7 15 12 18 Q17 15 21 5"/><path d="M12 18 L12 22 M9 22 L15 22"/></svg>' +
      '</div>' +
      '<h3 class="signup-prompt-title">Sign in to continue</h3>' +
      '<p class="signup-prompt-text">You need an account to download videos. It\'s free and takes 10 seconds.</p>' +
      '<a href="/login" class="signup-prompt-btn-primary">Continue with Google</a>' +
      '<p class="signup-prompt-note">Already have an account? <a href="/login">Sign in</a></p>' +
    '</div>';
  overlay.addEventListener('click', function (e) {
    if (e.target === overlay) closeSignupPrompt();
  });
  document.body.appendChild(overlay);
  requestAnimationFrame(function () { overlay.classList.add('show'); });
}

function closeSignupPrompt() {
  var overlay = document.getElementById('signup-prompt-overlay');
  if (overlay) {
    overlay.classList.remove('show');
    setTimeout(function () { overlay.remove(); }, 300);
  }
}

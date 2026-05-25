/* admin.js — VidFlow Admin Panel JS */
'use strict';

// ── Sidebar toggle ────────────────────────────────────────────────────────────
var sidebar   = document.getElementById('adminSidebar');
var overlay   = document.getElementById('sidebarOverlay');
var toggleBtn = document.getElementById('sidebarToggle');

function openSidebar() {
  sidebar && sidebar.classList.add('open');
  overlay && overlay.classList.add('active');
}
function closeSidebar() {
  sidebar && sidebar.classList.remove('open');
  overlay && overlay.classList.remove('active');
}

toggleBtn && toggleBtn.addEventListener('click', openSidebar);
overlay   && overlay.addEventListener('click', closeSidebar);


// ── Delete modal ──────────────────────────────────────────────────────────────
var deleteModal   = document.getElementById('deleteModal');
var deleteForm    = document.getElementById('deleteForm');
var deleteMessage = document.getElementById('deleteMessage');
var cancelDelete  = document.getElementById('cancelDelete');

function confirmDelete(action, message) {
  if (!deleteModal) return;
  deleteMessage.textContent = message || 'Are you sure? This cannot be undone.';
  deleteForm.action = action;
  deleteModal.classList.add('active');
}

cancelDelete && cancelDelete.addEventListener('click', function () {
  deleteModal.classList.remove('active');
});

deleteModal && deleteModal.addEventListener('click', function (e) {
  if (e.target === deleteModal) deleteModal.classList.remove('active');
});

window.confirmDelete = confirmDelete;


// ── Toast notifications ───────────────────────────────────────────────────────
function showToast(message, type) {
  type = type || 'success';
  var existing = document.querySelector('.toast');
  if (existing) existing.remove();

  var toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.innerHTML =
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
    (type === 'success'
      ? '<polyline points="20 6 9 17 4 12"/>'
      : '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>') +
    '</svg>' +
    '<span>' + message + '</span>';
  document.body.appendChild(toast);
  requestAnimationFrame(function () { toast.classList.add('show'); });
  setTimeout(function () {
    toast.classList.remove('show');
    setTimeout(function () { toast.remove(); }, 300);
  }, 3500);
}
window.showToast = showToast;

document.addEventListener('DOMContentLoaded', function () {
  var flashSuccess = document.querySelector('[data-flash-success]');
  var flashError   = document.querySelector('[data-flash-error]');
  if (flashSuccess) showToast(flashSuccess.dataset.flashSuccess, 'success');
  if (flashError)   showToast(flashError.dataset.flashError, 'error');
});


// ── Search debounce ───────────────────────────────────────────────────────────
var searchInput = document.getElementById('searchInput');
var searchTimer;
if (searchInput) {
  searchInput.addEventListener('input', function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      var form = searchInput.closest('form');
      if (form) form.submit();
    }, 500);
  });
}


// ── Charts ────────────────────────────────────────────────────────────────────
async function initCharts() {
  var daysParam = new URLSearchParams(window.location.search).get('days') || 30;

  if (typeof Chart === 'undefined') return;

  Chart.defaults.color = '#8b8fa8';
  Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';

  var response = await fetch('/admin/stats/json?days=' + daysParam);
  if (!response.ok) return;
  var data = await response.json();

  var lineCtx = document.getElementById('downloadsChart');
  if (lineCtx) {
    new Chart(lineCtx, {
      type: 'line',
      data: {
        labels: data.daily.map(function (r) { return r.date; }),
        datasets: [{
          label: 'Downloads',
          data: data.daily.map(function (r) { return r.count; }),
          borderColor: '#ff0000',
          backgroundColor: 'rgba(255,0,0,0.12)',
          borderWidth: 2,
          tension: 0.4,
          fill: true,
          pointBackgroundColor: '#ff0000',
          pointRadius: 3,
          pointHoverRadius: 5,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,0.04)' } },
          y: { grid: { color: 'rgba(255,255,255,0.04)' }, beginAtZero: true, ticks: { stepSize: 1 } },
        },
      },
    });
  }

  var donutCtx = document.getElementById('platformsChart');
  if (donutCtx && data.platforms.length) {
    var COLORS = ['#ff0000','#ef4444','#ec4899','#0ea5e9','#1d4ed8','#06b6d4','#14b8a6','#f59e0b'];
    new Chart(donutCtx, {
      type: 'doughnut',
      data: {
        labels: data.platforms.map(function (r) { return r.platform; }),
        datasets: [{
          data: data.platforms.map(function (r) { return r.count; }),
          backgroundColor: COLORS.slice(0, data.platforms.length),
          borderWidth: 0,
          hoverOffset: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'right', labels: { padding: 16, usePointStyle: true, pointStyleWidth: 10 } },
        },
        cutout: '65%',
      },
    });
  }

  var barCtx = document.getElementById('topUsersChart');
  if (barCtx && data.top_users.length) {
    new Chart(barCtx, {
      type: 'bar',
      data: {
        labels: data.top_users.map(function (r) { return r.name || 'Unknown'; }),
        datasets: [{
          label: 'Downloads',
          data: data.top_users.map(function (r) { return r.count; }),
          backgroundColor: 'rgba(255,0,0,0.7)',
          borderColor: '#ff0000',
          borderWidth: 1,
          borderRadius: 4,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,0.04)' }, beginAtZero: true, ticks: { stepSize: 1 } },
          y: { grid: { display: false } },
        },
      },
    });
  }
}

document.addEventListener('DOMContentLoaded', initCharts);


// ── Theme toggle ──────────────────────────────────────────────────────────────
var SUN_SVG  = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
var MOON_SVG = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';

function _syncThemeBtn(theme) {
  var btn = document.getElementById('themeToggleBtn');
  if (!btn) return;
  btn.innerHTML = theme === 'dark' ? SUN_SVG : MOON_SVG;
  btn.title     = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
}

function toggleAdminTheme() {
  var current = document.documentElement.getAttribute('data-theme') || 'dark';
  var next    = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('vf_admin_theme', next);
  _syncThemeBtn(next);
  fetch('/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ theme: next }),
  }).catch(function () {});
}

document.addEventListener('DOMContentLoaded', function () {
  var theme = document.documentElement.getAttribute('data-theme') || 'dark';
  _syncThemeBtn(theme);
  var btn = document.getElementById('themeToggleBtn');
  if (btn) btn.addEventListener('click', toggleAdminTheme);
});


// ── Day-range selector (stats page) ──────────────────────────────────────────
document.querySelectorAll('[data-days]').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var url = new URL(window.location.href);
    url.searchParams.set('days', btn.dataset.days);
    window.location.href = url.toString();
  });
});


// ── Toggle switch accessibility ───────────────────────────────────────────────
document.querySelectorAll('.toggle-track').forEach(function (track) {
  var toggle = track.closest('.toggle');
  if (toggle) {
    toggle.addEventListener('keydown', function (e) {
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        var cb = track.previousElementSibling;
        if (cb && cb.type === 'checkbox') {
          cb.checked = !cb.checked;
          cb.dispatchEvent(new Event('change'));
        }
      }
    });
  }
});


// ── Auto-refresh dashboard stats every 60s ────────────────────────────────────
if (document.getElementById('dashLiveStats')) {
  setInterval(function () {
    fetch('/admin/stats/json?days=1').then(function (r) { return r.json(); }).then(function (data) {
      var todayEl = document.getElementById('dashToday');
      if (todayEl && data.daily.length) {
        todayEl.textContent = data.daily[data.daily.length - 1].count;
      }
    }).catch(function () {});
  }, 60000);
}


// ── Lockout countdown ─────────────────────────────────────────────────────────
var lockoutEl  = document.getElementById('lockoutTimer');
var lockoutSec = parseInt(lockoutEl && lockoutEl.dataset.seconds, 10);

if (lockoutEl && lockoutSec > 0) {
  var remaining = lockoutSec;
  var tick = function () {
    if (remaining <= 0) { location.reload(); return; }
    var m = Math.floor(remaining / 60);
    var s = remaining % 60;
    lockoutEl.textContent = m + 'm ' + String(s).padStart(2, '0') + 's';
    remaining--;
    setTimeout(tick, 1000);
  };
  tick();
}

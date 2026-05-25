/* admin.js — VidFlow Admin Panel JS */
'use strict';

// ── Sidebar toggle ────────────────────────────────────────────────────────────
const sidebar  = document.getElementById('adminSidebar');
const overlay  = document.getElementById('sidebarOverlay');
const toggleBtn = document.getElementById('sidebarToggle');

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
const deleteModal   = document.getElementById('deleteModal');
const deleteForm    = document.getElementById('deleteForm');
const deleteMessage = document.getElementById('deleteMessage');
const cancelDelete  = document.getElementById('cancelDelete');

function confirmDelete(action, message) {
  if (!deleteModal) return;
  deleteMessage.textContent = message || 'Are you sure? This cannot be undone.';
  deleteForm.action = action;
  deleteModal.classList.add('active');
}

cancelDelete && cancelDelete.addEventListener('click', () => {
  deleteModal.classList.remove('active');
});

deleteModal && deleteModal.addEventListener('click', (e) => {
  if (e.target === deleteModal) deleteModal.classList.remove('active');
});

// expose globally for inline onclick
window.confirmDelete = confirmDelete;


// ── Toast notifications ───────────────────────────────────────────────────────
function showToast(message, type = 'success') {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      ${type === 'success'
        ? '<polyline points="20 6 9 17 4 12"/>'
        : '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>'}
    </svg>
    <span>${message}</span>
  `;
  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('show'));
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
window.showToast = showToast;

// Auto-show toast from flash data
document.addEventListener('DOMContentLoaded', () => {
  const flashSuccess = document.querySelector('[data-flash-success]');
  const flashError   = document.querySelector('[data-flash-error]');
  if (flashSuccess) showToast(flashSuccess.dataset.flashSuccess, 'success');
  if (flashError)   showToast(flashError.dataset.flashError, 'error');
});


// ── Search debounce ───────────────────────────────────────────────────────────
const searchInput = document.getElementById('searchInput');
let searchTimer;
if (searchInput) {
  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      const form = searchInput.closest('form');
      if (form) form.submit();
    }, 500);
  });
}


// ── Charts ────────────────────────────────────────────────────────────────────
async function initCharts() {
  const daysParam = new URLSearchParams(window.location.search).get('days') || 30;

  // Only run if Chart.js is loaded and we're on a chart page
  if (typeof Chart === 'undefined') return;

  Chart.defaults.color = '#8b8fa8';
  Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';

  const response = await fetch(`/admin/stats/json?days=${daysParam}`);
  if (!response.ok) return;
  const data = await response.json();

  // Line chart — daily downloads
  const lineCtx = document.getElementById('downloadsChart');
  if (lineCtx) {
    new Chart(lineCtx, {
      type: 'line',
      data: {
        labels: data.daily.map(r => r.date),
        datasets: [{
          label: 'Downloads',
          data: data.daily.map(r => r.count),
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

  // Doughnut chart — platforms
  const donutCtx = document.getElementById('platformsChart');
  if (donutCtx && data.platforms.length) {
    const COLORS = ['#ff0000','#ef4444','#ec4899','#0ea5e9','#1d4ed8','#06b6d4','#14b8a6','#f59e0b'];
    new Chart(donutCtx, {
      type: 'doughnut',
      data: {
        labels: data.platforms.map(r => r.platform),
        datasets: [{
          data: data.platforms.map(r => r.count),
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

  // Horizontal bar — top users
  const barCtx = document.getElementById('topUsersChart');
  if (barCtx && data.top_users.length) {
    new Chart(barCtx, {
      type: 'bar',
      data: {
        labels: data.top_users.map(r => r.name || 'Unknown'),
        datasets: [{
          label: 'Downloads',
          data: data.top_users.map(r => r.count),
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
const SUN_SVG  = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;
const MOON_SVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;

function _syncThemeBtn(theme) {
  const btn = document.getElementById('themeToggleBtn');
  if (!btn) return;
  btn.innerHTML = theme === 'dark' ? SUN_SVG : MOON_SVG;
  btn.title     = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
}

function toggleAdminTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  const next    = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('vf_admin_theme', next);
  _syncThemeBtn(next);
  fetch('/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ theme: next }),
  }).catch(() => {});
}

document.addEventListener('DOMContentLoaded', () => {
  // Sync icon with actual applied theme (may come from localStorage)
  const theme = document.documentElement.getAttribute('data-theme') || 'dark';
  _syncThemeBtn(theme);
  const btn = document.getElementById('themeToggleBtn');
  if (btn) btn.addEventListener('click', toggleAdminTheme);
});


// ── Day-range selector (stats page) ──────────────────────────────────────────
document.querySelectorAll('[data-days]').forEach(btn => {
  btn.addEventListener('click', () => {
    const url = new URL(window.location.href);
    url.searchParams.set('days', btn.dataset.days);
    window.location.href = url.toString();
  });
});


// ── Toggle switch accessibility ───────────────────────────────────────────────
document.querySelectorAll('.toggle-track').forEach(track => {
  track.closest('.toggle') && track.closest('.toggle').addEventListener('keydown', (e) => {
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      const cb = track.previousElementSibling;
      if (cb && cb.type === 'checkbox') {
        cb.checked = !cb.checked;
        cb.dispatchEvent(new Event('change'));
      }
    }
  });
});


// ── Auto-refresh dashboard stats every 60s ────────────────────────────────────
if (document.getElementById('dashLiveStats')) {
  setInterval(() => {
    fetch('/admin/stats/json?days=1').then(r => r.json()).then(data => {
      const todayEl = document.getElementById('dashToday');
      if (todayEl && data.daily.length) {
        todayEl.textContent = data.daily[data.daily.length - 1].count;
      }
    }).catch(() => {});
  }, 60000);
}


// ── Lockout countdown ─────────────────────────────────────────────────────────
const lockoutEl  = document.getElementById('lockoutTimer');
const lockoutSec = parseInt(lockoutEl && lockoutEl.dataset.seconds, 10);

if (lockoutEl && lockoutSec > 0) {
  let remaining = lockoutSec;
  const tick = () => {
    if (remaining <= 0) { location.reload(); return; }
    const m = Math.floor(remaining / 60);
    const s = remaining % 60;
    lockoutEl.textContent = `${m}m ${s.toString().padStart(2, '0')}s`;
    remaining--;
    setTimeout(tick, 1000);
  };
  tick();
}

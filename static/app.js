// State & Utilities
let authToken = localStorage.getItem('ninja_jwt');
let currentUser = null;
let currentView = 'page-home';
window.lastBulkResults = [];

// Expose routing exactly as requested
window.showPage = function(pageName) {
    if (pageName === 'dashboard' && !authToken) {
        showLoginModal();
        return;
    }
    
    // Hide all pages
    document.querySelectorAll('.page').forEach(p => {
        p.classList.remove('active');
    });
    
    // Show target page
    const target = document.getElementById('page-' + pageName);
    if(target) {
        target.classList.add('active');
    }
    
    // Update active nav link (optional visual tweak)
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    document.querySelectorAll(`.nav-link[onclick="showPage('${pageName}')"]`).forEach(l => l.classList.add('active'));

    currentView = 'page-' + pageName;
    window.scrollTo(0, 0);
    
    // Close mobile menu if open
    DOM.navContainer.classList.remove('show');
}

const DOM = {
    navAuth: document.getElementById('nav-auth'),
    navUnauth: document.getElementById('nav-unauth'),
    creditsText: document.getElementById('nav-credits'),
    mobileBtn: document.getElementById('mobile-toggle'),
    navContainer: document.querySelector('.nav-links'),

    // Modals
    overlay: document.getElementById('auth-modalOverlay'),
    loginModal: document.getElementById('login-modal'),
    signupModal: document.getElementById('signup-modal')
};

window.handleFileUpload = function(input) {
  const file = input.files[0];
  if (!file) return;
  
  const validTypes = ['.txt', '.csv', 'text/plain', 'text/csv'];
  const isValid = validTypes.some(t => 
    file.name.endsWith('.txt') || 
    file.name.endsWith('.csv') ||
    file.type === 'text/plain' ||
    file.type === 'text/csv'
  );
  
  if (!isValid) {
    alert('Only .txt and .csv files allowed');
    return;
  }
  
  const reader = new FileReader();
  reader.onload = function(e) {
    const content = e.target.result;
    const emails = content
      .split(/[\n,;|\s]+/)
      .map(e => e.trim().toLowerCase())
      .filter(e => e.includes('@'));
    
    document.getElementById('bulk-email-input').value = emails.join('\n');
    document.getElementById('file-upload-info').textContent = 
      'Found ' + emails.length + ' emails';
    document.getElementById('file-upload-info').style.display = 'inline-block';
  };
  reader.readAsText(file);
};

// ==========================================
// DASH PANELS
// ==========================================
function showDashTab(tabName) {
  // hide all tabs
  document.querySelectorAll('.dash-tab').forEach(function(tab) {
    tab.style.display = 'none';
  });
  // show selected tab
  var selectedTab = document.getElementById('tab-' + tabName);
  if (selectedTab) {
    selectedTab.style.display = 'block';
  }
  // update active sidebar link
  document.querySelectorAll('.sidebar-link').forEach(function(link) {
    link.classList.remove('active');
  });
}
window.showDashTab = showDashTab;

DOM.mobileBtn.addEventListener('click', () => DOM.navContainer.classList.toggle('show'));


// ==========================================
// MODALS
// ==========================================
window.showLoginModal = function() {
    DOM.overlay.classList.remove('hidden');
    DOM.loginModal.classList.remove('hidden');
    DOM.signupModal.classList.add('hidden');
}

window.showSignupModal = function() {
    DOM.overlay.classList.remove('hidden');
    DOM.signupModal.classList.remove('hidden');
    DOM.loginModal.classList.add('hidden');
}

function closeModals() {
    DOM.overlay.classList.add('hidden');
}

document.getElementById('nav-login-btn').addEventListener('click', showLoginModal);
document.getElementById('nav-signup-btn').addEventListener('click', showSignupModal);
document.querySelectorAll('.close-modal').forEach(x => x.addEventListener('click', closeModals));
document.getElementById('switch-to-signup').addEventListener('click', showSignupModal);
document.getElementById('switch-to-login').addEventListener('click', showLoginModal);


// ==========================================
// AUTHENTICATION FETCHER
// ==========================================
document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btnText = document.getElementById('login-btn-txt');
    const loader = document.getElementById('login-loader');
    const errObj = document.getElementById('login-error');
    
    btnText.classList.add('hidden');
    loader.classList.remove('hidden');
    errObj.classList.add('hidden');

    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                email: document.getElementById('login-email').value,
                password: document.getElementById('login-pass').value
            })
        });

        const data = await res.json();
        if(!res.ok) throw new Error(data.detail || "Authentication Failed.");

        authToken = data.access_token;
        localStorage.setItem('ninja_jwt', authToken);
        await initDash();
        closeModals();
        showPage('dashboard');
        
    } catch(err) {
        errObj.textContent = err.message;
        errObj.classList.remove('hidden');
    } finally {
        btnText.classList.remove('hidden');
        loader.classList.add('hidden');
    }
});

document.getElementById('signup-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btnText = document.getElementById('signup-btn-txt');
    const loader = document.getElementById('signup-loader');
    const errObj = document.getElementById('signup-error');
    
    btnText.classList.add('hidden');
    loader.classList.remove('hidden');
    errObj.classList.add('hidden');

    try {
        const res = await fetch('/api/register', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                email: document.getElementById('signup-email').value,
                password: document.getElementById('signup-pass').value
            })
        });

        const data = await res.json();
        if(!res.ok) throw new Error(data.detail || "Registration Failed.");

        authToken = data.access_token;
        localStorage.setItem('ninja_jwt', authToken);
        await initDash();
        closeModals();
        showPage('dashboard');
        
    } catch(err) {
        errObj.textContent = err.message;
        errObj.classList.remove('hidden');
    } finally {
        btnText.classList.remove('hidden');
        loader.classList.add('hidden');
    }
});

document.getElementById('user-logout-btn').addEventListener('click', () => {
    localStorage.removeItem('ninja_jwt');
    authToken = null;
    DOM.navAuth.classList.add('hidden');
    DOM.navUnauth.classList.remove('hidden');
    showPage('home');
});


// ==========================================
// DASHBOARD LOGIC
// ==========================================
async function initDash() {
    if(!authToken) return;
    try {
        const req = await fetch('/api/me', {
            headers: {'Authorization': `Bearer ${authToken}`}
        });
        
        if(!req.ok) {
            if(req.status === 401 || req.status === 403) throw new Error("Token expired");
            return;
        }

        currentUser = await req.json();
        
        // Populate UI
        DOM.navAuth.classList.remove('hidden');
        DOM.navUnauth.classList.add('hidden');
        DOM.creditsText.textContent = currentUser.credits.toLocaleString();
        
        document.getElementById('dash-user-email').textContent = currentUser.email.split('@')[0];
        document.getElementById('dash-credits-huge').textContent = currentUser.credits.toLocaleString();
        document.getElementById('dash-plan-huge').textContent = currentUser.plan;
        
        document.getElementById('dash-api-key').value = currentUser.api_key;
        document.getElementById('billing-tier').textContent = currentUser.plan;
        document.getElementById('billing-credits').textContent = currentUser.credits.toLocaleString();

        // Lock/Unlock Bulk Verifier
        const bulkLocked = document.getElementById('bulk-locked-ui');
        const bulkUnlocked = document.getElementById('bulk-unlocked-ui');
        const bulkBadge = document.getElementById('bulk-lock-badge');
        
        if(currentUser.plan === 'free') {
            bulkLocked.classList.remove('hidden');
            bulkUnlocked.classList.add('hidden');
            bulkBadge.textContent = "STARTER+ REQUIRED";
            bulkBadge.style.background = "var(--danger)";
        } else {
            bulkLocked.classList.add('hidden');
            bulkUnlocked.classList.remove('hidden');
            bulkBadge.textContent = "UNLOCKED";
            bulkBadge.style.background = "var(--success)";
        }
        
        initChart();
        
    } catch(err) {
        localStorage.removeItem('ninja_jwt');
        authToken = null;
        DOM.navAuth.classList.add('hidden');
        DOM.navUnauth.classList.remove('hidden');
    }
}

// ==========================================
// FREE VERIFIER
// ==========================================
const freeVerifyBtn = document.getElementById('free-verify-btn');
if(freeVerifyBtn) {
    freeVerifyBtn.addEventListener('click', async () => {
        const input = document.getElementById('free-verify-input').value;
        if(!input) return;

        // LocalStorage Tracking for Free Tier
        let freeCount = parseInt(localStorage.getItem('ninja_free_count') || "0");
        if(freeCount >= 10 && !authToken) {
            showLoginModal();
            return;
        }

        const btnText = document.getElementById('free-btn-text');
        const loader = document.getElementById('free-loader');
        const resBox = document.getElementById('free-result');
        
        btnText.classList.add('hidden');
        loader.classList.remove('hidden');
        resBox.classList.add('hidden');

        try {
            const req = await fetch('/api/verify-free', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ email: input })
            });
            
            const data = await req.json();
            if(!req.ok) throw new Error(data.detail || "Validation Error");
            
            if(!authToken) {
                freeCount++;
                localStorage.setItem('ninja_free_count', freeCount);
                document.getElementById('free-hint').textContent = `${10 - freeCount} free checks remaining today.`;
            }

            let blockNote = '';
            if (data.status === 'SPAM BLOCK') {
                blockNote = `<div style="margin-top: 0.5rem; padding: 0.5rem; background: rgba(255, 179, 0, 0.1); border-left: 3px solid var(--warning); font-size: 0.8rem; color: var(--warning);">⚠️ Our server IP is blocked by this mail provider. The email address may actually be valid. Consider this email as unverified rather than invalid.</div>`;
            }

            resBox.innerHTML = `
                <div class="flex flex-between align-center">
                    <strong>${data.email}</strong>
                    <span class="badge-${data.status.replace(' ', '').toLowerCase()}">${data.status}</span>
                </div>
                <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.5rem; text-align: left;">${data.details}</p>
                ${blockNote}
            `;
            resBox.classList.remove('hidden');

        } catch(err) {
            alert(err.message);
        } finally {
            loader.classList.add('hidden');
            btnText.classList.remove('hidden');
        }
    });
}

// ==========================================
// DASHBOARD SINGLE VERIFY (Paywalled)
// ==========================================
const authSingleBtn = document.getElementById('auth-single-btn');
if(authSingleBtn) {
    authSingleBtn.addEventListener('click', async () => {
        const input = document.getElementById('auth-single-inp').value;
        if(!input || !authToken) return;

        const btnText = document.getElementById('auth-single-text');
        const loader = document.getElementById('auth-single-loader');
        const resBox = document.getElementById('auth-single-res');
        
        btnText.classList.add('hidden');
        loader.classList.remove('hidden');
        resBox.classList.add('hidden');

        try {
            const req = await fetch('/api/verify', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${authToken}`
                },
                body: JSON.stringify({ email: input })
            });
            
            const data = await req.json();
            if(!req.ok) {
                if(req.status === 401 || req.status === 403) throw new Error("Unauthorized or Out of Credits");
                throw new Error(data.detail);
            }
            
            // Sync Credits Downward
            if(data.credits_remaining !== undefined) {
                currentUser.credits = data.credits_remaining;
                DOM.creditsText.textContent = currentUser.credits.toLocaleString();
                document.getElementById('dash-credits-huge').textContent = currentUser.credits.toLocaleString();
                document.getElementById('billing-credits').textContent = currentUser.credits.toLocaleString();
            }

            let blockNote = '';
            if (data.status === 'SPAM BLOCK') {
                blockNote = `<div style="margin-top: 0.5rem; padding: 0.5rem; background: rgba(255, 179, 0, 0.1); border-left: 3px solid var(--warning); font-size: 0.8rem; color: var(--warning);">⚠️ Our server IP is blocked by this mail provider. The email address may actually be valid. Consider this email as unverified rather than invalid.</div>`;
            }

            resBox.innerHTML = `
                <div class="flex flex-between align-center">
                    <strong>${data.email}</strong>
                    <span class="badge badge-${data.status.replace(' ', '').toLowerCase()}">${data.status}</span>
                </div>
                <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.5rem; text-align: left;">${data.details}</p>
                ${blockNote}
            `;
            resBox.classList.remove('hidden');

            // Append to table
            const rxTable = document.getElementById('recent-verifications-table');
            const h = document.createElement('div');
            h.innerHTML = `
                <div class="flex flex-between align-center mb-2 p-2" style="background: rgba(255,255,255,0.05); border-radius: 4px;">
                    <span style="font-size: 0.85rem;">${data.email}</span>
                    <span class="badge-${data.status.replace(' ', '').toLowerCase()}" style="font-size:0.7rem;">${data.status}</span>
                </div>
            `;
            rxTable.prepend(h);

        } catch(err) {
            alert(err.message);
        } finally {
            loader.classList.add('hidden');
            btnText.classList.remove('hidden');
        }
    });
}


// ==========================================
// BULK VERIFIER LOGIC
// ==========================================
let mockChartInstance = null;
function initChart() {
    if(mockChartInstance) return;
    const ctx = document.getElementById('dash-donut-chart').getContext('2d');
    mockChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Accepted', 'Rejected', 'Catch-All', 'Greylisted', 'Timeout'],
            datasets: [{
                data: [45, 25, 10, 10, 10],
                backgroundColor: [
                    '#00e676', '#ff3366', '#7b2fbe', '#a0a0b0', '#ffb300'
                ],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { color: '#f8f9fa' } }
            }
        }
    });
}

window.bulkResultsData = [];

window.addRowToTable = function(resultData) {
    const tableBody = document.getElementById('bulk-results-body');
    if (!tableBody) return;

    const tr = document.createElement('tr');
    tr.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
    const statusLabel = resultData.status || "UNKNOWN";
    const badgeClass = `badge badge-${statusLabel.replace(/\s+/g, '').toLowerCase()}`;

    // Map backend keys to what the table expects if necessary
    const syntaxIcon = resultData.syntax || resultData.syntax_valid ? '✅' : '❌';
    const mxIcon = resultData.mx || resultData.mx_found ? '✅' : '❌';
    const smtpIcon = resultData.smtp || resultData.smtp_valid ? '✅' : '❌';
    const disposable = resultData.disposable || resultData.is_disposable ? 'Yes' : 'No';
    const dispColor = (resultData.disposable || resultData.is_disposable) ? 'var(--danger)' : 'var(--text-muted)';

    tr.innerHTML = `
        <td class="p-2" style="font-size:0.9rem;">${resultData.email}</td>
        <td class="p-2"><span class="${badgeClass}" style="padding: 2px 6px; border-radius: 4px; font-size: 0.75rem;">${statusLabel}</span></td>
        <td class="p-2" style="font-size:0.9rem;">${resultData.score !== undefined ? resultData.score : '-'}</td>
        <td class="p-2" style="font-size:0.9rem;">${syntaxIcon}</td>
        <td class="p-2" style="font-size:0.9rem;">${mxIcon}</td>
        <td class="p-2" style="font-size:0.9rem;">${smtpIcon}</td>
        <td class="p-2" style="font-size:0.9rem; color: ${dispColor}">${disposable}</td>
    `;
    tableBody.appendChild(tr);

    // Update live stats
    if (typeof window.updateLiveStats === 'function') {
        window.updateLiveStats(statusLabel);
    }

    // Also update history feed
    const rxTable = document.getElementById('recent-verifications-table');
    if (rxTable) {
        const item = document.createElement('div');
        item.className = "flex flex-between align-center mb-2 p-2";
        item.style.background = "rgba(255,255,255,0.05)";
        item.style.borderRadius = "4px";
        item.innerHTML = `
            <span style="font-size: 0.85rem;">${resultData.email}</span>
            <span class="badge badge-${statusLabel.replace(/\s+/g, '').toLowerCase()}" style="font-size:0.7rem;">${statusLabel}</span>
        `;
        rxTable.prepend(item);
    }
};

async function processEmail(email, token) {
  const MAX_RETRIES = 3;
  let attempt = 0;
  
  while (attempt < MAX_RETRIES) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);
    
    try {
      console.log('Verifying:', email);
      const response = await fetch('/api/verify', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + token
        },
        body: JSON.stringify({ email: email }),
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      
      if (response.status === 429) {
        // Rate limited - wait and retry
        attempt++;
        await sleep(3000 * attempt); // 3s, 6s, 9s
        continue;
      }
      
      if (response.ok) {
        const data = await response.json();
        console.log('Response:', data);
        // Update global credits if returned
        if (data.credits_remaining !== undefined) {
            if (currentUser) currentUser.credits = data.credits_remaining;
            ['dash-credits-huge', 'nav-credits', 'billing-credits'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.textContent = data.credits_remaining.toLocaleString();
            });
        }
        return data;
      }
      
      throw new Error('HTTP ' + response.status);
      
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError') {
        return { 
          email, status: 'TIMEOUT', score: 30,
          syntax: true, mx: false, 
          smtp: false, disposable: false 
        };
      }
      attempt++;
      if (attempt >= MAX_RETRIES) {
        return { 
          email, status: 'TIMEOUT', score: 30,
          syntax: true, mx: false,
          smtp: false, disposable: false 
        };
      }
      await sleep(1000); // Wait bit before retry on network error
    }
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

const BULK_LARGE_THRESHOLD = 2000; // above this use background job (supports up to 1M)

async function startBulkVerify() {
  console.log('=== BULK VERIFY STARTED ===');
  const textarea = document.getElementById('bulk-email-input');

  const token = localStorage.getItem('ninja_jwt')
    || localStorage.getItem('token')
    || localStorage.getItem('access_token')
    || localStorage.getItem('jwt');

  if (!token) { alert('Please login first'); return; }

  const rawText = textarea ? textarea.value : '';
  const emails = rawText
    .split(/[\n,;]+/)
    .map(e => e.trim().toLowerCase())
    .filter(e => e.includes('@') && e.includes('.'));

  if (emails.length === 0) {
    alert('No emails found! Check textarea ID.');
    return;
  }

  const startBtn = document.getElementById('bulk-start-btn');
  const stopBtn = document.getElementById('bulk-stop-btn');
  const progressSection = document.getElementById('bulk-progress-section');
  const resultsTable = document.getElementById('bulk-results-table');
  const tbody = document.getElementById('bulk-results-body');
  const downloadBtn = document.getElementById('bulk-download-wrapper');
  const liveStats = document.getElementById('live-stats');

  if (startBtn) { startBtn.disabled = true; startBtn.innerHTML = '<span>Starting...</span>'; }
  if (stopBtn) stopBtn.style.display = 'inline-block';
  if (progressSection) progressSection.classList.remove('hidden');
  if (tbody) tbody.innerHTML = '';
  if (downloadBtn) downloadBtn.classList.add('hidden');

  // --- Large bulk (e.g. 1M): use background job, poll status, then download CSV ---
  if (emails.length > BULK_LARGE_THRESHOLD) {
    window.isVerifying = true;
    window._bulkJobId = null;
    try {
      const blob = new Blob([emails.join('\n')], { type: 'text/plain' });
      const formData = new FormData();
      formData.append('file', blob, 'emails.txt');
      const res = await fetch('/api/bulk-verify-large', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + token },
        body: formData
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.message || 'Upload failed');
      }
      const data = await res.json();
      window._bulkJobId = data.job_id;
      if (currentUser) currentUser.credits = data.credits_remaining;
      ['dash-credits-huge', 'nav-credits', 'billing-credits'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = (data.credits_remaining || 0).toLocaleString();
      });

      const total = data.total;
      const pText = document.getElementById('bulk-progress-text');
      const pBar = document.getElementById('bulk-progress-bar');
      while (window.isVerifying && window._bulkJobId) {
        const statusRes = await fetch('/api/bulk-verify/status/' + window._bulkJobId, {
          headers: { 'Authorization': 'Bearer ' + token }
        });
        if (!statusRes.ok) break;
        const st = await statusRes.json();
        if (pText) pText.textContent = 'Verifying ' + (st.processed || 0).toLocaleString() + ' of ' + (st.total || total).toLocaleString() + ' (' + (st.progress_pct || 0) + '%)';
        if (pBar) pBar.style.width = (st.progress_pct || 0) + '%';
        if (st.status === 'completed') {
          window.bulkResultsData = [];
          window.lastBulkResults = [];
          if (resultsTable) resultsTable.classList.add('hidden');
          if (downloadBtn) {
            downloadBtn.classList.remove('hidden');
            const dlBtn = document.getElementById('bulk-download-btn');
            if (dlBtn) {
              dlBtn.style.display = 'inline-block';
              dlBtn.onclick = () => downloadBulkJobCSV(window._bulkJobId, token);
            }
          }
          if (pText) pText.textContent = '✅ Complete! ' + (st.total || 0).toLocaleString() + ' emails processed. Download CSV below.';
          if (pBar) pBar.style.width = '100%';
          break;
        }
        if (st.status === 'failed') {
          if (pText) pText.textContent = '❌ Job failed: ' + (st.error || 'Unknown error');
          break;
        }
        await sleep(2500);
      }
    } catch (e) {
      alert('Bulk start failed: ' + (e.message || String(e)));
    } finally {
      window.isVerifying = false;
      if (startBtn) { startBtn.disabled = false; startBtn.innerHTML = '<span id="bulk-btn-text">🚀 Start Verification</span>'; }
      if (stopBtn) stopBtn.style.display = 'none';
    }
    return;
  }

  // --- Small/medium bulk: one-by-one (streaming results in UI) ---
  window.bulkResultsData = [];
  window.lastBulkResults = [];
  window.isVerifying = true;
  if (liveStats) {
    liveStats.style.display = 'flex';
    ['count-accepted', 'count-catchall', 'count-rejected', 'count-timeout', 'count-spamblock', 'count-mxerror', 'count-unverifiable', 'count-greylisted'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = '0';
    });
  }
  if (resultsTable) resultsTable.classList.remove('hidden');

  try {
    for (let i = 0; i < emails.length; i++) {
      if (!window.isVerifying) break;
      const email = emails[i];
      const pText = document.getElementById('bulk-progress-text');
      if (pText) pText.textContent = 'Verifying ' + (i + 1) + ' of ' + emails.length + ' emails...';
      const pBar = document.getElementById('bulk-progress-bar');
      if (pBar) pBar.style.width = ((i + 1) / emails.length * 100) + '%';
      const data = await processEmail(email, token);
      window.bulkResultsData.push(data);
      window.lastBulkResults.push(data);
      addRowToTable(data);
    }
  } finally {
    window.isVerifying = false;
    if (startBtn) { startBtn.disabled = false; startBtn.innerHTML = '<span id="bulk-btn-text">🚀 Start Verification</span>'; }
    if (stopBtn) stopBtn.style.display = 'none';
    const pText = document.getElementById('bulk-progress-text');
    if (pText) pText.textContent = '✅ Complete! ' + window.bulkResultsData.length + ' emails processed.';
    if (downloadBtn) {
      downloadBtn.classList.remove('hidden');
      const dlBtn = document.getElementById('bulk-download-btn');
      if (dlBtn) { dlBtn.style.display = 'inline-block'; dlBtn.onclick = () => downloadBulkCSV(); }
    }
  }
}

async function downloadBulkJobCSV(jobId, token) {
  if (!jobId || !token) return;
  try {
    const res = await fetch('/api/bulk-verify/download/' + jobId, { headers: { 'Authorization': 'Bearer ' + token } });
    if (!res.ok) throw new Error('Download failed');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'verified_' + jobId + '.csv';
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert('Download failed: ' + (e.message || String(e)));
  }
}

// Stop button function
function stopBulkVerify() {
  window.isVerifying = false;
}

function updateLiveStats(status) {
  const map = {
    'ACCEPTED': 'count-accepted',
    'CATCH-ALL': 'count-catchall',
    'REJECTED': 'count-rejected',
    'TIMEOUT': 'count-timeout',
    'SPAM BLOCK': 'count-spamblock',
    'MX ERROR': 'count-mxerror',
    'UNVERIFIABLE': 'count-unverifiable',
    'GREYLISTED': 'count-greylisted'
  };
  const id = map[status.toUpperCase()];
  if (id) {
    const el = document.getElementById(id);
    if (el) el.textContent = parseInt(el.textContent || 0) + 1;
  }
}

window.startBulkVerify = startBulkVerify;
window.stopBulkVerify = stopBulkVerify;
window.sleep = sleep;
window.updateLiveStats = updateLiveStats;

window.downloadBulkCSV = function() {
    if (!window.bulkResultsData || window.bulkResultsData.length === 0) return;
    
    const headers = ["Email", "Status", "Score", "Syntax", "MX", "SMTP", "Disposable"];
    const rows = window.bulkResultsData.map(r => [
        r.email,
        r.status,
        r.score || 0,
        r.syntax_valid,
        r.mx_found,
        r.smtp_valid,
        r.is_disposable
    ]);
    
    const csvContent = [
        headers.join(","),
        ...rows.map(row => row.join(","))
    ].join("\n");
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    
    const dateObj = new Date();
    const dateStr = dateObj.toISOString().split('T')[0];
    
    link.href = url;
    link.setAttribute('download', `verified_emails_${dateStr}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
};

const saveBtn = document.getElementById('bulk-save-btn');
if(saveBtn) {
    saveBtn.addEventListener('click', async () => {
        const filename = document.getElementById('bulk-save-filename').value || "export";
        if (!window.lastBulkResults || window.lastBulkResults.length === 0) return;
        saveBtn.textContent = "Saving...";
        
        try {
            const req = await fetch('/api/storage/save-results', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${authToken}`
                },
                body: JSON.stringify({
                    filename: filename,
                    results: window.lastBulkResults
                })
            });
            const data = await req.json();
            if(!req.ok) throw new Error(data.detail);
            
            saveBtn.textContent = "Saved to Storage ✅";
            saveBtn.style.background = "var(--success)";
            setTimeout(() => {
                saveBtn.textContent = "Save Results to Storage";
                saveBtn.style.background = "";
            }, 3000);
            
            loadUserFiles();
        } catch(err) {
            alert(err.message);
            saveBtn.textContent = "Save Results to Storage";
        }
    });
}

// Rating interaction script
const stars = document.querySelectorAll('.rating-stars span');
if (stars.length > 0) {
    stars.forEach(star => {
        star.addEventListener('click', (e) => {
            const val = parseInt(e.target.dataset.val);
            document.getElementById('feedback-rating').value = val;
            stars.forEach(s => {
                if (parseInt(s.dataset.val) <= val) {
                    s.style.opacity = '1';
                } else {
                    s.style.opacity = '0.3';
                }
            });
        });
    });

    document.getElementById('feedback-form').addEventListener('submit', (e) => {
        e.preventDefault();
        const msg = document.getElementById('feedback-msg').value;
        const name = document.getElementById('feedback-name').value || "Anonymous User";
        const btn = e.target.querySelector('button');
        
        btn.textContent = "Feedback Received!";
        btn.style.background = "var(--success)";
        setTimeout(() => {
            btn.textContent = "Submit Feedback";
            btn.style.background = "";
            e.target.reset();
            stars.forEach(s => s.style.opacity = '1');
            document.getElementById('feedback-rating').value = 5;
        }, 2000);
    });
}

// ==========================================
// FILE STORAGE LOGIC
// ==========================================
async function loadUserFiles() {
    if(!authToken) return;
    try {
        const reqUsage = await fetch('/api/storage/usage', {
            headers: {'Authorization': `Bearer ${authToken}`}
        });
        if(reqUsage.ok) {
            const usageData = await reqUsage.json();
            const mbUsed = (usageData.used_bytes / (1024*1024)).toFixed(2);
            document.getElementById('storage-usage-text').textContent = `Using ${mbUsed}MB of 1GB (${usageData.percentage}%)`;
            document.getElementById('storage-progress-fill').style.width = `${Math.min(usageData.percentage, 100)}%`;
        }

        const reqFiles = await fetch('/api/storage/files', {
            headers: {'Authorization': `Bearer ${authToken}`}
        });
        if(reqFiles.ok) {
            const filesData = await reqFiles.json();
            const tbody = document.getElementById('user-files-body');
            tbody.innerHTML = '';
            
            if(filesData.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">No files saved yet. Run a Bulk Verification to save results.</td></tr>`;
                return;
            }
            
            filesData.forEach(f => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${f.filename}</strong></td>
                    <td class="text-muted"><small>${(f.size / 1024).toFixed(2)} KB</small></td>
                    <td class="text-muted"><small>${new Date(f.date).toLocaleDateString()}</small></td>
                    <td>
                        <button class="btn btn-primary" style="padding: 0.2rem 0.5rem; font-size: 0.8rem; margin-right: 0.5rem;" onclick="downloadUserFile(${f.id})">Download</button>
                        <button class="btn btn-outline" style="padding: 0.2rem 0.5rem; font-size: 0.8rem; border-color: var(--danger); color: var(--danger);" onclick="deleteUserFile(${f.id})">Delete</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch(err) {
        console.error(err);
    }
}

window.downloadUserFile = async function(fileId) {
    if(!authToken) return;
    try {
        const req = await fetch(`/api/storage/download/${fileId}`, {
            headers: {'Authorization': `Bearer ${authToken}`}
        });
        if(!req.ok) throw new Error("Could not construct download");
        
        const blob = await req.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        
        let filename = "export.csv";
        const disposition = req.headers.get('content-disposition');
        if (disposition && disposition.indexOf('attachment') !== -1) {
            const filenameRegex = /filename[^;=\\n]*=((['"]).*?\\2|[^;\\n]*)/;
            const matches = filenameRegex.exec(disposition);
            if (matches != null && matches[1]) { 
                filename = matches[1].replace(/['"]/g, '');
            }
        }
        
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
    } catch(err) {
        alert(err.message);
    }
};

window.deleteUserFile = async function(fileId) {
    if(!authToken || !confirm("Delete this file permanently?")) return;
    try {
        const req = await fetch(`/api/storage/delete/${fileId}`, {
            method: 'DELETE',
            headers: {'Authorization': `Bearer ${authToken}`}
        });
        if(req.ok) {
            loadUserFiles();
        } else {
            const data = await req.json();
            throw new Error(data.detail);
        }
    } catch(err) {
        alert(err.message);
    }
};

// Hook into initDash
const originalInitDash = initDash;
initDash = async function() {
    await originalInitDash();
    await loadUserFiles();
    showDashTab('overview');
};

// Auto init dashboard if user token
initDash();

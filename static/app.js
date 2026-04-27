// State & Utilities
let authToken = localStorage.getItem('ninja_jwt');
let currentUser = null;
let currentView = 'page-home';
window.lastBulkResults = [];
window._bulkIsPaused = false;

// ==========================================
// THEME TOGGLE
// ==========================================
// Apply saved theme on load
(function() {
    const saved = localStorage.getItem('ninja_theme');
    if (saved === 'light') {
        document.body.classList.add('light-theme');
        const btn = document.getElementById('theme-toggle');
        if (btn) btn.textContent = '️';
    }
})();

// ==========================================
// BULK JOB PAUSE / RESUME
// ==========================================
async function toggleBulkPause() {
    const pauseBtn = document.getElementById('bulk-pause-btn');
    const token = localStorage.getItem('ninja_jwt') || localStorage.getItem('token');
    if (!token || !window._bulkJobId) {
        // For small bulk jobs (frontend-side), toggle pause flag
        window._bulkIsPaused = !window._bulkIsPaused;
        if (pauseBtn) {
            pauseBtn.textContent = window._bulkIsPaused ? '▶ Resume' : '⏸ Pause';
            pauseBtn.style.background = window._bulkIsPaused
                ? 'linear-gradient(135deg,#10b981,#059669)'
                : 'linear-gradient(135deg,#f59e0b,#d97706)';
        }
        return;
    }
    try {
        if (!window._bulkIsPaused) {
            await fetch('/api/bulk-verify/pause/' + window._bulkJobId, {
                method: 'POST', headers: { 'Authorization': 'Bearer ' + token }
            });
            window._bulkIsPaused = true;
            if (pauseBtn) {
                pauseBtn.textContent = '▶ Resume';
                pauseBtn.style.background = 'linear-gradient(135deg,#10b981,#059669)';
            }
        } else {
            await fetch('/api/bulk-verify/resume/' + window._bulkJobId, {
                method: 'POST', headers: { 'Authorization': 'Bearer ' + token }
            });
            window._bulkIsPaused = false;
            if (pauseBtn) {
                pauseBtn.textContent = '⏸ Pause';
                pauseBtn.style.background = 'linear-gradient(135deg,#f59e0b,#d97706)';
            }
        }
    } catch(e) {
        console.error('Pause/Resume error:', e);
    }
}

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

    // Fetch Dynamic Content if applicable
    const dynamicContainer = document.getElementById('dynamic-content-' + pageName);
    if (dynamicContainer) {
        fetch(`/api/page/${pageName}`)
            .then(res => res.json())
            .then(data => {
                if (data && data.html_content) {
                    dynamicContainer.innerHTML = data.html_content;
                }
            })
            .catch(err => console.error("Could not fetch page content", err));
    }
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
    document.getElementById('forgot-modal').classList.add('hidden');
    document.getElementById('otp-modal').classList.add('hidden');
}

window.showForgotModal = function() {
    DOM.overlay.classList.remove('hidden');
    document.getElementById('forgot-modal').classList.remove('hidden');
    DOM.loginModal.classList.add('hidden');
    DOM.signupModal.classList.add('hidden');
    document.getElementById('otp-modal').classList.add('hidden');
}

window.showOtpModal = function(email, action) {
    DOM.overlay.classList.remove('hidden');
    document.getElementById('otp-modal').classList.remove('hidden');
    DOM.loginModal.classList.add('hidden');
    DOM.signupModal.classList.add('hidden');
    document.getElementById('forgot-modal').classList.add('hidden');
    
    document.getElementById('otp-email').value = email;
    document.getElementById('otp-action').value = action;
    
    if(action === 'forgot') {
        document.getElementById('otp-new-password-group').classList.remove('hidden');
        document.getElementById('otp-new-password-group').style.display = 'flex';
        document.getElementById('otp-new-pass').required = true;
    } else {
        document.getElementById('otp-new-password-group').classList.add('hidden');
        document.getElementById('otp-new-password-group').style.display = 'none';
        document.getElementById('otp-new-pass').required = false;
    }
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
        const email = document.getElementById('signup-email').value;
        const res = await fetch('/api/register', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                email: email,
                password: document.getElementById('signup-pass').value
            })
        });

        const data = await res.json();
        if(!res.ok) throw new Error(data.detail || "Registration Failed.");

        showOtpModal(email, 'signup');
        
    } catch(err) {
        errObj.textContent = err.message;
        errObj.classList.remove('hidden');
    } finally {
        btnText.classList.remove('hidden');
        loader.classList.add('hidden');
    }
});

const forgotForm = document.getElementById('forgot-form');
if(forgotForm) {
    forgotForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btnText = document.getElementById('forgot-btn-txt');
        const loader = document.getElementById('forgot-loader');
        const msgObj = document.getElementById('forgot-msg');
        
        btnText.classList.add('hidden');
        loader.classList.remove('hidden');
        msgObj.classList.add('hidden');
        
        try {
            const email = document.getElementById('forgot-email').value;
            const res = await fetch('/api/forgot-password', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ email: email })
            });

            const data = await res.json();
            if(!res.ok) throw new Error(data.detail || "Failed to send reset code.");

            showOtpModal(email, 'forgot');

        } catch(err) {
            msgObj.textContent = err.message;
            msgObj.style.color = "var(--danger)";
            msgObj.style.background = "rgba(255,0,0,0.1)";
            msgObj.classList.remove('hidden');
        } finally {
            btnText.classList.remove('hidden');
            loader.classList.add('hidden');
        }
    });
}

const otpForm = document.getElementById('otp-form');
if(otpForm) {
    otpForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btnText = document.getElementById('otp-btn-txt');
        const loader = document.getElementById('otp-loader');
        const errObj = document.getElementById('otp-error');
        const successObj = document.getElementById('otp-success');
        
        btnText.classList.add('hidden');
        loader.classList.remove('hidden');
        errObj.classList.add('hidden');
        successObj.classList.add('hidden');
        
        try {
            const email = document.getElementById('otp-email').value;
            const action = document.getElementById('otp-action').value;
            const otpCode = document.getElementById('otp-code').value;
            
            if(action === 'forgot') {
                const newPass = document.getElementById('otp-new-pass').value;
                const res = await fetch('/api/reset-password', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ email: email, otp: otpCode, new_password: newPass })
                });

                const data = await res.json();
                if(!res.ok) throw new Error(data.detail || "Reset Failed.");
                
                successObj.textContent = "Password updated! Redirecting to login...";
                successObj.classList.remove('hidden');
                
                setTimeout(() => {
                    showLoginModal();
                }, 2000);
            } else {
                const res = await fetch('/api/verify-otp', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ email: email, otp: otpCode })
                });

                const data = await res.json();
                if(!res.ok) throw new Error(data.detail || "Verification Failed.");
                
                authToken = data.access_token;
                localStorage.setItem('ninja_jwt', authToken);
                await initDash();
                closeModals();
                showPage('dashboard');
            }
        } catch(err) {
            errObj.textContent = err.message;
            errObj.classList.remove('hidden');
        } finally {
            btnText.classList.remove('hidden');
            loader.classList.add('hidden');
        }
    });
}

document.getElementById('user-logout-btn').addEventListener('click', () => {
    localStorage.removeItem('ninja_jwt');
    authToken = null;
    DOM.navAuth.classList.add('hidden');
    DOM.navUnauth.classList.remove('hidden');
    showPage('home');
});


// ==========================================
// DASHBOARD LOGIC (refreshUserState)
// ==========================================
async function refreshUserState() {
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
        
        if(document.getElementById('dash-total-verifications')) {
            document.getElementById('dash-total-verifications').textContent = (currentUser.total_verifications || 0).toLocaleString();
        }
        if(document.getElementById('dash-monthly-verifications')) {
            document.getElementById('dash-monthly-verifications').textContent = (currentUser.monthly_verifications || 0).toLocaleString();
        }

        if(document.getElementById('dash-api-key')) {
            document.getElementById('dash-api-key').value = currentUser.api_key;
        }
        if(document.getElementById('dash-overview-api')) {
            document.getElementById('dash-overview-api').value = currentUser.api_key;
        }
        document.getElementById('billing-tier').textContent = currentUser.plan;
        document.getElementById('billing-credits').textContent = currentUser.credits.toLocaleString();

        // Lock/Unlock Bulk Verifier
        const bulkLocked = document.getElementById('bulk-locked-ui');
        const bulkUnlocked = document.getElementById('bulk-unlocked-ui');
        const bulkBadge = document.getElementById('bulk-lock-badge');
        
        // Multi-condition check for unlocking Bulk UI
        const hasBulkAccess = 
            currentUser.plan !== 'free' || 
            currentUser.has_partner_license === true || 
            currentUser.partner_status === 'approved' || 
            currentUser.credits > 500;

        if(!hasBulkAccess) {
            bulkLocked.classList.remove('hidden');
            bulkUnlocked.classList.add('hidden');
            bulkUnlocked.style.opacity = '0';
            bulkBadge.textContent = "STARTER+ REQUIRED";
            bulkBadge.style.background = "var(--danger)";
        } else {
            bulkLocked.classList.add('hidden');
            bulkUnlocked.classList.remove('hidden');
            
            // Smoothly display the unlocked section
            setTimeout(() => {
                bulkUnlocked.style.transition = 'opacity 0.5s ease-in-out';
                bulkUnlocked.style.opacity = '1';
            }, 50);

            bulkBadge.textContent = "UNLOCKED";
            bulkBadge.style.background = "var(--success)";
        }
        
        // Partner UI Update
        const statusEl = document.getElementById('partner-link-status');
        if (statusEl) {
            if (currentUser.partner_status === 'pending') {
                statusEl.textContent = "Your link request is Pending partner approval...";
                statusEl.style.color = "var(--warning)";
                statusEl.style.display = 'block';
            } else if (currentUser.partner_status === 'approved') {
                statusEl.innerHTML = `Active! Sharing Partner's limit.<br>Used: ${currentUser.partner_credits_used_today || 0} / ${currentUser.partner_daily_limit} today`;
                statusEl.style.color = "var(--success)";
                statusEl.style.display = 'block';
            } else {
                statusEl.style.display = 'none';
            }
        }
        
        initChart();
        
    } catch(err) {
        localStorage.removeItem('ninja_jwt');
        authToken = null;
        DOM.navAuth.classList.add('hidden');
        DOM.navUnauth.classList.remove('hidden');
    }
}

// Keep initDash alias for backwards compatibility
window.initDash = refreshUserState;
window.refreshUserState = refreshUserState;

function showToast(message) {
    const toast = document.createElement('div');
    toast.textContent = message;
    toast.style.cssText = "position:fixed;bottom:20px;right:20px;background:#00f260;color:#0f172a;padding:15px;border-radius:5px;font-weight:bold;z-index:9999;transition:opacity 0.4s ease-in-out;opacity:0;box-shadow:0 10px 25px rgba(0,242,96,0.3);";
    document.body.appendChild(toast);
    setTimeout(() => toast.style.opacity = '1', 50);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 400);
    }, 4500);
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
                blockNote = `<div style="margin-top: 0.5rem; padding: 0.5rem; background: rgba(255, 179, 0, 0.1); border-left: 3px solid var(--warning); font-size: 0.8rem; color: var(--warning);">️ Our server IP is blocked by this mail provider. The email address may actually be valid. Consider this email as unverified rather than invalid.</div>`;
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
                blockNote = `<div style="margin-top: 0.5rem; padding: 0.5rem; background: rgba(255, 179, 0, 0.1); border-left: 3px solid var(--warning); font-size: 0.8rem; color: var(--warning);">️ Our server IP is blocked by this mail provider. The email address may actually be valid. Consider this email as unverified rather than invalid.</div>`;
            }

            resBox.innerHTML = `
                <div class="flex flex-between align-center">
                    <strong>${data.email}</strong>
                    <span class="badge badge-${data.status.replace(' ', '').toLowerCase()}">${data.status}</span>
                </div>
                <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.5rem; text-align: left;">${data.details}</p>
                <div style="font-size: 0.75rem; color: var(--secondary); margin-top: 0.3rem; font-family: monospace;">Verified via: ${data.used_proxy || 'Direct IP'}</div>
                ${blockNote}
            `;
            resBox.classList.remove('hidden');
            
            // Update realtime chart
            if(typeof window.updateLiveStats === 'function') {
                window.updateLiveStats(data.status);
            }

            // Append to table
            const rxTable = document.getElementById('recent-verifications-table');
            const h = document.createElement('div');
            h.innerHTML = `
                <div class="flex flex-between align-center mb-2 p-2" style="background: rgba(255,255,255,0.05); border-radius: 4px;">
                    <span style="font-size: 0.85rem;">${data.email}</span>
                    <span class="badge-${data.status.replace(' ', '').toLowerCase()}" style="font-size:0.7rem;">${data.status}</span>
                </div>
            `;
            if (rxTable) {
                rxTable.prepend(h);
            }
            const rxHistory = document.getElementById('history-verifications-table');
            if (rxHistory) {
                rxHistory.prepend(h.cloneNode(true));
            }

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

// Live pie chart counters
const liveChartCounts = { accepted: 0, catchall: 0, rejected: 0, spamblock: 0, invalid: 0, greylisted: 0, disposable: 0 };

function initChart() {
    if(mockChartInstance) return;
    const canvasEl = document.getElementById('dash-donut-chart');
    if (!canvasEl) return;
    const ctx = canvasEl.getContext('2d');
    const isLight = document.body.classList.contains('light-theme');
    const legendColor = isLight ? '#1a1a2e' : '#f8f9fa';
    mockChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['✅ Accepted', '🔄 Catch-All', '❌ Rejected', '🚫 Spam Block', '⚠️ Invalid', '⏳ Greylisted', '🗑️ Disposable'],
            datasets: [{
                data: [0, 0, 0, 0, 0, 0, 0],
                backgroundColor: [
                    '#00f260', '#00e676', '#ff3366', '#ff9800', '#607d8b', '#ffc107', '#e65100'
                ],
                borderWidth: 2,
                borderColor: isLight ? '#f0f4f8' : '#050505',
                hoverOffset: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 400 },
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: legendColor,
                        font: { family: 'Outfit', size: 12 },
                        padding: 12,
                        usePointStyle: true,
                        pointStyleWidth: 10
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            const total = ctx.chart.data.datasets[0].data.reduce((a, b) => a + b, 0);
                            const pct = total > 0 ? Math.round(ctx.parsed / total * 100) : 0;
                            return ` ${ctx.label}: ${ctx.parsed} (${pct}%)`;
                        }
                    }
                }
            }
        }
    });
}

function updateChartFromCounts() {
    if (!mockChartInstance) return;
    const d = liveChartCounts;
    mockChartInstance.data.datasets[0].data = [
        d.accepted, d.catchall, d.rejected, d.spamblock, d.invalid, d.greylisted, d.disposable
    ];
    mockChartInstance.update('none');
}

window.updateLiveStats = function(status, isDisposable) {
    const s = (status || '').toUpperCase().replace(/\s+/g, '');
    const countMap = {
        'ACCEPTED': 'count-accepted',
        'CATCH_ALL': 'count-catchall', 'CATCHALL': 'count-catchall',
        'REJECTED': 'count-rejected', 'LIKELYINVALID': 'count-rejected', 'INVALID': 'count-rejected',
        'SPAMBLOCK': 'count-spamblock', 'SPAM BLOCK': 'count-spamblock',
        'LIKELYINVALID': 'count-mxerror', 'NOMX': 'count-mxerror',
        'GREYLISTED': 'count-greylisted',
    };
    const chartMap = {
        'ACCEPTED': 'accepted',
        'CATCH_ALL': 'catchall', 'CATCHALL': 'catchall',
        'REJECTED': 'rejected', 'LIKELYINVALID': 'invalid', 'INVALID': 'invalid',
        'SPAMBLOCK': 'spamblock',
        'GREYLISTED': 'greylisted',
    };
    const elId = countMap[s];
    if (elId) {
        const el = document.getElementById(elId);
        if (el) el.textContent = parseInt(el.textContent || '0') + 1;
    }
    const chartKey = chartMap[s];
    if (chartKey) liveChartCounts[chartKey]++;
    if (isDisposable) {
        liveChartCounts.disposable++;
        const dispEl = document.getElementById('count-disposable');
        if (dispEl) dispEl.textContent = parseInt(dispEl.textContent || '0') + 1;
    }
    updateChartFromCounts();
};

window.bulkResultsData = [];

window.addRowToTable = function(resultData) {
    const tableBody = document.getElementById('bulk-results-body');
    if (!tableBody) return;

    const tr = document.createElement('tr');
    tr.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
    const statusLabel = resultData.status || "UNKNOWN";
    const badgeClass = `badge badge-${statusLabel.replace(/\s+/g, '').toLowerCase()}`;

    // Map backend keys to what the table expects if necessary
    const syntaxIcon = resultData.syntax || resultData.syntax_valid ? '' : '';
    const mxIcon = resultData.mx || resultData.mx_found ? '' : '';
    const smtpIcon = resultData.smtp || resultData.smtp_valid ? '' : '';
    const disposable = resultData.disposable || resultData.is_disposable ? 'Yes' : 'No';
    const dispColor = (resultData.disposable || resultData.is_disposable) ? 'var(--danger)' : 'var(--text-muted)';

    tr.innerHTML = `
        <td class="p-2" style="font-size:0.9rem;">${resultData.email}</td>
        <td class="p-2"><span class="${badgeClass}" style="padding: 2px 6px; border-radius: 4px; font-size: 0.75rem;">${statusLabel}</span></td>
        <td class="p-2" style="font-size:0.8rem; font-family: monospace; color: var(--secondary);">${resultData.used_proxy || 'Direct'}</td>
        <td class="p-2" style="font-size:0.9rem;">${resultData.score !== undefined ? resultData.score : '-'}</td>
        <td class="p-2" style="font-size:0.9rem;">${syntaxIcon}</td>
        <td class="p-2" style="font-size:0.9rem;">${mxIcon}</td>
        <td class="p-2" style="font-size:0.9rem;">${smtpIcon}</td>
        <td class="p-2" style="font-size:0.9rem; color: ${dispColor}">${disposable}</td>
    `;
    tableBody.appendChild(tr);

    // Update live stats and live pie chart
    const isDisp = !!(resultData.disposable || resultData.is_disposable);
    if (typeof window.updateLiveStats === 'function') {
        window.updateLiveStats(statusLabel, isDisp);
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

const BULK_LARGE_THRESHOLD = 9999999; // Force all bulk uploads to use one-by-one frontend processing

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
  const pauseBtn = document.getElementById('bulk-pause-btn');
  if (pauseBtn) {
      pauseBtn.style.display = 'inline-block';
      pauseBtn.textContent = '⏸ Pause';
      pauseBtn.style.background = 'linear-gradient(135deg,#f59e0b,#d97706)';
  }
  if (progressSection) progressSection.classList.remove('hidden');
  if (tbody) tbody.innerHTML = '';
  if (downloadBtn) downloadBtn.classList.add('hidden');

  // Reset live chart counts
  Object.keys(liveChartCounts).forEach(k => liveChartCounts[k] = 0);
  if (mockChartInstance) updateChartFromCounts();
  window._bulkIsPaused = false;
  window._bulkJobId = null;

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
          if (pText) pText.textContent = ' Complete! ' + (st.total || 0).toLocaleString() + ' emails processed. Download CSV below.';
          if (pBar) pBar.style.width = '100%';
          break;
        }
        if (st.status === 'paused') {
          if (pText) pText.textContent = '⏸ Job paused at ' + (st.processed || 0).toLocaleString() + '/' + (st.total || 0).toLocaleString() + ' — click Resume to continue.';
          await sleep(3000);
          continue;
        }
        if (st.status === 'failed') {
          if (pText) pText.textContent = ' Job failed: ' + (st.error || 'Unknown error');
          break;
        }
        if (st.status === 'cancelled') {
          if (pText) pText.textContent = ' Job cancelled.';
          break;
        }
        await sleep(2500);
      }
    } catch (e) {
      alert('Bulk start failed: ' + (e.message || String(e)));
    } finally {
      window.isVerifying = false;
      if (startBtn) { startBtn.disabled = false; startBtn.innerHTML = '<span id="bulk-btn-text"> Start Verification</span>'; }
      if (stopBtn) stopBtn.style.display = 'none';
      if (pauseBtn) pauseBtn.style.display = 'none';
    }
    return;
  }

  // --- Small/medium bulk: one-by-one (streaming results in UI) ---
  window.bulkResultsData = [];
  window.lastBulkResults = [];
  window.isVerifying = true;
  if (liveStats) {
    liveStats.style.display = 'flex';
    ['count-accepted', 'count-catchall', 'count-rejected', 'count-spamblock', 'count-mxerror', 'count-greylisted', 'count-disposable'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = '0';
    });
  }
  if (resultsTable) resultsTable.classList.remove('hidden');

  try {
    for (let i = 0; i < emails.length; i++) {
      if (!window.isVerifying) break;
      // Handle pause for small bulk
      while (window._bulkIsPaused && window.isVerifying) {
          await sleep(500);
      }
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
    window._bulkIsPaused = false;
    if (startBtn) { startBtn.disabled = false; startBtn.innerHTML = '<span id="bulk-btn-text"> Start Verification</span>'; }
    if (stopBtn) stopBtn.style.display = 'none';
    if (pauseBtn) pauseBtn.style.display = 'none';
    const pText = document.getElementById('bulk-progress-text');
    if (pText) pText.textContent = ' Complete! ' + window.bulkResultsData.length + ' emails processed.';
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
  window._bulkIsPaused = false;
  const pauseBtn = document.getElementById('bulk-pause-btn');
  if (pauseBtn) { pauseBtn.style.display = 'none'; pauseBtn.textContent = '⏸ Pause'; }
}

window.startBulkVerify = startBulkVerify;
window.stopBulkVerify = stopBulkVerify;
window.sleep = sleep;

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
            
            saveBtn.textContent = "Saved to Storage ";
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
    await loadPartnerDashboard();
    showDashTab('overview');
};

async function loadPartnerDashboard() {
    if(!authToken) return;
    try {
        const [reqP, reqA] = await Promise.all([
            fetch('/api/partner/requests', { headers: {'Authorization': `Bearer ${authToken}`} }),
            fetch('/api/partner/users', { headers: {'Authorization': `Bearer ${authToken}`} })
        ]);
        
        if(reqP.ok && reqA.ok) {
            const pending = await reqP.json();
            const approved = await reqA.json();
            
            const tbodyP = document.getElementById('partner-requests-body');
            if (tbodyP) {
                if (pending.length === 0) {
                    tbodyP.innerHTML = '<tr><td colspan="4" class="text-muted text-center p-3">No pending requests.</td></tr>';
                } else {
                    tbodyP.innerHTML = '';
                    pending.forEach(u => {
                        tbodyP.innerHTML += `
                            <tr>
                                <td>${u.email}</td>
                                <td>${new Date(u.date).toLocaleDateString()}</td>
                                <td><input type="number" id="limit_${u.id}" class="input-modern" value="1000" style="width:100px; padding:0.2rem; background:rgba(0,0,0,0.5); border:1px solid var(--border-color); color:white;" min="1"></td>
                                <td>
                                    <button class="btn btn-primary" style="padding: 0.2rem 0.6rem; font-size: 0.8rem;" onclick="approvePartner(${u.id}, true)">Approve</button>
                                    <button class="btn btn-outline" style="padding: 0.2rem 0.6rem; font-size: 0.8rem; border-color: var(--danger); color: var(--danger);" onclick="approvePartner(${u.id}, false)">Reject</button>
                                </td>
                            </tr>
                        `;
                    });
                }
            }

            const tbodyA = document.getElementById('partner-users-body');
            if (tbodyA) {
                if (approved.length === 0) {
                    tbodyA.innerHTML = '<tr><td colspan="5" class="text-muted text-center p-3">No active linked users.</td></tr>';
                } else {
                    tbodyA.innerHTML = '';
                    approved.forEach(u => {
                        const tr = document.createElement('tr');

                        const tdEmail = document.createElement('td');
                        tdEmail.textContent = u.email;

                        const tdLimit = document.createElement('td');
                        tdLimit.innerHTML = `<input type="number" id="update_limit_${u.id}" class="input-modern" value="${u.daily_limit}" style="width:100px; padding:0.2rem; background:rgba(0,0,0,0.5); border:1px solid var(--border-color); color:white;" min="1">`;

                        const tdUsed = document.createElement('td');
                        tdUsed.textContent = u.used_today;

                        const tdLifetime = document.createElement('td');
                        tdLifetime.style.cssText = 'color: var(--primary); font-weight: 600;';
                        tdLifetime.textContent = (u.used_lifetime || 0).toLocaleString();

                        const tdAction = document.createElement('td');
                        
                        const btnUpdate = document.createElement('button');
                        btnUpdate.className = 'btn btn-primary';
                        btnUpdate.style.cssText = 'padding: 0.2rem 0.6rem; font-size: 0.8rem; margin-right: 0.5rem;';
                        btnUpdate.textContent = 'Update';
                        btnUpdate.addEventListener('click', () => updatePartnerLimit(u.id));
                        tdAction.appendChild(btnUpdate);

                        const btnRevoke = document.createElement('button');
                        btnRevoke.className = 'btn btn-outline';
                        btnRevoke.style.cssText = 'padding: 0.2rem 0.6rem; font-size: 0.8rem; border-color: var(--danger); color: var(--danger);';
                        btnRevoke.textContent = 'Revoke';
                        btnRevoke.addEventListener('click', () => revokePartner(u.id));
                        tdAction.appendChild(btnRevoke);

                        tr.appendChild(tdEmail);
                        tr.appendChild(tdLimit);
                        tr.appendChild(tdUsed);
                        tr.appendChild(tdLifetime);
                        tr.appendChild(tdAction);
                        tbodyA.appendChild(tr);
                    });
                }
            }
        }
    } catch(err) {
        console.error("Partner dash error: ", err);
    }
}

window.approvePartner = async function(userId, isApprove) {
    const limitInput = document.getElementById(`limit_${userId}`);
    const limit = limitInput ? parseInt(limitInput.value) : 1000;
    
    if (isApprove && isNaN(limit)) {
        alert("Invalid daily limit");
        return;
    }

    try {
        const endpoint = isApprove ? '/api/partner/approve' : '/api/partner/reject';
        const payload = isApprove ? { user_id: userId, daily_limit: limit } : { user_id: userId };
        
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error("Action failed");
        loadPartnerDashboard();
    } catch (err) {
        alert(err.message);
    }
};

window.updatePartnerLimit = async function(userId) {
    const limitInput = document.getElementById(`update_limit_${userId}`);
    const limit = limitInput ? parseInt(limitInput.value) : null;
    
    if (!limit || isNaN(limit)) {
        alert("Invalid daily limit");
        return;
    }

    try {
        const res = await fetch('/api/partner/update-limit', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({ user_id: userId, daily_limit: limit })
        });
        if (!res.ok) throw new Error("Update limit failed");
        if (typeof showToast === "function") {
            showToast("Limit updated successfully!");
        } else {
            alert("Limit updated successfully!");
        }
        loadPartnerDashboard();
    } catch (err) {
        alert(err.message);
    }
};

window.revokePartner = async function(userId) {
    if (!confirm("Are you sure you want to revoke this user's license access?")) return;
    try {
        const res = await fetch(`/api/partner/remove/${userId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        if (!res.ok) throw new Error("Revoke failed");
        loadPartnerDashboard();
    } catch (err) {
        alert(err.message);
    }
};

window.linkPartnerLicense = async function() {
    const pk = document.getElementById('partner-link-input').value;
    const btn = document.getElementById('btn-link-partner');
    try {
        if(btn) btn.textContent = "Linking...";
        const res = await fetch('/api/link-key', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({ partner_key: pk })
        });
        
        const data = await res.json();
        if(!res.ok) throw new Error(data.detail || "Failed to link partner key");
        
        btn.textContent = "Request Sent!";
        btn.style.background = "var(--success)";
        
        // Immediately fetch updated user data & unlock UI smoothly
        await refreshUserState();
        showToast("Partner access activated! Bulk tools are now unlocked.");
        
        setTimeout(() => {
            btn.textContent = "Link Account";
            btn.style.background = "";
        }, 2000);
    } catch(err) {
        alert(err.message);
    } finally {
        if(btn && btn.textContent !== "Request Sent!") btn.textContent = "Link Account";
    }
}

// Auto init dashboard if user token
initDash();

window.generateNewApiKey = async function() {
    if(!confirm("Are you sure? Your old API key will immediately stop working.")) return;
    try {
        const res = await fetch('/api/keys', {
            method: 'POST',
            headers: {'Authorization': `Bearer ${authToken}`}
        });
        if(!res.ok) throw new Error("Failed to generate key");
        
        const data = await res.json();
        
        const modalHtml = `
        <div id="apikey-modal" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); z-index:9999; display:flex; align-items:center; justify-content:center;">
            <div style="background:#222; padding:2rem; border-radius:10px; max-width:500px; text-align:center; border: 1px solid var(--primary);">
                <h2 style="color:var(--danger); margin-top:0;">️ IMPORTANT</h2>
                <p>${data.message}</p>
                <input type="text" id="new-key-value" value="${data.api_key}" readonly style="width:100%; padding:10px; background:#111; color:#0f0; border:1px solid #444; margin:15px 0;">
                <button onclick="navigator.clipboard.writeText(document.getElementById('new-key-value').value); alert('Copied!')" class="btn btn-outline" style="color: white; border-color: white;">Copy to Clipboard</button>
                <div style="margin-top:20px;">
                    <button onclick="document.getElementById('apikey-modal').remove()" class="btn btn-primary w-100">I have saved it</button>
                </div>
            </div>
        </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        const masked = "evs_...••••••••" + data.api_key.slice(-8);
        if(document.getElementById('dash-api-key')) {
            document.getElementById('dash-api-key').value = masked;
        }
        if(document.getElementById('dash-overview-api')) {
            document.getElementById('dash-overview-api').value = masked;
        }
        
    } catch(e) {
        alert(e.message);
    }
}

window.buyPack = async function(packName) {
    if(!authToken) return alert("Please login first");
    try {
        const res = await fetch('/billing/create-checkout', {
            method: 'POST',
            headers: {'Authorization': `Bearer ${authToken}`, 'Content-Type': 'application/json'},
            body: JSON.stringify({pack: packName})
        });
        const data = await res.json();
        if(data.checkout_url) {
            window.location.href = data.checkout_url;
        } else {
            alert("Error: " + data.detail);
        }
    } catch(e) {
        alert("Payment Error: " + e.message);
    }
};


window.showForgotModal = function() {
    DOM.overlay.classList.remove('hidden');
    DOM.loginModal.classList.add('hidden');
    DOM.signupModal.classList.add('hidden');
    const fm = document.getElementById('forgot-modal');
    if (fm) fm.classList.remove('hidden');
}


/* ADMIN.JS - PREMIUM REWRITE */
const DOM = {
    authView: document.getElementById('admin-auth-view'),
    dashView: document.getElementById('admin-dashboard-view'),
    userInp: document.getElementById('admin-user-input'),
    passInp: document.getElementById('admin-pass-input'),
    loginBtn: document.getElementById('admin-login-btn'),
    btnText: document.getElementById('admin-btn-text'),
    loader: document.getElementById('admin-loader'),
    errorMsg: document.getElementById('admin-error-msg'),
    navBtns: document.querySelectorAll('.nav-btn:not(.logout)'),
    panels: document.querySelectorAll('.admin-panel'),
    logoutBtn: document.getElementById('admin-logout-btn'),
    totalUsers: document.getElementById('stats-total-users'),
    verifsToday: document.getElementById('stats-verifs-today'),
    verifsMonth: document.getElementById('stats-verifs-month'),
    verifsAll: document.getElementById('stats-verifs-all'),
    statsChart: document.getElementById('admin-stats-chart'),
    usersBody: document.getElementById('admin-users-body'),
    searchInp: document.getElementById('user-search'),
    keysBody: document.getElementById('admin-keys-body'),
    userModal: document.getElementById('user-modal-overlay')
};

let adminToken = localStorage.getItem('admin_token');
let allUsers = [];
let allKeys = [];
let chartInstance = null;
let currentViewUserEmail = null;
let statsInterval = null;

async function init() {
    if (adminToken) {
        await loadDashboard();
        startStatsPolling();
    } else {
        showAuth();
    }
}

function showAuth() {
    DOM.dashView.classList.add('hidden');
    DOM.authView.classList.remove('hidden');
    if(statsInterval) clearInterval(statsInterval);
}

function showDash() {
    DOM.authView.classList.add('hidden');
    DOM.dashView.classList.remove('hidden');
}

DOM.navBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        DOM.navBtns.forEach(b => b.classList.remove('active'));
        DOM.panels.forEach(p => p.classList.add('hidden'));
        btn.classList.add('active');
        document.getElementById(btn.dataset.target).classList.remove('hidden');
    });
});

DOM.logoutBtn.addEventListener('click', () => {
    localStorage.removeItem('admin_token');
    adminToken = null;
    showAuth();
});

DOM.loginBtn.addEventListener('click', async () => {
    const username = DOM.userInp.value;
    const password = DOM.passInp.value;
    if(!username || !password) return;
    
    DOM.btnText.classList.add('hidden');
    DOM.loader.classList.remove('hidden');
    DOM.errorMsg.classList.add('hidden');

    try {
        const res = await fetch('/api/admin-login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Invalid credentials.");
        
        adminToken = data.access_token;
        localStorage.setItem('admin_token', adminToken);
        await loadDashboard();
        startStatsPolling();
    } catch (err) {
        DOM.errorMsg.textContent = err.message;
        DOM.errorMsg.classList.remove('hidden');
    } finally {
        DOM.btnText.classList.remove('hidden');
        DOM.loader.classList.add('hidden');
    }
});

function getHeaders() {
    return { 
        'Authorization': `Bearer ${adminToken}`,
        'Content-Type': 'application/json'
    };
}

async function fetchStats() {
    try {
        const statsRes = await fetch('/api/admin/stats', { headers: getHeaders() });
        if(!statsRes.ok) return;
        const stats = await statsRes.json();
        
        DOM.totalUsers.textContent = (stats.total_users || 0).toLocaleString();
        DOM.verifsToday.textContent = (stats.verifications_today || 0).toLocaleString();
        DOM.verifsMonth.textContent = (stats.verifications_month || 0).toLocaleString();
        DOM.verifsAll.textContent = (stats.verifications_all_time || 0).toLocaleString();
        
        if (stats.chart_data && stats.chart_data.labels) {
            renderChart(stats.chart_data.labels, stats.chart_data.values);
        }
    } catch(e) {}
}

function startStatsPolling() {
    if(statsInterval) clearInterval(statsInterval);
    statsInterval = setInterval(fetchStats, 10000);
}

async function loadDashboard() {
    try {
        await fetchStats();
        
        const usersRes = await fetch('/api/admin/users', { headers: getHeaders() });
        if (!usersRes.ok) throw new Error("Failed to fetch users");
        const usersData = await usersRes.json();
        allUsers = usersData.users || [];
        renderUsersTable(allUsers);
        
        const keysRes = await fetch('/api/admin/keys', { headers: getHeaders() });
        if (!keysRes.ok) throw new Error("Failed to fetch keys");
        const keysData = await keysRes.json();
        allKeys = keysData.keys || [];
        renderKeysTable(allKeys);
        
        showDash();
    } catch (err) {
        localStorage.removeItem('admin_token');
        adminToken = null;
        showAuth();
    }
}

function renderChart(labels, data) {
    if(chartInstance) chartInstance.destroy();
    const ctx = DOM.statsChart.getContext('2d');
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Daily Verifications',
                data: data,
                borderColor: '#00f260',
                backgroundColor: 'rgba(0, 242, 96, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 0 },
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' } },
                x: { grid: { display: false } }
            }
        }
    });
}

function renderUsersTable(usersArray) {
    DOM.usersBody.innerHTML = '';
    usersArray.forEach(u => {
        const tr = document.createElement('tr');
        tr.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
        const isAct = u.is_active !== false;
        
        tr.innerHTML = `
            <td style="padding: 1rem; font-weight: 600;">${u.email}</td>
            <td style="padding: 1rem;"><span class="badge ${u.plan}" style="text-transform:uppercase;">${u.plan}</span></td>
            <td style="padding: 1rem;">${(u.credits || 0).toLocaleString()}</td>
            <td style="padding: 1rem;">
                <span style="color: ${isAct ? 'var(--success)' : 'var(--danger)'}; font-weight: bold;">
                    ${isAct ? 'Active' : 'Suspended'}
                </span>
            </td>
            <td style="padding: 1rem;">
                <button class="btn" style="background: var(--primary); padding: 0.4rem 0.8rem; font-size: 0.8rem; width: auto; color: #000;" onclick="openUserModal('${u.email}')">View Details</button>
            </td>
        `;
        DOM.usersBody.appendChild(tr);
    });
}

function renderKeysTable(keysArray) {
    DOM.keysBody.innerHTML = '';
    keysArray.forEach(k => {
        const tr = document.createElement('tr');
        tr.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
        tr.innerHTML = `
            <td style="padding: 1rem; font-weight: 600;">${k.email}</td>
            <td style="padding: 1rem; font-family: monospace; color: var(--secondary);">${k.api_key}</td>
            <td style="padding: 1rem;">
                <span style="color: ${k.is_active ? 'var(--success)' : 'var(--danger)'}; font-weight: bold;">
                    ${k.is_active ? 'Active' : 'Inactive'}
                </span>
            </td>
            <td style="padding: 1rem; display: flex; gap: 0.5rem;">
                <button class="btn" style="padding: 0.4rem 0.8rem; font-size: 0.8rem; background: ${k.is_active ? 'var(--warning)' : 'var(--success)'}; color: #000;" onclick="toggleKeyStatus(${k.id}, ${!k.is_active})">
                    ${k.is_active ? 'Disable' : 'Enable'}
                </button>
                <button class="btn" style="padding: 0.4rem 0.8rem; font-size: 0.8rem; background: var(--danger); color: white;" onclick="revokeKey(${k.id})">Revoke</button>
            </td>
        `;
        DOM.keysBody.appendChild(tr);
    });
}

DOM.searchInp.addEventListener('input', (e) => {
    const term = e.target.value.toLowerCase();
    const filtered = allUsers.filter(u => u.email.toLowerCase().includes(term));
    renderUsersTable(filtered);
});

// Modal Logic
window.openUserModal = function(email) {
    const user = allUsers.find(u => u.email === email);
    if(!user) return;
    currentViewUserEmail = email;
    
    document.getElementById('modal-email').textContent = user.email;
    document.getElementById('modal-credits').textContent = (user.credits || 0).toLocaleString();
    
    const statBadge = document.getElementById('modal-status-badge');
    const toggleBtn = document.getElementById('modal-toggle-btn');
    if(user.is_active !== false) {
        statBadge.textContent = "Active";
        statBadge.style.background = "var(--success)";
        toggleBtn.textContent = "Suspend Account";
        toggleBtn.style.background = "var(--danger)";
    } else {
        statBadge.textContent = "Suspended";
        statBadge.style.background = "var(--danger)";
        toggleBtn.textContent = "Re-Activate Account";
        toggleBtn.style.background = "var(--success)";
    }
    
    const planBadge = document.getElementById('modal-plan-badge');
    planBadge.textContent = user.plan;
    planBadge.className = "badge " + user.plan;
    document.getElementById('modal-plan-select').value = user.plan;
    
    document.getElementById('modal-api').textContent = user.api_key ? (user.api_key.substring(0, 15) + "...") : "None";
    
    DOM.userModal.classList.remove('hidden');
};

window.adminUpdatePlan = async function() {
    if(!currentViewUserEmail) return;
    const plan = document.getElementById('modal-plan-select').value;
    try {
        const res = await fetch('/api/admin/upgrade-plan', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ user_email: currentViewUserEmail, plan: plan })
        });
        if(!res.ok) {
            const errBody = await res.text();
            throw new Error(`Update failed (${res.status}): ${errBody}`);
        }
        alert("Plan updated!");
        DOM.userModal.classList.add('hidden');
        loadDashboard();
    } catch(e) { alert(e.message); }
};

window.adminAddCredits = async function() {
    if(!currentViewUserEmail) return;
    const amt = parseInt(document.getElementById('modal-credits-input').value);
    if (!amt || amt <= 0) return;
    try {
        const res = await fetch('/api/admin/add-credits', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ user_email: currentViewUserEmail, credits_to_add: amt })
        });
        if(!res.ok) {
            const errBody = await res.text();
            throw new Error(`Credits update failed (${res.status}): ${errBody}`);
        }
        alert("Quota added!");
        DOM.userModal.classList.add('hidden');
        loadDashboard();
    } catch(e) { alert(e.message); }
};

window.adminToggleUser = async function() {
    if(!currentViewUserEmail) return;
    const user = allUsers.find(u => u.email === currentViewUserEmail);
    const newState = user.is_active === false ? true : false;
    try {
        const res = await fetch('/api/admin/toggle-user', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ user_email: currentViewUserEmail, is_active: newState })
        });
        if(!res.ok) throw new Error("Status update failed");
        DOM.userModal.classList.add('hidden');
        loadDashboard();
    } catch(e) { alert(e.message); }
};

window.toggleKeyStatus = async function(keyId, activeState) {
    try {
        const res = await fetch('/api/admin/toggle-key', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ key_id: keyId, is_active: activeState })
        });
        if(!res.ok) throw new Error("Key toggle failed");
        loadDashboard();
    } catch(e) { alert(e.message); }
};

window.revokeKey = async function(keyId) {
    if(!confirm("Are you sure you want to completely revoke and delete this API Key?")) return;
    try {
        const res = await fetch('/api/admin/revoke-key', {
            method: 'DELETE',
            headers: getHeaders(),
            body: JSON.stringify({ key_id: keyId })
        });
        if(!res.ok) throw new Error("Revocation failed");
        loadDashboard();
    } catch(e) { alert(e.message); }
};

init();

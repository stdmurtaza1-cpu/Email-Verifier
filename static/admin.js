const DOM = {
    authView: document.getElementById('admin-auth-view'),
    dashView: document.getElementById('admin-dashboard-view'),
    
    // Login Elements
    userInp: document.getElementById('admin-user-input'),
    passInp: document.getElementById('admin-pass-input'),
    loginBtn: document.getElementById('admin-login-btn'),
    btnText: document.getElementById('admin-btn-text'),
    loader: document.getElementById('admin-loader'),
    errorMsg: document.getElementById('admin-error-msg'),
    
    // Nav
    navBtns: document.querySelectorAll('.nav-btn:not(.logout)'),
    panels: document.querySelectorAll('.admin-panel'),
    logoutBtn: document.getElementById('admin-logout-btn'),

    // Stats
    totalUsers: document.getElementById('stats-total-users'),
    verifsToday: document.getElementById('stats-verifs-today'),
    verifsMonth: document.getElementById('stats-verifs-month'),
    verifsAll: document.getElementById('stats-verifs-all'),
    statsChart: document.getElementById('admin-stats-chart'),
    
    // Tables
    usersBody: document.getElementById('admin-users-body'),
    searchInp: document.getElementById('user-search'),
    keysBody: document.getElementById('admin-keys-body')
};

let adminToken = localStorage.getItem('admin_token');
let allUsers = [];
let allKeys = [];
let chartInstance = null;

// Init
async function init() {
    if (adminToken) {
        await loadDashboard();
    } else {
        showAuth();
    }
}

function showAuth() {
    DOM.dashView.classList.add('hidden');
    DOM.authView.classList.remove('hidden');
}

function showDash() {
    DOM.authView.classList.add('hidden');
    DOM.dashView.classList.remove('hidden');
}

// Navigation Logic
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

// Authentication
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
        
        if (!res.ok) {
            if (res.status === 429) throw new Error("Too many attempts. Locked for 15 minutes.");
            throw new Error(data.detail || "Invalid credentials.");
        }
        
        adminToken = data.access_token;
        localStorage.setItem('admin_token', adminToken);
        await loadDashboard();
        
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

async function loadDashboard() {
    try {
        // Fetch Stats
        const statsRes = await fetch('/admin/stats', { headers: getHeaders() });
        if(statsRes.status === 401 || statsRes.status === 403) throw new Error("Unauthorized");
        const stats = await statsRes.json().catch(() => ({}));
        
        DOM.totalUsers.textContent = (stats.total_users || 0).toLocaleString();
        DOM.verifsToday.textContent = (stats.verifications_today || 0).toLocaleString();
        DOM.verifsMonth.textContent = (stats.verifications_month || 0).toLocaleString();
        DOM.verifsAll.textContent = (stats.verifications_all_time || 0).toLocaleString();
        
        if (stats.chart_data) {
            renderChart(stats.chart_data.labels || [], stats.chart_data.values || []);
        } else {
            // Mock Data if API missing
            const mockLabels = Array.from({length: 30}, (_, i) => `Day ${i+1}`);
            const mockValues = Array.from({length: 30}, () => Math.floor(Math.random() * 5000));
            renderChart(mockLabels, mockValues);
        }
        
        // Fetch Users
        const usersRes = await fetch('/admin/users', { headers: getHeaders() });
        const usersData = await usersRes.json().catch(() => ({users: []}));
        allUsers = usersData.users || [];
        renderUsersTable(allUsers);
        
        // Fetch API Keys
        const keysRes = await fetch('/admin/keys', { headers: getHeaders() });
        const keysData = await keysRes.json().catch(() => ({keys: []}));
        allKeys = keysData.keys || [];
        if (allKeys.length === 0) {
            // Mock key if empty
            allKeys = [{ id: 1, email: 'user@example.com', api_key: 'vn_live_xxxxxxxxxxxxxxxx', is_active: true }];
        }
        renderKeysTable(allKeys);
        
        showDash();
    } catch (err) {
        console.error(err);
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
                borderColor: '#00d4ff',
                backgroundColor: 'rgba(0, 212, 255, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
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
        
        const isAct = u.is_active !== false; // default true
        
        tr.innerHTML = `
            <td style="padding: 1rem; font-weight: 600;">${u.email}</td>
            <td style="padding: 1rem;"><span class="badge ${u.plan}" style="text-transform:uppercase;">${u.plan}</span></td>
            <td style="padding: 1rem;">${(u.credits || 0).toLocaleString()}</td>
            <td style="padding: 1rem; color: var(--text-muted);">${u.joined_date ? u.joined_date.split('T')[0] : '-'}</td>
            <td style="padding: 1rem;">
                <span style="color: ${isAct ? 'var(--success)' : 'var(--danger)'}; font-weight: bold;">
                    ${isAct ? 'Active' : 'Inactive'}
                </span>
            </td>
            <td style="padding: 1rem; display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; min-width: 350px;">
                <select id="plan-${u.id}" style="padding: 0.4rem; border-radius: 4px; border: 1px solid var(--border-color); background: rgba(0,0,0,0.5); color: white;">
                    <option value="free" ${u.plan==='free'?'selected':''}>Free</option>
                    <option value="starter" ${u.plan==='starter'?'selected':''}>Starter</option>
                    <option value="pro" ${u.plan==='pro'?'selected':''}>Pro</option>
                    <option value="enterprise" ${u.plan==='enterprise'?'selected':''}>Enterprise</option>
                </select>
                <button class="btn btn-outline" style="padding: 0.4rem 0.8rem; font-size: 0.8rem;" onclick="updatePlan('${u.email}', ${u.id})">Update Plan</button>
                
                <div style="border-left: 1px solid var(--border-color); height: 20px; margin: 0 0.5rem;"></div>
                
                <input type="number" id="credits-${u.id}" placeholder="Add Credits" style="width: 80px; padding: 0.4rem; border-radius: 4px; border: 1px solid var(--border-color); background: rgba(0,0,0,0.5); color: white;">
                <button class="btn btn-outline" style="padding: 0.4rem 0.8rem; font-size: 0.8rem; color: var(--success); border-color: var(--success);" onclick="addCredits('${u.email}', ${u.id})">Add</button>
                
                <div style="border-left: 1px solid var(--border-color); height: 20px; margin: 0 0.5rem;"></div>
                
                <button class="btn" style="padding: 0.4rem 0.8rem; font-size: 0.8rem; background: ${isAct ? 'var(--warning)' : 'var(--success)'}; color: white;" onclick="toggleUserStatus('${u.email}', ${!isAct})">
                    ${isAct ? 'Deactivate' : 'Activate'}
                </button>
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
                <button class="btn" style="padding: 0.4rem 0.8rem; font-size: 0.8rem; background: ${k.is_active ? 'var(--warning)' : 'var(--success)'}; color: white;" onclick="toggleKeyStatus(${k.id}, ${!k.is_active})">
                    ${k.is_active ? 'Disable' : 'Enable'}
                </button>
                <button class="btn" style="padding: 0.4rem 0.8rem; font-size: 0.8rem; background: var(--danger); color: white;" onclick="revokeKey(${k.id})">Revoke</button>
            </td>
        `;
        DOM.keysBody.appendChild(tr);
    });
}

// Search Filter
DOM.searchInp.addEventListener('input', (e) => {
    const term = e.target.value.toLowerCase();
    const filtered = allUsers.filter(u => u.email.toLowerCase().includes(term));
    renderUsersTable(filtered);
});

// Admin Actions Hooks
window.updatePlan = async function(email, id) {
    const plan = document.getElementById(`plan-${id}`).value;
    try {
        const res = await fetch('/admin/upgrade-plan', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ user_email: email, plan: plan })
        });
        if(!res.ok) throw new Error("Update failed");
        alert(`Plan updated to ${plan.toUpperCase()}`);
        loadDashboard();
    } catch(e) { alert(e.message); }
};

window.addCredits = async function(email, id) {
    const amt = parseInt(document.getElementById(`credits-${id}`).value);
    if (!amt || amt <= 0) return;
    try {
        const res = await fetch('/admin/add-credits', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ user_email: email, credits_to_add: amt })
        });
        if(!res.ok) throw new Error("Credits update failed");
        alert(`Added ${amt} credits`);
        loadDashboard();
    } catch(e) { alert(e.message); }
};

window.toggleUserStatus = async function(email, activeState) {
    try {
        const res = await fetch('/admin/toggle-user', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ user_email: email, is_active: activeState })
        });
        if(!res.ok) throw new Error("Status toggle failed");
        loadDashboard();
    } catch(e) { alert(e.message); }
};

window.toggleKeyStatus = async function(keyId, activeState) {
    try {
        const res = await fetch('/admin/toggle-key', {
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
        const res = await fetch('/admin/revoke-key', {
            method: 'DELETE',
            headers: getHeaders(),
            body: JSON.stringify({ key_id: keyId })
        });
        if(!res.ok) throw new Error("Revocation failed");
        loadDashboard();
    } catch(e) { alert(e.message); }
};

init();

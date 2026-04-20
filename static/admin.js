/* ADMIN.JS - PREMIUM REWRITE */

function esc(str) {
    return String(str ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

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
    userModal: document.getElementById('user-modal-overlay'),
    workerCrashes: document.getElementById('stats-worker-crashes'),
    clusterWorkers: document.getElementById('cluster-total-workers'),
    clusterIps: document.getElementById('cluster-total-ips'),
    clusterSuccess: document.getElementById('cluster-success-rate'),
    workersBody: document.getElementById('admin-workers-body'),
    ipsBody: document.getElementById('admin-ips-body'),
    addIpModal: document.getElementById('add-ip-modal-overlay'),
    assignWorkerModal: document.getElementById('assign-worker-modal-overlay')
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
        
        DOM.totalUsers.textContent = (stats.overview?.total_users || stats.total_users || 0).toLocaleString();
        DOM.verifsToday.textContent = (stats.overview?.verifications_today || stats.verifications_today || 0).toLocaleString();
        DOM.verifsMonth.textContent = (stats.overview?.verifications_month || stats.verifications_month || 0).toLocaleString();
        DOM.verifsAll.textContent = (stats.overview?.verifications_all_time || stats.verifications_all_time || 0).toLocaleString();
        
        DOM.clusterWorkers.textContent = stats.overview?.total_workers_online || "0";
        DOM.clusterIps.textContent = stats.overview?.total_active_ips || "0";
        DOM.clusterSuccess.textContent = stats.overview?.overall_success_rate || "N/A";
        if(DOM.workerCrashes) DOM.workerCrashes.textContent = stats.overview?.total_worker_crashes || "0";
        
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
        
        const workersRes = await fetch('/api/admin/workers', { headers: getHeaders() });
        let activeWorkersData = [];
        if(workersRes.ok) {
            const wData = await workersRes.json();
            activeWorkersData = wData.workers || [];
            renderWorkersTable(activeWorkersData);
        }

        const ipsRes = await fetch('/api/admin/ips', { headers: getHeaders() });
        if(ipsRes.ok) {
            const iData = await ipsRes.json();
            renderIpsTable(iData.ips || [], activeWorkersData);
        }
        
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
        
        const partnerCell = u.partner_email
            ? `<span style="display:inline-block; background:rgba(0,242,96,0.12); border:1px solid var(--primary); color:var(--primary); border-radius:6px; padding:0.2rem 0.5rem; font-size:0.75rem; font-weight:600;">SHARED</span> <span style="font-size:0.8rem; color:var(--text-muted);">${esc(u.partner_email)}</span>`
            : `<span style="display:inline-block; background:rgba(255,255,255,0.06); border:1px solid var(--border-color); color:var(--text-muted); border-radius:6px; padding:0.2rem 0.5rem; font-size:0.75rem;">Independent</span>`;
        tr.innerHTML = `
            <td style="padding: 1rem; font-weight: 600;">${esc(u.email)}</td>
            <td style="padding: 1rem;"><span class="badge ${esc(u.plan)}" style="text-transform:uppercase;">${esc(u.plan)}</span></td>
            <td style="padding: 1rem;">${(u.credits || 0).toLocaleString()}</td>
            <td style="padding: 1rem; color: var(--text-muted);">${u.joined_date ? esc(u.joined_date.split('T')[0]) : 'N/A'}</td>
            <td style="padding: 1rem; font-weight: 500; color: var(--success);">${(u.total_verifications || 0).toLocaleString()}</td>
            <td style="padding: 1rem; font-weight: 500; color: var(--warning);">${(u.monthly_verifications || 0).toLocaleString()}</td>
            <td style="padding: 1rem;">${partnerCell}</td>
            <td style="padding: 1rem;">
                <span style="color: ${isAct ? 'var(--success)' : 'var(--danger)'}; font-weight: bold;">
                    ${isAct ? 'Active' : 'Suspended'}
                </span>
            </td>
            <td style="padding: 1rem;">
                <button class="btn" style="background: var(--primary); padding: 0.4rem 0.8rem; font-size: 0.8rem; width: auto; color: #000;" data-email="${esc(u.email)}">View Details</button>
            </td>
        `;
        tr.querySelector('button[data-email]').addEventListener('click', function() {
            openUserModal(this.dataset.email);
        });
        DOM.usersBody.appendChild(tr);
    });
}

function renderKeysTable(keysArray) {
    DOM.keysBody.innerHTML = '';
    keysArray.forEach(k => {
        const tr = document.createElement('tr');
        tr.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
        tr.innerHTML = `
            <td style="padding: 1rem; font-weight: 600;">${esc(k.email)}</td>
            <td style="padding: 1rem; font-family: monospace; color: var(--secondary);">${esc(k.api_key)}</td>
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

// Distributed Grid Renderers
function renderWorkersTable(workersArray) {
    DOM.workersBody.innerHTML = '';
    workersArray.forEach(w => {
        const tr = document.createElement('tr');
        tr.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
        
        tr.innerHTML = `
            <td style="padding: 1rem; font-weight: 600; font-family: monospace; color: var(--secondary);">${esc(w.worker_name)}</td>
            <td style="padding: 1rem;">
                <span style="color: ${w.status === 'online' ? 'var(--success)' : 'var(--danger)'}; font-weight: bold;">
                    ${esc(w.status).toUpperCase()}
                </span>
            </td>
            <td style="padding: 1rem;">${Number(w.assigned_ip_count) || 0} IPs Configured Native Scope</td>
        `;
        DOM.workersBody.appendChild(tr);
    });
}

function renderIpsTable(ipsArray, workersArray) {
    DOM.ipsBody.innerHTML = '';
    // Reverse Map IPs to workers
    const ipWorkerMap = {};
    workersArray.forEach(w => {
        w.assigned_ips.forEach(ip => { ipWorkerMap[ip] = w.worker_name; });
    });
    
    ipsArray.forEach(ip => {
        const tr = document.createElement('tr');
        tr.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
        const nodeOwner = ipWorkerMap[ip.ip_address] || "Global (Unassigned Master Pool)";
        
        let statColor = 'var(--text-muted)';
        if(ip.status === 'active') statColor = 'var(--success)';
        if(ip.status === 'frozen') statColor = 'var(--danger)';
        if(ip.status === 'cooldown') statColor = 'var(--warning)';
        
        let healthColor = ip.health_score > 70 ? 'var(--success)' : (ip.health_score > 40 ? 'var(--warning)' : 'var(--danger)');
        
        tr.innerHTML = `
            <td style="padding: 1rem; font-weight: bold; font-family: monospace;">${esc(ip.ip_address)}</td>
            <td style="padding: 1rem; font-weight: bold; color: ${healthColor};">${Number(ip.health_score) || 0} / 100</td>
            <td style="padding: 1rem; color: ${statColor}; font-weight: bold; text-transform: uppercase;">${esc(ip.status)}</td>
            <td style="padding: 1rem; color: ${nodeOwner.includes("Global") ? 'var(--text-muted)' : 'var(--secondary)'};">${esc(nodeOwner)}</td>
            <td style="padding: 1rem; display: flex; gap: 0.5rem;">
                <button class="btn assign-btn" style="padding: 0.4rem 0.8rem; font-size: 0.8rem; background: var(--secondary); color: #000;" data-ip="${esc(ip.ip_address)}">Assign Node Route</button>
                <button class="btn" style="padding: 0.4rem 0.8rem; font-size: 0.8rem; background: var(--danger); color: white;" onclick="adminFreezeIp('${ip.id}')">Force Freeze</button>
            </td>
        `;
        tr.querySelector('button.assign-btn').addEventListener('click', function() {
            openAssignIpModal(this.dataset.ip);
        });
        DOM.ipsBody.appendChild(tr);
    });
}

// IP Action Handlers
window.openAddIpModal = function() {
    DOM.addIpModal.classList.remove('hidden');
};

window.adminSubmitNewIp = async function() {
    const ip = document.getElementById('add-ip-address').value;
    const score = document.getElementById('add-ip-score').value || 100;
    if(!ip) return;
    try {
        const res = await fetch('/api/admin/ips', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ ip_address: ip, health_score: parseInt(score), status: 'active' })
        });
        if(!res.ok) throw new Error("Failed injecting IP Target.");
        alert("IP successfully injected natively.");
        DOM.addIpModal.classList.add('hidden');
        loadDashboard();
    } catch(e) { alert(e.message); }
};

window.adminFreezeIp = async function(id) {
    if(!confirm("Are you sure? This immediately strips bounds across all worker nodes and global sets!")) return;
    try {
        const res = await fetch('/api/admin/ips/'+id+'/freeze', { method: 'PATCH', headers: getHeaders() });
        if(!res.ok) throw new Error("Failed execution");
        loadDashboard();
    } catch(e) { alert(e.message); }
};

window.openAssignIpModal = async function(ip_address) {
    document.getElementById('assign-ip-label').textContent = ip_address;
    
    // fetch active workers to fill dropdown
    try {
        const res = await fetch('/api/admin/workers', { headers: getHeaders() });
        if(res.ok) {
            const data = await res.json();
            const sel = document.getElementById('assign-worker-select');
            sel.innerHTML = '<option value="GLOBAL_RELEASE">-- Release to Global Pool --</option>';
            data.workers.forEach(w => {
                const opt = document.createElement('option');
                opt.value = w.worker_name;
                opt.textContent = w.worker_name;
                sel.appendChild(opt);
            });
        }
        DOM.assignWorkerModal.classList.remove('hidden');
    } catch(e){}
};

window.adminSubmitAssignWorker = async function() {
    const ip = document.getElementById('assign-ip-label').textContent;
    const targetWorker = document.getElementById('assign-worker-select').value;
    
    try {
        if(targetWorker === "GLOBAL_RELEASE") {
            // we must figure out the old worker to release it, or we can just call an API to release from whatever.
            // since we do a direct POST to specific worker:
            alert("To release explicitly, use the specific worker API in postman or backend context natively. Selecting a worker binds it.");
            return;
        }
        const res = await fetch(`/api/admin/workers/${targetWorker}/assign/${ip}`, {
            method: 'POST',
            headers: getHeaders()
        });
        if(!res.ok) throw new Error("Check if IP is active and inside Global Array.");
        alert("IP Strict assignment completed gracefully.");
        DOM.assignWorkerModal.classList.add('hidden');
        loadDashboard();
    } catch(e) { alert(e.message); }
};

// ==========================================
// PAGES CMS / QUILL EDITOR LOGIC
// ==========================================
let quillEditor = null;

function initQuill() {
    if(quillEditor) return;
    
    quillEditor = new Quill('#editor-container', {
        theme: 'snow',
        modules: {
            toolbar: {
                container: [
                    [{ header: [1, 2, 3, 4, false] }],
                    ['bold', 'italic', 'underline', 'strike'],
                    [{ list: 'ordered' }, { list: 'bullet' }],
                    [{ color: [] }, { background: [] }],
                    ['link', 'image', 'video'],
                    ['clean']
                ],
                handlers: {
                    image: imageHandler
                }
            }
        }
    });
}

// Custom Image Upload Handler for Quill
function imageHandler() {
    const input = document.createElement('input');
    input.setAttribute('type', 'file');
    input.setAttribute('accept', 'image/*');
    input.click();

    input.onchange = async () => {
        const file = input.files[0];
        if (file) {
            const formData = new FormData();
            formData.append('file', file);
            
            try {
                // Assuming admin headers if required, but FormData boundary handles it automatically when not explicitly setting Content-Type
                const res = await fetch('/api/admin/upload-image', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${adminToken}` },
                    body: formData
                });
                if (!res.ok) throw new Error("Image upload failed");
                const data = await res.json();
                
                const range = quillEditor.getSelection();
                quillEditor.insertEmbed(range.index, 'image', data.url);
            } catch (err) {
                alert("Upload failed: " + err.message);
            }
        }
    };
}

window.adminLoadPageContent = async function() {
    initQuill();
    const slug = document.getElementById('admin-page-selector').value;
    try {
        const res = await fetch(`/api/admin/page/${slug}`, { headers: getHeaders() });
        const data = await res.json();
        const content = data.html_content || '';
        // Set the content safely via Quill's internal HTML setter
        quillEditor.clipboard.dangerouslyPasteHTML(content);
    } catch(e) {
        alert("Failed to load page content.");
    }
};

window.adminSavePageContent = async function() {
    const slug = document.getElementById('admin-page-selector').value;
    const htmlContent = quillEditor.root.innerHTML;
    
    document.getElementById('admin-save-page-txt').classList.add('hidden');
    document.getElementById('admin-save-page-loader').classList.remove('hidden');
    
    try {
        const res = await fetch(`/api/admin/page/${slug}`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ html_content: htmlContent })
        });
        if(!res.ok) throw new Error("Save failed");
        alert(`Page '${slug}' updated successfully! Note: You may need to refresh the public site to see changes.`);
    } catch (e) {
        alert("Failed to save content.");
    } finally {
        document.getElementById('admin-save-page-txt').classList.remove('hidden');
        document.getElementById('admin-save-page-loader').classList.add('hidden');
    }
};

// Hook into navigation to lazy load quill if they click Pages tab
DOM.navBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
        if(e.target.dataset.target === 'panel-pages') {
            initQuill();
            adminLoadPageContent(); // Auto load "home" which is default
        }
    });
});

init();

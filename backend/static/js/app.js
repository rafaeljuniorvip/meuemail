const API = '';
const state = {
    page: 1,
    perPage: 50,
    sortBy: 'date',
    sortOrder: 'desc',
    filters: {},
    selectedIds: new Set(),
    totalEmails: 0,
    totalPages: 1,
    authenticated: false,
    accountId: null,
    currentUser: null,
};

// Init
document.addEventListener('DOMContentLoaded', () => {
    loadCurrentUser();
    checkAuth();
    setupFilters();
    setupSelectAll();
    setupNav();
    setupChatInput();
    restoreSidebarState();
    restoreSidebarCompact();
    showSidebarLoading();
    window.addEventListener('hashchange', handleRoute);
});

// ===== SESSION / USER =====
async function loadCurrentUser() {
    try {
        const res = await fetch(`${API}/auth/me`);
        if (res.status === 401) return;
        const user = await res.json();
        state.currentUser = user;
        updateUserUI(user);
    } catch (e) {
        console.error('Failed to load user:', e);
    }
}

function updateUserUI(user) {
    if (!user) return;

    // User info in sidebar
    const nameEl = document.getElementById('user-name');
    const emailEl = document.getElementById('user-email-display');
    const avatarEl = document.getElementById('user-avatar');

    if (nameEl) nameEl.textContent = user.name || user.email.split('@')[0];
    if (emailEl) emailEl.textContent = user.email;

    if (user.picture && avatarEl) {
        avatarEl.src = user.picture;
        avatarEl.style.display = 'block';
    }

    // Show admin menu item
    if (user.role === 'admin') {
        const navUsers = document.getElementById('nav-users');
        if (navUsers) navUsers.style.display = '';
    }
}

async function logout() {
    try {
        await fetch(`${API}/auth/logout`, { method: 'POST' });
    } catch (e) {}
    window.location.href = '/login';
}

// ===== ROUTING =====
function handleRoute() {
    const hash = location.hash || '#/emails';
    const [path, query] = hash.substring(1).split('?');
    const segments = path.split('/').filter(Boolean);

    // Reset sidebar active
    document.querySelectorAll('.nav-item, .label-item').forEach(el => el.classList.remove('active'));

    if (segments[0] === 'email' && segments[1]) {
        showPage('email-detail');
        loadEmailDetail(segments[1]);
    } else if (segments[0] === 'stats') {
        showPage('stats');
        document.querySelector('.nav-item[data-page="stats"]')?.classList.add('active');
        loadStats();
    } else if (segments[0] === 'analysis') {
        showPage('analysis');
        document.querySelector('.nav-item[data-page="analysis"]')?.classList.add('active');
        loadAnalysis();
    } else if (segments[0] === 'agent') {
        showPage('agent');
        document.querySelector('.nav-item[data-page="agent"]')?.classList.add('active');
    } else if (segments[0] === 'query' && segments[1]) {
        showPage('query-results');
        loadQueryResults(segments[1]);
    } else if (segments[0] === 'sync') {
        showPage('sync');
        document.querySelector('.nav-item[data-page="sync"]')?.classList.add('active');
        loadSyncStatus();
    } else if (segments[0] === 'settings') {
        if (segments[1] === 'accounts') {
            showPage('settings-accounts');
            document.querySelector('.nav-item[data-page="settings/accounts"]')?.classList.add('active');
            loadAccounts();
            loadIRedMailConfig();
        } else {
            // Default to agent config for #/settings and #/settings/agent
            showPage('settings-agent');
            document.querySelector('.nav-item[data-page="settings/agent"]')?.classList.add('active');
            loadAiConfig();
            loadApiKeys();
        }
    } else if (segments[0] === 'users') {
        showPage('users');
        document.querySelector('.nav-item[data-page="users"]')?.classList.add('active');
        loadUsers();
    } else {
        // /emails or /emails?filters...
        showPage('emails');
        document.querySelector('.nav-item[data-page="emails"]')?.classList.add('active');
        const params = new URLSearchParams(query || '');
        restoreFiltersFromParams(params);
        loadEmails();
    }
}

function navigate(hash) {
    location.hash = hash;
}

function showPage(pageName) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const el = document.getElementById(`page-${pageName}`);
    if (el) el.classList.add('active');
}

function buildEmailsHash() {
    const params = new URLSearchParams();
    if (state.page > 1) params.set('page', state.page);
    if (state.sortBy !== 'date') params.set('sort', state.sortBy);
    if (state.sortOrder !== 'desc') params.set('order', state.sortOrder);
    Object.entries(state.filters).forEach(([k, v]) => {
        if (v !== '' && v !== null && v !== undefined) params.set(k, v);
    });
    const qs = params.toString();
    return '#/emails' + (qs ? '?' + qs : '');
}

function getDefaultDateFrom() {
    const d = new Date();
    d.setDate(d.getDate() - 60);
    return d.toISOString().split('T')[0];
}

function restoreFiltersFromParams(params) {
    state.page = parseInt(params.get('page')) || 1;
    state.sortBy = params.get('sort') || 'date';
    state.sortOrder = params.get('order') || 'desc';
    state.filters = {};

    const filterKeys = ['sender', 'subject', 'date_from', 'date_to', 'label', 'has_attachments', 'is_read', 'min_size'];
    filterKeys.forEach(k => {
        if (params.has(k)) state.filters[k] = params.get(k);
    });

    // Default: last 60 days if no date_from specified
    if (!state.filters.date_from) {
        state.filters.date_from = getDefaultDateFrom();
    }

    // Sync filter inputs
    document.getElementById('filter-sender').value = state.filters.sender || '';
    document.getElementById('filter-subject').value = state.filters.subject || '';
    document.getElementById('filter-date-from').value = state.filters.date_from || '';
    document.getElementById('filter-date-to').value = state.filters.date_to || '';
    document.getElementById('filter-label').value = state.filters.label || '';
    document.getElementById('filter-attachments').value = state.filters.has_attachments || '';
    document.getElementById('filter-read').value = state.filters.is_read || '';
    document.getElementById('filter-size').value = state.filters.min_size || '';

    // Highlight label in sidebar
    if (state.filters.label) {
        document.querySelectorAll('.label-item').forEach(el => {
            if (el.dataset.label === state.filters.label) el.classList.add('active');
        });
    }
}

function updateUrlSilently() {
    const newHash = buildEmailsHash();
    if (location.hash !== newHash) {
        history.replaceState(null, '', newHash);
    }
}

// ===== NAV =====
function setupNav() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            const page = item.dataset.page;
            navigate(`#/${page}`);
        });
    });
}

// ===== AUTH =====
async function checkAuth() {
    try {
        const res = await fetch(`${API}/api/auth/status`);
        const data = await res.json();
        state.authenticated = data.authenticated;
        updateAuthUI(data);
        if (data.authenticated) {
            loadSidebar();
            loadAccountSelector();
            const syncRes = await fetch(`${API}/api/sync/status`);
            const syncData = await syncRes.json();
            if (syncData.running) startSyncPolling();
        }
        handleRoute();
    } catch (e) {
        console.error('Auth check failed:', e);
        handleRoute();
    }
}

async function connectGmail() {
    const btn = document.getElementById('btn-connect');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Conectando...';
    try {
        const res = await fetch(`${API}/api/auth/connect`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'ok') {
            state.authenticated = true;
            updateAuthUI(data);
            showToast('Gmail conectado com sucesso!', 'success');
            loadSidebar();
            loadEmails();
        } else {
            showToast(data.message || 'Erro ao conectar', 'error');
        }
    } catch (e) {
        showToast('Erro ao conectar ao Gmail', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg> Conectar Gmail';
    }
}

function updateAuthUI(data) {
    const dot = document.getElementById('auth-dot');
    const email = document.getElementById('auth-email');
    const connectBtn = document.getElementById('btn-connect');
    const syncBtn = document.getElementById('btn-sync');

    if (data.authenticated || data.status === 'ok') {
        if (dot) dot.classList.add('connected');
        if (email) email.textContent = data.email || 'Conectado';
        if (connectBtn) connectBtn.style.display = 'none';
        if (syncBtn) syncBtn.style.display = 'inline-flex';
    } else {
        if (dot) dot.classList.remove('connected');
        if (email) email.textContent = 'Desconectado';
        if (connectBtn) connectBtn.style.display = 'inline-flex';
        if (syncBtn) syncBtn.style.display = 'none';
    }
}

// ===== SYNC =====
let syncPollInterval = null;

async function syncEmails() {
    try {
        const res = await fetch(`${API}/api/sync`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'already_running') {
            showToast('Sincronização já em andamento', 'info');
        } else if (data.status === 'started') {
            showToast('Sincronização iniciada em background', 'info');
        }
        startSyncPolling();
    } catch (e) {
        showToast('Erro ao iniciar sincronização: ' + e.message, 'error');
    }
}

function startSyncPolling() {
    if (syncPollInterval) return;
    const bar = document.getElementById('sync-bar');
    bar.classList.add('visible');

    syncPollInterval = setInterval(async () => {
        try {
            const res = await fetch(`${API}/api/sync/status`);
            const progress = await res.json();
            const fill = document.getElementById('sync-bar-fill');
            const text = document.getElementById('sync-bar-text');

            if (progress.running) {
                const pct = progress.total > 0 ? Math.round((progress.synced / progress.total) * 100) : 0;
                fill.style.width = `${pct}%`;
                text.textContent = progress.status === 'fetching_ids'
                    ? `Buscando lista de emails... (${progress.total.toLocaleString()} encontrados)`
                    : `Sincronizando: ${progress.synced.toLocaleString()} de ${progress.total.toLocaleString()} (${pct}%)`;
            } else {
                clearInterval(syncPollInterval);
                syncPollInterval = null;
                fill.style.width = '100%';
                if (progress.status === 'done') {
                    text.textContent = 'Sincronização concluída!';
                    showToast('Sincronização concluída!', 'success');
                } else if (progress.status === 'error') {
                    text.textContent = 'Erro na sincronização';
                    showToast('Erro na sincronização', 'error');
                }
                loadEmails();
                loadSidebar();
                setTimeout(() => bar.classList.remove('visible'), 3000);
            }
        } catch (e) {}
    }, 1000);
}

// ===== EMAILS LIST =====
async function loadEmails() {
    const params = new URLSearchParams({
        page: state.page,
        per_page: state.perPage,
        sort_by: state.sortBy,
        sort_order: state.sortOrder,
    });
    if (state.accountId) params.set('account_id', state.accountId);
    Object.entries(state.filters).forEach(([key, val]) => {
        if (val !== '' && val !== null && val !== undefined) params.set(key, val);
    });

    try {
        const res = await fetch(`${API}/api/emails?${params}`);
        const data = await res.json();
        state.totalEmails = data.total;
        state.totalPages = data.total_pages;
        state.page = data.page;
        renderTable(data.emails);
        renderPagination(data);
        updateSelectionBar();
        updateUrlSilently();
    } catch (e) {
        console.error('Failed to load emails:', e);
        showToast('Erro ao carregar emails', 'error');
    }
}

function renderTable(emails) {
    const tbody = document.getElementById('emails-tbody');
    const emptyState = document.getElementById('empty-state');
    const tableContainer = document.getElementById('table-container');

    if (emails.length === 0) {
        emptyState.style.display = 'block';
        tableContainer.style.display = 'none';
        return;
    }
    emptyState.style.display = 'none';
    tableContainer.style.display = 'block';

    tbody.innerHTML = emails.map(email => {
        const isSelected = state.selectedIds.has(email.gmail_id);
        const isUnread = !email.is_read;
        const date = email.date ? formatDate(email.date) : '-';
        const size = formatSize(email.size_estimate);
        const labels = (email.labels || [])
            .filter(l => !l.startsWith('Label_'))
            .slice(0, 3)
            .map(l => `<span class="label-tag ${l.toLowerCase()}">${l}</span>`)
            .join('');

        return `<tr class="${isSelected ? 'selected' : ''} ${isUnread ? 'unread-row' : ''}" data-id="${email.gmail_id}">
            <td><input type="checkbox" class="email-check" data-id="${email.gmail_id}" ${isSelected ? 'checked' : ''} /></td>
            <td class="email-sender" title="${escapeHtml(email.sender)}">${escapeHtml(email.sender_email || email.sender)}</td>
            <td class="email-subject"><a href="#/email/${email.gmail_id}" class="email-link" title="${escapeHtml(email.subject)}">${escapeHtml(email.subject)}</a></td>
            <td class="email-snippet" title="${escapeHtml(email.snippet)}">${escapeHtml(email.snippet)}</td>
            <td><div class="email-labels">${labels}</div></td>
            <td class="email-size">${size}</td>
            <td>${email.has_attachments ? '📎' : ''}</td>
            <td>${date}</td>
        </tr>`;
    }).join('');

    tbody.querySelectorAll('.email-check').forEach(cb => {
        cb.addEventListener('change', (e) => {
            const id = e.target.dataset.id;
            if (e.target.checked) state.selectedIds.add(id); else state.selectedIds.delete(id);
            e.target.closest('tr').classList.toggle('selected', e.target.checked);
            updateSelectionBar();
        });
    });
}

function renderPagination(data) {
    const info = document.getElementById('pagination-info');
    const controls = document.getElementById('pagination-controls');
    const start = (data.page - 1) * data.per_page + 1;
    const end = Math.min(data.page * data.per_page, data.total);
    info.textContent = data.total > 0
        ? `Mostrando ${start}-${end} de ${data.total.toLocaleString()} emails`
        : 'Nenhum email encontrado';

    let buttons = '';
    buttons += `<button ${data.page <= 1 ? 'disabled' : ''} onclick="goToPage(1)">«</button>`;
    buttons += `<button ${data.page <= 1 ? 'disabled' : ''} onclick="goToPage(${data.page - 1})">‹</button>`;
    const startPage = Math.max(1, data.page - 2);
    const endPage = Math.min(data.total_pages, data.page + 2);
    for (let i = startPage; i <= endPage; i++) {
        buttons += `<button class="${i === data.page ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
    }
    buttons += `<button ${data.page >= data.total_pages ? 'disabled' : ''} onclick="goToPage(${data.page + 1})">›</button>`;
    buttons += `<button ${data.page >= data.total_pages ? 'disabled' : ''} onclick="goToPage(${data.total_pages})">»</button>`;
    controls.innerHTML = buttons;
}

function goToPage(page) {
    state.page = page;
    loadEmails();
    window.scrollTo(0, 0);
}

// ===== FILTERS =====
function setupFilters() {
    document.getElementById('btn-apply-filters').addEventListener('click', applyFilters);
    document.getElementById('btn-clear-filters').addEventListener('click', clearFilters);
}

function applyFilters() {
    state.filters = {};
    const sender = document.getElementById('filter-sender').value.trim();
    const subject = document.getElementById('filter-subject').value.trim();
    const dateFrom = document.getElementById('filter-date-from').value;
    const dateTo = document.getElementById('filter-date-to').value;
    const label = document.getElementById('filter-label').value;
    const attachments = document.getElementById('filter-attachments').value;
    const read = document.getElementById('filter-read').value;
    const minSize = document.getElementById('filter-size').value;

    if (sender) state.filters.sender = sender;
    if (subject) state.filters.subject = subject;
    if (dateFrom) state.filters.date_from = dateFrom;
    if (dateTo) state.filters.date_to = dateTo;
    if (label) state.filters.label = label;
    if (attachments !== '') state.filters.has_attachments = attachments;
    if (read !== '') state.filters.is_read = read;
    if (minSize) state.filters.min_size = parseInt(minSize);

    state.page = 1;
    loadEmails();
}

function clearFilters() {
    document.getElementById('filter-sender').value = '';
    document.getElementById('filter-subject').value = '';
    document.getElementById('filter-date-from').value = getDefaultDateFrom();
    document.getElementById('filter-date-to').value = '';
    document.getElementById('filter-label').value = '';
    document.getElementById('filter-attachments').value = '';
    document.getElementById('filter-read').value = '';
    document.getElementById('filter-size').value = '';
    state.filters = { date_from: getDefaultDateFrom() };
    state.page = 1;
    navigate('#/emails');
}

// ===== SELECTION =====
function setupSelectAll() {
    document.getElementById('select-all').addEventListener('change', (e) => {
        const checked = e.target.checked;
        document.querySelectorAll('.email-check').forEach(cb => {
            cb.checked = checked;
            const id = cb.dataset.id;
            if (checked) state.selectedIds.add(id); else state.selectedIds.delete(id);
            cb.closest('tr').classList.toggle('selected', checked);
        });
        updateSelectionBar();
    });
}

function updateSelectionBar() {
    const bar = document.getElementById('selection-bar');
    const countEl = document.getElementById('selection-count');
    const deleteBtn = document.getElementById('btn-delete-selected');
    if (state.selectedIds.size > 0) {
        bar.classList.add('visible');
        countEl.textContent = `${state.selectedIds.size} email(s) selecionado(s)`;
        deleteBtn.disabled = false;
    } else {
        bar.classList.remove('visible');
        deleteBtn.disabled = true;
    }
}

function clearSelection() {
    state.selectedIds.clear();
    document.getElementById('select-all').checked = false;
    document.querySelectorAll('.email-check').forEach(cb => {
        cb.checked = false;
        cb.closest('tr')?.classList.remove('selected');
    });
    updateSelectionBar();
}

// ===== DELETE =====
function confirmDelete() {
    if (state.selectedIds.size === 0) return;
    document.getElementById('delete-count').textContent = state.selectedIds.size;
    document.getElementById('delete-modal').classList.add('visible');
}

function closeDeleteModal() {
    document.getElementById('delete-modal').classList.remove('visible');
}

async function executeDelete() {
    closeDeleteModal();
    const gmail_ids = Array.from(state.selectedIds);
    const btn = document.getElementById('btn-delete-selected');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Deletando...';

    try {
        const res = await fetch(`${API}/api/emails/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gmail_ids }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
            showToast(`${data.deleted_gmail} email(s) movidos para a lixeira`, 'success');
            state.selectedIds.clear();
            loadEmails();
        } else {
            showToast('Erro ao deletar emails', 'error');
        }
    } catch (e) {
        showToast('Erro ao deletar: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg> Deletar Selecionados';
        updateSelectionBar();
    }
}

// ===== SORTING =====
function sortBy(column) {
    if (state.sortBy === column) {
        state.sortOrder = state.sortOrder === 'desc' ? 'asc' : 'desc';
    } else {
        state.sortBy = column;
        state.sortOrder = 'desc';
    }
    document.querySelectorAll('thead th[data-sort]').forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
        if (th.dataset.sort === state.sortBy) {
            th.classList.add(state.sortOrder === 'asc' ? 'sort-asc' : 'sort-desc');
        }
    });
    loadEmails();
}

// ===== STATS =====
async function loadStats() {
    try {
        const res = await fetch(`${API}/api/emails/stats`);
        const data = await res.json();
        document.getElementById('stat-total').textContent = data.total_emails.toLocaleString();
        document.getElementById('stat-size').textContent = formatSize(data.total_size_bytes);
        document.getElementById('stat-unread').textContent = (data.unread || 0).toLocaleString();

        document.getElementById('top-senders-list').innerHTML = data.top_senders.map(s =>
            `<li><span><a href="#/emails?sender=${encodeURIComponent(s.email)}" style="color:var(--text);text-decoration:none;">${escapeHtml(s.email)}</a></span><span class="sender-count">${s.count}</span></li>`
        ).join('');

        document.getElementById('top-domains-list').innerHTML = (data.top_domains || []).map(d =>
            `<li><span><a href="#/emails?sender=${encodeURIComponent('@' + d.domain)}" style="color:var(--text);text-decoration:none;">${escapeHtml(d.domain)}</a></span><a href="#/emails?sender=${encodeURIComponent('@' + d.domain)}" class="sender-count">${d.count}</a></li>`
        ).join('');
    } catch (e) {
        console.error('Failed to load stats:', e);
    }
}

// ===== SIDEBAR =====
function showSidebarLoading() {
    const skeleton = '<div class="sidebar-skeleton"><div class="skeleton-line"></div><div class="skeleton-line short"></div><div class="skeleton-line"></div><div class="skeleton-line short"></div></div>';
    const labels = document.getElementById('sidebar-labels');
    const senders = document.getElementById('sidebar-senders');
    if (labels && !labels.innerHTML.trim()) labels.innerHTML = skeleton;
    if (senders && !senders.innerHTML.trim()) senders.innerHTML = skeleton;
}

async function loadSidebar() {
    showSidebarLoading();
    try {
        const statsParams = state.accountId ? `?account_id=${state.accountId}` : '';
        const res = await fetch(`${API}/api/emails/stats${statsParams}`);
        const data = await res.json();

        const labelMap = {
            'INBOX': 'Caixa de Entrada', 'SENT': 'Enviados', 'DRAFT': 'Rascunhos',
            'SPAM': 'Spam', 'TRASH': 'Lixeira', 'STARRED': 'Com Estrela',
            'IMPORTANT': 'Importantes', 'UNREAD': 'Não Lidos',
            'CATEGORY_PROMOTIONS': 'Promoções', 'CATEGORY_SOCIAL': 'Social',
            'CATEGORY_UPDATES': 'Atualizações', 'CATEGORY_FORUMS': 'Fóruns',
            'CATEGORY_PERSONAL': 'Pessoal',
        };
        const order = ['INBOX', 'UNREAD', 'STARRED', 'IMPORTANT', 'SENT', 'DRAFT', 'SPAM', 'TRASH'];

        const sortedLabels = data.labels
            .filter(l => labelMap[l.label] || !l.label.startsWith('Label_'))
            .sort((a, b) => {
                const ia = order.indexOf(a.label), ib = order.indexOf(b.label);
                if (ia !== -1 && ib !== -1) return ia - ib;
                if (ia !== -1) return -1;
                if (ib !== -1) return 1;
                return b.count - a.count;
            });

        document.getElementById('sidebar-labels').innerHTML = sortedLabels.slice(0, 15).map(l => {
            const name = labelMap[l.label] || l.label;
            return `<div class="label-item" data-label="${l.label}" onclick="filterByLabel('${l.label}', this)" title="${name} (${l.count.toLocaleString()})">
                <span class="label-name">${name}</span>
                <span class="label-count">${l.count.toLocaleString()}</span>
            </div>`;
        }).join('');

        document.getElementById('sidebar-senders').innerHTML = data.top_senders.slice(0, 10).map(s => {
            const name = s.email ? s.email.split('@')[0] : '?';
            return `<div class="sender-item" onclick="filterBySender('${escapeHtml(s.email)}')" title="${escapeHtml(s.email)} (${s.count})">
                <span class="sender-name">${escapeHtml(name)}</span>
                <span class="sender-count-badge">${s.count}</span>
            </div>`;
        }).join('');
    } catch (e) {
        console.error('Failed to load sidebar:', e);
    }
}

function filterByLabel(label, el) {
    document.querySelectorAll('.label-item').forEach(e => e.classList.remove('active'));
    if (el) el.classList.add('active');
    navigate(`#/emails?label=${encodeURIComponent(label)}`);
}

function filterBySender(email) {
    navigate(`#/emails?sender=${encodeURIComponent(email)}`);
}

// ===== SIDEBAR COLLAPSE =====
function toggleSidebarSection(el) {
    const targetId = el.dataset.target;
    const content = document.getElementById(targetId);
    if (!content) return;

    el.classList.toggle('collapsed');
    content.classList.toggle('collapsed');

    // Persist state
    const collapsed = JSON.parse(localStorage.getItem('sidebarCollapsed') || '{}');
    collapsed[targetId] = el.classList.contains('collapsed');
    localStorage.setItem('sidebarCollapsed', JSON.stringify(collapsed));
}

function restoreSidebarState() {
    const collapsed = JSON.parse(localStorage.getItem('sidebarCollapsed') || '{}');
    Object.entries(collapsed).forEach(([targetId, isCollapsed]) => {
        if (!isCollapsed) return;
        const content = document.getElementById(targetId);
        const title = document.querySelector(`.sidebar-section-title[data-target="${targetId}"]`);
        if (content && title) {
            title.classList.add('collapsed');
            content.classList.add('collapsed');
        }
    });
}

function toggleSidebarCompact() {
    if (window.innerWidth <= 1024) return;
    const compact = document.body.classList.toggle('sidebar-compact');
    localStorage.setItem('sidebarCompact', compact ? '1' : '0');
    const btn = document.getElementById('sidebar-toggle-btn');
    if (btn) btn.setAttribute('aria-pressed', compact ? 'true' : 'false');
}

function restoreSidebarCompact() {
    const compact = localStorage.getItem('sidebarCompact') === '1';
    if (compact && window.innerWidth > 1024) {
        document.body.classList.add('sidebar-compact');
    }
    const btn = document.getElementById('sidebar-toggle-btn');
    if (btn) btn.setAttribute('aria-pressed', document.body.classList.contains('sidebar-compact') ? 'true' : 'false');
}

// ===== ANALYSIS =====
async function loadAnalysis() {
    try {
        const [noreplyRes, domainsRes, fuzzyRes] = await Promise.all([
            fetch(`${API}/api/emails/analysis/noreply`),
            fetch(`${API}/api/emails/analysis/domain-groups`),
            fetch(`${API}/api/emails/analysis/fuzzy-senders`),
        ]);
        const noreply = await noreplyRes.json();
        const domains = await domainsRes.json();
        const fuzzy = await fuzzyRes.json();

        // Summary cards
        document.getElementById('summary-automated').textContent = noreply.total_automated.toLocaleString();
        document.getElementById('summary-domains').textContent = domains.length.toLocaleString();
        document.getElementById('summary-fuzzy').textContent = fuzzy.length.toLocaleString();

        document.getElementById('noreply-total').textContent = noreply.senders.length + ' remetentes';
        document.getElementById('noreply-list').innerHTML = noreply.senders.map((s, i) =>
            `<li>
                <div class="analysis-list-left">
                    <span class="analysis-rank">${i + 1}</span>
                    <a href="#/emails?sender=${encodeURIComponent(s.email)}">${escapeHtml(s.email)}</a>
                </div>
                <a href="#/emails?sender=${encodeURIComponent(s.email)}" class="analysis-count">${s.count.toLocaleString()}</a>
            </li>`
        ).join('');

        document.getElementById('domain-groups').innerHTML = domains.map(d =>
            `<div class="domain-group">
                <div class="domain-group-header" onclick="this.nextElementSibling.classList.toggle('open')">
                    <div class="domain-group-left">
                        <span class="domain-name">${escapeHtml(d.domain)}</span>
                        <span class="domain-group-tag">${d.unique_senders} remetente${d.unique_senders > 1 ? 's' : ''}</span>
                    </div>
                    <div class="domain-group-meta">
                        <a href="#/emails?sender=${encodeURIComponent('@' + d.domain)}" class="domain-meta-pill" onclick="event.stopPropagation()">${d.total_emails.toLocaleString()} emails</a>
                        <span class="domain-meta-size">${formatSize(d.total_size)}</span>
                        <svg class="domain-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="6 9 12 15 18 9"/></svg>
                    </div>
                </div>
                <div class="domain-group-senders">
                    <div class="domain-senders-list">
                        ${d.top_senders.map(s => `<a href="#/emails?sender=${encodeURIComponent(s)}" class="domain-sender-chip">${escapeHtml(s)}</a>`).join('')}
                    </div>
                    <a href="#/emails?sender=${encodeURIComponent('@' + d.domain)}" class="drill-link-all">Ver todos do domínio →</a>
                </div>
            </div>`
        ).join('');

        document.getElementById('fuzzy-tbody').innerHTML = fuzzy.map(f => {
            const pct = Math.round(f.similarity * 100);
            const barColor = pct >= 80 ? 'var(--success)' : pct >= 60 ? 'var(--warning)' : 'var(--primary)';
            return `<tr>
                <td><a href="#/emails?sender=${encodeURIComponent(f.email_a)}" class="fuzzy-email">${escapeHtml(f.email_a)}</a></td>
                <td style="text-align:right"><a href="#/emails?sender=${encodeURIComponent(f.email_a)}" class="analysis-count">${f.count_a.toLocaleString()}</a></td>
                <td><a href="#/emails?sender=${encodeURIComponent(f.email_b)}" class="fuzzy-email">${escapeHtml(f.email_b)}</a></td>
                <td style="text-align:right"><a href="#/emails?sender=${encodeURIComponent(f.email_b)}" class="analysis-count">${f.count_b.toLocaleString()}</a></td>
                <td>
                    <div class="sim-bar-container">
                        <div class="sim-bar-fill" style="width:${pct}%; background:${barColor}"></div>
                    </div>
                    <span class="sim-pct">${pct}%</span>
                </td>
            </tr>`;
        }).join('') || '<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--text-muted)">Nenhum par similar encontrado</td></tr>';
    } catch (e) {
        console.error('Failed to load analysis:', e);
    }
}

// ===== EMAIL DETAIL PAGE =====
async function loadEmailDetail(gmailId) {
    const container = document.getElementById('email-detail-content');
    container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted)">Carregando...</div>';

    try {
        const res = await fetch(`${API}/api/emails/${gmailId}`);
        if (!res.ok) throw new Error('Email não encontrado');
        const email = await res.json();

        const date = email.date ? new Date(email.date).toLocaleString('pt-BR') : '-';
        const labels = (email.labels || []).map(l =>
            `<span class="label-tag ${l.toLowerCase()}">${l}</span>`
        ).join(' ');

        let attachmentsHtml = '';
        if (email.attachments && email.attachments.length > 0) {
            attachmentsHtml = `
                <div class="detail-attachments">
                    <h4>Anexos (${email.attachments.length})</h4>
                    <div class="ep-attachment-list">
                        ${email.attachments.map(att => {
                            const url = `${API}/api/emails/${email.gmail_id}/attachments/${encodeURIComponent(att.attachmentId)}`;
                            return `<a href="${url}" class="ep-attachment-item" download="${escapeHtml(att.filename)}">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                                ${escapeHtml(att.filename)} <span class="ep-att-size">(${formatSize(att.size)})</span>
                            </a>`;
                        }).join('')}
                    </div>
                </div>`;
        } else if (email.has_attachments) {
            // Attachments exist but metadata not synced yet - offer to fetch live
            attachmentsHtml = `
                <div class="detail-attachments">
                    <h4>Anexos</h4>
                    <p style="font-size:13px;color:var(--text-muted)">Este email tem anexos mas os metadados ainda não foram sincronizados.
                    <a href="${email.gmail_link}" target="_blank" class="email-link">Abrir no Gmail para baixar</a></p>
                </div>`;
        }

        let bodyHtml;
        if (email.body && email.body.trim().startsWith('<')) {
            bodyHtml = `<iframe id="email-body-iframe" sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" referrerpolicy="no-referrer"
                style="width:100%;border:none;min-height:500px;"
                srcdoc="${escapeAttr(`<base target="_blank"><style>body{font-family:sans-serif;font-size:14px;margin:0;padding:16px;color:#333;}a{color:#1976d2;}img{max-width:100%;height:auto;}</style>${email.body}`)}"></iframe>`;
        } else {
            bodyHtml = `<pre class="ep-body-text">${escapeHtml(email.body || 'Conteúdo não disponível. Sincronize novamente para buscar o corpo do email.')}</pre>`;
        }

        container.innerHTML = `
            <div class="detail-header">
                <a href="#/emails" class="btn btn-outline detail-back">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><polyline points="15 18 9 12 15 6"/></svg>
                    Voltar
                </a>
                <a href="${email.gmail_link}" target="_blank" class="btn btn-outline">Abrir no Gmail</a>
            </div>
            <div class="detail-subject">${escapeHtml(email.subject || '(sem assunto)')}</div>
            <div class="detail-meta">
                <div class="detail-meta-row">
                    <strong>De:</strong> ${escapeHtml(email.sender)}
                </div>
                <div class="detail-meta-row">
                    <strong>Para:</strong> ${escapeHtml(email.recipients)}
                </div>
                <div class="detail-meta-row">
                    <strong>Data:</strong> ${date}
                    <span style="margin-left:12px;">${labels}</span>
                    <span style="margin-left:12px;color:var(--text-muted)">${formatSize(email.size_estimate)}</span>
                </div>
            </div>
            ${attachmentsHtml}
            <div class="detail-body">${bodyHtml}</div>
        `;

        // Auto-resize iframe
        const iframe = document.getElementById('email-body-iframe');
        if (iframe) {
            iframe.onload = () => {
                try {
                    iframe.style.height = iframe.contentDocument.body.scrollHeight + 40 + 'px';
                } catch(e) {}
            };
        }
    } catch (e) {
        container.innerHTML = `<div style="text-align:center;padding:40px;">
            <p style="color:var(--danger);margin-bottom:16px;">Erro ao carregar email</p>
            <a href="#/emails" class="btn btn-outline">Voltar</a>
        </div>`;
    }
}

// ===== UTILS =====
function formatDate(isoStr) {
    const d = new Date(isoStr);
    const now = new Date();
    if (d.toDateString() === now.toDateString()) {
        return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' });
}

function formatSize(bytes) {
    if (!bytes || bytes === 0) return '-';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escapeAttr(str) {
    return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

// ===== AGENT CHAT =====
let chatHistory = [];
let chatBusy = false;
let chatSessions = [];
let currentSessionId = null;

function setupChatInput() {
    const input = document.getElementById('chat-input');
    if (input) {
        input.addEventListener('input', () => autoResizeTextarea(input));
    }
    loadChatSessions();
}

function useSuggestion(btn) {
    document.getElementById('chat-input').value = btn.textContent;
    sendChatMessage();
}

function handleChatKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
    }
}

async function sendChatMessage() {
    if (chatBusy) return;
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text) return;

    // Hide welcome
    const welcome = document.getElementById('chat-welcome');
    if (welcome) welcome.style.display = 'none';

    // Create session if first message
    if (!currentSessionId) {
        currentSessionId = Date.now().toString();
        chatSessions.unshift({
            id: currentSessionId,
            title: text.substring(0, 60),
            messages: [],
            toolsMap: {},
            createdAt: new Date().toISOString(),
        });
    }

    // Add user message
    chatHistory.push({ role: 'user', content: text });
    appendChatMessage('user', text);
    input.value = '';
    autoResizeTextarea(input);

    // Show typing
    chatBusy = true;
    const sendBtn = document.getElementById('chat-send-btn');
    sendBtn.disabled = true;
    const typingEl = showTypingIndicator();

    try {
        const res = await fetch(`${API}/api/agent/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages: chatHistory }),
        });
        const data = await res.json();

        removeTypingIndicator(typingEl);

        if (data.response) {
            chatHistory.push({ role: 'assistant', content: data.response });
            appendChatMessage('assistant', data.response, data.tools_used);
            // Save to session
            const session = chatSessions.find(s => s.id === currentSessionId);
            if (session) {
                session.messages = chatHistory.map(m => ({ ...m }));
                session.toolsMap[chatHistory.length - 1] = data.tools_used || [];
            }
        } else if (data.detail) {
            appendChatMessage('assistant', 'Erro: ' + data.detail);
        } else {
            console.error('Agent response empty:', data);
            appendChatMessage('assistant', 'Resposta vazia do agente. Verifique o modelo e a API key nas Configurações.');
        }
    } catch (e) {
        removeTypingIndicator(typingEl);
        console.error('Agent fetch error:', e);
        appendChatMessage('assistant', 'Erro ao comunicar com o agente: ' + e.message + '. O modelo pode estar demorando — tente novamente.');
    } finally {
        chatBusy = false;
        sendBtn.disabled = false;
        saveChatSessions();
        renderSessionsList();
    }
}

function appendChatMessage(role, content, toolsUsed = []) {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = `chat-message ${role}`;

    const avatar = role === 'user' ? 'U' : 'IA';
    let bubbleContent = role === 'assistant' ? renderMarkdown(content) : escapeHtml(content);

    let toolsHtml = '';
    if (toolsUsed && toolsUsed.length > 0) {
        const toolItems = toolsUsed.map(t => {
            const args = Object.entries(t.args || {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ');
            return `<div class="chat-tool-item">${escapeHtml(t.tool)}(${escapeHtml(args)})</div>`;
        }).join('');
        toolsHtml = `
            <div class="chat-tools-used">
                <button class="chat-tools-toggle" onclick="this.nextElementSibling.classList.toggle('open')">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
                    ${toolsUsed.length} ferramenta(s) utilizada(s)
                </button>
                <div class="chat-tools-list">${toolItems}</div>
            </div>`;
    }

    div.innerHTML = `
        <div class="chat-avatar">${avatar}</div>
        <div class="chat-bubble">${bubbleContent}${toolsHtml}</div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function showTypingIndicator() {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = 'chat-message assistant';
    div.id = 'chat-typing';
    div.innerHTML = `
        <div class="chat-avatar">IA</div>
        <div class="chat-bubble">
            <div class="chat-typing">
                <div class="chat-typing-dot"></div>
                <div class="chat-typing-dot"></div>
                <div class="chat-typing-dot"></div>
            </div>
        </div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
}

function removeTypingIndicator(el) {
    if (el && el.parentNode) el.parentNode.removeChild(el);
}

function clearChat() {
    chatHistory = [];
    currentSessionId = null;
    const container = document.getElementById('chat-messages');
    container.innerHTML = '';
    const welcome = document.getElementById('chat-welcome');
    if (welcome) {
        welcome.style.display = '';
        container.appendChild(welcome);
    }
    renderSessionsList();
}

// ===== CHAT SESSIONS (DB) =====
async function loadChatSessions() {
    try {
        const res = await fetch(`${API}/api/agent/sessions`);
        chatSessions = await res.json();
        renderSessionsList();
    } catch (e) {
        console.error('Failed to load sessions:', e);
        chatSessions = [];
    }
}

async function saveChatSessions() {
    const session = chatSessions.find(s => s.id === currentSessionId);
    if (!session) return;
    try {
        await fetch(`${API}/api/agent/sessions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(session),
        });
    } catch (e) {
        console.error('Failed to save session:', e);
    }
}

async function loadSession(id) {
    try {
        const res = await fetch(`${API}/api/agent/sessions/${id}`);
        const session = await res.json();
        currentSessionId = session.id;
        chatHistory = session.messages || [];

        const container = document.getElementById('chat-messages');
        container.innerHTML = '';
        const welcome = document.getElementById('chat-welcome');
        if (welcome) welcome.style.display = 'none';

        chatHistory.forEach((msg, idx) => {
            const tools = (session.toolsMap && session.toolsMap[idx]) || [];
            appendChatMessage(msg.role, msg.content, tools);
        });

        renderSessionsList();
    } catch (e) {
        showToast('Erro ao carregar sessão', 'error');
    }
}

async function deleteSession(id, e) {
    e.stopPropagation();
    try {
        await fetch(`${API}/api/agent/sessions/${id}`, { method: 'DELETE' });
        chatSessions = chatSessions.filter(s => s.id !== id);
        if (currentSessionId === id) clearChat();
        renderSessionsList();
    } catch (err) {
        showToast('Erro ao deletar sessão', 'error');
    }
}

function renderSessionsList() {
    const container = document.getElementById('chat-sessions-list');
    if (!container) return;
    if (!chatSessions || chatSessions.length === 0) {
        container.innerHTML = '<div class="sessions-empty">Nenhuma conversa salva</div>';
        return;
    }
    container.innerHTML = chatSessions.map(s => {
        const isActive = s.id === currentSessionId;
        const date = new Date(s.createdAt || s.created_at).toLocaleDateString('pt-BR');
        return `<div class="session-item ${isActive ? 'active' : ''}" onclick="loadSession('${s.id}')">
            <div class="session-title">${escapeHtml(s.title || 'Conversa')}</div>
            <div class="session-meta">${date}</div>
            <button class="session-delete" onclick="deleteSession('${s.id}', event)" title="Excluir">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
        </div>`;
    }).join('');
}

function autoResizeTextarea(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 150) + 'px';
}

// ===== SETTINGS / AI CONFIG =====
const DEFAULT_SYSTEM_PROMPT = `Você é um assistente de busca de emails inteligente. O usuário tem ~130 mil emails sincronizados no banco de dados.

Sua função:
1. Entender a pergunta do usuário sobre seus emails
2. Usar as ferramentas de busca disponíveis para encontrar os emails relevantes
3. Responder em português brasileiro (pt-BR) de forma clara e organizada

Regras:
- Sempre use as ferramentas para buscar dados. NUNCA invente informações.
- Ao listar emails, inclua: assunto, remetente, data e o link no formato [Assunto](link)
- O link para abrir o email no app é: #/email/{gmail_id}
- Se a busca retornar vários resultados, resuma os mais relevantes (máximo 10)
- Se não encontrar resultados, sugira buscas alternativas
- Quando o usuário perguntar sobre um remetente, use search_sender ou search_sender_exact
- Para buscas por conteúdo no corpo do email, use search_body_fulltext
- Para perguntas sobre período, use search_date_range ou search_combined com date_from/date_to
- Para perguntas que combinam vários critérios, use search_combined
- Formate datas no formato brasileiro (dd/mm/aaaa)
- Use get_email_detail apenas quando precisar do conteúdo completo de um email específico
- Use get_sender_summary para estatísticas sobre um remetente específico`;

async function loadAiConfig() {
    try {
        const res = await fetch(`${API}/api/config/ai`);
        const data = await res.json();
        document.getElementById('config-api-key').value = data.api_key_masked || '';
        document.getElementById('config-model').value = data.model || '';
        document.getElementById('config-system-prompt').value = data.system_prompt || DEFAULT_SYSTEM_PROMPT;
    } catch (e) {
        console.error('Failed to load AI config:', e);
    }
}

async function saveAiConfig() {
    const apiKey = document.getElementById('config-api-key').value.trim();
    const model = document.getElementById('config-model').value.trim();
    const systemPrompt = document.getElementById('config-system-prompt').value;

    const body = {};
    if (apiKey && !apiKey.includes('****')) body.api_key = apiKey;
    if (model) body.model = model;
    body.system_prompt = systemPrompt;

    try {
        const res = await fetch(`${API}/api/config/ai`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await res.json();
        document.getElementById('config-api-key').value = data.api_key_masked || '';
        document.getElementById('config-api-key').type = 'password';
        document.getElementById('config-model').value = data.model || '';
        document.getElementById('config-system-prompt').value = data.system_prompt || DEFAULT_SYSTEM_PROMPT;
        showToast('Configuração salva com sucesso!', 'success');
    } catch (e) {
        showToast('Erro ao salvar configuração', 'error');
    }
}

function resetSystemPrompt() {
    document.getElementById('config-system-prompt').value = DEFAULT_SYSTEM_PROMPT;
    showToast('Prompt restaurado ao padrão. Clique "Salvar" para aplicar.', 'info');
}

function toggleApiKeyVisibility() {
    const input = document.getElementById('config-api-key');
    input.type = input.type === 'password' ? 'text' : 'password';
}

// ===== API KEYS MANAGEMENT =====

async function loadApiKeys() {
    try {
        const res = await fetch(`${API}/api/api-keys`);
        const keys = await res.json();
        const tbody = document.getElementById('api-keys-tbody');
        if (!keys.length) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:20px;">Nenhuma chave criada</td></tr>';
            return;
        }
        tbody.innerHTML = keys.map(k => {
            const created = k.created_at ? new Date(k.created_at).toLocaleDateString('pt-BR') : '-';
            const lastUsed = k.last_used_at ? new Date(k.last_used_at).toLocaleDateString('pt-BR', {hour:'2-digit',minute:'2-digit'}) : 'Nunca';
            const status = k.is_active
                ? '<span style="color:var(--success,#22c55e);font-weight:600;">Ativa</span>'
                : '<span style="color:var(--text-muted);font-weight:600;">Revogada</span>';
            const actions = k.is_active
                ? `<button class="btn btn-sm btn-outline" onclick="revokeApiKey(${k.id})" title="Revogar">Revogar</button> <button class="btn btn-sm btn-danger-outline" onclick="deleteApiKey(${k.id},'${k.name.replace(/'/g,"\\'")}')" title="Excluir">Excluir</button>`
                : `<button class="btn btn-sm btn-danger-outline" onclick="deleteApiKey(${k.id},'${k.name.replace(/'/g,"\\'")}')" title="Excluir">Excluir</button>`;
            return `<tr>
                <td>${k.name}</td>
                <td><code style="font-size:12px;">${k.key_prefix}...</code></td>
                <td>${created}</td>
                <td>${lastUsed}</td>
                <td>${k.request_count}</td>
                <td>${status}</td>
                <td>${actions}</td>
            </tr>`;
        }).join('');
    } catch (e) {
        console.error('Failed to load API keys:', e);
    }
}

function showCreateApiKeyModal() {
    document.getElementById('api-key-create-form').style.display = '';
    document.getElementById('api-key-created-result').style.display = 'none';
    document.getElementById('api-key-name').value = '';
    document.getElementById('modal-create-api-key').style.display = 'flex';
    document.getElementById('api-key-name').focus();
}

async function createApiKey() {
    const name = document.getElementById('api-key-name').value.trim();
    if (!name) {
        showToast('Informe um nome para a chave', 'error');
        return;
    }
    try {
        const res = await fetch(`${API}/api/api-keys`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
        });
        if (!res.ok) throw new Error('Erro ao criar chave');
        const data = await res.json();
        document.getElementById('api-key-raw-value').value = data.key;
        document.getElementById('api-key-create-form').style.display = 'none';
        document.getElementById('api-key-created-result').style.display = '';
        loadApiKeys();
    } catch (e) {
        showToast('Erro ao criar chave de API', 'error');
    }
}

function copyApiKey() {
    const input = document.getElementById('api-key-raw-value');
    navigator.clipboard.writeText(input.value).then(() => {
        showToast('Chave copiada!', 'success');
    }).catch(() => {
        input.select();
        document.execCommand('copy');
        showToast('Chave copiada!', 'success');
    });
}

function closeApiKeyModal() {
    document.getElementById('modal-create-api-key').style.display = 'none';
}

async function revokeApiKey(id) {
    if (!confirm('Revogar esta chave? Sistemas que a utilizam perderão acesso.')) return;
    try {
        const res = await fetch(`${API}/api/api-keys/${id}/revoke`, { method: 'POST' });
        if (!res.ok) throw new Error();
        showToast('Chave revogada', 'success');
        loadApiKeys();
    } catch (e) {
        showToast('Erro ao revogar chave', 'error');
    }
}

async function deleteApiKey(id, name) {
    if (!confirm(`Excluir permanentemente a chave "${name}"?`)) return;
    try {
        const res = await fetch(`${API}/api/api-keys/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error();
        showToast('Chave excluída', 'success');
        loadApiKeys();
    } catch (e) {
        showToast('Erro ao excluir chave', 'error');
    }
}

// ===== MODELS BROWSER =====
let allModels = [];
let modelsSortBy = 'name';
let modelsSortOrder = 'asc';

function getModelProvider(model) {
    if (!model) return 'unknown';
    if (model.provider) return String(model.provider);
    if (!model.id) return 'unknown';
    return String(model.id).split('/')[0] || 'unknown';
}

function getModelContext(model) {
    return parseInt(model.context_length, 10) || 0;
}

function getModelPromptPricePerM(model) {
    return (parseFloat(model.pricing_prompt) || 0) * 1000000;
}

function getModelCompletionPricePerM(model) {
    return (parseFloat(model.pricing_completion) || 0) * 1000000;
}

function getModelCreated(model) {
    return parseInt(model.created, 10) || 0;
}

function compareModels(a, b) {
    let va;
    let vb;

    if (modelsSortBy === 'provider') {
        va = getModelProvider(a).toLowerCase();
        vb = getModelProvider(b).toLowerCase();
    } else if (modelsSortBy === 'context_length') {
        va = getModelContext(a);
        vb = getModelContext(b);
    } else if (modelsSortBy === 'pricing_prompt') {
        va = getModelPromptPricePerM(a);
        vb = getModelPromptPricePerM(b);
    } else if (modelsSortBy === 'pricing_completion') {
        va = getModelCompletionPricePerM(a);
        vb = getModelCompletionPricePerM(b);
    } else if (modelsSortBy === 'supports_tools') {
        va = a.supports_tools ? 1 : 0;
        vb = b.supports_tools ? 1 : 0;
    } else if (modelsSortBy === 'created') {
        va = getModelCreated(a);
        vb = getModelCreated(b);
    } else {
        va = String(a.name || a.id || '').toLowerCase();
        vb = String(b.name || b.id || '').toLowerCase();
    }

    if (va < vb) return modelsSortOrder === 'asc' ? -1 : 1;
    if (va > vb) return modelsSortOrder === 'asc' ? 1 : -1;
    return 0;
}

function renderModelRow(m, currentModel) {
    const provider = getModelProvider(m);
    const isCurrent = m.id === currentModel;
    const promptPrice = getModelPromptPricePerM(m);
    const completionPrice = getModelCompletionPricePerM(m);
    const ctx = getModelContext(m);
    const ctxK = ctx ? Math.round(ctx / 1024) + 'K' : '-';
    return `<tr class="${isCurrent ? 'model-current' : ''}">
        <td><button class="btn-use-model" onclick="selectModel('${escapeHtml(m.id)}')">${isCurrent ? 'Atual' : 'Usar'}</button></td>
        <td title="${escapeHtml(m.id)}">${escapeHtml(m.name || m.id)}</td>
        <td>${escapeHtml(provider)}</td>
        <td>${ctxK}</td>
        <td>$${promptPrice.toFixed(2)}/M</td>
        <td>$${completionPrice.toFixed(2)}/M</td>
        <td><span class="tools-badge ${m.supports_tools ? 'yes' : 'no'}">${m.supports_tools ? 'Sim' : 'Não'}</span></td>
        <td>${m.created ? new Date(m.created * 1000).toLocaleDateString('pt-BR') : '-'}</td>
    </tr>`;
}

function populateProviderFilter(models) {
    const select = document.getElementById('models-provider-filter');
    if (!select) return;
    const current = select.value;
    const providers = Array.from(new Set(models.map(getModelProvider))).sort((a, b) => a.localeCompare(b));
    select.innerHTML = '<option value="">Todos</option>' + providers.map(p => `<option value="${escapeAttr(p)}">${escapeHtml(p)}</option>`).join('');
    if (providers.includes(current)) select.value = current;
}

async function loadAiModels() {
    const btn = document.getElementById('btn-load-models');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Buscando...';

    try {
        const res = await fetch(`${API}/api/config/ai/models`);
        const data = await res.json();
        allModels = data.models || [];
        populateProviderFilter(allModels);
        document.getElementById('models-container').style.display = 'block';
        filterModels();
        showToast(`${allModels.length} modelos carregados`, 'success');
    } catch (e) {
        showToast('Erro ao buscar modelos: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Buscar Modelos';
    }
}

function filterModels() {
    const search = (document.getElementById('models-search')?.value || '').toLowerCase();
    const toolsFilter = document.getElementById('models-tools-filter')?.value;
    const providerFilter = document.getElementById('models-provider-filter')?.value || '';
    const groupBy = document.getElementById('models-group-by')?.value || 'none';
    const minContext = parseInt(document.getElementById('models-min-context-filter')?.value || '0', 10) || 0;
    const maxPromptPrice = parseFloat(document.getElementById('models-max-prompt-price')?.value || '');
    const maxCompletionPrice = parseFloat(document.getElementById('models-max-completion-price')?.value || '');
    const createdWithinDays = parseInt(document.getElementById('models-created-filter')?.value || '0', 10) || 0;
    const limit = parseInt(document.getElementById('models-limit')?.value || '200', 10) || 200;
    const nowSec = Math.floor(Date.now() / 1000);

    let filtered = allModels.filter(m => {
        if (search) {
            const haystack = `${m.id} ${m.name}`.toLowerCase();
            if (!haystack.includes(search)) return false;
        }
        if (toolsFilter === 'true' && !m.supports_tools) return false;
        if (toolsFilter === 'false' && m.supports_tools) return false;
        if (providerFilter && getModelProvider(m) !== providerFilter) return false;
        if (minContext > 0 && getModelContext(m) < minContext) return false;
        if (Number.isFinite(maxPromptPrice) && getModelPromptPricePerM(m) > maxPromptPrice) return false;
        if (Number.isFinite(maxCompletionPrice) && getModelCompletionPricePerM(m) > maxCompletionPrice) return false;
        if (createdWithinDays > 0) {
            const created = getModelCreated(m);
            if (!created) return false;
            const ageInDays = (nowSec - created) / 86400;
            if (ageInDays > createdWithinDays) return false;
        }
        return true;
    });

    filtered.sort(compareModels);

    const currentModel = document.getElementById('config-model').value;
    const limited = filtered.slice(0, limit);
    document.getElementById('models-info').textContent = `Mostrando ${limited.length} de ${filtered.length} filtrados (total: ${allModels.length})`;

    const tbody = document.getElementById('models-tbody');
    if (groupBy === 'provider') {
        const groups = new Map();
        limited.forEach(m => {
            const provider = getModelProvider(m);
            if (!groups.has(provider)) groups.set(provider, []);
            groups.get(provider).push(m);
        });

        const providers = Array.from(groups.keys()).sort((a, b) => a.localeCompare(b));
        let html = '';
        providers.forEach(provider => {
            const models = groups.get(provider) || [];
            html += `<tr class="models-group-row"><td colspan="8">${escapeHtml(provider)} <span>${models.length} modelo(s)</span></td></tr>`;
            html += models.map(m => renderModelRow(m, currentModel)).join('');
        });
        tbody.innerHTML = html;
    } else {
        tbody.innerHTML = limited.map(m => renderModelRow(m, currentModel)).join('');
    }

    // Update sort indicators
    document.querySelectorAll('.sortable-model').forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
        if (th.dataset.sort === modelsSortBy) {
            th.classList.add(modelsSortOrder === 'asc' ? 'sort-asc' : 'sort-desc');
        }
    });
}

function sortModels(column) {
    if (modelsSortBy === column) {
        modelsSortOrder = modelsSortOrder === 'asc' ? 'desc' : 'asc';
    } else {
        modelsSortBy = column;
        modelsSortOrder = column === 'name' || column === 'provider' ? 'asc' : 'desc';
    }
    filterModels();
}

function selectModel(id) {
    document.getElementById('config-model').value = id;
    filterModels(); // re-render to update highlight
    showToast(`Modelo selecionado: ${id}. Clique "Salvar Configuração" para aplicar.`, 'info');
}

function resetModelsFilters() {
    document.getElementById('models-search').value = '';
    document.getElementById('models-tools-filter').value = '';
    document.getElementById('models-provider-filter').value = '';
    document.getElementById('models-group-by').value = 'none';
    document.getElementById('models-min-context-filter').value = '';
    document.getElementById('models-max-prompt-price').value = '';
    document.getElementById('models-max-completion-price').value = '';
    document.getElementById('models-created-filter').value = '';
    document.getElementById('models-limit').value = '200';
    filterModels();
}

// ===== ACCOUNTS =====
async function loadAccountSelector() {
    try {
        const res = await fetch(`${API}/api/accounts`);
        const accounts = await res.json();
        renderAccountSelector(accounts);
    } catch (e) {
        console.error('Failed to load account selector:', e);
    }
}

async function loadAccounts() {
    try {
        const res = await fetch(`${API}/api/accounts`);
        const accounts = await res.json();
        renderAccountsList(accounts);
        renderAccountSelector(accounts);
    } catch (e) {
        console.error('Failed to load accounts:', e);
    }
}

function renderAccountsList(accounts) {
    const container = document.getElementById('accounts-list');
    if (!container) return;

    if (accounts.length === 0) {
        container.innerHTML = '<p style="color:var(--text-muted);font-size:13px;padding:12px 0;">Nenhuma conta configurada. Adicione uma conta para começar.</p>';
        return;
    }

    container.innerHTML = accounts.map(a => {
        const lastSync = a.last_sync_at ? new Date(a.last_sync_at).toLocaleString('pt-BR') : 'Nunca';
        const statusClass = a.is_active ? 'active' : 'inactive';
        const isGmail = (a.provider || '').toLowerCase() === 'gmail';
        const hasError = a.sync_status === 'error';
        const reconnectBtn = isGmail
            ? `<a class="btn btn-sm ${hasError ? 'btn-primary' : 'btn-outline'}" href="/auth/gmail/connect">Reconectar</a>`
            : '';
        const errorHtml = hasError && a.sync_error
            ? `<div class="account-error-msg">${escapeHtml(a.sync_error)}</div>`
            : '';
        return `<div class="account-item">
            <div class="account-info">
                <span class="account-status-dot ${statusClass}"></span>
                <div class="account-details">
                    <div class="account-name">${escapeHtml(a.name)}</div>
                    <div class="account-email">${escapeHtml(a.email)}</div>
                    <div class="account-meta">Último sync: ${lastSync}${hasError ? ' <span style="color:var(--danger)">Erro</span>' : ''}</div>
                </div>
                <span class="account-provider-badge ${a.provider}">${a.provider.toUpperCase()}</span>
            </div>
            ${errorHtml}
            <div class="account-actions">
                ${reconnectBtn}
                <button class="btn btn-sm btn-outline" onclick="syncAccountById(${a.id})">Sincronizar</button>
                <button class="btn btn-sm btn-outline" onclick="editAccount(${a.id})">Editar</button>
                <button class="btn btn-sm btn-danger" onclick="deleteAccount(${a.id}, '${escapeHtml(a.name)}')">Remover</button>
            </div>
        </div>`;
    }).join('');
}

function renderAccountSelector(accounts) {
    const selector = document.getElementById('account-selector');
    const select = document.getElementById('account-select');
    if (!selector || !select) return;

    if (accounts.length <= 1) {
        selector.style.display = 'none';
        return;
    }

    selector.style.display = 'block';
    const currentVal = select.value;
    select.innerHTML = '<option value="">Todas as Contas</option>' +
        accounts.map(a => `<option value="${a.id}" ${String(a.id) === currentVal ? 'selected' : ''}>${escapeHtml(a.name)} (${a.provider})</option>`).join('');
}

function switchAccount(accountId) {
    state.accountId = accountId ? parseInt(accountId) : null;
    state.page = 1;
    loadEmails();
    loadSidebar();
}

function showAddAccountModal() {
    document.getElementById('account-modal-title').textContent = 'Adicionar Conta';
    document.getElementById('account-edit-id').value = '';
    document.getElementById('account-name').value = '';
    document.getElementById('account-email').value = '';
    document.getElementById('account-provider').value = 'gmail';
    document.getElementById('account-provider').disabled = false;
    document.getElementById('account-imap-host').value = '';
    document.getElementById('account-imap-port').value = '993';
    document.getElementById('account-imap-username').value = '';
    document.getElementById('account-imap-password').value = '';
    document.getElementById('account-imap-ssl').checked = true;
    document.getElementById('test-connection-result').textContent = '';
    toggleImapFields();
    document.getElementById('account-modal').classList.add('visible');
}

function closeAccountModal() {
    document.getElementById('account-modal').classList.remove('visible');
}

function toggleImapFields() {
    const provider = document.getElementById('account-provider').value;
    const imapFields = document.getElementById('imap-fields');
    const gmailFields = document.getElementById('gmail-fields');
    const nameField = document.getElementById('account-name-field');
    const emailField = document.getElementById('account-email-field');
    const saveBtn = document.getElementById('account-save-btn');
    const isEditing = !!document.getElementById('account-edit-id').value;

    if (provider === 'imap') {
        imapFields.classList.add('visible');
        if (gmailFields) gmailFields.classList.remove('visible');
        if (nameField) nameField.style.display = '';
        if (emailField) emailField.style.display = '';
        if (saveBtn) saveBtn.style.display = '';
    } else {
        imapFields.classList.remove('visible');
        if (gmailFields) gmailFields.classList.add('visible');
        // For new Gmail accounts, hide name/email/save (user goes through OAuth)
        if (!isEditing) {
            if (nameField) nameField.style.display = 'none';
            if (emailField) emailField.style.display = 'none';
            if (saveBtn) saveBtn.style.display = 'none';
        } else {
            if (nameField) nameField.style.display = '';
            if (emailField) emailField.style.display = '';
            if (saveBtn) saveBtn.style.display = '';
        }
    }
}

async function testNewConnection() {
    const resultEl = document.getElementById('test-connection-result');
    resultEl.textContent = 'Testando...';
    resultEl.style.color = 'var(--text-muted)';

    const body = {
        imap_host: document.getElementById('account-imap-host').value,
        imap_port: parseInt(document.getElementById('account-imap-port').value) || 993,
        imap_username: document.getElementById('account-imap-username').value,
        imap_password: document.getElementById('account-imap-password').value,
        imap_use_ssl: document.getElementById('account-imap-ssl').checked,
    };

    try {
        const res = await fetch(`${API}/api/accounts/test-connection`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await res.json();
        resultEl.textContent = data.message;
        resultEl.style.color = data.success ? 'var(--success)' : 'var(--danger)';
    } catch (e) {
        resultEl.textContent = 'Erro: ' + e.message;
        resultEl.style.color = 'var(--danger)';
    }
}

async function saveAccount() {
    const editId = document.getElementById('account-edit-id').value;
    const body = {
        name: document.getElementById('account-name').value.trim(),
        email: document.getElementById('account-email').value.trim(),
        provider: document.getElementById('account-provider').value,
    };

    if (body.provider === 'imap') {
        body.imap_host = document.getElementById('account-imap-host').value.trim();
        body.imap_port = parseInt(document.getElementById('account-imap-port').value) || 993;
        body.imap_username = document.getElementById('account-imap-username').value.trim();
        body.imap_password = document.getElementById('account-imap-password').value;
        body.imap_use_ssl = document.getElementById('account-imap-ssl').checked;
    }

    if (!body.name || !body.email) {
        showToast('Preencha nome e email', 'error');
        return;
    }

    try {
        const url = editId ? `${API}/api/accounts/${editId}` : `${API}/api/accounts`;
        const method = editId ? 'PUT' : 'POST';
        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Erro ao salvar');
        }
        closeAccountModal();
        showToast(editId ? 'Conta atualizada!' : 'Conta criada!', 'success');
        loadAccounts();
    } catch (e) {
        showToast('Erro: ' + e.message, 'error');
    }
}

async function editAccount(id) {
    try {
        const res = await fetch(`${API}/api/accounts/${id}`);
        const a = await res.json();
        document.getElementById('account-modal-title').textContent = 'Editar Conta';
        document.getElementById('account-edit-id').value = a.id;
        document.getElementById('account-name').value = a.name;
        document.getElementById('account-email').value = a.email;
        document.getElementById('account-provider').value = a.provider;
        document.getElementById('account-provider').disabled = true;

        if (a.provider === 'imap') {
            document.getElementById('account-imap-host').value = a.imap_host || '';
            document.getElementById('account-imap-port').value = a.imap_port || 993;
            document.getElementById('account-imap-username').value = a.imap_username || '';
            document.getElementById('account-imap-password').value = '';
            document.getElementById('account-imap-ssl').checked = a.imap_use_ssl !== false;
        }

        toggleImapFields();
        document.getElementById('test-connection-result').textContent = '';
        document.getElementById('account-modal').classList.add('visible');
    } catch (e) {
        showToast('Erro ao carregar conta', 'error');
    }
}

async function deleteAccount(id, name) {
    if (!confirm(`Remover a conta "${name}"?\n\nTodos os emails sincronizados desta conta também serão apagados.`)) return;
    try {
        const res = await fetch(`${API}/api/accounts/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Erro ao remover');
        showToast('Conta removida', 'success');
        loadAccounts();
    } catch (e) {
        showToast('Erro: ' + e.message, 'error');
    }
}

async function syncAccountById(id) {
    try {
        const res = await fetch(`${API}/api/accounts/${id}/sync`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'started') {
            showToast('Sincronização iniciada', 'info');
        } else if (data.status === 'already_running') {
            showToast('Sincronização já em andamento', 'info');
        }
        // For Gmail accounts, use existing sync polling
        if (data.status === 'started' || data.status === 'already_running') {
            startSyncPolling();
        }
    } catch (e) {
        showToast('Erro ao sincronizar: ' + e.message, 'error');
    }
}

// ===== MARKDOWN RENDERER =====
function renderMarkdown(text) {
    if (!text) return '';
    if (typeof marked !== 'undefined') {
        marked.setOptions({ breaks: true, gfm: true });
        return marked.parse(text);
    }
    // Fallback if marked.js not loaded
    let html = escapeHtml(text);
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\n\n/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');
    return '<p>' + html + '</p>';
}

// ===== QUERY RESULTS PAGE =====
let queryResultsState = { queryId: null, page: 1, perPage: 50 };

async function loadQueryResults(queryId, page = 1) {
    queryResultsState.queryId = queryId;
    queryResultsState.page = page;

    const loading = document.getElementById('query-results-loading');
    const card = document.getElementById('query-results-card');
    const empty = document.getElementById('query-results-empty');
    const sqlPreview = document.getElementById('query-sql-preview');

    loading.style.display = '';
    card.style.display = 'none';
    empty.style.display = 'none';
    sqlPreview.style.display = 'none';
    document.getElementById('query-title').textContent = 'Carregando...';
    document.getElementById('query-description').textContent = '';
    document.getElementById('query-results-info').textContent = '';

    try {
        const res = await fetch(`${API}/api/queries/${queryId}/results?page=${page}&per_page=${queryResultsState.perPage}`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `Erro ${res.status}`);
        }
        const data = await res.json();
        const { query, results } = data;

        // Title and description
        document.getElementById('query-title').textContent = query.title || 'Consulta';
        document.getElementById('query-description').textContent = query.description || '';

        // SQL preview
        if (query.sql) {
            sqlPreview.style.display = '';
            sqlPreview.querySelector('.query-sql-code').textContent = query.sql;
        }

        loading.style.display = 'none';

        if (results.rows.length === 0 && page === 1) {
            empty.style.display = '';
            return;
        }

        card.style.display = '';

        // Render table header
        const thead = document.getElementById('query-results-thead');
        thead.innerHTML = '<tr>' + results.columns.map(col =>
            `<th>${escapeHtml(col)}</th>`
        ).join('') + '</tr>';

        // Render table body
        const tbody = document.getElementById('query-results-tbody');
        tbody.innerHTML = results.rows.map(row =>
            '<tr>' + results.columns.map(col => {
                const val = row[col];
                const display = val !== null && val !== undefined ? val : '';
                // Auto-link gmail_id values
                if (col === 'gmail_id' && display) {
                    return `<td><a href="#/email/${escapeHtml(display)}" class="email-link">${escapeHtml(display)}</a></td>`;
                }
                return `<td>${escapeHtml(String(display))}</td>`;
            }).join('') + '</tr>'
        ).join('');

        // Pagination info
        const start = (results.page - 1) * results.per_page + 1;
        const end = start + results.rows.length - 1;
        document.getElementById('query-pagination-info').textContent =
            `${start}-${end} de ${results.total} resultado(s)`;
        document.getElementById('query-results-info').textContent =
            `${results.total} resultado(s) encontrado(s)`;

        // Pagination controls
        renderQueryPagination(results.page, results.total_pages, queryId);

    } catch (e) {
        loading.style.display = 'none';
        empty.style.display = '';
        empty.querySelector('h3').textContent = 'Erro';
        empty.querySelector('p').textContent = e.message;
    }
}

function renderQueryPagination(currentPage, totalPages, queryId) {
    const container = document.getElementById('query-pagination-controls');
    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '';

    // Previous button
    html += `<button ${currentPage <= 1 ? 'disabled' : ''} onclick="loadQueryResults('${queryId}', ${currentPage - 1})">Anterior</button>`;

    // Page numbers
    const maxButtons = 7;
    let startPage = Math.max(1, currentPage - Math.floor(maxButtons / 2));
    let endPage = Math.min(totalPages, startPage + maxButtons - 1);
    if (endPage - startPage < maxButtons - 1) {
        startPage = Math.max(1, endPage - maxButtons + 1);
    }

    if (startPage > 1) {
        html += `<button onclick="loadQueryResults('${queryId}', 1)">1</button>`;
        if (startPage > 2) html += `<button disabled>...</button>`;
    }

    for (let i = startPage; i <= endPage; i++) {
        html += `<button class="${i === currentPage ? 'active' : ''}" onclick="loadQueryResults('${queryId}', ${i})">${i}</button>`;
    }

    if (endPage < totalPages) {
        if (endPage < totalPages - 1) html += `<button disabled>...</button>`;
        html += `<button onclick="loadQueryResults('${queryId}', ${totalPages})">${totalPages}</button>`;
    }

    // Next button
    html += `<button ${currentPage >= totalPages ? 'disabled' : ''} onclick="loadQueryResults('${queryId}', ${currentPage + 1})">Próximo</button>`;

    container.innerHTML = html;
}

// ===== ADMIN: USERS MANAGEMENT =====
let adminUsers = [];

async function loadUsers() {
    try {
        const res = await fetch(`${API}/api/users`);
        if (res.status === 403) {
            showToast('Acesso negado: apenas administradores', 'error');
            navigate('#/emails');
            return;
        }
        adminUsers = await res.json();
        renderUsersTable(adminUsers);
    } catch (e) {
        showToast('Erro ao carregar usuarios', 'error');
    }
}

function renderUsersTable(users) {
    const tbody = document.getElementById('users-tbody');
    if (!tbody) return;

    tbody.innerHTML = users.map(u => {
        const lastLogin = u.last_login ? new Date(u.last_login).toLocaleString('pt-BR') : 'Nunca';
        const avatar = u.picture
            ? `<img class="user-avatar-small" src="${escapeHtml(u.picture)}" alt="">`
            : `<div class="user-avatar-small" style="background:#e0e0e0;display:flex;align-items:center;justify-content:center;font-size:12px;color:#666;">${(u.name || u.email)[0].toUpperCase()}</div>`;

        return `<tr>
            <td>${avatar}</td>
            <td>${escapeHtml(u.email)}</td>
            <td>${escapeHtml(u.name || '-')}</td>
            <td><span class="user-role-badge ${u.role}">${u.role}</span></td>
            <td><span class="user-status-badge ${u.is_active ? 'active' : 'inactive'}">${u.is_active ? 'Ativo' : 'Inativo'}</span></td>
            <td>${lastLogin}</td>
            <td>
                <button class="btn btn-sm btn-outline" onclick="toggleUserActive(${u.id}, ${!u.is_active})">${u.is_active ? 'Desativar' : 'Ativar'}</button>
                <button class="btn btn-sm btn-outline" onclick="toggleUserRole(${u.id}, '${u.role === 'admin' ? 'user' : 'admin'}')">${u.role === 'admin' ? 'Tornar User' : 'Tornar Admin'}</button>
                <button class="btn btn-sm btn-danger" onclick="removeUser(${u.id}, '${escapeHtml(u.email)}')">Remover</button>
            </td>
        </tr>`;
    }).join('');
}

function showAddUserModal() {
    document.getElementById('new-user-email').value = '';
    document.getElementById('new-user-role').value = 'user';
    document.getElementById('user-modal').classList.add('visible');
}

function closeUserModal() {
    document.getElementById('user-modal').classList.remove('visible');
}

async function addUser() {
    const email = document.getElementById('new-user-email').value.trim();
    const role = document.getElementById('new-user-role').value;

    if (!email) {
        showToast('Preencha o email', 'error');
        return;
    }

    try {
        const res = await fetch(`${API}/api/users`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, role }),
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Erro ao adicionar');
        }
        closeUserModal();
        showToast('Usuario adicionado!', 'success');
        loadUsers();
    } catch (e) {
        showToast('Erro: ' + e.message, 'error');
    }
}

async function toggleUserActive(userId, isActive) {
    try {
        const res = await fetch(`${API}/api/users/${userId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: isActive }),
        });
        if (!res.ok) throw new Error('Erro ao atualizar');
        showToast(isActive ? 'Usuario ativado' : 'Usuario desativado', 'success');
        loadUsers();
    } catch (e) {
        showToast('Erro: ' + e.message, 'error');
    }
}

async function toggleUserRole(userId, role) {
    try {
        const res = await fetch(`${API}/api/users/${userId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role }),
        });
        if (!res.ok) throw new Error('Erro ao atualizar');
        showToast(`Role alterada para ${role}`, 'success');
        loadUsers();
    } catch (e) {
        showToast('Erro: ' + e.message, 'error');
    }
}

async function removeUser(userId, email) {
    if (!confirm(`Remover o usuario "${email}"?`)) return;
    try {
        const res = await fetch(`${API}/api/users/${userId}`, { method: 'DELETE' });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Erro ao remover');
        }
        showToast('Usuario removido', 'success');
        loadUsers();
    } catch (e) {
        showToast('Erro: ' + e.message, 'error');
    }
}

// ===== IREDMAIL INTEGRATION =====
let iredmailMailboxes = [];
let iredmailSelectedEmails = new Set();

async function loadIRedMailConfig() {
    if (!state.currentUser || state.currentUser.role !== 'admin') return;
    const card = document.getElementById('iredmail-card');
    if (card) card.style.display = '';
    try {
        const res = await fetch(`${API}/api/iredmail/config`);
        const config = await res.json();
        if (config) {
            document.getElementById('btn-iredmail-discover').style.display = '';
            document.getElementById('iredmail-status').textContent =
                `Configurado: ${config.mariadb_host} | Master user: ${config.has_master_password ? 'Sim' : 'Nao configurado'}`;
        } else {
            document.getElementById('iredmail-status').textContent =
                'Nao configurado. Clique em "Configurar" para conectar ao iRedMail.';
        }
    } catch (e) {
        console.error('Failed to load iRedMail config:', e);
    }
}

async function showIRedMailConfig() {
    try {
        const res = await fetch(`${API}/api/iredmail/config`);
        const config = await res.json();
        if (config) {
            document.getElementById('iredmail-mariadb-host').value = config.mariadb_host || '';
            document.getElementById('iredmail-mariadb-port').value = config.mariadb_port || 3306;
            document.getElementById('iredmail-mariadb-user').value = config.mariadb_user || '';
            document.getElementById('iredmail-mariadb-database').value = config.mariadb_database || 'vmail';
            document.getElementById('iredmail-imap-host').value = config.imap_host || '';
            document.getElementById('iredmail-imap-port').value = config.imap_port || 993;
            document.getElementById('iredmail-master-user').value = config.master_user || 'dovecotadmin';
        }
    } catch (e) { /* ignore */ }
    document.getElementById('iredmail-config-modal').classList.add('active');
}

function closeIRedMailConfig() {
    document.getElementById('iredmail-config-modal').classList.remove('active');
    document.getElementById('iredmail-test-result').textContent = '';
    document.getElementById('iredmail-master-test-result').textContent = '';
}

async function saveIRedMailConfig() {
    const body = {
        mariadb_host: document.getElementById('iredmail-mariadb-host').value,
        mariadb_port: parseInt(document.getElementById('iredmail-mariadb-port').value) || 3306,
        mariadb_user: document.getElementById('iredmail-mariadb-user').value,
        mariadb_password: document.getElementById('iredmail-mariadb-password').value,
        mariadb_database: document.getElementById('iredmail-mariadb-database').value || 'vmail',
        imap_host: document.getElementById('iredmail-imap-host').value,
        imap_port: parseInt(document.getElementById('iredmail-imap-port').value) || 993,
        master_user: document.getElementById('iredmail-master-user').value || 'dovecotadmin',
        master_password: document.getElementById('iredmail-master-password').value || null,
    };
    if (!body.mariadb_host || !body.mariadb_user || !body.mariadb_password) {
        showToast('Preencha host, usuario e senha do MariaDB', 'error');
        return;
    }
    try {
        const res = await fetch(`${API}/api/iredmail/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error('Erro ao salvar');
        showToast('Configuracao iRedMail salva', 'success');
        closeIRedMailConfig();
        loadIRedMailConfig();
    } catch (e) {
        showToast('Erro: ' + e.message, 'error');
    }
}

async function testIRedMailConnection() {
    const el = document.getElementById('iredmail-test-result');
    el.textContent = 'Testando...';
    el.style.color = 'var(--text-muted)';
    try {
        const res = await fetch(`${API}/api/iredmail/test-connection`, { method: 'POST' });
        const data = await res.json();
        el.textContent = data.message;
        el.style.color = data.success ? '#2e7d32' : '#c62828';
    } catch (e) {
        el.textContent = 'Erro: ' + e.message;
        el.style.color = '#c62828';
    }
}

async function testIRedMailMasterUser() {
    const el = document.getElementById('iredmail-master-test-result');
    el.textContent = 'Testando...';
    el.style.color = 'var(--text-muted)';
    try {
        const res = await fetch(`${API}/api/iredmail/test-master-user`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ test_email: document.getElementById('iredmail-mariadb-user').value + '@' + document.getElementById('iredmail-mariadb-host').value }),
        });
        const data = await res.json();
        el.textContent = data.message;
        el.style.color = data.success ? '#2e7d32' : '#c62828';
    } catch (e) {
        el.textContent = 'Erro: ' + e.message;
        el.style.color = '#c62828';
    }
}

async function discoverIRedMail() {
    const domain = document.getElementById('iredmail-domain-select').value || null;
    try {
        // Load domains for filter
        const domainsRes = await fetch(`${API}/api/iredmail/domains`);
        const domains = await domainsRes.json();
        const select = document.getElementById('iredmail-domain-select');
        select.innerHTML = '<option value="">Todos os Dominios</option>';
        domains.forEach(d => {
            if (d.mailbox_count > 0) {
                select.innerHTML += `<option value="${d.domain}" ${d.domain === domain ? 'selected' : ''}>${d.domain} (${d.mailbox_count})</option>`;
            }
        });
        document.getElementById('iredmail-domain-filter').style.display = '';

        // Load mailboxes
        const url = domain ? `${API}/api/iredmail/mailboxes?domain=${domain}` : `${API}/api/iredmail/mailboxes`;
        const res = await fetch(url);
        iredmailMailboxes = await res.json();
        iredmailSelectedEmails.clear();
        renderIRedMailMailboxes();
        document.getElementById('iredmail-mailboxes').style.display = '';
    } catch (e) {
        showToast('Erro ao descobrir caixas: ' + e.message, 'error');
    }
}

function filterIRedMailDomain(domain) {
    discoverIRedMail();
}

function renderIRedMailMailboxes() {
    const tbody = document.getElementById('iredmail-mailboxes-tbody');
    tbody.innerHTML = '';
    iredmailMailboxes.forEach(m => {
        const imported = m.already_imported;
        const active = m.active === 1;
        const usedMB = (m.used_bytes / (1024 * 1024)).toFixed(1);
        const tr = document.createElement('tr');
        if (imported) tr.style.opacity = '0.6';
        tr.innerHTML = `
            <td><input type="checkbox" class="iredmail-cb" data-email="${m.username}" ${imported ? 'disabled' : ''} ${iredmailSelectedEmails.has(m.username) ? 'checked' : ''} onchange="toggleIRedMailSelect(this)"></td>
            <td><strong>${m.username}</strong></td>
            <td>${m.name || '-'}</td>
            <td>${m.domain}</td>
            <td>${m.message_count.toLocaleString()}</td>
            <td>${usedMB} MB</td>
            <td>${imported ? '<span class="iredmail-badge-imported">Importada</span>' : active ? '<span class="iredmail-badge-active">Ativa</span>' : '<span class="iredmail-badge-inactive">Inativa</span>'}</td>
        `;
        tbody.appendChild(tr);
    });
    updateIRedMailSelectedCount();
}

function toggleIRedMailSelect(cb) {
    if (cb.checked) {
        iredmailSelectedEmails.add(cb.dataset.email);
    } else {
        iredmailSelectedEmails.delete(cb.dataset.email);
    }
    updateIRedMailSelectedCount();
}

function toggleIRedMailSelectAll(checked) {
    document.querySelectorAll('.iredmail-cb:not(:disabled)').forEach(cb => {
        cb.checked = checked;
        if (checked) iredmailSelectedEmails.add(cb.dataset.email);
        else iredmailSelectedEmails.delete(cb.dataset.email);
    });
    updateIRedMailSelectedCount();
}

function updateIRedMailSelectedCount() {
    document.getElementById('iredmail-selected-count').textContent = `${iredmailSelectedEmails.size} selecionadas`;
}

async function importSelectedIRedMail() {
    if (iredmailSelectedEmails.size === 0) {
        showToast('Selecione pelo menos uma caixa postal', 'error');
        return;
    }
    try {
        const res = await fetch(`${API}/api/iredmail/import`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ emails: Array.from(iredmailSelectedEmails) }),
        });
        const data = await res.json();
        showToast(`${data.total_created} criadas, ${data.total_skipped} ja existiam, ${data.total_errors} erros`, data.total_errors > 0 ? 'error' : 'success');
        iredmailSelectedEmails.clear();
        discoverIRedMail();
        loadAccounts();
    } catch (e) {
        showToast('Erro na importacao: ' + e.message, 'error');
    }
}

// ===== SYNC STATUS PAGE =====
let syncPagePollInterval = null;
const syncConnectionState = {};

function timeAgo(dateStr) {
    if (!dateStr) return 'Nunca';
    const now = new Date();
    const d = new Date(dateStr);
    const diffMs = now - d;
    const diffSec = Math.floor(diffMs / 1000);
    if (diffSec < 30) return 'agora';
    if (diffSec < 60) return `ha ${diffSec}s`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `ha ${diffMin} min`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `ha ${diffHr} hora${diffHr > 1 ? 's' : ''}`;
    const diffDay = Math.floor(diffHr / 24);
    return `ha ${diffDay} dia${diffDay > 1 ? 's' : ''}`;
}

async function loadSyncStatus() {
    // Clear any previous polling
    if (syncPagePollInterval) {
        clearInterval(syncPagePollInterval);
        syncPagePollInterval = null;
    }

    try {
        const res = await fetch(`${API}/api/accounts/sync/all-status?include_connection=true`);
        const accounts = await res.json();
        renderSyncTable(accounts);
        startSyncPagePolling(accounts.some(a => a.sync_status === 'syncing'));
    } catch (e) {
        console.error('Failed to load sync status:', e);
    }
}

function startSyncPagePolling(isSyncing) {
    if (syncPagePollInterval) {
        clearInterval(syncPagePollInterval);
        syncPagePollInterval = null;
    }
    const interval = isSyncing ? 2000 : 30000;

    syncPagePollInterval = setInterval(async () => {
        const hash = location.hash || '';
        if (!hash.includes('sync')) {
            clearInterval(syncPagePollInterval);
            syncPagePollInterval = null;
            return;
        }
        try {
            const r = await fetch(`${API}/api/accounts/sync/all-status`);
            const accs = await r.json();
            renderSyncTable(accs);

            const nowSyncing = accs.some(a => a.sync_status === 'syncing');
            if (nowSyncing !== isSyncing) {
                startSyncPagePolling(nowSyncing);
            }
        } catch (e) {}
    }, interval);
}

function renderSyncTable(accounts) {
    const container = document.getElementById('sync-accounts-list');
    if (!container) return;

    if (accounts.length === 0) {
        container.innerHTML = '<div class="card" style="text-align:center;padding:40px;color:var(--text-muted);">Nenhuma conta configurada. Adicione contas em Configuracoes.</div>';
        return;
    }

    container.innerHTML = accounts.map(a => {
        if (typeof a.connection_ok === 'boolean') {
            syncConnectionState[a.id] = {
                ok: a.connection_ok,
                message: a.connection_message || '',
            };
        }
        const savedConnection = syncConnectionState[a.id];
        const connectionOk = savedConnection ? savedConnection.ok : null;
        const connectionMessage = savedConnection ? savedConnection.message : '';

        const statusClass = a.sync_status || 'idle';
        const statusLabel = {syncing: 'Sincronizando', idle: 'Parado', error: 'Erro'}[statusClass] || statusClass;
        const providerLabel = (a.provider || '').toLowerCase() === 'gmail' ? 'OAuth Gmail' : 'IMAP';
        const connectionClass = connectionOk === true ? 'ok' : connectionOk === false ? 'error' : 'unknown';
        const connectionLabel = connectionOk === true
            ? `${providerLabel} conectado`
            : connectionOk === false
                ? `${providerLabel} com falha`
                : `${providerLabel} não verificado`;
        const connectionHint = connectionMessage
            ? escapeHtml(connectionMessage)
            : 'Status de conexão será validado ao abrir a página.';

        let progressHtml = '';
        if (a.sync_status === 'syncing' && a.progress) {
            const p = a.progress;
            let pct = 0;
            if (p.status === 'connecting') {
                progressHtml = `
                    <div class="sync-progress-bar"><div class="sync-progress-fill indeterminate"></div></div>
                    <div class="sync-folder-info">Conectando...</div>`;
            } else {
                pct = p.total > 0 ? Math.round((p.synced / p.total) * 100) : 0;
                progressHtml = `
                    <div class="sync-progress-bar"><div class="sync-progress-fill" style="width:${pct}%"></div></div>
                    <div class="sync-folder-info">${escapeHtml(p.folder)}: ${p.synced}/${p.total} (pasta ${p.folders_done + 1}/${p.folders_total})</div>`;
            }
        } else if (a.sync_status === 'syncing') {
            progressHtml = `
                <div class="sync-progress-bar"><div class="sync-progress-fill indeterminate"></div></div>
                <div class="sync-folder-info">Sincronizando...</div>`;
        }

        const errorHtml = a.sync_status === 'error' && a.sync_error
            ? `<div class="sync-error-msg">${escapeHtml(a.sync_error)}</div>` : '';

        const syncBtnClass = a.sync_status === 'syncing' ? 'btn-sync-spinning' : '';
        const syncBtnDisabled = a.sync_status === 'syncing' ? 'disabled' : '';

        const isGmail = (a.provider || '').toLowerCase() === 'gmail';
        const needsReconnect = isGmail && (a.sync_status === 'error' || connectionOk === false);
        const reconnectBtn = isGmail ? `<a class="btn btn-sm ${needsReconnect ? 'btn-primary' : 'btn-outline'}" href="/auth/gmail/connect" title="Re-autorizar acesso Gmail via OAuth">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                        <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/>
                    </svg>
                    Reconectar
                </a>` : '';

        return `<div class="sync-account-card">
            <div class="sync-account-main">
                <div class="sync-account-info">
                    <div class="sync-status-dot ${statusClass}"></div>
                    <div>
                        <div class="sync-account-name">${escapeHtml(a.name)}</div>
                        <div class="sync-account-email">${escapeHtml(a.email)}</div>
                        <div class="sync-connection-row">
                            <span class="sync-connection-badge ${connectionClass}">${connectionLabel}</span>
                            <span class="sync-connection-hint">${connectionHint}</span>
                        </div>
                    </div>
                </div>
                <span class="account-provider-badge ${a.provider}">${a.provider.toUpperCase()}</span>
                <div class="sync-account-stats">
                    <div class="sync-stat">
                        <span class="sync-stat-value">${(a.email_count || 0).toLocaleString()}</span>
                        <span class="sync-stat-label">emails</span>
                    </div>
                    <div class="sync-stat">
                        <span class="sync-stat-value">${timeAgo(a.last_sync_at)}</span>
                        <span class="sync-stat-label">ultimo sync</span>
                    </div>
                </div>
                <div class="sync-account-status">
                    <span class="sync-status-badge ${statusClass}">${statusLabel}</span>
                </div>
                <div class="sync-account-buttons">
                    ${reconnectBtn}
                    <button class="btn btn-sm btn-outline ${syncBtnClass}" onclick="syncSingleAccount(${a.id})" ${syncBtnDisabled}>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                            <polyline points="23 4 23 10 17 10"/>
                            <polyline points="1 20 1 14 7 14"/>
                            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                        </svg>
                        Sincronizar
                    </button>
                </div>
            </div>
            ${progressHtml}
            ${errorHtml}
        </div>`;
    }).join('');
}

async function syncAllAccounts() {
    try {
        const btn = document.getElementById('btn-sync-all');
        btn.disabled = true;
        btn.textContent = 'Iniciando...';

        const res = await fetch(`${API}/api/accounts/sync/all`, { method: 'POST' });
        const data = await res.json();

        const total = data.started.length + data.skipped.length;
        if (data.started.length > 0) {
            showToast(`Sync iniciado em ${data.started.length} conta(s)`, 'info');
        }
        if (data.skipped.length > 0) {
            showToast(`${data.skipped.length} conta(s) ja sincronizando`, 'info');
        }

        btn.disabled = false;
        btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Sincronizar Todas';

        // Restart polling with fast interval
        loadSyncStatus();
    } catch (e) {
        showToast('Erro: ' + e.message, 'error');
    }
}

async function syncSingleAccount(id) {
    try {
        // Capture email count before sync
        const beforeRes = await fetch(`${API}/api/accounts/sync/all-status`);
        const beforeAccs = await beforeRes.json();
        const beforeAcc = beforeAccs.find(a => a.id === id);
        const beforeCount = beforeAcc ? beforeAcc.email_count : 0;

        const res = await fetch(`${API}/api/accounts/${id}/sync`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'started') {
            showToast('Sincronizacao iniciada...', 'info');
            // Poll until done, then show result
            _pollSyncUntilDone(id, beforeCount);
        } else if (data.status === 'already_running') {
            showToast('Ja em andamento', 'info');
        }
        loadSyncStatus();
    } catch (e) {
        showToast('Erro: ' + e.message, 'error');
    }
}

function _pollSyncUntilDone(accountId, beforeCount, attempt = 0) {
    const maxAttempts = 60;
    const interval = attempt < 5 ? 1000 : 3000;

    setTimeout(async () => {
        try {
            const r = await fetch(`${API}/api/accounts/sync/all-status`);
            const accs = await r.json();
            const acc = accs.find(a => a.id === accountId);
            renderSyncTable(accs);

            if (!acc || acc.sync_status !== 'syncing') {
                const newCount = acc ? acc.email_count : 0;
                const diff = newCount - beforeCount;
                if (acc && acc.sync_status === 'error') {
                    showToast(`Erro na sincronizacao: ${acc.sync_error || 'desconhecido'}`, 'error');
                } else if (diff > 0) {
                    showToast(`Sincronizacao concluida! ${diff} novos emails`, 'success');
                } else {
                    showToast('Sincronizacao concluida. Nenhum email novo.', 'success');
                }
                loadSidebar();
                return;
            }

            if (attempt < maxAttempts) {
                _pollSyncUntilDone(accountId, beforeCount, attempt + 1);
            }
        } catch (e) {}
    }, interval);
}

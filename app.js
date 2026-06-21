// Paywall 管理面板 JS
const bridge = window.AstrBotPluginPage;
let currentData = {};
var _serverSettings = {};
var _pagination = {
    users: {page: 1},
    groups: {page: 1}
};

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, function(ch) {
        return {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }[ch];
    });
}

function jsArg(value) {
    return JSON.stringify(String(value ?? ''));
}

function clampNumber(value, min, max, fallback) {
    var n = parseInt(value, 10);
    if (isNaN(n)) return fallback;
    return Math.max(min, Math.min(max, n));
}

function getPageSize() {
    return clampNumber(_serverSettings['page-size'], 5, 100, 10);
}

function getAvatarStyle(id) {
    var text = String(id || '');
    var hash = 0;
    for (var i = 0; i < text.length; i++) {
        hash = ((hash << 5) - hash) + text.charCodeAt(i);
        hash |= 0;
    }
    var hue = Math.abs(hash) % 360;
    return 'background: linear-gradient(135deg, hsl(' + hue + ', 74%, 60%), hsl(' + ((hue + 42) % 360) + ', 70%, 42%));';
}

function getAvatarUrl(type, id) {
    var text = String(id || '').trim();
    if (!/^\d+$/.test(text)) return '';
    if (type === 'group') {
        return 'https://p.qlogo.cn/gh/' + encodeURIComponent(text) + '/' + encodeURIComponent(text) + '/100';
    }
    return 'https://q1.qlogo.cn/g?b=qq&nk=' + encodeURIComponent(text) + '&s=100';
}

function renderIdentity(type, id) {
    var safeId = escapeHtml(id);
    var text = String(id || '');
    var avatarText = type === 'group' ? '群' : (text.slice(-2) || 'U');
    var avatarUrl = getAvatarUrl(type, id);
    var avatarImg = avatarUrl
        ? '<img src="' + escapeHtml(avatarUrl) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">'
        : '';
    return '<div class="identity-cell">' +
        '<span class="avatar ' + (type === 'group' ? 'avatar-group' : 'avatar-user') + '" style="' + getAvatarStyle(id) + '">' + avatarImg + '<span class="avatar-fallback">' + escapeHtml(avatarText) + '</span></span>' +
        '<div class="identity-meta"><strong>' + safeId + '</strong><span>' + (type === 'group' ? '群组' : '用户') + ' ID</span></div>' +
        '</div>';
}

function getPagedList(type, list) {
    var pageSize = getPageSize();
    var totalPages = Math.max(1, Math.ceil(list.length / pageSize));
    _pagination[type].page = Math.max(1, Math.min(_pagination[type].page, totalPages));
    var start = (_pagination[type].page - 1) * pageSize;
    return {
        items: list.slice(start, start + pageSize),
        page: _pagination[type].page,
        totalPages: totalPages,
        total: list.length,
        start: list.length ? start + 1 : 0,
        end: Math.min(start + pageSize, list.length)
    };
}

function renderPagination(type, meta) {
    var el = document.getElementById(type === 'users' ? 'user-pagination' : 'group-pagination');
    if (!el) return;
    if (!meta.total) {
        el.innerHTML = '';
        return;
    }
    el.innerHTML = `
        <div class="page-info">显示 ${meta.start}-${meta.end} / ${meta.total}</div>
        <div class="page-actions">
            <button class="btn btn-small page-btn" onclick="changePage('${type}', -1)" ${meta.page <= 1 ? 'disabled' : ''}>上一页</button>
            <span class="page-current">${meta.page} / ${meta.totalPages}</span>
            <button class="btn btn-small page-btn" onclick="changePage('${type}', 1)" ${meta.page >= meta.totalPages ? 'disabled' : ''}>下一页</button>
        </div>`;
}

function changePage(type, delta) {
    _pagination[type].page += delta;
    if (type === 'users') renderUsers();
    if (type === 'groups') renderGroups();
}

function updatePageSize() {
    var input = document.getElementById('page-size-input');
    var value = clampNumber(input ? input.value : getPageSize(), 5, 100, 10);
    _serverSettings['page-size'] = String(value);
    if (input) input.value = value;
    _pagination.users.page = 1;
    _pagination.groups.page = 1;
    renderUsers();
    renderGroups();
}

function switchTab(tab) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    if (event && event.currentTarget) event.currentTarget.classList.add('active');
    var content = document.getElementById('tab-' + tab);
    if (!content) return;
    content.classList.remove('tab-animate');
    void content.offsetWidth;
    content.classList.add('active', 'tab-animate');
}

function showManagement() {
    var home = document.getElementById('home-view');
    var management = document.getElementById('management-view');
    if (!home || !management) return;
    management.classList.remove('leaving');
    home.classList.add('is-hidden');
    management.classList.add('active');
    var activeTab = management.querySelector('.tab-content.active');
    if (activeTab) {
        activeTab.classList.remove('tab-animate');
        void activeTab.offsetWidth;
        activeTab.classList.add('tab-animate');
    }
}

function showHome() {
    var home = document.getElementById('home-view');
    var management = document.getElementById('management-view');
    if (!home || !management) return;
    management.classList.add('leaving');
    window.setTimeout(function() {
        management.classList.remove('active', 'leaving');
        home.classList.remove('is-hidden');
    }, 420);
}

function showToast(msg, type) {
    var toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = msg;
    toast.className = 'toast toast-' + type + ' show';
    setTimeout(function() { toast.classList.remove('show'); }, 3000);
}

function showModal(id) {
    document.getElementById('modal-' + id).classList.add('active');
}

function hideModal() {
    var modals = document.querySelectorAll('.modal-overlay');
    for (var mi = 0; mi < modals.length; mi++) { modals[mi].classList.remove('active'); }
}

function setLoading(id, show) {
    document.getElementById(id).style.display = show ? 'inline-block' : 'none';
}

async function apiGet(path, params) {
    console.log('API GET (bridge):', path, params || '');
    return await bridge.apiGet(path, params);
}

async function apiPost(path, data) {
    console.log('API POST (bridge):', path, data);
    return await bridge.apiPost(path, data);
}

async function refreshData() {
    try {
        currentData = await apiGet('stats');
        _pagination.users.page = 1;
        _pagination.groups.page = 1;
        renderUsers();
        renderGroups();
        renderShop();
        renderKeys();
        updateStats();
        showToast('数据已刷新', 'success');
    } catch (e) {
        showToast('刷新失败: ' + e.message, 'error');
    }
}

function updateStats() {
    document.getElementById('user-count').textContent = currentData.users?.length || 0;
    document.getElementById('group-count').textContent = currentData.groups?.length || 0;
    const total = (currentData.users || []).reduce((s, u) => s + u.balance, 0) +
                 (currentData.groups || []).reduce((s, g) => s + g.balance, 0);
    document.getElementById('total-balance').textContent = total.toFixed(2);
    document.getElementById('item-count').textContent = (currentData.shop || []).length;
}

function renderUsers() {
    const tbody = document.getElementById('user-list');
    if (!currentData.users?.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">暂无用户数据</td></tr>';
        renderPagination('users', {total: 0});
        return;
    }
    const paged = getPagedList('users', currentData.users);
    tbody.innerHTML = paged.items.map((u, index) => `
        <tr class="list-row" style="--row-delay:${index * 58}ms"><td>${renderIdentity('user', u.id)}</td><td>${u.balance.toFixed(2)}</td><td>${u.total_used.toFixed(2)}</td><td>${u.total_calls}</td>
        <td><span class="badge ${u.balance > 0 ? 'badge-green' : 'badge-red'}">${u.balance > 0 ? '正常' : '欠费'}</span></td>
        <td class="action-btns">
            <button class="btn btn-success btn-small" onclick="quickRecharge('user', ${jsArg(u.id)}, 100)">+100</button>
            <button class="btn btn-success btn-small" onclick="quickRecharge('user', ${jsArg(u.id)}, 1000)">+1000</button>
            <button class="btn btn-danger btn-small" onclick="quickRecharge('user', ${jsArg(u.id)}, -50)">-50</button>
            <button class="btn btn-primary btn-small" onclick="openSetBalance('user', ${jsArg(u.id)}, ${u.balance})">设置额度</button>
        </td></tr>`).join('');
    renderPagination('users', paged);
}

function renderGroups() {
    const tbody = document.getElementById('group-list');
    if (!currentData.groups?.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">暂无群组数据</td></tr>';
        renderPagination('groups', {total: 0});
        return;
    }
    const paged = getPagedList('groups', currentData.groups);
    tbody.innerHTML = paged.items.map((g, index) => `
        <tr class="list-row" style="--row-delay:${index * 58}ms"><td>${renderIdentity('group', g.id)}</td><td>${g.balance.toFixed(2)}</td><td>${g.total_used.toFixed(2)}</td><td>${g.total_calls}</td>
        <td><span class="badge ${g.balance > 0 ? 'badge-green' : 'badge-red'}">${g.balance > 0 ? '正常' : '欠费'}</span></td>
        <td class="action-btns">
            <button class="btn btn-success btn-small" onclick="quickRecharge('group', ${jsArg(g.id)}, 100)">+100</button>
            <button class="btn btn-success btn-small" onclick="quickRecharge('group', ${jsArg(g.id)}, 1000)">+1000</button>
            <button class="btn btn-danger btn-small" onclick="quickRecharge('group', ${jsArg(g.id)}, -50)">-50</button>
            <button class="btn btn-primary btn-small" onclick="openSetBalance('group', ${jsArg(g.id)}, ${g.balance})">设置额度</button>
        </td></tr>`).join('');
    renderPagination('groups', paged);
}

function renderShop() {
    const tbody = document.getElementById('shop-list');
    if (!currentData.shop?.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">暂无商品</td></tr>';
        return;
    }
    tbody.innerHTML = currentData.shop.map((item, index) => `
        <tr class="list-row" style="--row-delay:${index * 58}ms"><td><code>${escapeHtml(item.id)}</code></td><td>${escapeHtml(item.name)}</td><td>${item.price.toFixed(2)}</td><td>${item.stock}</td>
        <td>${escapeHtml(item.seller_name || item.seller)}</td><td><span class="badge badge-yellow">${escapeHtml(item.shop_type)}</span></td>
        <td><button class="btn btn-danger btn-small" onclick="delistItem(${jsArg(item.id)})">下架</button></td></tr>`).join('');
}

function renderKeys() {
    const tbody = document.getElementById('key-list');
    if (!currentData.keys?.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">暂无卡密</td></tr>';
        return;
    }
    tbody.innerHTML = currentData.keys.map((k, index) => `
        <tr class="list-row" style="--row-delay:${index * 58}ms"><td><code>${escapeHtml(k.key)}</code></td><td>${k.amount.toFixed(0)}</td>
        <td><span class="badge ${k.status === 'unused' ? 'badge-green' : 'badge-red'}">${k.status === 'unused' ? '未使用' : '已使用'}</span></td>
        <td>${escapeHtml(k.created_by)}</td><td>${escapeHtml(k.used_by || '-')}</td></tr>`).join('');
}

async function quickRecharge(type, id, amount) {
    try {
        const res = await apiPost('recharge', {type, id, amount});
        if (res.success) {
            showToast(`${type === 'user' ? '用户' : '群组'} ${id} ${amount > 0 ? '充值' : '扣费'} ${Math.abs(amount)} 积分成功`, 'success');
            refreshData();
        } else {
            showToast('操作失败: ' + (res.error || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('操作失败: ' + e.message, 'error');
    }
}

let _setBalanceTarget = null;
function openSetBalance(type, id, current) {
    _setBalanceTarget = {type, id};
    document.getElementById('setbal-title').textContent =
        `设置${type === 'user' ? '用户' : '群组'} ${id} 的额度`;
    const input = document.getElementById('setbal-amount');
    input.value = (current != null ? current : '');
    showModal('set-balance');
    setTimeout(() => input.focus(), 50);
}

async function confirmSetBalance() {
    if (!_setBalanceTarget) return;
    const amount = parseFloat(document.getElementById('setbal-amount').value);
    if (isNaN(amount) || amount < 0) {
        showToast('请输入有效的额度（≥0）', 'error');
        return;
    }
    const {type, id} = _setBalanceTarget;
    setLoading('setbal-loading', true);
    try {
        const res = await apiPost('recharge', {type, id, amount, mode: 'set'});
        if (res.success) {
            showToast(`${type === 'user' ? '用户' : '群组'} ${id} 额度已设为 ${res.new_balance.toFixed(2)}`, 'success');
            hideModal();
            _setBalanceTarget = null;
            refreshData();
        } else {
            showToast('设置失败: ' + (res.error || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('设置失败: ' + e.message, 'error');
    }
    setLoading('setbal-loading', false);
}

async function doRecharge() {
    const type = document.getElementById('recharge-type').value;
    const id = document.getElementById('recharge-id').value.trim();
    const amount = parseFloat(document.getElementById('recharge-amount').value);
    if (!id || isNaN(amount)) {
        showToast('请填写完整信息', 'error');
        return;
    }
    setLoading('recharge-loading', true);
    try {
        const res = await apiPost('recharge', {type, id, amount});
        if (res.success) {
            showToast(`操作成功！新余额: ${res.new_balance.toFixed(2)}`, 'success');
            document.getElementById('recharge-id').value = '';
            document.getElementById('recharge-amount').value = '';
            refreshData();
        } else {
            showToast('操作失败: ' + (res.error || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('操作失败: ' + e.message, 'error');
    }
    setLoading('recharge-loading', false);
}

let _confirmCallback = null;
function showConfirm(message, onOk) {
    _confirmCallback = onOk;
    document.getElementById('confirm-message').textContent = message;
    showModal('confirm');
}
function confirmOk() {
    hideModal();
    const cb = _confirmCallback;
    _confirmCallback = null;
    if (cb) cb();
}

async function delistItem(itemId) {
    showConfirm('确认下架商品 ' + itemId + ' ?', async () => {
        try {
            const res = await apiPost('delist', {item_id: itemId});
            if (res.success) {
                showToast('下架成功: ' + res.name, 'success');
                refreshData();
            } else {
                showToast('下架失败: ' + (res.error || '未知错误'), 'error');
            }
        } catch (e) {
            showToast('下架失败: ' + e.message, 'error');
        }
    });
}

async function confirmListItem() {
    const name = document.getElementById('list-name').value.trim();
    const price = parseFloat(document.getElementById('list-price').value);
    const stock = parseInt(document.getElementById('list-stock').value);
    const shop_type = document.getElementById('list-type').value;
    if (!name) {
        showToast('请填写商品名称', 'error');
        return;
    }
    if (isNaN(price) || price < 0) {
        showToast('请填写有效价格', 'error');
        return;
    }
    if (isNaN(stock) || stock <= 0) {
        showToast('库存需大于0', 'error');
        return;
    }
    setLoading('listitem-loading', true);
    try {
        const res = await apiPost('list_item', {name, price, stock, shop_type});
        if (res.success) {
            showToast(`上架成功: ${res.name} (${res.id})`, 'success');
            hideModal();
            document.getElementById('list-name').value = '';
            document.getElementById('list-price').value = '';
            refreshData();
        } else {
            showToast('上架失败: ' + (res.error || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('上架失败: ' + e.message, 'error');
    }
    setLoading('listitem-loading', false);
}

async function testApi() {
    try {
        const res = await apiGet('test');
        document.getElementById('api-test').textContent = res.success ? '✅ 正常' : '❌ 失败';
        showToast(res.message || 'API 测试完成', res.success ? 'success' : 'error');
    } catch (e) {
        document.getElementById('api-test').textContent = '❌ 错误';
        showToast('API 测试失败: ' + e.message, 'error');
    }
}

async function confirmGenKey() {
    const amount = parseFloat(document.getElementById('key-amount').value);
    const count = parseInt(document.getElementById('key-count').value);
    if (!amount || !count) {
        showToast('请填写完整信息', 'error');
        return;
    }
    setLoading('genkey-loading', true);
    try {
        const res = await apiPost('genkey', {amount, count});
        if (res.success) {
            showToast(`成功生成 ${count} 张 ${amount} 积分卡密`, 'success');
            hideModal();
            document.getElementById('key-amount').value = '';
            refreshData();
        } else {
            showToast('生成失败: ' + (res.error || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('生成失败: ' + e.message, 'error');
    }
    setLoading('genkey-loading', false);
}

var _pendingWallpaper = null;
var _pendingWallpaperName = '';

function chooseBgFile() {
    document.getElementById('bg-upload').click();
}

async function uploadBgToServer(dataUrl, filename) {
    var parts = dataUrl.split(',');
    var base64 = parts.length > 1 ? parts[1] : '';
    if (!base64) return {success: false, error: '文件数据为空'};
    var byteChars = atob(base64);
    var byteLen = byteChars.length;
    var CHUNK_SIZE = 512 * 1024;
    var total = Math.ceil(byteLen / CHUNK_SIZE);
    for (var i = 0; i < total; i++) {
        var start = i * CHUNK_SIZE;
        var end = Math.min(start + CHUNK_SIZE, byteLen);
        var chunk = '';
        for (var j = start; j < end; j++) {
            chunk += String.fromCharCode(byteChars.charCodeAt(j));
        }
        var chunkBase64 = btoa(chunk);
        try {
            var res = await apiPost('upload_bg', {
                data: chunkBase64,
                index: i,
                total: total,
                name: filename
            });
            if (!res.success && !res.chunk_received) {
                return res;
            }
        } catch (e) {
            return {success: false, error: e.message};
        }
    }
    return {success: true};
}

function uploadWallpaper() {
    var fileInput = document.getElementById('bg-upload');
    var file = fileInput.files[0];
    if (!file) { showToast('请先选择图片', 'error'); return; }
    var reader = new FileReader();
    reader.onload = function(e) {
        _pendingWallpaper = e.target.result;
        _pendingWallpaperName = file.name;
        document.body.style.backgroundImage = 'url(' + _pendingWallpaper + ')';
        document.getElementById('bg-file-name').textContent = file.name + ' (预览中)';
        showToast('壁纸已预览，点「确定保存」后上传并生效', 'success');
    };
    reader.onerror = function() { showToast('读取文件失败', 'error'); };
    reader.readAsDataURL(file);
}

function applyDisplaySettings() {
    var blur = _serverSettings['glass-blur'] || '20';
    var alpha = _serverSettings['glass-alpha'] || '0.15';
    var textColor = _serverSettings['text-color'] || '#ffffff';

    var glassEls = document.querySelectorAll('.header, .stat-card, .panel, .tabs, .modal, .settings-panel, .settings-section');
    for (var gi = 0; gi < glassEls.length; gi++) {
        glassEls[gi].style.backdropFilter = 'blur(' + blur + 'px) saturate(180%)';
        glassEls[gi].style.background = 'rgba(255, 255, 255, ' + alpha + ')';
    }

    document.documentElement.style.setProperty('--ui-font-color', textColor);
    document.documentElement.style.setProperty('--ui-muted-color', hexToRgba(textColor, 0.72));
    document.documentElement.style.setProperty('--ui-faint-color', hexToRgba(textColor, 0.5));
    document.documentElement.style.setProperty('--ui-text-shadow', textColor.toLowerCase() === '#ffffff' ? '0 1px 3px rgba(0,0,0,0.35)' : 'none');

    var textColorInput = document.getElementById('text-color-input');
    if (textColorInput) textColorInput.value = textColor;
    var pageInput = document.getElementById('page-size-input');
    if (pageInput) pageInput.value = getPageSize();

    var blurSlider = document.getElementById('glass-blur-slider');
    if (blurSlider) { blurSlider.value = blur; document.getElementById('glass-blur-val').textContent = blur; }
    var alphaSlider = document.getElementById('glass-alpha-slider');
    if (alphaSlider) { alphaSlider.value = Math.round(parseFloat(alpha) * 100); document.getElementById('glass-alpha-val').textContent = Math.round(parseFloat(alpha) * 100); }
}

function hexToRgba(hex, alpha) {
    var clean = String(hex || '#ffffff').replace('#', '');
    if (clean.length === 3) clean = clean.split('').map(function(c) { return c + c; }).join('');
    var n = parseInt(clean, 16);
    if (isNaN(n)) return 'rgba(255,255,255,' + alpha + ')';
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + alpha + ')';
}

function updateTextColor() {
    var input = document.getElementById('text-color-input');
    _serverSettings['text-color'] = input ? input.value : '#ffffff';
    applyDisplaySettings();
}

function updateGlassBlur() {
    var v = document.getElementById('glass-blur-slider').value;
    _serverSettings['glass-blur'] = v;
    var els = document.querySelectorAll('.header, .stat-card, .panel, .tabs, .modal, .settings-panel, .settings-section');
    for (var gi = 0; gi < els.length; gi++) {
        els[gi].style.backdropFilter = 'blur(' + v + 'px) saturate(180%)';
    }
    document.getElementById('glass-blur-val').textContent = v;
}

function updateGlassAlpha() {
    var v = document.getElementById('glass-alpha-slider').value;
    var a = v / 100;
    _serverSettings['glass-alpha'] = String(a);
    var els = document.querySelectorAll('.header, .stat-card, .panel, .tabs, .modal, .settings-panel, .settings-section');
    for (var gi = 0; gi < els.length; gi++) { els[gi].style.background = 'rgba(255, 255, 255, ' + a + ')'; }
    document.getElementById('glass-alpha-val').textContent = v;
}

function resetDisplaySettings() {
    _serverSettings['glass-blur'] = '20';
    _serverSettings['glass-alpha'] = '0.15';
    _serverSettings['text-color'] = '#ffffff';
    _serverSettings['page-size'] = '10';
    _pagination.users.page = 1;
    _pagination.groups.page = 1;
    applyDisplaySettings();
    renderUsers();
    renderGroups();
}

async function saveSettings() {
    _serverSettings['glass-blur'] = document.getElementById('glass-blur-slider').value;
    _serverSettings['glass-alpha'] = String(document.getElementById('glass-alpha-slider').value / 100);
    _serverSettings['text-color'] = document.getElementById('text-color-input').value || '#ffffff';
    _serverSettings['page-size'] = String(clampNumber(document.getElementById('page-size-input').value, 5, 100, 10));
    delete _serverSettings['rainbow-enabled'];
    delete _serverSettings['breath-enabled'];
    delete _serverSettings['breath-color1'];
    delete _serverSettings['breath-color2'];
    delete _serverSettings['breath-color3'];
    delete _serverSettings['font-color-mode'];

    if (_pendingWallpaper) {
        showToast('正在上传壁纸...', 'success');
        try {
            var res = await uploadBgToServer(_pendingWallpaper, _pendingWallpaperName);
            if (res.success) {
                _pendingWallpaper = null;
                _pendingWallpaperName = '';
                showToast('壁纸上传成功！', 'success');
            } else {
                showToast('壁纸上传失败: ' + (res.error || '未知错误'), 'error');
                return;
            }
        } catch (e) {
            showToast('壁纸上传失败: ' + e.message, 'error');
            return;
        }
    }

    try {
        var saveRes = await apiPost('save_settings', {settings: _serverSettings});
        if (!saveRes.success) {
            showToast('设置保存失败: ' + (saveRes.error || '未知错误'), 'error');
            return;
        }
    } catch (e) {
        showToast('设置保存失败: ' + e.message, 'error');
        return;
    }

    applyDisplaySettings();
    try {
        var p = document.getElementById('settings-panel');
        var o = document.getElementById('settings-overlay');
        if (p) p.classList.remove('open');
        if (o) o.classList.remove('open');
    } catch(e) {}
    showToast('设置已保存', 'success');
}

function toggleSettings() {
    var panel = document.getElementById('settings-panel');
    var overlay = document.getElementById('settings-overlay');
    if (!panel) return;
    var open = panel.classList.toggle('open');
    if (overlay) overlay.classList.toggle('open');
    if (open) applyDisplaySettings();
}

async function loadSettings() {
    try {
        var res = await apiGet('get_settings');
        if (res.success && res.settings) {
            _serverSettings = res.settings;
        }
    } catch (e) {
        console.error('加载设置失败:', e);
    }
}

function initApp() {
    document.getElementById('app').innerHTML = `
        <div class="container">
            <div class="header">
                <span class="gear-btn" onclick="toggleSettings()">⚙️</span>
                <h1 id="main-title">🏦 Paywall 管理面板</h1>
                <p id="main-subtitle" style="font-size:16px;margin-top:8px;opacity:0.9;">API 双维度收费插件 - 积分管理系统</p>
            </div>
            <div id="home-view" class="home-view">
            <div class="stats-grid">
                <div class="stat-card"><h3>👤 用户总数</h3><div class="value" id="user-count">-</div></div>
                <div class="stat-card"><h3>👥 群组总数</h3><div class="value" id="group-count">-</div></div>
                <div class="stat-card"><h3>💰 积分总流通</h3><div class="value" id="total-balance">-</div></div>
                <div class="stat-card"><h3>📦 商品总数</h3><div class="value" id="item-count">-</div></div>
                <div class="stat-card stat-action" onclick="showManagement()"><h3>🧭 管理界面</h3><div class="value">进入</div></div>
                <div class="stat-card stat-action" onclick="testApi()"><h3>🔧 API 测试</h3><div class="value" id="api-test">点击测试</div></div>
            </div>
            </div>
            <div id="management-view" class="management-view">
            <div class="management-top">
                <button class="btn btn-primary" onclick="showHome()">← 返回</button>
                <div>
                    <h2>管理界面</h2>
                    <p>用户、群组、商城、卡密与充值操作</p>
                </div>
            </div>
            <div class="tabs">
                <div class="tab active" onclick="switchTab('users')">👤 用户管理</div>
                <div class="tab" onclick="switchTab('groups')">👥 群组管理</div>
                <div class="tab" onclick="switchTab('shop')">🛒 商城管理</div>
                <div class="tab" onclick="switchTab('keys')">🔑 卡密管理</div>
                <div class="tab" onclick="switchTab('recharge')">💳 快捷充值</div>

            </div>
            <div id="tab-users" class="tab-content active">
                <div class="panel">
                    <div class="panel-header"><span>用户余额列表</span><button class="btn btn-primary" onclick="refreshData()">🔄 刷新</button></div>
                    <div class="panel-body"><table><thead><tr><th>用户</th><th>余额</th><th>累计消耗</th><th>调用次数</th><th>状态</th><th>操作</th></tr></thead><tbody id="user-list"><tr><td colspan="6" class="empty-state">加载中...</td></tr></tbody></table><div id="user-pagination" class="pagination"></div></div>
                </div>
            </div>
            <div id="tab-groups" class="tab-content">
                <div class="panel">
                    <div class="panel-header"><span>群组余额列表</span><button class="btn btn-primary" onclick="refreshData()">🔄 刷新</button></div>
                    <div class="panel-body"><table><thead><tr><th>群组</th><th>余额</th><th>累计消耗</th><th>调用次数</th><th>状态</th><th>操作</th></tr></thead><tbody id="group-list"><tr><td colspan="6" class="empty-state">加载中...</td></tr></tbody></table><div id="group-pagination" class="pagination"></div></div>
                </div>
            </div>
            <div id="tab-shop" class="tab-content">
                <div class="panel">
                    <div class="panel-header"><span>商城商品列表</span><div><button class="btn btn-primary" onclick="refreshData()">🔄 刷新</button><button class="btn btn-success" onclick="showModal('list-item')">➕ 上架商品</button></div></div>
                    <div class="panel-body"><table><thead><tr><th>编号</th><th>名称</th><th>价格</th><th>库存</th><th>卖家</th><th>类型</th><th>操作</th></tr></thead><tbody id="shop-list"><tr><td colspan="7" class="empty-state">加载中...</td></tr></tbody></table></div>
                </div>
            </div>
            <div id="tab-keys" class="tab-content">
                <div class="panel">
                    <div class="panel-header"><span>卡密管理</span><div><button class="btn btn-primary" onclick="refreshData()">🔄 刷新</button><button class="btn btn-success" onclick="showModal('gen-key')">➕ 生成卡密</button></div></div>
                    <div class="panel-body"><table><thead><tr><th>卡密</th><th>面额</th><th>状态</th><th>创建者</th><th>使用者</th></tr></thead><tbody id="key-list"><tr><td colspan="5" class="empty-state">加载中...</td></tr></tbody></table></div>
                </div>
            </div>
            <div id="tab-recharge" class="tab-content">
                <div class="panel">
                    <div class="panel-header">💳 快捷充值 / 扣费</div>
                    <div class="panel-body">
                        <div class="form-row">
                            <div class="form-group"><label>目标类型</label><select id="recharge-type"><option value="user">👤 用户</option><option value="group">👥 群组</option></select></div>
                            <div class="form-group"><label>目标ID</label><input type="text" id="recharge-id" placeholder="QQ号或群号"></div>
                            <div class="form-group"><label>金额（正数充值，负数扣费）</label><input type="number" id="recharge-amount" placeholder="例如: 100 或 -50" step="1"></div>
                        </div>
                        <button class="btn btn-success" onclick="doRecharge()">✅ 确认操作 <span id="recharge-loading" style="display:none;" class="loading"></span></button>
                    </div>
                </div>
            </div>
            </div>
        </div>
        <div id="settings-panel" class="settings-panel">
            <div class="settings-top">
                <div>
                    <h2>⚙️ 设置</h2>
                    <p>调整面板外观和列表显示</p>
                </div>
                <span class="settings-close" onclick="toggleSettings()">✕</span>
            </div>

            <div class="settings-section">
                <h3>🖼️ 壁纸</h3>
                <p>上传 JPG/PNG 图片作为背景壁纸。</p>
                <div class="file-input-area">
                    <input type="file" id="bg-upload" accept="image/jpeg,image/png" style="display:none;" onchange="uploadWallpaper()">
                    <button class="btn btn-primary" onclick="chooseBgFile()">📁 选择图片</button>
                    <span id="bg-file-name">未选择文件</span>
                    <span id="bg-upload-loading" style="display:none;" class="loading"></span>
                </div>
                <div class="settings-note">选择图片后自动预览，点「确定保存」上传并生效。</div>
            </div>

            <div class="settings-section">
                <h3>🎨 显示设置</h3>
                <div class="form-group">
                    <label>玻璃模糊 <span id="glass-blur-val">20</span>px</label>
                    <input type="range" id="glass-blur-slider" min="0" max="40" value="20" oninput="updateGlassBlur()">
                </div>
                <div class="form-group">
                    <label>玻璃透明度 <span id="glass-alpha-val">15</span>%</label>
                    <input type="range" id="glass-alpha-slider" min="5" max="50" value="15" oninput="updateGlassAlpha()">
                </div>
                <div class="settings-grid">
                    <div class="form-group">
                        <label>文字颜色</label>
                        <input type="color" id="text-color-input" value="#ffffff" oninput="updateTextColor()">
                    </div>
                    <div class="form-group">
                        <label>每页显示</label>
                        <input type="number" id="page-size-input" min="5" max="100" value="10" onchange="updatePageSize()">
                    </div>
                </div>
                <div class="settings-note">每页显示数量会同时应用到用户和群组列表。</div>
            </div>

            <div class="settings-actions">
                <button class="btn btn-primary" onclick="resetDisplaySettings()">↺ 重置默认</button>
                <button class="btn btn-success" onclick="saveSettings()">✅ 确定保存</button>
            </div>
        </div>
        <div class="settings-overlay" id="settings-overlay" onclick="toggleSettings()"></div>
        <div class="modal-overlay" id="modal-gen-key">
            <div class="modal">
                <h2>🔑 生成卡密</h2>
                <div class="form-group"><label>面额</label><input type="number" id="key-amount" placeholder="积分数量" min="1"></div>
                <div class="form-group"><label>数量</label><input type="number" id="key-count" placeholder="生成几张" min="1" max="50" value="1"></div>
                <div class="modal-footer"><button class="btn" onclick="hideModal()">取消</button><button class="btn btn-success" onclick="confirmGenKey()">生成 <span id="genkey-loading" style="display:none;" class="loading"></span></button></div>
            </div>
        </div>
        <div class="modal-overlay" id="modal-list-item">
            <div class="modal">
                <h2>➕ 上架商品</h2>
                <div class="form-group"><label>商品名称</label><input type="text" id="list-name" placeholder="例如: 蘑菇"></div>
                <div class="form-group"><label>价格（积分）</label><input type="number" id="list-price" placeholder="例如: 1000" min="0" step="1"></div>
                <div class="form-group"><label>库存</label><input type="number" id="list-stock" placeholder="例如: 999" min="1" step="1" value="999"></div>
                <div class="form-group"><label>商城类型</label><select id="list-type"><option value="百货">百货商城</option><option value="道具">道具商城</option></select></div>
                <div class="modal-footer"><button class="btn" onclick="hideModal()">取消</button><button class="btn btn-success" onclick="confirmListItem()">上架 <span id="listitem-loading" style="display:none;" class="loading"></span></button></div>
            </div>
        </div>
        <div class="modal-overlay" id="modal-set-balance">
            <div class="modal">
                <h2 id="setbal-title">设置额度</h2>
                <div class="form-group"><label>额度（直接设为该值）</label><input type="number" id="setbal-amount" placeholder="例如: 5000" min="0" step="1"></div>
                <div class="modal-footer"><button class="btn" onclick="hideModal()">取消</button><button class="btn btn-success" onclick="confirmSetBalance()">确认设置 <span id="setbal-loading" style="display:none;" class="loading"></span></button></div>
            </div>
        </div>
        <div class="modal-overlay" id="modal-confirm">
            <div class="modal">
                <h2>⚠️ 确认操作</h2>
                <p id="confirm-message" style="color:#fff;margin:10px 0 20px;"></p>
                <div class="modal-footer"><button class="btn" onclick="hideModal()">取消</button><button class="btn btn-danger" onclick="confirmOk()">确认</button></div>
            </div>
        </div>
        <div class="toast" id="toast"></div>
    `;
}

bridge.ready().then(async () => {
    initApp();
    await loadSettings();
    refreshData();
    applyDisplaySettings();
}).catch(e => {
    console.error('Bridge 初始化失败:', e);
    document.getElementById('app').innerHTML = '<div style="padding:40px;text-align:center;color:#fff;">❌ 插件 Bridge 初始化失败，请刷新页面重试</div>';
});

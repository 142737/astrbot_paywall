// Paywall 管理面板 JS
const bridge = window.AstrBotPluginPage;
let currentData = {};

function switchTab(tab) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById('tab-' + tab).classList.add('active');
}

function showToast(msg, type) {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.className = 'toast toast-' + type + ' show';
    setTimeout(() => toast.classList.remove('show'), 3000);
}

function showModal(id) {
    document.getElementById('modal-' + id).classList.add('active');
}

function hideModal() {
    document.querySelectorAll('.modal-overlay').forEach(m => m.classList.remove('active'));
}

function setLoading(id, show) {
    document.getElementById(id).style.display = show ? 'inline-block' : 'none';
}

// bridge.apiGet / apiPost 直接返回已解析的数据对象（不是 fetch 的 Response）。
// Page 运行在受限 iframe 中，必须走 bridge 才能复用 Dashboard 鉴权，
// 不能退回到裸 fetch（会因缺少鉴权 token 报 Failed to fetch）。
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
        return;
    }
    tbody.innerHTML = currentData.users.map(u => `
        <tr><td>${u.id}</td><td>${u.balance.toFixed(2)}</td><td>${u.total_used.toFixed(2)}</td><td>${u.total_calls}</td>
        <td><span class="badge ${u.balance > 0 ? 'badge-green' : 'badge-red'}">${u.balance > 0 ? '正常' : '欠费'}</span></td>
        <td class="action-btns">
            <button class="btn btn-success btn-small" onclick="quickRecharge('user', '${u.id}', 100)">+100</button>
            <button class="btn btn-success btn-small" onclick="quickRecharge('user', '${u.id}', 1000)">+1000</button>
            <button class="btn btn-danger btn-small" onclick="quickRecharge('user', '${u.id}', -50)">-50</button>
            <button class="btn btn-primary btn-small" onclick="openSetBalance('user', '${u.id}', ${u.balance})">设置额度</button>
        </td></tr>`).join('');
}

function renderGroups() {
    const tbody = document.getElementById('group-list');
    if (!currentData.groups?.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">暂无群组数据</td></tr>';
        return;
    }
    tbody.innerHTML = currentData.groups.map(g => `
        <tr><td>${g.id}</td><td>${g.balance.toFixed(2)}</td><td>${g.total_used.toFixed(2)}</td><td>${g.total_calls}</td>
        <td><span class="badge ${g.balance > 0 ? 'badge-green' : 'badge-red'}">${g.balance > 0 ? '正常' : '欠费'}</span></td>
        <td class="action-btns">
            <button class="btn btn-success btn-small" onclick="quickRecharge('group', '${g.id}', 100)">+100</button>
            <button class="btn btn-success btn-small" onclick="quickRecharge('group', '${g.id}', 1000)">+1000</button>
            <button class="btn btn-danger btn-small" onclick="quickRecharge('group', '${g.id}', -50)">-50</button>
            <button class="btn btn-primary btn-small" onclick="openSetBalance('group', '${g.id}', ${g.balance})">设置额度</button>
        </td></tr>`).join('');
}

function renderShop() {
    const tbody = document.getElementById('shop-list');
    if (!currentData.shop?.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">暂无商品</td></tr>';
        return;
    }
    tbody.innerHTML = currentData.shop.map(item => `
        <tr><td><code>${item.id}</code></td><td>${item.name}</td><td>${item.price.toFixed(2)}</td><td>${item.stock}</td>
        <td>${item.seller_name || item.seller}</td><td><span class="badge badge-yellow">${item.shop_type}</span></td>
        <td><button class="btn btn-danger btn-small" onclick="delistItem('${item.id}')">下架</button></td></tr>`).join('');
}

function renderKeys() {
    const tbody = document.getElementById('key-list');
    if (!currentData.keys?.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">暂无卡密</td></tr>';
        return;
    }
    tbody.innerHTML = currentData.keys.map(k => `
        <tr><td><code>${k.key}</code></td><td>${k.amount.toFixed(0)}</td>
        <td><span class="badge ${k.status === 'unused' ? 'badge-green' : 'badge-red'}">${k.status === 'unused' ? '未使用' : '已使用'}</span></td>
        <td>${k.created_by}</td><td>${k.used_by || '-'}</td></tr>`).join('');
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

// 设置额度：直接把余额设为指定值（mode=set）
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

// 页面内确认弹窗（受限 iframe 沙箱中原生 confirm 会被拦截并返回 false，故自实现）
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

async function uploadWallpaper() {
    const fileInput = document.getElementById('bg-upload');
    const file = fileInput.files[0];
    if (!file) { showToast('请先选择图片', 'error'); return; }
    showConfirm('是否将「' + file.name + '」设置为壁纸？确定后将自动上传并刷新页面。', async function() {
        document.getElementById('bg-file-name').textContent = file.name + ' (上传中...)';
        setLoading('bg-upload-loading', true);
        try {
            const reader = new FileReader();
            reader.onload = async function(e) {
                const base64 = e.target.result.split(',')[1];
                const res = await bridge.apiPost('upload_bg', {data: base64, name: file.name});
                setLoading('bg-upload-loading', false);
                if (res.success) {
                    showConfirm('壁纸已更新，是否刷新页面？', function() { location.reload(); });
                } else {
                    showToast('上传失败: ' + (res.error || '未知错误'), 'error');
                }
            };
            reader.onerror = function() {
                showToast('读取文件失败', 'error');
                setLoading('bg-upload-loading', false);
            };
            reader.readAsDataURL(file);
        } catch (e) {
            showToast('上传失败: ' + e.message, 'error');
            setLoading('bg-upload-loading', false);
        }
    });
}// 初始化页面结构
function initApp() {
    document.getElementById('app').innerHTML = `
        <div class="container">
            <div class="header">
                <h1>🏦 Paywall 管理面板</h1>
                <p>API 双维度收费插件 - 积分管理系统</p>
            </div>
            <div class="stats-grid">
                <div class="stat-card"><h3>👤 用户总数</h3><div class="value" id="user-count">-</div></div>
                <div class="stat-card"><h3>👥 群组总数</h3><div class="value" id="group-count">-</div></div>
                <div class="stat-card"><h3>💰 积分总流通</h3><div class="value" id="total-balance">-</div></div>
                <div class="stat-card"><h3>📦 商品总数</h3><div class="value" id="item-count">-</div></div>
            <div class="stat-card" style="cursor:pointer;" onclick="testApi()"><h3>🔧 API 测试</h3><div class="value" id="api-test">点击测试</div></div>
            </div>
            <div class="tabs">
                <div class="tab active" onclick="switchTab('users')">👤 用户管理</div>
                <div class="tab" onclick="switchTab('groups')">👥 群组管理</div>
                <div class="tab" onclick="switchTab('shop')">🛒 商城管理</div>
                <div class="tab" onclick="switchTab('keys')">🔑 卡密管理</div>
                <div class="tab" onclick="switchTab('recharge')">💳 快捷充值</div>
                <div class="tab" onclick="switchTab('wallpaper')">🖼️ 更换壁纸</div>
            </div>
            <div id="tab-users" class="tab-content active">
                <div class="panel">
                    <div class="panel-header"><span>用户余额列表</span><button class="btn btn-primary" onclick="refreshData()">🔄 刷新</button></div>
                    <div class="panel-body"><table><thead><tr><th>用户ID</th><th>余额</th><th>累计消耗</th><th>调用次数</th><th>状态</th><th>操作</th></tr></thead><tbody id="user-list"><tr><td colspan="6" class="empty-state">加载中...</td></tr></tbody></table></div>
                </div>
            </div>
            <div id="tab-groups" class="tab-content">
                <div class="panel">
                    <div class="panel-header"><span>群组余额列表</span><button class="btn btn-primary" onclick="refreshData()">🔄 刷新</button></div>
                    <div class="panel-body"><table><thead><tr><th>群号</th><th>余额</th><th>累计消耗</th><th>调用次数</th><th>状态</th><th>操作</th></tr></thead><tbody id="group-list"><tr><td colspan="6" class="empty-state">加载中...</td></tr></tbody></table></div>
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
        <div id="tab-wallpaper" class="tab-content">
            <div class="panel">
                <div class="panel-header">🖼️ 更换壁纸</div>
                <div class="panel-body">
                    <p style="margin-bottom:15px;color:rgba(255,255,255,0.8);">上传一张 JPG/PNG 图片作为管理面板的壁纸（自动保存为 bg.jpg）。</p>
                    <div class="file-input-area">
                        <input type="file" id="bg-upload" accept="image/jpeg,image/png" style="display:none;" onchange="uploadWallpaper()">
                        <button class="btn btn-primary" onclick="document.getElementById('bg-upload').click()">📁 选择图片</button>
                        <span id="bg-file-name" style="margin-left:10px;color:rgba(255,255,255,0.6);">未选择文件</span>
                        <span id="bg-upload-loading" style="display:none;margin-left:10px;" class="loading"></span>
                    </div>
                    <div style="margin-top:20px;padding:15px;background:rgba(255,255,255,0.1);border-radius:8px;">
                        <p style="margin-bottom:5px;color:rgba(255,255,255,0.8);">💡 提示：新图片会自动覆盖旧文件，上传后刷新页面即可看到效果。</p>
                    </div>
                </div>
            </div>
        </div>
        <div class="modal-overlay" id="modal-gen-key"id="modal-gen-key"id="modal-gen-key">
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

// 启动
bridge.ready().then(() => {
    initApp();
    refreshData();

}).catch(e => {
    console.error('Bridge 初始化失败:', e);
    document.getElementById('app').innerHTML = '<div style="padding:40px;text-align:center;color:#fff;">❌ 插件 Bridge 初始化失败，请刷新页面重试</div>';
});

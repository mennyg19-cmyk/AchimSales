/* ================================================================
   Settings page -- extracted from settings.html inline script
   ================================================================ */

/* -- Collapsible sections ------------------------------------------------ */

function toggleSection(header) {
    var parent = header.parentElement;
    var body = parent.querySelector('.collapsible-body');
    if (!body) body = parent.parentElement.querySelector('.collapsible-body');
    if (!body) return;
    header.classList.toggle('collapsed');
    body.classList.toggle('collapsed');
}

/* -- Customer exclusions ------------------------------------------------- */

var _excludedAccounts = (typeof SETTINGS_CONFIG !== 'undefined' && SETTINGS_CONFIG.excluded) ? SETTINGS_CONFIG.excluded : [];
var _hasChanges = false;

function toggleCustomer(account, checkbox) {
    var item = checkbox.closest('.settings-customer-item');
    if (checkbox.checked) {
        var idx = _excludedAccounts.indexOf(account);
        if (idx > -1) _excludedAccounts.splice(idx, 1);
        item.classList.remove('excluded');
    } else {
        if (_excludedAccounts.indexOf(account) === -1) _excludedAccounts.push(account);
        item.classList.add('excluded');
    }
    _hasChanges = true;
    document.getElementById('saveBar').style.display = 'flex';
    document.getElementById('saveStatus').textContent = 'Unsaved changes';
}

function saveExclusions() {
    var saveStatus = document.getElementById('saveStatus');
    saveStatus.textContent = 'Saving...';

    fetch('/api/settings/excluded-customers', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({accounts: _excludedAccounts})
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            saveStatus.textContent = 'Saved!';
            _hasChanges = false;
            setTimeout(function() {
                if (!_hasChanges) document.getElementById('saveBar').style.display = 'none';
            }, 2000);
        } else {
            saveStatus.textContent = 'Error saving';
        }
    })
    .catch(function() {
        saveStatus.textContent = 'Error saving';
    });
}

function filterSettingsCustomers() {
    var q = document.getElementById('settingsSearch').value.toLowerCase();
    var body = document.getElementById('settingsCustomerList').closest('.collapsible-body');
    if (q && body && body.classList.contains('collapsed')) {
        body.classList.remove('collapsed');
        var header = body.parentElement.querySelector('.settings-section-title.collapsible');
        if (header) header.classList.remove('collapsed');
    }
    var items = document.querySelectorAll('#settingsCustomerList .settings-customer-item');
    items.forEach(function(item) {
        var text = item.textContent.toLowerCase();
        item.style.display = text.indexOf(q) !== -1 ? '' : 'none';
    });
}

function toggleTheme(checkbox) {
    var theme = checkbox.checked ? 'dark' : 'light';
    document.body.classList.toggle('dark-theme', checkbox.checked);
    fetch('/api/settings/theme', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({theme: theme})
    }).catch(function() { });
}

function toggleSalesmanField(prefix) {
    var role = document.getElementById(prefix + 'UserRole').value;
    var wrap = document.getElementById(prefix + 'SalesmanKeyWrap');
    if (wrap) wrap.style.display = role === 'salesman' ? '' : 'none';
    var smAssign = document.getElementById(prefix + 'AssignedSalesmenWrap');
    if (smAssign) smAssign.style.display = role === 'manager' ? '' : 'none';
    // The "External (magic-link)" option only makes sense for salesmen.
    // Hide it for any other role to avoid mismatched configs.
    var extWrap = (prefix === 'new')
        ? document.getElementById('newUserExternalWrap')
        : document.getElementById('editUserExternalRow');
    if (extWrap) extWrap.style.display = role === 'salesman' ? '' : 'none';
    if (role !== 'salesman') {
        var newCb = document.getElementById('newUserIsExternal');
        if (newCb && prefix === 'new') newCb.checked = false;
        var editCb = document.getElementById('editUserIsExternal');
        if (editCb && prefix === 'edit') editCb.checked = false;
    }
}

function showMsg(elId, msg, isError) {
    var el = document.getElementById(elId);
    el.textContent = msg;
    el.style.color = isError ? 'var(--error)' : 'var(--success)';
    el.style.display = 'block';
    if (!isError) setTimeout(function() { el.style.display = 'none'; }, 3000);
}

function addUser() {
    var email = document.getElementById('newUserEmail').value.trim();
    var role = document.getElementById('newUserRole').value;
    var key = document.getElementById('newUserSalesmanKey').value.trim();
    var name = document.getElementById('newUserDisplayName').value.trim();
    var isExt = !!(document.getElementById('newUserIsExternal') || {}).checked;

    if (!email) { showMsg('addUserMsg', 'Email is required', true); return; }

    fetch('/api/users', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({email: email, role: role, salesman_key: key,
                              display_name: name, is_external: isExt})
    })
    .then(function(r) { return r.json().then(function(d) { return {ok: r.ok, data: d}; }); })
    .then(function(res) {
        if (res.ok) {
            showMsg('addUserMsg', 'User added!', false);
            setTimeout(function() { location.reload(); }, 1000);
        } else {
            showMsg('addUserMsg', res.data.error || 'Error', true);
        }
    })
    .catch(function() { showMsg('addUserMsg', 'Network error', true); });
}

/* User edit/delete functions are in admin.js */

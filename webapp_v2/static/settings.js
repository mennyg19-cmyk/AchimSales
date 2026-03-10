/* ================================================================
   Settings page -- extracted from settings.html inline script
   ================================================================ */

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

var _excludedSalesmen = (typeof SETTINGS_CONFIG !== 'undefined' && SETTINGS_CONFIG.excludedSalesmen) ? SETTINGS_CONFIG.excludedSalesmen : [];
var _smHasChanges = false;

function toggleSalesman(key, checkbox) {
    var item = checkbox.closest('.settings-customer-item');
    if (checkbox.checked) {
        var idx = _excludedSalesmen.indexOf(key);
        if (idx > -1) _excludedSalesmen.splice(idx, 1);
        item.classList.remove('excluded');
    } else {
        if (_excludedSalesmen.indexOf(key) === -1) _excludedSalesmen.push(key);
        item.classList.add('excluded');
    }
    _smHasChanges = true;
    document.getElementById('smSaveBar').style.display = 'flex';
    document.getElementById('smSaveStatus').textContent = 'Unsaved changes';
}

function saveSalesmenExclusions() {
    var status = document.getElementById('smSaveStatus');
    status.textContent = 'Saving...';
    fetch('/api/settings/excluded-salesmen', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({keys: _excludedSalesmen})
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            status.textContent = 'Saved!';
            _smHasChanges = false;
            setTimeout(function() {
                if (!_smHasChanges) document.getElementById('smSaveBar').style.display = 'none';
            }, 2000);
        } else { status.textContent = 'Error saving'; }
    })
    .catch(function() { status.textContent = 'Error saving'; });
}

function toggleSalesmanField(prefix) {
    var role = document.getElementById(prefix + 'UserRole').value;
    var wrap = document.getElementById(prefix + 'SalesmanKeyWrap');
    if (wrap) wrap.style.display = role === 'salesman' ? '' : 'none';
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

    if (!email) { showMsg('addUserMsg', 'Email is required', true); return; }

    fetch('/api/users', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({email: email, role: role, salesman_key: key, display_name: name})
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

function editUserFromBtn(btn) {
    var u = JSON.parse(btn.getAttribute('data-user'));
    editUser(u.email, u.role, u.salesman_key || '', u.display_name || '');
}

function editUser(email, role, key, name) {
    document.getElementById('editUserEmail').value = email;
    document.getElementById('editUserEmailDisplay').value = email;
    document.getElementById('editUserRole').value = role;
    document.getElementById('editUserSalesmanKey').value = key;
    document.getElementById('editUserDisplayName').value = name;
    toggleSalesmanField('edit');
    document.getElementById('editUserModal').style.display = 'flex';
}

function closeEditModal() {
    document.getElementById('editUserModal').style.display = 'none';
    document.getElementById('editUserMsg').style.display = 'none';
}

function saveEditUser() {
    var email = document.getElementById('editUserEmail').value;
    var role = document.getElementById('editUserRole').value;
    var key = document.getElementById('editUserSalesmanKey').value.trim();
    var name = document.getElementById('editUserDisplayName').value.trim();

    fetch('/api/users/' + encodeURIComponent(email), {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({role: role, salesman_key: key, display_name: name})
    })
    .then(function(r) { return r.json().then(function(d) { return {ok: r.ok, data: d}; }); })
    .then(function(res) {
        if (res.ok) {
            closeEditModal();
            location.reload();
        } else {
            showMsg('editUserMsg', res.data.error || 'Error', true);
        }
    })
    .catch(function() { showMsg('editUserMsg', 'Network error', true); });
}

function deleteUserFromBtn(btn) {
    deleteUser(btn.getAttribute('data-email'));
}

function deleteUser(email) {
    if (!confirm('Remove ' + email + ' from the app?')) return;

    fetch('/api/users/' + encodeURIComponent(email), {method: 'DELETE'})
    .then(function(r) { return r.json().then(function(d) { return {ok: r.ok, data: d}; }); })
    .then(function(res) {
        if (res.ok) location.reload();
        else alert(res.data.error || 'Error');
    })
    .catch(function() { alert('Network error'); });
}

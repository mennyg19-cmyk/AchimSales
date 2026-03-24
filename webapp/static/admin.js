/* ================================================================
   Admin Tools panel -- unified permission grid, report visibility,
   feature flags, user edit modal with permissions.
   ================================================================ */

/* -- Report visibility (global toggle) ---------------------------------- */

function toggleReportEnabled(reportKey, checkbox) {
    var enabled = checkbox.checked;
    fetch('/api/admin/reports/visibility', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({report_key: reportKey, enabled: enabled})
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (!data.success) checkbox.checked = !enabled;
    })
    .catch(function() { checkbox.checked = !enabled; });
}

/* -- Feature flags ------------------------------------------------------- */

function toggleFeatureFlag(flagKey, checkbox) {
    var enabled = checkbox.checked;
    fetch('/api/admin/feature-flags', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({flag_key: flagKey, enabled: enabled})
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (!data.success) checkbox.checked = !enabled;
    })
    .catch(function() { checkbox.checked = !enabled; });
}

/* -- Permission grid search --------------------------------------------- */

function filterPermGrid() {
    var q = document.getElementById('permGridSearch').value.toLowerCase();
    var rows = document.querySelectorAll('#permUserList .perm-user-row');
    rows.forEach(function(row) {
        row.style.display = row.textContent.toLowerCase().indexOf(q) !== -1 ? '' : 'none';
    });
}

/* -- User permission modal ---------------------------------------------- */

var _editUserData = null;

document.addEventListener('DOMContentLoaded', function() {
    var list = document.getElementById('permUserList');
    if (!list) return;
    list.addEventListener('click', function(e) {
        var row = e.target.closest('.perm-user-row');
        if (row) openUserPermModal(row);
    });
});

function openUserPermModal(rowEl) {
    try {
        _editUserData = JSON.parse(rowEl.getAttribute('data-user'));
    } catch (err) {
        console.error('Failed to parse user data:', err);
        return;
    }
    var u = _editUserData;

    document.getElementById('editUserEmail').value = u.email;
    document.getElementById('editUserEmailDisplay').value = u.email;
    document.getElementById('editUserRole').value = u.role;
    document.getElementById('editUserDisplayName').value = u.display_name || '';

    var smWrap = document.getElementById('editSalesmanKeyWrap');
    var smSelect = document.getElementById('editUserSalesmanKey');
    if (smWrap) smWrap.style.display = u.role === 'salesman' ? '' : 'none';
    if (smSelect) smSelect.value = u.salesman_key || '';

    var assignedSm = u.allowed_salesmen || [];
    var smToggles = document.querySelectorAll('.assigned-sm-toggle');
    smToggles.forEach(function(toggle) {
        toggle.checked = assignedSm.indexOf(toggle.getAttribute('data-sm-key')) !== -1;
    });

    toggleSalesmanField('edit');

    var activeToggle = document.getElementById('editUserActive');
    if (activeToggle) activeToggle.checked = !!u.active;

    var dashToggle = document.getElementById('editUserDashboard');
    if (dashToggle) dashToggle.checked = !!u.dashboard_enabled;

    var reports = u.reports || {};
    var reportToggles = document.querySelectorAll('[id^="editReport_"]');
    reportToggles.forEach(function(toggle) {
        var rk = toggle.getAttribute('data-report-key');
        toggle.checked = !!reports[rk];
    });

    document.getElementById('editUserMsg').style.display = 'none';
    document.getElementById('editUserModal').style.display = 'flex';
}

function closeEditModal() {
    document.getElementById('editUserModal').style.display = 'none';
    document.getElementById('editUserMsg').style.display = 'none';
    _editUserData = null;
}

function saveEditUser() {
    var email = document.getElementById('editUserEmail').value;
    var role = document.getElementById('editUserRole').value;
    var key = document.getElementById('editUserSalesmanKey').value.trim();
    var name = document.getElementById('editUserDisplayName').value.trim();
    var msg = document.getElementById('editUserMsg');

    var promises = [];

    promises.push(
        fetch('/api/users/' + encodeURIComponent(email), {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({role: role, salesman_key: key, display_name: name})
        }).then(function(r) { return r.json(); })
    );

    var activeToggle = document.getElementById('editUserActive');
    if (activeToggle && _editUserData && _editUserData.salesman_key) {
        var active = activeToggle.checked ? 1 : 0;
        promises.push(
            fetch('/api/admin/salesmen/' + encodeURIComponent(_editUserData.salesman_key), {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({active: active})
            }).then(function(r) { return r.json(); })
        );
    }

    var dashToggle = document.getElementById('editUserDashboard');
    if (dashToggle) {
        promises.push(
            fetch('/api/admin/user-dashboard', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email: email, enabled: dashToggle.checked})
            }).then(function(r) { return r.json(); })
        );
    }

    var reportToggles = document.querySelectorAll('[id^="editReport_"]');
    reportToggles.forEach(function(toggle) {
        var rk = toggle.getAttribute('data-report-key');
        promises.push(
            fetch('/api/admin/user-report-access', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email: email, report_key: rk, allowed: toggle.checked})
            }).then(function(r) { return r.json(); })
        );
    });

    if (role === 'manager') {
        var selectedKeys = [];
        document.querySelectorAll('.assigned-sm-toggle').forEach(function(toggle) {
            if (toggle.checked) selectedKeys.push(toggle.getAttribute('data-sm-key'));
        });
        promises.push(
            fetch('/api/admin/user-salesman-access', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email: email, salesman_keys: selectedKeys})
            }).then(function(r) { return r.json(); })
        );
    }

    Promise.all(promises).then(function(results) {
        var anyFail = results.some(function(r) { return !r.success; });
        if (anyFail) {
            _showMsg(msg, 'Some changes may have failed', true);
        } else {
            _showMsg(msg, 'Saved!', false);
            setTimeout(function() { location.reload(); }, 600);
        }
    }).catch(function() {
        _showMsg(msg, 'Network error', true);
    });
}

function deleteUserFromModal() {
    var email = document.getElementById('editUserEmail').value;
    if (!confirm('Remove ' + email + ' from the app?')) return;
    fetch('/api/users/' + encodeURIComponent(email), {method: 'DELETE'})
    .then(function(r) { return r.json(); })
    .then(function(d) {
        if (d.success) { closeEditModal(); location.reload(); }
        else alert(d.error || 'Error');
    })
    .catch(function() { alert('Network error'); });
}

function _showMsg(el, msg, isError) {
    if (!el) return;
    el.textContent = msg;
    el.style.color = isError ? 'var(--error)' : 'var(--success)';
    el.style.display = 'block';
    if (!isError) setTimeout(function() { el.style.display = 'none'; }, 3000);
}

function _adminMsg(elId, msg, isError) {
    _showMsg(document.getElementById(elId), msg, isError);
}

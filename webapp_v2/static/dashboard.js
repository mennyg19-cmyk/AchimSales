/* ================================================================
   Dashboard page -- extracted from dashboard.html inline script
   ================================================================ */

function dismissNotification(id, btn) {
    var item = btn.closest('.dash-alert-item');
    fetch('/api/notifications/dismiss', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id})
    }).then(function() {
        item.style.transition = 'opacity 0.3s, max-height 0.3s';
        item.style.opacity = '0';
        item.style.maxHeight = '0';
        item.style.overflow = 'hidden';
        item.style.padding = '0';
        item.style.margin = '0';
        setTimeout(function() { item.remove(); updateAlertCount(); }, 300);
    }).catch(function() { });
}

function updateAlertCount() {
    var items = document.querySelectorAll('.dash-alert-item');
    var countBadge = document.querySelector('.dash-alerts .badge');
    if (countBadge) countBadge.textContent = items.length;
    if (!items.length) {
        var panel = document.getElementById('dashAlerts');
        if (panel) panel.style.display = 'none';
    }
}

function triggerDashRefresh() {
    var btn = document.getElementById('refreshBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px;"></span> Refreshing&hellip;';
    showRefreshProgress(true);

    fetch('/api/dashboard/refresh', {method: 'POST'})
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var before = data.before || '';
            var reqEl = document.getElementById('refreshRequested');
            if (reqEl && data.requested_at) {
                reqEl.textContent = 'Last requested: ' + data.requested_at.substring(0, 16).replace('T', ' ');
            }
            pollRefreshStatus(before, 0);
        })
        .catch(function() {
            resetRefreshBtn();
        });
}

function showRefreshProgress(show) {
    var panel = document.getElementById('refreshProgress');
    if (panel) panel.style.display = show ? 'block' : 'none';
}

function resetRefreshBtn() {
    var btn = document.getElementById('refreshBtn');
    if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i data-feather="refresh-cw" style="width:14px;height:14px;"></i> Refresh';
        if (typeof feather !== 'undefined') feather.replace();
    }
    showRefreshProgress(false);
}

function pollRefreshStatus(before, attempts) {
    if (attempts > 120) {
        window.location.reload();
        return;
    }
    setTimeout(function() {
        fetch('/api/dashboard/refresh-status?before=' + encodeURIComponent(before))
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var label = document.getElementById('refreshProgressLabel');
                if (data.step && label) {
                    label.textContent = data.step;
                }
                if (data.done) {
                    if (label) label.textContent = 'Refresh complete! Reloading\u2026';
                    setTimeout(function() { window.location.reload(); }, 600);
                } else {
                    pollRefreshStatus(before, attempts + 1);
                }
            })
            .catch(function() {
                window.location.reload();
            });
    }, 2000);
}

var _activeStatusFilter = '';

function filterByCard(card, status) {
    _activeStatusFilter = status;
    document.querySelectorAll('.dash-card-filter').forEach(function(c) {
        c.classList.remove('dash-card-filter-active');
    });
    card.classList.add('dash-card-filter-active');
    applyDashFilters();
}

function filterDashTable() {
    applyDashFilters();
}

function applyDashFilters() {
    var q = (document.getElementById('dashSearch').value || '').toLowerCase();
    var rows = document.querySelectorAll('#dashTable tbody .dash-row');
    rows.forEach(function(row) {
        var matchStatus = !_activeStatusFilter || row.getAttribute('data-status') === _activeStatusFilter;
        var matchText = !q || row.textContent.toLowerCase().indexOf(q) !== -1;
        row.style.display = (matchStatus && matchText) ? '' : 'none';
    });
}

var _dashSortCol = -1;
var _dashSortAsc = true;

function sortDashTable(colIdx) {
    if (_dashSortCol === colIdx) {
        _dashSortAsc = !_dashSortAsc;
    } else {
        _dashSortCol = colIdx;
        _dashSortAsc = true;
    }
    var tbody = document.querySelector('#dashTable tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('.dash-row'));
    rows.sort(function(a, b) {
        var aVal = a.children[colIdx].textContent.trim();
        var bVal = b.children[colIdx].textContent.trim();
        var aNum = parseFloat(aVal);
        var bNum = parseFloat(bVal);
        if (!isNaN(aNum) && !isNaN(bNum)) {
            return _dashSortAsc ? aNum - bNum : bNum - aNum;
        }
        return _dashSortAsc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
    });
    rows.forEach(function(r) { tbody.appendChild(r); });
}

/* Dashboard interactions for the v2 app. */

var _dashPrefix = window.V2_URL_PREFIX || "";
var _activeStatusFilter = "";
var _dashSortCol = -1;
var _dashSortAsc = true;

function _dashApi(path) {
    return _dashPrefix + path;
}

function dismissNotification(id, btn) {
    var item = btn.closest(".dash-alert-item");
    fetch(_dashApi("/api/notifications/dismiss"), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id: id})
    }).then(function() {
        if (!item) return;
        item.style.transition = "opacity 0.3s, max-height 0.3s";
        item.style.opacity = "0";
        item.style.maxHeight = "0";
        item.style.overflow = "hidden";
        item.style.padding = "0";
        item.style.margin = "0";
        setTimeout(function() {
            item.remove();
            updateAlertCount();
        }, 300);
    }).catch(function() { });
}

function updateAlertCount() {
    var items = document.querySelectorAll(".dash-alert-item");
    var badge = document.getElementById("alertCountBadge");
    if (badge) badge.textContent = items.length;
    if (!items.length) {
        var panel = document.getElementById("dashAlerts");
        if (panel) panel.style.display = "none";
    }
}

function toggleAlerts() {
    var body = document.getElementById("alertsBody");
    var toggle = document.getElementById("alertsToggle");
    if (!body) return;
    body.classList.toggle("collapsed");
    if (toggle) toggle.classList.toggle("collapsed");
}

function clearAllNotifications() {
    fetch(_dashApi("/api/notifications/dismiss"), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({all: true})
    }).then(function() {
        var panel = document.getElementById("dashAlerts");
        if (panel) panel.style.display = "none";
    }).catch(function() { });
}

function triggerDashRefresh() {
    var btn = document.getElementById("refreshBtn");
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px;"></span> Refreshing&hellip;';
    }
    showRefreshProgress(true);

    fetch(_dashApi("/api/dashboard/refresh"), {method: "POST"})
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var before = data.before || "";
            var reqEl = document.getElementById("refreshRequested");
            if (reqEl && data.requested_at) {
                reqEl.textContent = "Last requested: " + data.requested_at.substring(0, 16).replace("T", " ");
            }
            pollRefreshStatus(before, 0);
        })
        .catch(function() {
            resetRefreshBtn();
        });
}

function showRefreshProgress(show) {
    var panel = document.getElementById("refreshProgress");
    if (panel) panel.style.display = show ? "block" : "none";
}

function resetRefreshBtn() {
    var btn = document.getElementById("refreshBtn");
    if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i data-feather="refresh-cw" style="width:14px;height:14px;"></i> Refresh';
        if (typeof feather !== "undefined") feather.replace();
    }
    showRefreshProgress(false);
}

function pollRefreshStatus(before, attempts) {
    if (attempts > 120) {
        window.location.reload();
        return;
    }
    setTimeout(function() {
        fetch(_dashApi("/api/dashboard/refresh-status") + "?before=" + encodeURIComponent(before || ""))
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var label = document.getElementById("refreshProgressLabel");
                if (data.step && label) {
                    label.textContent = data.step;
                }
                if (data.done) {
                    if (label) label.textContent = data.step || "Refresh complete. Reloading...";
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

function filterByCard(card, status) {
    _activeStatusFilter = status;
    document.querySelectorAll(".dash-card-filter").forEach(function(c) {
        c.classList.remove("dash-card-filter-active");
    });
    card.classList.add("dash-card-filter-active");
    applyDashFilters();
}

function filterDashTable() {
    applyDashFilters();
}

function applyDashFilters() {
    var input = document.getElementById("dashSearch");
    var q = ((input && input.value) || "").toLowerCase();
    var rows = document.querySelectorAll("#dashTable tbody .dash-row");
    rows.forEach(function(row) {
        var matchStatus = !_activeStatusFilter || row.getAttribute("data-status") === _activeStatusFilter;
        var matchText = !q || row.textContent.toLowerCase().indexOf(q) !== -1;
        row.style.display = (matchStatus && matchText) ? "" : "none";
    });
}

function _sortValue(row, colIdx) {
    var text = row.children[colIdx].textContent.trim();
    var normalized = text.replace(/[$,]/g, "");
    if (normalized === "N/A" || normalized === "-") return "";
    var num = parseFloat(normalized);
    return !isNaN(num) && /^-?\d+(\.\d+)?$/.test(normalized) ? num : text.toLowerCase();
}

function sortDashTable(colIdx) {
    if (_dashSortCol === colIdx) {
        _dashSortAsc = !_dashSortAsc;
    } else {
        _dashSortCol = colIdx;
        _dashSortAsc = true;
    }
    var tbody = document.querySelector("#dashTable tbody");
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll(".dash-row"));
    rows.sort(function(a, b) {
        var aVal = _sortValue(a, colIdx);
        var bVal = _sortValue(b, colIdx);
        if (typeof aVal === "number" && typeof bVal === "number") {
            return _dashSortAsc ? aVal - bVal : bVal - aVal;
        }
        return _dashSortAsc
            ? String(aVal).localeCompare(String(bVal))
            : String(bVal).localeCompare(String(aVal));
    });
    rows.forEach(function(r) { tbody.appendChild(r); });
}

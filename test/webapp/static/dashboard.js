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

function dashEscape(value) {
    return String(value == null ? "" : value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function dashDisplay(value, fallback) {
    if (value === null || value === undefined || value === "") return fallback;
    return value;
}

function updateSummaryCards(summary) {
    var map = {
        "": "total_customers",
        "new": "new",
        "active": "active",
        "overdue": "overdue",
        "inactive": "inactive"
    };
    Object.keys(map).forEach(function(filter) {
        var card = document.querySelector('.dash-card-filter[data-filter="' + filter + '"] .dash-card-value');
        if (card) card.textContent = summary && summary[map[filter]] != null ? summary[map[filter]] : 0;
    });
}

function renderDashboardRows(customers) {
    var wrapper = document.getElementById("dashTableWrapper");
    if (!wrapper) return;
    if (!customers || !customers.length) {
        wrapper.innerHTML = [
            '<div class="empty-state">',
            '<i data-feather="bar-chart-2" width="48" height="48"></i>',
            '<h3>No dashboard data yet</h3>',
            '<p>Data will appear after the first refresh from the reporting API. This may take a few minutes.</p>',
            '</div>'
        ].join("");
        if (typeof feather !== "undefined") feather.replace();
        return;
    }

    var rows = customers.map(function(c) {
        var status = c.status || "new";
        return [
            '<tr class="dash-row clickable-row" data-status="', dashEscape(status), '" data-url="', dashEscape(c.url || "#"), '" onclick="window.location=this.dataset.url">',
            '<td>', dashEscape(c.customer_name || c.customer_account || ""), '</td>',
            '<td class="cell-nowrap">', dashEscape(c.customer_account || ""), '</td>',
            '<td class="cell-nowrap">', dashEscape(c.last_order_date || "N/A"), '</td>',
            '<td class="num">', dashEscape(dashDisplay(c.days_since_last, "-")), '</td>',
            '<td class="num">', dashEscape(dashDisplay(c.avg_gap_days, "-")), '</td>',
            '<td class="num">', dashEscape(dashDisplay(c.overdue_threshold, "-")), '</td>',
            '<td><span class="status-badge status-dash-', dashEscape(status), '">', dashEscape(status.charAt(0).toUpperCase() + status.slice(1)), '</span></td>',
            '</tr>'
        ].join("");
    }).join("");

    wrapper.innerHTML = [
        '<table class="data-table dash-activity-table sticky-col-first" id="dashTable">',
        '<thead><tr>',
        '<th onclick="sortDashTable(0)">Name <span class="sort-arrow">&#9650;</span></th>',
        '<th onclick="sortDashTable(1)">Account <span class="sort-arrow">&#9650;</span></th>',
        '<th onclick="sortDashTable(2)">Last Order <span class="sort-arrow">&#9650;</span></th>',
        '<th onclick="sortDashTable(3)">Days Since <span class="sort-arrow">&#9650;</span></th>',
        '<th onclick="sortDashTable(4)">Avg Freq <button class="help-icon" data-help="dashboard-avg-freq" style="width:16px;height:16px;font-size:10px;">?</button> <span class="sort-arrow">&#9650;</span></th>',
        '<th onclick="sortDashTable(5)">Threshold <button class="help-icon" data-help="dashboard-threshold" style="width:16px;height:16px;font-size:10px;">?</button> <span class="sort-arrow">&#9650;</span></th>',
        '<th onclick="sortDashTable(6)">Status <span class="sort-arrow">&#9650;</span></th>',
        '</tr></thead>',
        '<tbody>', rows, '</tbody>',
        '</table>'
    ].join("");
    applyDashFilters();
}

function updateRefreshMeta(refresh) {
    if (!refresh) return;
    var completed = document.getElementById("refreshCompleted");
    var requested = document.getElementById("refreshRequested");
    var cache = document.getElementById("refreshCache");
    var windowLabel = document.getElementById("refreshWindow");
    var orderStats = document.getElementById("refreshOrderMirrorStats");
    var backfillStats = document.getElementById("refreshBackfillStats");
    if (completed) {
        completed.textContent = refresh.last_completed
            ? "Last completed: " + refresh.last_completed.substring(0, 16).replace("T", " ")
            : "No data yet";
    }
    if (requested && refresh.last_requested) {
        requested.textContent = "Last requested: " + refresh.last_requested.substring(0, 16).replace("T", " ");
    }
    if (cache) {
        cache.textContent = "Shared mirror: "
            + (refresh.cache_customers || 0) + " customers, "
            + (refresh.cache_order_lines || 0) + " order lines, "
            + (refresh.dated_order_lines || 0) + " dated, "
            + (refresh.order_customers || 0) + " customers with dated lines, "
            + (refresh.customers_with_last_order || 0) + " with last order";
    }
    if (windowLabel) {
        windowLabel.textContent = "Dashboard metrics use the rolling "
            + (refresh.salesline_window_days || 60)
            + "-day salesline mirror.";
    }
    if (orderStats) {
        orderStats.textContent = refresh.order_mirror_stats || "";
        orderStats.style.display = refresh.order_mirror_stats ? "" : "none";
    }
    if (backfillStats) {
        backfillStats.textContent = refresh.backfill_stats || "";
        backfillStats.style.display = refresh.backfill_stats ? "" : "none";
    }
}

function refreshDashboardData() {
    var label = document.getElementById("refreshProgressLabel");
    if (label) label.textContent = "Loading refreshed dashboard data...";
    return fetch(_dashApi("/api/dashboard/data"))
        .then(function(r) { return r.json(); })
        .then(function(data) {
            updateSummaryCards(data.summary || {});
            renderDashboardRows(data.customers || []);
            updateRefreshMeta(data.refresh || {});
            if (label) label.textContent = "Dashboard data updated.";
        });
}

function pollRefreshStatus(before, attempts) {
    if (attempts > 120) {
        var label = document.getElementById("refreshProgressLabel");
        if (label) label.textContent = "Refresh is still running. The dashboard will keep using the current mirror data.";
        resetRefreshBtn();
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
                    if (label) label.textContent = data.step || "Refresh complete.";
                    refreshDashboardData().finally(function() {
                        resetRefreshBtn();
                    });
                } else {
                    pollRefreshStatus(before, attempts + 1);
                }
            })
            .catch(function() {
                var label = document.getElementById("refreshProgressLabel");
                if (label) label.textContent = "Could not check refresh status. Try again in a moment.";
                resetRefreshBtn();
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

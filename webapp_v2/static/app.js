/* ================================================================
   Sales Reports Mobile Web App -- Client JS
   ================================================================ */

document.addEventListener('DOMContentLoaded', function () {
    initPeriodButtons();
    initStatusButtons();
    initFormSubmit();
    initTabs();
    loadCustomers();
    initCustomerSearch();
    initSalesmanDropdownRefresh();
    startNotificationPolling();
});


/* -- Period selection ---------------------------------------------------- */

function initPeriodButtons() {
    const btns = document.querySelectorAll('.period-btn');
    const input = document.getElementById('periodInput');
    const customRange = document.getElementById('customDateRange');
    if (!btns.length) return;

    btns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            btns.forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');
            input.value = btn.dataset.period;

            if (btn.dataset.period === 'custom') {
                customRange.style.display = 'block';
            } else {
                customRange.style.display = 'none';
            }
        });
    });
}


/* -- Status selection ---------------------------------------------------- */

function initStatusButtons() {
    var btns = document.querySelectorAll('.status-btn');
    var input = document.getElementById('statusInput');
    if (!btns.length) return;

    btns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            btns.forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');
            input.value = btn.dataset.status;
        });
    });
}


/* -- Tab switching ------------------------------------------------------- */

function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.remove('active'); });
            document.querySelectorAll('.tab-content').forEach(function (c) { c.classList.remove('active'); });
            btn.classList.add('active');
            var target = document.getElementById(btn.dataset.tab + 'Tab');
            if (target) target.classList.add('active');
        });
    });
}


/* -- Customer multi-select picker ---------------------------------------- */

var _allCustomers = [];
var _selectedCustomers = {};

function loadCustomers() {
    if (typeof HAS_CUSTOMER_FILTER === 'undefined' || !HAS_CUSTOMER_FILTER) return;

    var listEl = document.getElementById('customerList');
    if (!listEl) return;

    listEl.innerHTML = '<div class="customer-picker-loading">Loading customers...</div>';
    _selectedCustomers = {};
    _renderSelectedChips();

    var url = '/api/customers';
    if (typeof HAS_SALESMAN_FILTER !== 'undefined' && HAS_SALESMAN_FILTER) {
        var smSelect = document.getElementById('salesmanSelect');
        if (smSelect && smSelect.value) {
            url += '?salesman=' + encodeURIComponent(smSelect.value);
        }
    }

    fetch(url)
        .then(function (r) { return r.json(); })
        .then(function (customers) {
            _allCustomers = customers;
            if (typeof PRESET_PARAMS !== 'undefined' && PRESET_PARAMS.customers && PRESET_PARAMS.customers.length) {
                PRESET_PARAMS.customers.forEach(function(acct) {
                    var match = customers.find(function(c) { return c.account === acct; });
                    if (match) _selectedCustomers[acct] = match.name;
                });
                _renderSelectedChips();
            }
            _renderCustomerList('');
        })
        .catch(function () {
            listEl.innerHTML = '<div class="customer-picker-loading">Failed to load customers</div>';
        });
}

function _renderCustomerList(filter) {
    var listEl = document.getElementById('customerList');
    if (!listEl) return;

    var filterLower = (filter || '').toLowerCase();
    var filtered = _allCustomers.filter(function (c) {
        if (!filterLower) return true;
        return c.account.toLowerCase().indexOf(filterLower) !== -1 ||
               c.name.toLowerCase().indexOf(filterLower) !== -1;
    });

    if (!filtered.length) {
        listEl.innerHTML = '<div class="customer-picker-empty">' +
            (filterLower ? 'No customers match "' + escapeHtml(filter) + '"' : 'No customers found') + '</div>';
        return;
    }

    var html = '';
    filtered.forEach(function (c) {
        var isSelected = !!_selectedCustomers[c.account];
        html += '<div class="customer-item' + (isSelected ? ' selected' : '') + '" data-account="' + escapeHtml(c.account) + '" data-name="' + escapeHtml(c.name) + '">' +
            '<div class="cust-check">&#10003;</div>' +
            '<div class="cust-label"><span class="cust-account">' + escapeHtml(c.account) + '</span><span class="cust-name">' + escapeHtml(c.name) + '</span></div>' +
            '</div>';
    });
    listEl.innerHTML = html;

    listEl.querySelectorAll('.customer-item').forEach(function (item) {
        item.addEventListener('click', function () {
            var acct = item.dataset.account;
            var name = item.dataset.name;
            if (_selectedCustomers[acct]) {
                delete _selectedCustomers[acct];
                item.classList.remove('selected');
            } else {
                _selectedCustomers[acct] = name;
                item.classList.add('selected');
            }
            _renderSelectedChips();
        });
    });
}

function _renderSelectedChips() {
    var chipsEl = document.getElementById('selectedCustomers');
    var countEl = document.getElementById('customerCount');
    if (!chipsEl) return;

    var keys = Object.keys(_selectedCustomers);
    if (!keys.length) {
        chipsEl.innerHTML = '';
        if (countEl) countEl.textContent = '';
        return;
    }

    if (countEl) countEl.textContent = keys.length + ' selected';

    var html = '';
    keys.forEach(function (acct) {
        html += '<span class="chip" data-account="' + escapeHtml(acct) + '">' +
            escapeHtml(acct) + ' \u2014 ' + escapeHtml(_selectedCustomers[acct]) +
            '<span class="chip-remove">&times;</span></span>';
    });
    chipsEl.innerHTML = html;

    chipsEl.querySelectorAll('.chip').forEach(function (chip) {
        chip.addEventListener('click', function () {
            var acct = chip.dataset.account;
            delete _selectedCustomers[acct];
            _renderSelectedChips();
            var item = document.querySelector('.customer-item[data-account="' + acct + '"]');
            if (item) item.classList.remove('selected');
        });
    });
}

function initCustomerSearch() {
    var searchInput = document.getElementById('customerSearch');
    if (!searchInput) return;
    searchInput.addEventListener('input', function () {
        _renderCustomerList(searchInput.value);
    });
}

function getSelectedCustomerAccounts() {
    return Object.keys(_selectedCustomers);
}

/* -- Refresh customers when salesman changes (admin) --------------------- */

function initSalesmanDropdownRefresh() {
    var smSelect = document.getElementById('salesmanSelect');
    if (!smSelect) return;
    smSelect.addEventListener('change', function () {
        loadCustomers();
    });
}


/* -- Form submission ----------------------------------------------------- */

function initFormSubmit() {
    var form = document.getElementById('reportForm');
    if (!form) return;

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        runReport();
    });
}

function runReport() {
    var params = {};

    var period = document.getElementById('periodInput');
    if (period) params.period = period.value;

    var fromDate = document.getElementById('fromDate');
    var toDate = document.getElementById('toDate');
    if (fromDate && fromDate.value) params.from_date = fromDate.value;
    if (toDate && toDate.value) params.to_date = toDate.value;

    var yearInput = document.getElementById('yearInput');
    if (yearInput) params.year = parseInt(yearInput.value);

    var status = document.getElementById('statusInput');
    if (status && status.value) params.status = status.value;

    var smSelect = document.getElementById('salesmanSelect');
    if (smSelect && smSelect.value) {
        var selectedOpt = smSelect.options[smSelect.selectedIndex];
        params.salesman = selectedOpt.getAttribute('data-display') || smSelect.value;
    }

    var selectedCusts = getSelectedCustomerAccounts();
    if (selectedCusts.length) params.customers = selectedCusts;

    var loading = document.getElementById('loadingOverlay');
    var results = document.getElementById('resultsSection');
    var runBtn = document.getElementById('runBtn');

    loading.style.display = 'flex';
    results.style.display = 'none';
    runBtn.disabled = true;
    updateProgress(0, 'Starting...', '');

    fetch('/report/' + REPORT_KEY + '/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params)
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (!data.run_id) {
            loading.style.display = 'none';
            runBtn.disabled = false;
            showError(data.error || 'Failed to start report.');
            return;
        }
        listenForProgress(data.run_id);
    })
    .catch(function (err) {
        loading.style.display = 'none';
        runBtn.disabled = false;
        showError('Network error: ' + err.message);
    });
}

function listenForProgress(runId) {
    var loading = document.getElementById('loadingOverlay');
    var runBtn = document.getElementById('runBtn');
    var evtSource = new EventSource('/report/progress/' + runId);

    evtSource.onmessage = function (event) {
        var msg = JSON.parse(event.data);
        updateProgress(msg.pct || 0, msg.msg || '', msg.step || '');

        if (msg.step === 'done' || msg.step === 'error') {
            evtSource.close();
            loading.style.display = 'none';
            runBtn.disabled = false;

            if (msg.result) {
                if (msg.result.success) {
                    displayResults(msg.result);
                } else {
                    showError(msg.result.error || 'Report failed.');
                }
            }
        }
    };

    evtSource.onerror = function () {
        evtSource.close();
        loading.style.display = 'none';
        runBtn.disabled = false;
        showError('Lost connection to server. The report may still be running \u2014 check History.');
    };
}

function updateProgress(pct, msg, step) {
    var bar = document.getElementById('progressBar');
    var msgEl = document.getElementById('progressMsg');
    if (bar) bar.style.width = pct + '%';
    if (msgEl) msgEl.textContent = msg;

    var steps = document.querySelectorAll('.progress-step');
    var stepOrder = ['connecting', 'fetching', 'processing', 'writing', 'done'];
    var currentIdx = stepOrder.indexOf(step);

    steps.forEach(function (el) {
        var elStep = el.getAttribute('data-step');
        var elIdx = stepOrder.indexOf(elStep);
        el.classList.remove('active', 'done');
        if (elIdx < currentIdx) {
            el.classList.add('done');
        } else if (elIdx === currentIdx) {
            el.classList.add('active');
        }
    });
}


/* -- Display results ----------------------------------------------------- */

function displayResults(data) {
    var results = document.getElementById('resultsSection');
    results.style.display = 'block';

    var downloadBtn = document.getElementById('downloadBtn');
    if (data.filename) {
        downloadBtn.href = '/report/' + REPORT_KEY + '/download';
        downloadBtn.style.display = 'inline-flex';
    } else {
        downloadBtn.style.display = 'none';
    }

    renderSummary(data.summary || {});
    renderSheets(data.sheets || {});

    results.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderSummary(summary) {
    var container = document.getElementById('summaryCards');
    container.innerHTML = '';

    var entries = Object.entries(summary);
    if (!entries.length) {
        container.innerHTML = '<p style="color: var(--text-muted); padding: 16px;">No summary data available.</p>';
        return;
    }

    entries.forEach(function (pair) {
        var key = pair[0];
        var val = pair[1];
        if (key === 'message') {
            container.innerHTML = '<p style="color: var(--text-muted); padding: 16px;">' + escapeHtml(val) + '</p>';
            return;
        }

        var card = document.createElement('div');
        card.className = 'summary-card';

        var label = formatLabel(key);
        var formatted = typeof val === 'number' ? formatNumber(val, key) : escapeHtml(val);

        card.innerHTML =
            '<div class="card-label">' + escapeHtml(label) + '</div>' +
            '<div class="card-value">' + formatted + '</div>';
        container.appendChild(card);
    });
}

function renderSheets(sheets) {
    var sheetNames = Object.keys(sheets);
    var sheetTabsEl = document.getElementById('sheetTabs');
    var detailTableEl = document.getElementById('detailTable');
    var summaryTableEl = document.getElementById('summaryTable');

    sheetTabsEl.innerHTML = '';
    detailTableEl.innerHTML = '';

    if (!sheetNames.length) {
        detailTableEl.innerHTML = '<p style="padding: 16px; color: var(--text-muted);">No data sheets available.</p>';
        return;
    }

    if (sheetNames.length > 0) {
        var firstRows = sheets[sheetNames[0]];
        summaryTableEl.innerHTML = buildTable(firstRows, 25);
    }

    sheetNames.forEach(function (name, idx) {
        var btn = document.createElement('button');
        btn.className = 'sheet-tab-btn' + (idx === 0 ? ' active' : '');
        btn.textContent = name;
        btn.addEventListener('click', function () {
            document.querySelectorAll('.sheet-tab-btn').forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');
            detailTableEl.innerHTML = buildTable(sheets[name], 500);
        });
        sheetTabsEl.appendChild(btn);
    });

    detailTableEl.innerHTML = buildTable(sheets[sheetNames[0]], 500);
}

function buildTable(rows, maxRows) {
    if (!rows || !rows.length) {
        return '<p style="padding: 16px; color: var(--text-muted);">No data.</p>';
    }

    var displayRows = rows.slice(0, maxRows || 500);
    var cols = Object.keys(displayRows[0]);

    var html = '<table class="data-table"><thead><tr>';
    cols.forEach(function (col, idx) {
        html += '<th data-col="' + idx + '">' + escapeHtml(col) + '<span class="sort-arrow">&#9650;</span></th>';
    });
    html += '</tr></thead><tbody>';

    displayRows.forEach(function (row) {
        html += '<tr>';
        cols.forEach(function (col) {
            var val = row[col];
            var isNum = typeof val === 'number';
            var display = isNum ? formatNumber(val, col) : (val === '' || val === null ? '' : escapeHtml(val));
            html += '<td class="' + (isNum ? 'num' : '') + '">' + display + '</td>';
        });
        html += '</tr>';
    });

    html += '</tbody></table>';

    if (rows.length > maxRows) {
        html += '<p style="padding: 12px; color: var(--text-muted); font-size: 13px; text-align: center;">' +
                'Showing ' + maxRows + ' of ' + rows.length + ' rows. Download Excel for full data.</p>';
    }

    return html;
}


/* -- Notification polling ------------------------------------------------ */

var _pollInterval = null;

function startNotificationPolling() {
    var navReports = document.getElementById('badgeReports');
    var navDashboard = document.getElementById('badgeDashboard');
    if (!navReports && !navDashboard) return;

    if (_pollInterval) clearInterval(_pollInterval);
    pollNotifications();
    _pollInterval = setInterval(pollNotifications, 30000);

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            if (_pollInterval) { clearInterval(_pollInterval); _pollInterval = null; }
        } else {
            if (!_pollInterval) {
                pollNotifications();
                _pollInterval = setInterval(pollNotifications, 30000);
            }
        }
    });
}

function pollNotifications() {
    fetch('/api/notifications')
        .then(function (r) { return r.json(); })
        .then(function (data) {
            updateBadge('badgeReports', data.report_ready_count || 0);
            updateBadge('badgeDashboard', data.overdue_count || 0);
        })
        .catch(function () {});
}

function updateBadge(elementId, count) {
    var badge = document.getElementById(elementId);
    if (!badge) return;
    if (count > 0) {
        badge.textContent = count > 99 ? '99+' : count;
        badge.style.display = 'flex';
    } else {
        badge.style.display = 'none';
    }
}


/* -- Helpers ------------------------------------------------------------- */

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatNumber(val, key) {
    if (key && key.toLowerCase().indexOf('unique') !== -1) {
        return val.toLocaleString();
    }
    if (key && key.toLowerCase() === 'total_rows') {
        return val.toLocaleString();
    }
    if (Math.abs(val) >= 1 && (
        key && (key.toLowerCase().indexOf('total') !== -1 ||
                key.toLowerCase().indexOf('amount') !== -1 ||
                key.toLowerCase().indexOf('subtotal') !== -1 ||
                key.toLowerCase().indexOf('net') !== -1 ||
                key.toLowerCase().indexOf('revenue') !== -1 ||
                key.toLowerCase().indexOf('price') !== -1 ||
                key.toLowerCase().indexOf('sales') !== -1)
    )) {
        return '$' + val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    if (Number.isInteger(val)) return val.toLocaleString();
    return val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatLabel(key) {
    return key
        .replace(/_/g, ' ')
        .replace(/([A-Z])/g, ' $1')
        .replace(/\bunique\b/i, '')
        .trim()
        .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
}

function showError(message) {
    var results = document.getElementById('resultsSection');
    results.style.display = 'block';
    results.innerHTML =
        '<div class="error-box">' +
        '<h3>Report Error</h3>' +
        '<p>' + escapeHtml(message) + '</p>' +
        '<button class="btn btn-outline" style="margin-top: 16px;" onclick="document.getElementById(\'resultsSection\').style.display=\'none\'">Dismiss</button>' +
        '</div>';
    results.scrollIntoView({ behavior: 'smooth' });
}

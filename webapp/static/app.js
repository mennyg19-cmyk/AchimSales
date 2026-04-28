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
        if (countEl) { countEl.textContent = ''; countEl.style.display = 'none'; }
        return;
    }

    if (countEl) { countEl.textContent = keys.length + ' selected'; countEl.style.display = ''; }

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

var _currentRunId = null;
var _progressTimer = null;
var _bgReportPending = false;
var _reportSubmitting = false;

function initFormSubmit() {
    var form = document.getElementById('reportForm');
    if (!form) return;

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        runReport();
    });
}

function runReport() {
    if (_reportSubmitting) return;
    _reportSubmitting = true;

    var params = {};

    var period = document.getElementById('periodInput');
    if (period) params.period = period.value;

    /* Only forward the custom-range dates when the user actually picked
       Custom Range. Otherwise we'd ship stale values left over from a
       previous custom selection -- the date fields are hidden but their
       values stick around, and the backend will happily prefer them
       over the period preset (a real bug Dad hit). */
    if (period && period.value === 'custom') {
        var fromDate = document.getElementById('fromDate');
        var toDate = document.getElementById('toDate');
        if (fromDate && fromDate.value) params.from_date = fromDate.value;
        if (toDate && toDate.value) params.to_date = toDate.value;
    }

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

    if (typeof REPORT_FORM_CONFIG !== 'undefined' && REPORT_FORM_CONFIG.presetParams && REPORT_FORM_CONFIG.presetParams.preset_name) {
        params.preset_name = REPORT_FORM_CONFIG.presetParams.preset_name;
    }

    var loading = document.getElementById('loadingOverlay');
    var results = document.getElementById('resultsSection');
    var runBtn = document.getElementById('runBtn');

    loading.style.display = 'flex';
    results.style.display = 'none';
    runBtn.disabled = true;
    _currentRunId = null;
    var cancelBtn = document.getElementById('cancelBtn');
    if (cancelBtn) { cancelBtn.disabled = false; cancelBtn.style.display = ''; }
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
            _reportSubmitting = false;
            showError(data.error || 'Failed to start report.');
            return;
        }
        _currentRunId = data.run_id;
        listenForProgress(data.run_id);
    })
    .catch(function (err) {
        loading.style.display = 'none';
        runBtn.disabled = false;
        _reportSubmitting = false;
        showError('Network error: ' + err.message);
    });
}

function listenForProgress(runId) {
    var loading = document.getElementById('loadingOverlay');
    var runBtn = document.getElementById('runBtn');
    var cancelBtn = document.getElementById('cancelBtn');

    if (_progressTimer) clearInterval(_progressTimer);

    _progressTimer = setInterval(function () {
        fetch('/report/progress/' + runId)
            .then(function (r) { return r.json(); })
            .then(function (msg) {
                updateProgress(msg.pct || 0, msg.msg || '', msg.step || '');

                if (msg.step === 'done' || msg.step === 'error') {
                    clearInterval(_progressTimer);
                    _progressTimer = null;
                    loading.style.display = 'none';
                    runBtn.disabled = false;
                    _reportSubmitting = false;
                    _currentRunId = null;
                    if (cancelBtn) cancelBtn.style.display = 'none';

                    if (msg.result) {
                        if (msg.result.success) {
                            displayResults(msg.result);
                        } else {
                            showError(msg.result.error || 'Report failed.');
                        }
                    }
                }
            })
            .catch(function () {});
    }, 1000);
}

function sendToBackground() {
    if (_progressTimer) {
        clearInterval(_progressTimer);
        _progressTimer = null;
    }
    var loading = document.getElementById('loadingOverlay');
    var runBtn = document.getElementById('runBtn');
    loading.style.display = 'none';
    runBtn.disabled = false;
    _reportSubmitting = false;
    _currentRunId = null;
    _bgReportPending = true;

    _showInAppToast('Report running in background. You\u2019ll be notified when it\u2019s ready.');

    if (_pollInterval) clearInterval(_pollInterval);
    _pollInterval = setInterval(pollNotifications, 5000);
    pollNotifications();
}

function _showInAppToast(message) {
    var existing = document.getElementById('appToast');
    if (existing) existing.remove();

    var toast = document.createElement('div');
    toast.id = 'appToast';
    toast.style.cssText = 'position:fixed; bottom:80px; left:50%; transform:translateX(-50%); ' +
        'background:var(--bg-card); color:var(--text); border:1px solid var(--border); ' +
        'padding:12px 20px; border-radius:10px; box-shadow:0 4px 20px rgba(0,0,0,0.15); ' +
        'z-index:2000; font-size:14px; max-width:90%; text-align:center; ' +
        'animation: toastIn 0.3s ease;';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(function() {
        toast.style.transition = 'opacity 0.3s';
        toast.style.opacity = '0';
        setTimeout(function() { toast.remove(); }, 300);
    }, 4000);
}

function cancelReport() {
    if (!_currentRunId) return;
    var cancelBtn = document.getElementById('cancelBtn');
    if (cancelBtn) { cancelBtn.disabled = true; cancelBtn.textContent = 'Cancelling...'; }

    fetch('/report/cancel/' + _currentRunId, { method: 'POST' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.success) {
                if (cancelBtn) { cancelBtn.disabled = false; cancelBtn.textContent = 'Cancel'; }
            }
        })
        .catch(function () {
            if (cancelBtn) { cancelBtn.disabled = false; cancelBtn.textContent = 'Cancel'; }
        });
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
        downloadBtn.textContent = '';
        var ico = document.createElement('i');
        ico.setAttribute('data-feather', 'download');
        downloadBtn.appendChild(ico);
        downloadBtn.appendChild(document.createTextNode(
            data.extra_files && data.extra_files.length
                ? ' ' + _friendlyLabel(data.filename)
                : ' Download Excel'
        ));
    } else {
        downloadBtn.style.display = 'none';
    }

    var oldExtra = document.getElementById('extraDownloadBtns');
    if (oldExtra) oldExtra.remove();

    if (data.extra_files && data.extra_files.length) {
        var wrap = document.createElement('span');
        wrap.id = 'extraDownloadBtns';
        wrap.style.display = 'inline-flex';
        wrap.style.gap = '8px';
        wrap.style.marginLeft = '8px';
        data.extra_files.forEach(function(ef) {
            var a = document.createElement('a');
            a.href = '/report/download-file?path=' + encodeURIComponent(ef.filepath);
            a.className = 'btn btn-primary';
            a.style.display = 'inline-flex';
            a.style.alignItems = 'center';
            a.style.gap = '6px';
            var ico2 = document.createElement('i');
            ico2.setAttribute('data-feather', 'download');
            a.appendChild(ico2);
            a.appendChild(document.createTextNode(' ' + _friendlyLabel(ef.filename)));
            wrap.appendChild(a);
        });
        downloadBtn.parentNode.insertBefore(wrap, downloadBtn.nextSibling);
    }

    if (typeof feather !== 'undefined') feather.replace();

    renderSummary(data.summary || {});
    renderSheets(data.sheets || {});

    results.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function _friendlyLabel(filename) {
    if (!filename) return 'Download';
    if (filename.indexOf('_Item_') !== -1) return 'By Item';
    if (filename.indexOf('_Customer_') !== -1) return 'By Customer';
    return filename.replace(/\.xlsx$/i, '').replace(/_/g, ' ');
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

var _lastSeenReportCount = 0;

function pollNotifications() {
    fetch('/api/notifications')
        .then(function (r) { return r.json(); })
        .then(function (data) {
            var reportCount = data.report_ready_count || 0;
            updateBadge('badgeReports', reportCount);
            updateBadge('badgeDashboard', data.overdue_count || 0);

            if (_bgReportPending && reportCount > _lastSeenReportCount) {
                _bgReportPending = false;
                if (_pollInterval) clearInterval(_pollInterval);
                _pollInterval = setInterval(pollNotifications, 30000);

                var reportItem = null;
                if (data.items) {
                    for (var i = 0; i < data.items.length; i++) {
                        if (data.items[i].type === 'report_ready') { reportItem = data.items[i]; break; }
                    }
                }

                _showReportReadyBanner(reportItem);
            }
            _lastSeenReportCount = reportCount;
        })
        .catch(function () {});
}

function _showReportReadyBanner(notif) {
    var existing = document.getElementById('reportReadyBanner');
    if (existing) existing.remove();

    var title = (notif && notif.title) ? notif.title : 'Report is ready';

    var banner = document.createElement('div');
    banner.id = 'reportReadyBanner';
    banner.style.cssText = 'position:fixed; bottom:80px; left:50%; transform:translateX(-50%); ' +
        'background:var(--primary); color:#fff; padding:14px 20px; border-radius:12px; ' +
        'box-shadow:0 4px 20px rgba(0,0,0,0.25); z-index:2000; font-size:14px; max-width:90%; ' +
        'text-align:center; cursor:pointer; display:flex; align-items:center; gap:10px;';
    banner.innerHTML = '<span style="flex:1;">' + escapeHtml(title) + ' \u2014 <strong>Tap to view</strong></span>' +
        '<span onclick="event.stopPropagation(); this.parentElement.remove(); dismissReportNotifications();" ' +
        'style="cursor:pointer; opacity:0.7; font-size:18px;">&times;</span>';
    banner.addEventListener('click', function () {
        banner.remove();
        dismissReportNotifications();
        window.location.href = '/history';
    });
    document.body.appendChild(banner);
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


/* -- Dismiss report notifications ---------------------------------------- */

function dismissReportNotifications() {
    fetch('/api/notifications/dismiss', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'report_ready' }),
    }).then(function () {
        updateBadge('badgeReports', 0);
        _lastSeenReportCount = 0;
    }).catch(function () {});
}


/* -- Helpers ------------------------------------------------------------- */

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatNumber(val, key) {
    var kl = (key || '').toLowerCase();
    if (kl.indexOf('unique') !== -1) {
        return val.toLocaleString();
    }
    if (kl === 'total_rows') {
        return val.toLocaleString();
    }
    var moneyKeywords = ['total', 'amount', 'subtotal', 'net', 'revenue', 'price', 'sales',
                         'invoice', 'balance', 'commission', 'freight', 'tariff', 'charges'];
    var isMoney = false;
    for (var i = 0; i < moneyKeywords.length; i++) {
        if (kl.indexOf(moneyKeywords[i]) !== -1) { isMoney = true; break; }
    }
    if (isMoney) {
        return '$' + val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    if (Number.isInteger(val)) return val.toLocaleString();
    return val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatLabel(key) {
    var label = key
        .replace(/^total_/i, '')
        .replace(/_/g, ' ')
        .replace(/([A-Z])/g, ' $1')
        .replace(/\bunique\b/i, '')
        .replace(/\s+/g, ' ')
        .trim()
        .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
    return label;
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

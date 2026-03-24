/* Schedules management page */

// ── Arg parsing helpers ─────────────────────────────────────────────────

function parseExtraArgs(raw) {
    var result = { period: '', from: '', to: '', customer: '', salesman: '', status: '', email: false };
    if (!raw) return result;

    var tokens = raw.match(/(?:[^\s"]+|"[^"]*")+/g) || [];
    var i = 0;
    while (i < tokens.length) {
        var t = tokens[i];
        if (t === '--period' && tokens[i + 1]) {
            result.period = tokens[++i];
        } else if (t === '--from' && tokens[i + 1]) {
            result.from = tokens[++i];
        } else if (t === '--to' && tokens[i + 1]) {
            result.to = tokens[++i];
        } else if (t === '--customer') {
            var vals = [];
            while (i + 1 < tokens.length && !tokens[i + 1].startsWith('--')) {
                vals.push(tokens[++i]);
            }
            result.customer = vals.join(' ');
        } else if (t === '--salesman') {
            var vals2 = [];
            while (i + 1 < tokens.length && !tokens[i + 1].startsWith('--')) {
                vals2.push(tokens[++i]);
            }
            result.salesman = vals2.join(' ');
        } else if (t === '--status' && tokens[i + 1]) {
            result.status = tokens[++i];
        } else if (t === '--email') {
            result.email = true;
        }
        i++;
    }

    if (result.from && result.to && !result.period) {
        result.period = 'custom';
    }
    return result;
}

function buildExtraArgs() {
    var parts = [];
    var report = document.getElementById('schedReport').value;
    var caps = PARAM_CAPS[report] || {};

    if (caps.period) {
        var period = document.getElementById('schedPeriod').value;
        if (period && period !== 'custom') {
            parts.push('--period ' + period);
        } else if (period === 'custom') {
            var df = document.getElementById('schedDateFrom').value;
            var dt = document.getElementById('schedDateTo').value;
            if (df) parts.push('--from ' + df);
            if (dt) parts.push('--to ' + dt);
        }
    }
    if (caps.customer) {
        var cust = document.getElementById('schedCustomer').value.trim();
        if (cust) parts.push('--customer ' + cust);
    }
    if (caps.salesman) {
        var sm = document.getElementById('schedSalesman').value.trim();
        if (sm) parts.push('--salesman ' + sm);
    }
    if (caps.status) {
        var st = document.getElementById('schedStatus').value;
        if (st) parts.push('--status ' + st);
    }
    if (caps.email) {
        if (document.getElementById('schedEmail').checked) {
            parts.push('--email');
        }
    }
    return parts.join(' ');
}

// ── Table cell rendering ────────────────────────────────────────────────

function renderParamCells() {
    var cells = document.querySelectorAll('.sched-param-cell');
    cells.forEach(function(td) {
        var report = td.getAttribute('data-report');
        var param = td.getAttribute('data-param');
        var caps = PARAM_CAPS[report] || {};
        var row = td.closest('tr');
        var schedId = parseInt(row.getAttribute('data-id'));
        var sched = SCHEDULES_DATA.find(function(s) { return s.id === schedId; });
        var parsed = sched ? parseExtraArgs(sched.extra_args) : {};

        if (!caps[param]) {
            td.innerHTML = '<span style="color:var(--text-muted);">—</span>';
            return;
        }

        if (param === 'period') {
            var val = parsed.period || '';
            if (val === 'custom') {
                td.textContent = (parsed.from || '?') + ' → ' + (parsed.to || '?');
            } else {
                td.textContent = val || '—';
            }
        } else if (param === 'customer') {
            td.textContent = parsed.customer || '—';
        } else if (param === 'salesman') {
            td.textContent = parsed.salesman || '—';
        } else if (param === 'email') {
            if (parsed.email) {
                td.innerHTML = '<i data-feather="check" style="width:14px;height:14px;color:var(--success, #16a34a);"></i>';
            } else {
                td.innerHTML = '<span style="color:var(--text-muted);">—</span>';
            }
        }
    });
    if (typeof feather !== 'undefined') feather.replace();
}

// ── Modal: report change → enable/disable fields ────────────────────────

function onReportChange() {
    var report = document.getElementById('schedReport').value;
    var caps = PARAM_CAPS[report] || {};

    var fields = [
        { param: 'period',   inputId: 'schedPeriod' },
        { param: 'customer', inputId: 'schedCustomer' },
        { param: 'salesman', inputId: 'schedSalesman' },
        { param: 'status',   inputId: 'schedStatus' },
        { param: 'email',    inputId: 'schedEmail' },
    ];

    fields.forEach(function(f) {
        var el = document.getElementById(f.inputId);
        var wrap = document.getElementById('param' + f.param.charAt(0).toUpperCase() + f.param.slice(1) + 'Wrap');
        if (caps[f.param]) {
            el.disabled = false;
            if (wrap) wrap.style.opacity = '1';
        } else {
            el.disabled = true;
            if (f.inputId === 'schedEmail') {
                el.checked = false;
            } else if (el.tagName === 'SELECT') {
                el.selectedIndex = 0;
            } else {
                el.value = '';
            }
            if (wrap) wrap.style.opacity = '0.4';
        }
    });
}

function onFrequencyChange() {
    var freq = document.getElementById('schedFrequency').value;
    document.getElementById('daysOfWeekWrap').style.display = freq === 'Week' ? '' : 'none';
    document.getElementById('monthDaysWrap').style.display = freq === 'Month' ? '' : 'none';
    document.getElementById('intervalWrap').style.display = freq === 'OneTime' ? 'none' : '';
}

function onLastDayToggle() {
    var checked = document.getElementById('domLastDay').checked;
    document.querySelectorAll('.dom-check').forEach(function(cb) {
        cb.checked = false;
        cb.disabled = checked;
        cb.closest('.dom-label').style.opacity = checked ? '0.35' : '1';
    });
}

function onPeriodChange() {
    var val = document.getElementById('schedPeriod').value;
    document.getElementById('customDateWrap').style.display = val === 'custom' ? '' : 'none';
}

// ── Modal open / close ──────────────────────────────────────────────────

function openCreateModal() {
    document.getElementById('editScheduleId').value = '';
    document.getElementById('modalTitle').textContent = 'Add Schedule';
    document.getElementById('schedName').value = '';
    document.getElementById('schedReport').value = '';
    document.getElementById('schedFrequency').value = 'Day';
    document.getElementById('schedInterval').value = '1';
    document.getElementById('schedStartTime').value = '';
    document.getElementById('schedTimeZone').value = 'America/New_York';
    document.getElementById('schedDescription').value = '';
    document.querySelectorAll('.dow-check').forEach(function(cb) { cb.checked = false; });
    document.querySelectorAll('.dom-check').forEach(function(cb) { cb.checked = false; cb.disabled = false; cb.closest('.dom-label').style.opacity = '1'; });
    document.getElementById('domLastDay').checked = false;

    document.getElementById('schedPeriod').value = '';
    document.getElementById('schedDateFrom').value = '';
    document.getElementById('schedDateTo').value = '';
    document.getElementById('schedCustomer').value = '';
    document.getElementById('schedSalesman').value = '';
    document.getElementById('schedStatus').value = '';
    document.getElementById('schedEmail').checked = false;

    onReportChange();
    onFrequencyChange();
    onPeriodChange();
    hideMsg();
    document.getElementById('scheduleModal').style.display = 'flex';
    if (typeof feather !== 'undefined') feather.replace();
}

function openEditModal(id) {
    var sched = SCHEDULES_DATA.find(function(s) { return s.id === id; });
    if (!sched) return;

    document.getElementById('editScheduleId').value = id;
    document.getElementById('modalTitle').textContent = 'Edit Schedule';
    document.getElementById('schedName').value = sched.name || '';
    document.getElementById('schedReport').value = sched.report_key || '';
    document.getElementById('schedFrequency').value = sched.frequency || 'Day';
    document.getElementById('schedInterval').value = sched.interval_val || 1;
    document.getElementById('schedTimeZone').value = sched.time_zone || 'America/New_York';
    document.getElementById('schedDescription').value = sched.description || '';

    var st = sched.start_time || '';
    if (st.length >= 16) {
        document.getElementById('schedStartTime').value = st.substring(0, 16);
    } else {
        document.getElementById('schedStartTime').value = '';
    }

    var dow = (sched.days_of_week || '').split(',').map(function(d) { return d.trim(); });
    document.querySelectorAll('.dow-check').forEach(function(cb) {
        cb.checked = dow.indexOf(cb.value) !== -1;
    });

    var md = (sched.month_days || '').split(',').map(function(d) { return d.trim(); });
    var isLastDay = md.indexOf('-1') !== -1;
    document.getElementById('domLastDay').checked = isLastDay;
    document.querySelectorAll('.dom-check').forEach(function(cb) {
        cb.disabled = isLastDay;
        cb.closest('.dom-label').style.opacity = isLastDay ? '0.35' : '1';
        cb.checked = !isLastDay && md.indexOf(cb.value) !== -1;
    });

    onReportChange();
    onFrequencyChange();

    var parsed = parseExtraArgs(sched.extra_args);
    document.getElementById('schedPeriod').value = parsed.period || '';
    document.getElementById('schedDateFrom').value = parsed.from || '';
    document.getElementById('schedDateTo').value = parsed.to || '';
    document.getElementById('schedCustomer').value = parsed.customer || '';
    document.getElementById('schedSalesman').value = parsed.salesman || '';
    document.getElementById('schedStatus').value = parsed.status || '';
    document.getElementById('schedEmail').checked = parsed.email;

    onPeriodChange();
    hideMsg();
    document.getElementById('scheduleModal').style.display = 'flex';
    if (typeof feather !== 'undefined') feather.replace();
}

function closeModal() {
    document.getElementById('scheduleModal').style.display = 'none';
}

// ── Messages ────────────────────────────────────────────────────────────

function showMsg(text, isError) {
    var el = document.getElementById('modalMsg');
    el.textContent = text;
    el.style.display = '';
    el.style.color = isError ? 'var(--error)' : 'var(--success, #16a34a)';
}

function hideMsg() {
    document.getElementById('modalMsg').style.display = 'none';
}

// ── Form data & save ────────────────────────────────────────────────────

function getFormData() {
    var dow = [];
    document.querySelectorAll('.dow-check:checked').forEach(function(cb) {
        dow.push(cb.value);
    });

    var monthDays = [];
    if (document.getElementById('domLastDay').checked) {
        monthDays.push(-1);
    } else {
        document.querySelectorAll('.dom-check:checked').forEach(function(cb) {
            monthDays.push(parseInt(cb.value));
        });
    }

    return {
        name: document.getElementById('schedName').value.trim(),
        report_key: document.getElementById('schedReport').value,
        frequency: document.getElementById('schedFrequency').value,
        interval: parseInt(document.getElementById('schedInterval').value) || 1,
        start_time: document.getElementById('schedStartTime').value,
        time_zone: document.getElementById('schedTimeZone').value,
        days_of_week: dow.join(','),
        month_days: monthDays.join(','),
        extra_args: buildExtraArgs(),
        description: document.getElementById('schedDescription').value.trim(),
    };
}

function saveSchedule() {
    var data = getFormData();
    if (!data.name || !data.report_key || !data.start_time) {
        showMsg('Name, report, and start time are required.', true);
        return;
    }
    if (data.frequency === 'Month' && !data.month_days) {
        showMsg('Pick at least one day of the month (or "Last day").', true);
        return;
    }

    var editId = document.getElementById('editScheduleId').value;
    var url = editId ? '/schedules/' + editId + '/update' : '/schedules/create';

    var btn = document.getElementById('modalSaveBtn');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    })
    .then(function(r) {
        if (r.redirected) { window.location.href = r.url; return; }
        var ct = r.headers.get('content-type') || '';
        if (!ct.includes('application/json')) throw new Error('Session expired. Please reload and log in.');
        return r.json();
    })
    .then(function(res) {
        if (!res) return;
        btn.disabled = false;
        btn.textContent = 'Save';
        if (res.success) {
            window.location.reload();
        } else {
            showMsg(res.error || 'Failed to save schedule.', true);
        }
    })
    .catch(function(err) {
        btn.disabled = false;
        btn.textContent = 'Save';
        showMsg(err.message, true);
    });
}

// ── Toggle / Delete / Sync ──────────────────────────────────────────────

function toggleSchedule(id, checkbox) {
    fetch('/schedules/' + id + '/toggle', { method: 'POST' })
    .then(function(r) {
        if (r.redirected) { window.location.href = r.url; return; }
        var ct = r.headers.get('content-type') || '';
        if (!ct.includes('application/json')) throw new Error('Session expired. Please reload and log in.');
        return r.json();
    })
    .then(function(res) {
        if (!res) return;
        if (!res.success) {
            checkbox.checked = !checkbox.checked;
            alert('Failed to toggle: ' + (res.error || 'Unknown error'));
        }
    })
    .catch(function(err) {
        checkbox.checked = !checkbox.checked;
        alert(err.message);
    });
}

function deleteSchedule(id) {
    var sched = SCHEDULES_DATA.find(function(s) { return s.id === id; });
    var name = sched ? sched.name : '#' + id;
    if (!confirm('Delete schedule "' + name + '"?\n\nThis will remove it from Azure Automation.')) {
        return;
    }

    fetch('/schedules/' + id + '/delete', { method: 'POST' })
    .then(function(r) {
        if (r.redirected) { window.location.href = r.url; return; }
        var ct = r.headers.get('content-type') || '';
        if (!ct.includes('application/json')) throw new Error('Session expired. Please reload and log in.');
        return r.json();
    })
    .then(function(res) {
        if (!res) return;
        if (res.success) {
            window.location.reload();
        } else {
            alert('Failed to delete: ' + (res.error || 'Unknown error'));
        }
    })
    .catch(function(err) {
        alert(err.message);
    });
}

function syncFromAzure() {
    var btn = document.getElementById('syncBtn');
    var status = document.getElementById('syncStatus');
    btn.disabled = true;
    status.textContent = 'Syncing...';

    fetch('/schedules/sync', { method: 'POST' })
    .then(function(r) {
        if (r.redirected) { window.location.href = r.url; return; }
        var ct = r.headers.get('content-type') || '';
        if (!ct.includes('application/json')) throw new Error('Session expired. Please reload and log in.');
        return r.json();
    })
    .then(function(res) {
        if (!res) return;
        btn.disabled = false;
        if (res.success) {
            status.textContent = 'Synced ' + res.count + ' schedule(s)';
            window.location.reload();
        } else {
            status.textContent = 'Sync failed: ' + (res.error || 'Unknown error');
            status.style.color = 'var(--error)';
        }
    })
    .catch(function(err) {
        btn.disabled = false;
        status.textContent = err.message;
        status.style.color = 'var(--error)';
    });
}

// ── Init ────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function() {
    renderParamCells();
    if (typeof feather !== 'undefined') feather.replace();
});

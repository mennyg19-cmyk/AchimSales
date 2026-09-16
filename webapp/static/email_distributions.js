/* Email Distributions management page */

var _recipients = [];
var _ccList = [];

// -- Status banner --------------------------------------------------------

function showBanner(msg, type) {
    var el = document.getElementById('statusBanner');
    el.textContent = msg;
    el.className = 'banner-' + type;  // info, success, error
}

function hideBanner() {
    var el = document.getElementById('statusBanner');
    el.className = '';
    el.style.display = 'none';
}

// -- Modal message --------------------------------------------------------

function _showMsg(msg, isError) {
    var el = document.getElementById('distModalMsg');
    el.textContent = msg;
    el.style.display = 'block';
    el.style.color = isError ? 'var(--error)' : 'var(--success, green)';
}

function _clearMsg() {
    var el = document.getElementById('distModalMsg');
    el.style.display = 'none';
}

// -- Chip rendering -------------------------------------------------------

function _renderChips(containerId, list, removeCallback) {
    var container = document.getElementById(containerId);
    container.innerHTML = '';
    list.forEach(function(email, idx) {
        var chip = document.createElement('span');
        chip.className = 'chip';
        chip.innerHTML = email + ' <span class="chip-remove" onclick="' + removeCallback + '(' + idx + ')">&times;</span>';
        container.appendChild(chip);
    });
}

function addRecipient() {
    var input = document.getElementById('distRecipientInput');
    var email = input.value.trim().toLowerCase();
    if (!email || _recipients.indexOf(email) !== -1) return;
    if (!email.includes('@')) return;
    _recipients.push(email);
    input.value = '';
    _renderChips('recipientChips', _recipients, 'removeRecipient');
}

function removeRecipient(idx) {
    _recipients.splice(idx, 1);
    _renderChips('recipientChips', _recipients, 'removeRecipient');
}

function addCc() {
    var input = document.getElementById('distCcInput');
    var email = input.value.trim().toLowerCase();
    if (!email || _ccList.indexOf(email) !== -1) return;
    if (!email.includes('@')) return;
    _ccList.push(email);
    input.value = '';
    _renderChips('ccChips', _ccList, 'removeCc');
}

function removeCc(idx) {
    _ccList.splice(idx, 1);
    _renderChips('ccChips', _ccList, 'removeCc');
}

// -- Report checkbox + path template --------------------------------------

function onReportCheckChange(checkbox) {
    var item = checkbox.closest('.report-check-item');
    var pathDiv = item.querySelector('.report-path-input');
    var pathInput = item.querySelector('.report-path-field');
    if (checkbox.checked) {
        pathDiv.style.display = 'block';
        if (!pathInput.value) {
            var key = checkbox.value;
            pathInput.value = DEFAULT_PATH_TEMPLATES[key] || '';
        }
    } else {
        pathDiv.style.display = 'none';
    }
}

// -- Trigger / Frequency UI -----------------------------------------------

function onTriggerChange() {
    var mode = document.querySelector('input[name="triggerMode"]:checked').value;
    document.getElementById('sendTimeRow').style.display = mode === 'scheduled' ? 'block' : 'none';
}

function onFrequencyChange() {
    var freq = document.getElementById('distFrequency').value;
    document.getElementById('dowSection').style.display = freq === 'weekly' ? 'block' : 'none';
    document.getElementById('domSection').style.display = freq === 'monthly' ? 'block' : 'none';
}

// -- Modal ----------------------------------------------------------------

function _resetModal() {
    document.getElementById('editDistId').value = '';
    document.getElementById('distName').value = '';
    document.getElementById('distSubject').value = 'Daily Reports - {date}';
    document.getElementById('distBody').value = '';
    document.getElementById('distEnabled').checked = true;
    _recipients = [];
    _ccList = [];
    _renderChips('recipientChips', _recipients, 'removeRecipient');
    _renderChips('ccChips', _ccList, 'removeCc');

    // Reset report checks and path inputs
    var checks = document.querySelectorAll('.dist-report-check');
    for (var i = 0; i < checks.length; i++) {
        checks[i].checked = false;
        var item = checks[i].closest('.report-check-item');
        item.querySelector('.report-path-input').style.display = 'none';
        item.querySelector('.report-path-field').value = '';
    }

    // Reset trigger/schedule
    var radios = document.querySelectorAll('input[name="triggerMode"]');
    for (var r = 0; r < radios.length; r++) radios[r].checked = radios[r].value === 'after_reports';
    document.getElementById('distFrequency').value = 'daily';
    document.getElementById('distSendTime').value = '09:00';
    var dowChecks = document.querySelectorAll('.dow-check');
    for (var d = 0; d < dowChecks.length; d++) dowChecks[d].checked = false;
    var domChecks = document.querySelectorAll('.dom-check');
    for (var m = 0; m < domChecks.length; m++) domChecks[m].checked = false;

    onTriggerChange();
    onFrequencyChange();
    _clearMsg();
}

function openAddModal() {
    _resetModal();
    document.getElementById('distModalTitle').textContent = 'Add Distribution';
    document.getElementById('distModal').style.display = 'flex';
    if (window.feather) feather.replace();
}

function openEditModal(id) {
    _resetModal();
    var dist = null;
    for (var i = 0; i < DISTRIBUTIONS_DATA.length; i++) {
        if (DISTRIBUTIONS_DATA[i].id === id) { dist = DISTRIBUTIONS_DATA[i]; break; }
    }
    if (!dist) return;

    document.getElementById('distModalTitle').textContent = 'Edit Distribution';
    document.getElementById('editDistId').value = id;
    document.getElementById('distName').value = dist.name;
    document.getElementById('distSubject').value = dist.subject_template || 'Daily Reports - {date}';
    document.getElementById('distBody').value = dist.body_template || '';
    document.getElementById('distEnabled').checked = !!dist.enabled;

    _recipients = (dist.recipients || []).slice();
    _ccList = (dist.cc || []).slice();
    _renderChips('recipientChips', _recipients, 'removeRecipient');
    _renderChips('ccChips', _ccList, 'removeCc');

    // Set report checks and path templates
    var reportKeys = {};
    (dist.report_keys || []).forEach(function(r) {
        reportKeys[r.report_key] = r.file_path_template || '';
    });
    var checks = document.querySelectorAll('.dist-report-check');
    for (var j = 0; j < checks.length; j++) {
        var key = checks[j].value;
        if (key in reportKeys) {
            checks[j].checked = true;
            var item = checks[j].closest('.report-check-item');
            item.querySelector('.report-path-input').style.display = 'block';
            var pathField = item.querySelector('.report-path-field');
            pathField.value = reportKeys[key] || DEFAULT_PATH_TEMPLATES[key] || '';
        }
    }

    // Set trigger/schedule
    var triggerMode = dist.trigger_mode || 'after_reports';
    var radios = document.querySelectorAll('input[name="triggerMode"]');
    for (var r = 0; r < radios.length; r++) radios[r].checked = radios[r].value === triggerMode;

    document.getElementById('distFrequency').value = dist.frequency || 'daily';
    document.getElementById('distSendTime').value = dist.send_time || '09:00';

    var dowDays = (dist.days_of_week || '').split(',').map(function(s) { return s.trim(); });
    var dowChecks = document.querySelectorAll('.dow-check');
    for (var d = 0; d < dowChecks.length; d++) {
        dowChecks[d].checked = dowDays.indexOf(dowChecks[d].value) !== -1;
    }

    var domDays = (dist.month_days || '').split(',').map(function(s) { return s.trim(); });
    var domChecks = document.querySelectorAll('.dom-check');
    for (var m = 0; m < domChecks.length; m++) {
        domChecks[m].checked = domDays.indexOf(domChecks[m].value) !== -1;
    }

    onTriggerChange();
    onFrequencyChange();

    document.getElementById('distModal').style.display = 'flex';
    if (window.feather) feather.replace();
}

function closeDistModal() {
    document.getElementById('distModal').style.display = 'none';
}

// -- Save -----------------------------------------------------------------

function saveDist() {
    var distId = document.getElementById('editDistId').value;
    var name = document.getElementById('distName').value.trim();
    var subject = document.getElementById('distSubject').value.trim();
    var body = document.getElementById('distBody').value.trim();
    var enabled = document.getElementById('distEnabled').checked;

    // Collect report keys with path templates
    var reportKeys = [];
    var checks = document.querySelectorAll('.dist-report-check');
    for (var i = 0; i < checks.length; i++) {
        if (checks[i].checked) {
            var item = checks[i].closest('.report-check-item');
            var pathField = item.querySelector('.report-path-field');
            reportKeys.push({
                report_key: checks[i].value,
                file_path_template: (pathField.value || '').trim()
            });
        }
    }

    // Collect trigger/schedule
    var triggerMode = document.querySelector('input[name="triggerMode"]:checked').value;
    var frequency = document.getElementById('distFrequency').value;
    var sendTime = document.getElementById('distSendTime').value || '';

    var daysOfWeek = [];
    var dowChecks = document.querySelectorAll('.dow-check');
    for (var d = 0; d < dowChecks.length; d++) {
        if (dowChecks[d].checked) daysOfWeek.push(dowChecks[d].value);
    }

    var monthDays = [];
    var domChecks = document.querySelectorAll('.dom-check');
    for (var m = 0; m < domChecks.length; m++) {
        if (domChecks[m].checked) monthDays.push(domChecks[m].value);
    }

    if (!name) { _showMsg('Name is required.', true); return; }
    if (reportKeys.length === 0) { _showMsg('Select at least one report.', true); return; }
    if (_recipients.length === 0) { _showMsg('Add at least one recipient.', true); return; }

    var payload = {
        name: name,
        recipients: _recipients,
        cc: _ccList,
        report_keys: reportKeys,
        subject_template: subject || 'Daily Reports - {date}',
        body_template: body,
        enabled: enabled,
        trigger_mode: triggerMode,
        frequency: frequency,
        days_of_week: daysOfWeek.join(','),
        month_days: monthDays.join(','),
        send_time: triggerMode === 'scheduled' ? sendTime : ''
    };

    var url, method;
    if (distId) {
        url = '/api/email-distributions/' + distId;
        method = 'PUT';
    } else {
        url = '/api/email-distributions';
        method = 'POST';
    }

    var btn = document.getElementById('distSaveBtn');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            location.reload();
        } else {
            _showMsg(data.error || 'Failed to save.', true);
            btn.disabled = false;
            btn.textContent = 'Save';
        }
    })
    .catch(function(err) {
        _showMsg('Network error: ' + err.message, true);
        btn.disabled = false;
        btn.textContent = 'Save';
    });
}

// -- Actions --------------------------------------------------------------

function toggleDist(id, checkbox) {
    fetch('/api/email-distributions/' + id + '/toggle', { method: 'POST' })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (!data.success) {
            checkbox.checked = !checkbox.checked;
            showBanner(data.error || 'Failed to toggle.', 'error');
        }
    })
    .catch(function() {
        checkbox.checked = !checkbox.checked;
    });
}

function deleteDist(id) {
    if (!confirm('Delete this email distribution?')) return;
    fetch('/api/email-distributions/' + id, { method: 'DELETE' })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) location.reload();
        else showBanner(data.error || 'Failed to delete.', 'error');
    });
}

function sendNow(id, btnEl) {
    var btn = btnEl || event.target.closest('button');
    btn.disabled = true;
    showBanner('Downloading files from SharePoint and sending email...', 'info');

    fetch('/api/email-distributions/' + id + '/send-now', { method: 'POST' })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        btn.disabled = false;
        if (data.success) {
            var files = (data.reports_sent || []).join(', ');
            showBanner('Email sent successfully! Files: ' + files, 'success');
            refreshLog();
        } else {
            showBanner('Send failed: ' + (data.error || 'Unknown error'), 'error');
            refreshLog();
        }
    })
    .catch(function(err) {
        btn.disabled = false;
        showBanner('Network error: ' + err.message, 'error');
    });
}

// -- Log refresh ----------------------------------------------------------

function refreshLog() {
    fetch('/api/email-distributions/log')
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (!data.success) return;
        var container = document.getElementById('logTableContainer');
        var entries = data.log || [];
        if (entries.length === 0) {
            container.innerHTML = '<p style="color:var(--text-muted); font-size:13px; margin:0;">No emails sent yet.</p>';
            return;
        }
        var html = '<div class="table-wrapper" style="max-height:300px; overflow-y:auto;">';
        html += '<table class="data-table" style="font-size:12px;"><thead><tr>';
        html += '<th>Distribution</th><th>Date</th><th>Status</th><th>Reports</th><th>Error</th>';
        html += '</tr></thead><tbody>';
        entries.forEach(function(e) {
            html += '<tr>';
            html += '<td>' + (e.distribution_name || '') + '</td>';
            html += '<td style="white-space:nowrap;">' + (e.sent_date || '') + '</td>';
            html += '<td><span class="status-badge status-' + e.status + '">' + e.status + '</span></td>';
            html += '<td>';
            (e.reports_included || []).forEach(function(rk) {
                html += '<span class="chip">' + rk + '</span>';
            });
            html += '</td>';
            html += '<td style="max-width:200px; overflow:hidden; text-overflow:ellipsis;" title="' +
                    (e.error || '').replace(/"/g, '&quot;') + '">' + (e.error || '') + '</td>';
            html += '</tr>';
        });
        html += '</tbody></table></div>';
        container.innerHTML = html;
    })
    .catch(function() {});
}

// -- Modal backdrop close -------------------------------------------------
document.addEventListener('DOMContentLoaded', function() {
    var overlay = document.getElementById('distModal');
    if (overlay) {
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) closeDistModal();
        });
    }
});

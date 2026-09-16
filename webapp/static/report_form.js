/* ================================================================
   Report form page -- extracted from report_form.html inline script
   ================================================================ */

document.addEventListener('DOMContentLoaded', function() {
    if (typeof REPORT_FORM_CONFIG === 'undefined') return;
    var PRESET_PARAMS = REPORT_FORM_CONFIG.presetParams || {};
    if (!PRESET_PARAMS || !Object.keys(PRESET_PARAMS).length) return;

    if (PRESET_PARAMS.period) {
        var periodBtns = document.querySelectorAll('.period-btn');
        periodBtns.forEach(function(b) {
            b.classList.toggle('active', b.dataset.period === PRESET_PARAMS.period);
        });
        var pi = document.getElementById('periodInput');
        if (pi) pi.value = PRESET_PARAMS.period;
        if (PRESET_PARAMS.period === 'custom') {
            var cr = document.getElementById('customDateRange');
            if (cr) cr.style.display = '';
            if (PRESET_PARAMS.from_date) document.getElementById('fromDate').value = PRESET_PARAMS.from_date;
            if (PRESET_PARAMS.to_date) document.getElementById('toDate').value = PRESET_PARAMS.to_date;
        }
    }
    if (PRESET_PARAMS.year) {
        var yi = document.getElementById('yearInput');
        if (yi) yi.value = PRESET_PARAMS.year;
    }
    if (PRESET_PARAMS.status !== undefined) {
        var statusBtns = document.querySelectorAll('.status-btn');
        statusBtns.forEach(function(b) {
            b.classList.toggle('active', b.dataset.status === PRESET_PARAMS.status);
        });
        var si = document.getElementById('statusInput');
        if (si) si.value = PRESET_PARAMS.status;
    }
    if (PRESET_PARAMS.salesman) {
        var ss = document.getElementById('salesmanSelect');
        if (ss) { ss.value = PRESET_PARAMS.salesman; ss.dispatchEvent(new Event('change')); }
    }
    if (PRESET_PARAMS.autorun) {
        var delay = (typeof HAS_CUSTOMER_FILTER !== 'undefined' && HAS_CUSTOMER_FILTER) ? 1500 : 300;
        setTimeout(function() { document.getElementById('reportForm').requestSubmit(); }, delay);
    }
});

function _collectParams() {
    var p = {};
    var form = document.getElementById('reportForm');
    var fd = new FormData(form);
    fd.forEach(function(v, k) { if (v) p[k] = v; });
    /* Same fix as runReport(): the custom-range inputs aren't cleared
       when the user picks This Month / YTD / etc., so FormData would
       otherwise smuggle stale dates into the saved preset. */
    if (p.period !== 'custom') {
        delete p.from_date;
        delete p.to_date;
    }
    var chips = document.querySelectorAll('#selectedCustomers .chip');
    if (chips.length) {
        var customers = [];
        chips.forEach(function(c) { customers.push(c.dataset.account); });
        p['customers'] = customers;
    }
    return p;
}

function openSavePreset() {
    document.getElementById('savePresetModal').style.display = 'block';
    document.getElementById('presetName').value = '';
    document.getElementById('presetMsg').style.display = 'none';
    document.getElementById('presetName').focus();
}

function closeSavePreset() {
    document.getElementById('savePresetModal').style.display = 'none';
}

function doSavePreset() {
    var cfg = (typeof REPORT_FORM_CONFIG !== 'undefined') ? REPORT_FORM_CONFIG : {};
    var REPORT_KEY = cfg.reportKey || '';
    var REPORT_NAME = cfg.reportName || '';

    var name = document.getElementById('presetName').value.trim();
    var msg = document.getElementById('presetMsg');
    if (!name) { msg.style.display = 'block'; msg.style.color = 'var(--error)'; msg.textContent = 'Please enter a name.'; return; }
    var params = _collectParams();
    var payload = {name: name, report_key: REPORT_KEY, report_name: REPORT_NAME, params: params};
    var forUserEl = document.getElementById('presetForUser');
    if (forUserEl && forUserEl.value) {
        payload.for_user_email = forUserEl.value;
    }
    fetch('/api/saved-reports', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    }).then(function(r) { return r.json(); }).then(function(d) {
        if (d.error) { msg.style.display = 'block'; msg.style.color = 'var(--error)'; msg.textContent = d.error; }
        else {
            var who = (forUserEl && forUserEl.value) ? forUserEl.options[forUserEl.selectedIndex].text : 'you';
            msg.style.display = 'block'; msg.style.color = 'var(--success)';
            msg.textContent = 'Preset saved for ' + who + '!';
            setTimeout(closeSavePreset, 1000);
        }
    }).catch(function() { msg.style.display = 'block'; msg.style.color = 'var(--error)'; msg.textContent = 'Network error'; });
}

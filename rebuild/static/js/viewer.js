// === What's in this file ===
// The invoiced report viewer. It reads the filter form, asks the server to run
// the report (which drops a background job), polls until the job finishes, then
// shows the result one tab at a time in a Tabulator table. A Cancel button is
// shown only while a run is in flight.
//
// Plain browser JavaScript on purpose: the preview slot has no build step, so
// there's nothing to compile. Tabulator is loaded from a CDN in the page.

(function () {
  "use strict";

  var root = document.getElementById("report-root");
  if (!root) return;

  var runUrl = root.dataset.runUrl;
  var resultUrl = root.dataset.resultUrl;
  var jobUrlTpl = root.dataset.jobUrlTpl;
  var cancelUrlTpl = root.dataset.cancelUrlTpl;
  var csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

  var form = document.getElementById("filters");
  var runBtn = document.getElementById("run-btn");
  var statusBox = document.getElementById("run-status");
  var statusText = document.getElementById("run-status-text");
  var cancelBtn = document.getElementById("cancel-btn");
  var tabbar = document.getElementById("tabbar");

  var table = null;
  var pollTimer = null;
  var currentJobId = null;
  var currentCacheKey = null;
  var activeTabKey = null;
  var tabData = {};        // tab_key -> already-fetched tab payload (cleared per run)
  var tabReqToken = 0;     // guards against a slow tab response landing after a newer click

  var tableHost = document.getElementById("report-table");
  var tableMsg = document.createElement("div");
  tableMsg.className = "table-msg";
  tableMsg.hidden = true;
  tableHost.parentNode.appendChild(tableMsg);

  function gatherFilters() {
    var filters = {};
    var fields = form.querySelectorAll("[data-filter-key]");
    for (var i = 0; i < fields.length; i++) {
      var key = fields[i].getAttribute("data-filter-key");
      var value = (fields[i].value || "").trim();
      if (value !== "") filters[key] = value;
    }
    return filters;
  }

  function setStatus(message, busy) {
    statusBox.hidden = false;
    statusText.textContent = message;
    cancelBtn.hidden = !busy;
    runBtn.disabled = !!busy;
  }

  function clearStatusSoon() {
    cancelBtn.hidden = true;
    runBtn.disabled = false;
  }

  function jsonHeaders() {
    return { "Content-Type": "application/json", "X-CSRF-Token": csrfToken };
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    startRun();
  });

  cancelBtn.addEventListener("click", function () {
    if (!currentJobId) return;
    fetch(cancelUrlTpl.replace("__JOB__", currentJobId), { method: "POST", headers: jsonHeaders() })
      .then(function () { setStatus("Cancelling\u2026", true); });
  });

  function startRun() {
    stopPolling();
    setStatus("Starting\u2026", true);
    fetch(runUrl, { method: "POST", headers: jsonHeaders(), body: JSON.stringify(gatherFilters()) })
      .then(function (resp) { return resp.json().then(function (b) { return { status: resp.status, body: b }; }); })
      .then(function (r) {
        if (r.status === 202) {
          currentJobId = r.body.job_id;
          currentCacheKey = r.body.cache_key;
          setStatus("Running\u2026", true);
          startPolling();
        } else {
          setStatus(r.body.error || "Could not start the report.", false);
          clearStatusSoon();
        }
      })
      .catch(function () { setStatus("Could not reach the server.", false); clearStatusSoon(); });
  }

  function startPolling() {
    pollTimer = setInterval(pollOnce, 1500);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function pollOnce() {
    if (!currentJobId) return;
    fetch(jobUrlTpl.replace("__JOB__", currentJobId), { headers: { "X-CSRF-Token": csrfToken } })
      .then(function (resp) { return resp.json(); })
      .then(function (job) {
        if (job.status === "done") {
          stopPolling();
          setStatus("Done.", false);
          clearStatusSoon();
          loadResult();
        } else if (job.status === "failed") {
          stopPolling();
          setStatus(job.error || "The report failed.", false);
          clearStatusSoon();
        } else if (job.status === "cancelled") {
          stopPolling();
          setStatus("Cancelled.", false);
          clearStatusSoon();
        }
      })
      .catch(function () { /* keep polling; a blip shouldn't stop the run */ });
  }

  function loadResult() {
    tabData = {};
    fetch(resultUrl + "?cache_key=" + encodeURIComponent(currentCacheKey), { headers: { "X-CSRF-Token": csrfToken } })
      .then(function (resp) { return resp.json(); })
      .then(function (summary) {
        if (summary.stale) {
          setStatus(summary.stale_reason || "Showing the last saved copy.", false);
        }
        renderTabs(summary.tabs, summary.active_tab);
        if (summary.active_tab) loadTab(summary.active_tab);
        prefetchTabs(summary.tabs, summary.active_tab);
      });
  }

  // Quietly fetch the other tabs once so switching to them is instant.
  function prefetchTabs(tabs, active) {
    tabs.forEach(function (tab) {
      if (tab.key === active || tabData[tab.key]) return;
      fetch(resultUrl + "/" + encodeURIComponent(tab.key) + "?cache_key=" + encodeURIComponent(currentCacheKey),
            { headers: { "X-CSRF-Token": csrfToken } })
        .then(function (resp) { return resp.ok ? resp.json() : null; })
        .then(function (data) { if (data) tabData[tab.key] = data; })
        .catch(function () { /* a failed prefetch just means that tab loads on click */ });
    });
  }

  function renderTabs(tabs, active) {
    tabbar.innerHTML = "";
    tabbar.hidden = tabs.length === 0;
    tabs.forEach(function (tab) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tab" + (tab.key === active ? " tab--active" : "");
      btn.textContent = tab.label + " (" + tab.row_count + ")";
      btn.addEventListener("click", function () { loadTab(tab.key); });
      btn.dataset.tabKey = tab.key;
      tabbar.appendChild(btn);
    });
  }

  function loadTab(tabKey) {
    activeTabKey = tabKey;
    var btns = tabbar.querySelectorAll(".tab");
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.toggle("tab--active", btns[i].dataset.tabKey === tabKey);
    }
    if (tabData[tabKey]) { renderTable(tabData[tabKey]); return; }

    var token = ++tabReqToken;
    showTableMessage("Loading\u2026");
    fetch(resultUrl + "/" + encodeURIComponent(tabKey) + "?cache_key=" + encodeURIComponent(currentCacheKey),
          { headers: { "X-CSRF-Token": csrfToken } })
      .then(function (resp) {
        if (!resp.ok) throw new Error("This tab couldn't be loaded (" + resp.status + ").");
        return resp.json();
      })
      .then(function (tab) {
        tabData[tabKey] = tab;
        if (token === tabReqToken && activeTabKey === tabKey) renderTable(tab);
      })
      .catch(function (err) {
        if (token === tabReqToken && activeTabKey === tabKey) {
          showTableMessage(err.message || "This tab couldn't be loaded.");
        }
      });
  }

  // Drop the old table at once so a slow fetch never leaves the previous tab on
  // screen, and show a loading/error note in its place.
  function showTableMessage(message) {
    if (table) { table.destroy(); table = null; }
    tableHost.innerHTML = "";
    tableMsg.textContent = message;
    tableMsg.hidden = false;
  }

  function columnDef(col) {
    var def = { title: col.label || col.field, field: col.field };
    if (col.type === "money") {
      def.formatter = "money";
      def.formatterParams = { decimal: ".", thousand: ",", symbol: "$", precision: 2 };
      def.hozAlign = "right";
    } else if (col.type === "int") {
      def.hozAlign = "right";
    } else if (col.type === "percent") {
      def.formatter = function (cell) {
        var v = cell.getValue();
        return (v === "" || v === null || v === undefined) ? "" : (Number(v) * 100).toFixed(2) + "%";
      };
      def.hozAlign = "right";
    }
    return def;
  }

  function renderTable(tab) {
    tableMsg.hidden = true;
    var columns = (tab.columns || []).map(columnDef);
    var data = (tab.rows || []).slice();
    if (tab.total) {
      var totalRow = Object.assign({}, tab.total);
      totalRow.__total = true;
      data.push(totalRow);
    }
    if (table) { table.destroy(); }
    table = new Tabulator("#report-table", {
      data: data,
      columns: columns,
      layout: "fitDataStretch",
      height: "100%",
      movableColumns: true,
      resizableColumns: true,
      placeholder: "No rows for this tab.",
      rowFormatter: function (row) {
        if (row.getData().__total) {
          row.getElement().style.fontWeight = "700";
          row.getElement().style.background = "#f1f5f9";
        }
      },
    });
  }
})();

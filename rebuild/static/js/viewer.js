// === What's in this file ===
// The invoiced report viewer. It reads the filter form, asks the server to run
// the report (which drops a background job), polls until the job finishes, then
// shows the result one tab at a time. Tabs are fetched once and cached, the
// other tabs prefetched quietly, so switching is instant; a click clears the
// old table and shows a loading note so you never stare at the previous tab.
// Most tabs render in a Tabulator table; the Commissions (Cards) tab renders as
// per-salesman cards. A Cancel button shows only while a run is in flight.
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
  var filtersToggle = document.getElementById("filters-toggle");

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

  // Size the table to the space left below it so it scrolls inside its own box
  // (both scrollbars reachable) instead of pushing the page taller. Recomputed
  // on resize and whenever the filters panel collapses/expands.
  function fitHeight() {
    var top = tableHost.getBoundingClientRect().top;
    return Math.max(240, Math.floor(window.innerHeight - top - 16));
  }

  function refit() {
    if (table) {
      table.setHeight(fitHeight());
    } else {
      var cards = tableHost.querySelector(".commission-cards");
      if (cards) cards.style.height = fitHeight() + "px";
    }
  }

  window.addEventListener("resize", refit);

  filtersToggle.addEventListener("click", function () {
    var collapsed = root.classList.toggle("viewer--filters-collapsed");
    filtersToggle.setAttribute("aria-expanded", String(!collapsed));
    filtersToggle.textContent = collapsed ? "Show filters" : "Hide filters";
    refit();
  });

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
    if (tab.layout === "commission_cards") {
      renderCommissionCards(tab);
      return;
    }
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
      height: fitHeight(),
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

  function money(value) {
    var n = Number(value);
    if (!isFinite(n)) n = 0;
    return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // The card view: one block per salesman with a Month / Net / Commission
  // mini-table and a YTD footer. Same numbers as the Commissions pivot tab,
  // shown the way the old v3 app showed them so the two can be compared.
  function renderCommissionCards(tab) {
    if (table) { table.destroy(); table = null; }
    var host = document.getElementById("report-table");
    host.innerHTML = "";
    var salesmen = tab.salesmen || [];
    if (salesmen.length === 0) {
      showTableMessage("No commissions for this period.");
      return;
    }
    var wrap = document.createElement("div");
    wrap.className = "commission-cards";
    wrap.style.height = fitHeight() + "px";
    salesmen.forEach(function (s) {
      var card = document.createElement("div");
      card.className = "commission-card";

      var head = document.createElement("div");
      head.className = "commission-card__head";
      var title = document.createElement("span");
      title.className = "commission-card__title";
      title.textContent = s.salesman_number + " \u2014 " + s.salesman_name;
      var payable = document.createElement("span");
      payable.className = "commission-card__payable";
      var payLabel = document.createElement("small");
      payLabel.textContent = "YTD commission";
      var payAmt = document.createElement("strong");
      payAmt.textContent = money(s.ytd.commission);
      payable.appendChild(payLabel);
      payable.appendChild(payAmt);
      head.appendChild(title);
      head.appendChild(payable);
      card.appendChild(head);

      var sub = document.createElement("div");
      sub.className = "commission-card__sub";
      sub.textContent = "Commission " + (Number(s.commission_pct) * 100).toFixed(1) + "%";
      card.appendChild(sub);

      // Month labels come from our own constant and the amounts are numbers, so
      // there's no untrusted text in this table markup.
      var rows = (s.monthly || []).map(function (m) {
        return "<tr><td>" + m.month_label + "</td><td>" + money(m.net) + "</td><td>" + money(m.commission) + "</td></tr>";
      }).join("");
      var tbl = document.createElement("table");
      tbl.className = "commission-month-table";
      tbl.innerHTML =
        "<thead><tr><th>Month</th><th>Net</th><th>Commission</th></tr></thead>" +
        "<tbody>" + rows + "</tbody>" +
        "<tfoot><tr><td>YTD</td><td>" + money(s.ytd.net) + "</td><td>" + money(s.ytd.commission) + "</td></tr></tfoot>";
      card.appendChild(tbl);
      wrap.appendChild(card);
    });
    host.appendChild(wrap);
  }
})();

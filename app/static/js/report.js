let table = null;
let tabsByKey = {};
let activeKey = "";
let lastJobId = null;
let selectedCustomers = [];
let runAbort = null;
let frozenFields = new Set();

function customerCatalog() {
  const controls = document.getElementById("reportControls");
  if (!controls) return [];
  try {
    return JSON.parse(controls.getAttribute("data-customers") || "[]");
  } catch (err) {
    setStatus("Customer list could not be read (" + err.message + "). Expected a JSON array.");
    return [];
  }
}

function collectParams() {
  const controls = document.getElementById("reportControls");
  const params = {};
  const period = document.getElementById("periodSelect");
  if (period) params.period = period.value;
  const fromDate = document.getElementById("fromDate");
  const toDate = document.getElementById("toDate");
  if (fromDate) params.from_date = fromDate.value;
  if (toDate) params.to_date = toDate.value;
  const status = document.getElementById("statusSelect");
  if (status) params.status = status.value;
  const year = document.getElementById("yearSelect");
  if (year) params.year = year.value;
  const n4 = document.getElementById("n4Select");
  if (n4) params.n4_mode = n4.value;
  const salesman = document.getElementById("salesmanSelect");
  if (salesman) params.salesman = salesman.value;
  if (document.getElementById("customerPicker")) {
    params.customers = selectedCustomers.slice();
  }
  params.report_key = controls.getAttribute("data-report-key");
  return params;
}

function columnsFromRows(rows) {
  const first = rows[0] || {};
  return Object.keys(first).map((field, idx) => {
    const sample = first[field];
    const isNumber = typeof sample === "number";
    const moneyName = /total|amount|invoice|commission|percent|charge|sales|price|qty|open|ordered|fulfill/i.test(field)
      && !/count/i.test(field);
    return {
      title: field,
      field,
      frozen: frozenFields.size ? frozenFields.has(field) : idx === 0,
      hozAlign: isNumber ? "right" : "left",
      headerFilter: "input",
      formatter: isNumber && moneyName ? "money" : "plaintext",
      bottomCalc: isNumber ? "sum" : undefined,
    };
  });
}

function setStatus(text, canCancel) {
  const row = document.getElementById("reportStatus");
  const label = document.getElementById("reportStatusText");
  const cancel = document.getElementById("cancelRunBtn");
  if (!row || !label) return;
  row.hidden = !text;
  label.textContent = text || "";
  if (cancel) cancel.hidden = !canCancel;
}

function logJob(step) {
  const panel = document.getElementById("jobLiveLogPanel");
  const list = document.getElementById("jobLiveLog");
  if (!panel || !list) return;
  panel.hidden = false;
  const item = document.createElement("li");
  item.textContent = new Date().toISOString().slice(11, 19) + " · " + step;
  list.appendChild(item);
}

function showCommissionCards(rows) {
  const wrap = document.getElementById("commissionCards");
  const grid = document.getElementById("reportTable");
  wrap.hidden = false;
  grid.hidden = true;
  wrap.innerHTML = rows.map((row) => {
    const name = row.SalesmanName || row.Salesman || "";
    const pct = row.Percent != null ? Math.round(row.Percent * 1000) / 10 + "%" : "";
    const dollars = row.CommissionDollars != null ? row.CommissionDollars : "";
    return '<div class="settings-card"><h3>' + name + "</h3><p>" + pct + " · $" + dollars + "</p></div>";
  }).join("");
}

function fillGroupBy(columns) {
  const wrap = document.getElementById("groupByWrap");
  const select = document.getElementById("groupBySelect");
  if (!wrap || !select) return;
  wrap.hidden = false;
  const current = select.value;
  select.innerHTML = '<option value="">None</option>';
  columns.forEach((col) => {
    const opt = document.createElement("option");
    opt.value = col.field;
    opt.textContent = col.title;
    select.appendChild(opt);
  });
  if (current) select.value = current;
}

function showTab(key) {
  activeKey = key;
  const tab = tabsByKey[key];
  document.querySelectorAll(".report-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-key") === key);
  });
  const rows = (tab && tab.rows) || [];
  const wrap = document.getElementById("commissionCards");
  const grid = document.getElementById("reportTable");
  if (key === "commissions") {
    showCommissionCards(rows);
    return;
  }
  wrap.hidden = true;
  grid.hidden = false;
  if (table) table.destroy();
  const columns = columnsFromRows(rows);
  fillGroupBy(columns);
  const groupField = (document.getElementById("groupBySelect") || {}).value || "";
  table = new Tabulator("#reportTable", {
    data: rows,
    layout: "fitDataStretch",
    placeholder: "No rows",
    movableColumns: true,
    groupBy: groupField || false,
    columns,
  });
}

function renderTabs(payload) {
  const data = payload.data || {};
  const tabs = data.tabs || {};
  tabsByKey = tabs;
  lastJobId = data.job_id || lastJobId;
  const keys = Object.keys(tabs);
  const bar = document.getElementById("reportTabs");
  bar.innerHTML = "";
  keys.forEach((key, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "report-tab" + (idx === 0 ? " active" : "");
    btn.setAttribute("data-key", key);
    btn.textContent = tabs[key].name || key;
    btn.addEventListener("click", () => showTab(key));
    bar.appendChild(btn);
  });
  const meta = document.getElementById("reportMeta");
  const from = data.from_date || "";
  const to = data.to_date || "";
  meta.textContent = (from && to ? from + " – " + to + " · " : "") + (data.source || "mock") + " data";
  document.getElementById("reportSurface").hidden = false;
  if (keys.length) showTab(keys[0]);
}

async function runReport(bodyOverride) {
  const params = bodyOverride || collectParams();
  const preview = document.getElementById("apiPreview");
  if (preview && !bodyOverride) preview.value = JSON.stringify(params, null, 2);
  setStatus("Running…", true);
  logJob("Start run");
  if (runAbort) runAbort.abort();
  runAbort = new AbortController();
  try {
    const res = await fetch("/api/reports/" + params.report_key + "/run", {
      method: "POST",
      headers: csrfHeaders(),
      body: JSON.stringify(params),
      signal: runAbort.signal,
    });
    const payload = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(payload.error || ("Could not run report (HTTP " + res.status + ")"));
    logJob("Bound " + Object.keys((payload.data || {}).tabs || {}).length + " tabs");
    renderTabs(payload);
    setStatus("Loaded.", false);
    const summary = document.getElementById("controlsSummary");
    if (summary && params.period) summary.textContent = params.period.replace(/_/g, " ");
  } catch (err) {
    if (err.name === "AbortError") {
      setStatus("Cancelled.", false);
      logJob("Cancelled");
      return;
    }
    setStatus(err.message, false);
    document.getElementById("reportSurface").hidden = false;
    throw err;
  }
}

function applySavedParams(params) {
  if (!params) return;
  const map = {
    period: "periodSelect",
    status: "statusSelect",
    year: "yearSelect",
    n4_mode: "n4Select",
    salesman: "salesmanSelect",
  };
  Object.keys(map).forEach((key) => {
    const el = document.getElementById(map[key]);
    if (el && params[key] != null) el.value = params[key];
  });
  if (Array.isArray(params.customers)) {
    selectedCustomers = params.customers.slice();
    renderPills();
  }
  toggleCustomDates();
}

function toggleCustomDates() {
  const period = document.getElementById("periodSelect");
  const fromWrap = document.getElementById("customDates");
  const toWrap = document.getElementById("customDatesTo");
  const custom = period && period.value === "custom";
  if (fromWrap) fromWrap.hidden = !custom;
  if (toWrap) toWrap.hidden = !custom;
}

function exportHref() {
  const params = collectParams();
  const query = new URLSearchParams();
  Object.keys(params).forEach((key) => {
    if (key === "customers") {
      if (params.customers && params.customers.length) query.set("customers", params.customers.join(","));
    } else if (params[key]) {
      query.set(key, params[key]);
    }
  });
  return "/api/reports/" + params.report_key + "/xlsx?" + query.toString();
}

function renderPills() {
  const pills = document.getElementById("customerPills");
  if (!pills) return;
  const catalog = customerCatalog();
  pills.innerHTML = selectedCustomers.map((account) => {
    const row = catalog.find((item) => item.account === account) || { name: account };
    return '<button type="button" class="customer-chip" data-account="' + account + '">'
      + row.name + " ✕</button>";
  }).join("");
  pills.querySelectorAll(".customer-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      selectedCustomers = selectedCustomers.filter((item) => item !== chip.getAttribute("data-account"));
      renderPills();
    });
  });
}

function initCustomerPicker() {
  const search = document.getElementById("customerSearch");
  const menu = document.getElementById("customerMenu");
  if (!search || !menu) return;
  function showMenu() {
    const term = (search.value || "").toLowerCase();
    const rows = customerCatalog().filter((item) => {
      if (selectedCustomers.indexOf(item.account) !== -1) return false;
      return !term || (item.name + item.account).toLowerCase().indexOf(term) !== -1;
    });
    menu.innerHTML = rows.map((item) =>
      '<button type="button" class="toolbar-dropdown-item" data-account="' + item.account + '">'
      + item.name + " · " + item.account + "</button>"
    ).join("") || '<p class="muted">No matches</p>';
    menu.hidden = false;
    menu.querySelectorAll("[data-account]").forEach((btn) => {
      btn.addEventListener("click", () => {
        selectedCustomers.push(btn.getAttribute("data-account"));
        search.value = "";
        menu.hidden = true;
        renderPills();
      });
    });
  }
  search.addEventListener("focus", showMenu);
  search.addEventListener("input", showMenu);
  document.addEventListener("click", (evt) => {
    if (!evt.target.closest(".filter-field-customers")) menu.hidden = true;
  });
}

function closeOverlay(id) {
  const el = document.getElementById(id);
  if (el) el.hidden = true;
}

function openOverlay(id) {
  const el = document.getElementById(id);
  if (el) el.hidden = false;
}

document.addEventListener("DOMContentLoaded", () => {
  const controls = document.getElementById("reportControls");
  if (!controls) return;
  const toggle = document.getElementById("controlsToggle");
  const body = document.getElementById("controlsBody");
  if (toggle && body) {
    toggle.addEventListener("click", () => {
      const open = body.hasAttribute("hidden");
      if (open) body.removeAttribute("hidden");
      else body.setAttribute("hidden", "");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }
  const period = document.getElementById("periodSelect");
  if (period) period.addEventListener("change", toggleCustomDates);
  const rawParams = controls.getAttribute("data-view-params") || "{}";
  try {
    applySavedParams(JSON.parse(rawParams));
  } catch (err) {
    document.getElementById("reportMeta").textContent =
      "Saved view params could not be read (" + err.message + "). Expected JSON object.";
  }
  initCustomerPicker();
  document.getElementById("runBtn").addEventListener("click", () => {
    runReport().catch(() => {});
  });
  const cancel = document.getElementById("cancelRunBtn");
  if (cancel) {
    cancel.addEventListener("click", () => {
      if (runAbort) runAbort.abort();
      if (lastJobId) {
        fetch("/api/jobs/" + lastJobId + "/cancel", { method: "POST", headers: csrfHeaders() });
      }
    });
  }
  document.getElementById("emailMeBtn").addEventListener("click", () => openOverlay("emailOverlay"));
  document.getElementById("emailConfirm").addEventListener("click", async () => {
    const params = collectParams();
    params.recipients = document.getElementById("emailTo").value;
    params.subject = document.getElementById("emailSubject").value;
    const folder = document.getElementById("emailSharepoint");
    if (folder) params.sharepoint_folder = folder.value;
    const res = await fetch("/api/reports/" + params.report_key + "/email", {
      method: "POST",
      headers: csrfHeaders(),
      body: JSON.stringify(params),
    });
    const data = await res.json().catch(() => ({}));
    alert(res.ok ? "Mock mail queued to " + data.recipients : (data.error || "Email failed"));
    if (res.ok) closeOverlay("emailOverlay");
  });
  document.getElementById("exportBtn").addEventListener("click", (evt) => {
    evt.preventDefault();
    window.location.href = exportHref();
  });
  const exportsBtn = document.getElementById("exportsBtn");
  if (exportsBtn) {
    exportsBtn.addEventListener("click", async () => {
      const panel = document.getElementById("exportsPanel");
      const list = document.getElementById("exportsList");
      const res = await fetch("/api/jobs");
      const data = await res.json().catch(() => ({}));
      const jobs = (data.jobs || []).filter((job) => /export/i.test(job.title));
      panel.hidden = false;
      list.innerHTML = jobs.length
        ? jobs.map((job) => '<div class="recent-row">' + job.title + " · " + job.created_at + "</div>").join("")
        : "No exports yet. Click Export Excel.";
    });
  }
  document.getElementById("keepBtn").addEventListener("click", async () => {
    if (!lastJobId) {
      alert("Run a report first.");
      return;
    }
    const name = prompt("Name this kept run", "Kept run");
    if (!name) return;
    const res = await fetch("/api/jobs/" + lastJobId + "/keep", {
      method: "POST",
      headers: csrfHeaders(),
      body: JSON.stringify({ name }),
    });
    const data = await res.json().catch(() => ({}));
    alert(res.ok ? "Kept." : (data.error || "Keep failed (HTTP " + res.status + ")"));
  });
  document.getElementById("saveViewBtn").addEventListener("click", () => {
    openOverlay("saveViewOverlay");
    document.getElementById("saveViewName").focus();
  });
  document.getElementById("saveViewConfirm").addEventListener("click", async () => {
    const name = document.getElementById("saveViewName").value.trim();
    if (!name) {
      alert("Name is required.");
      return;
    }
    const params = collectParams();
    const kind = document.getElementById("saveViewKind").value || "personal";
    const forEmail = (document.getElementById("saveViewFor") || {}).value || "";
    const include = document.getElementById("saveViewIncludePeriod");
    const res = await fetch("/api/views", {
      method: "POST",
      headers: csrfHeaders(),
      body: JSON.stringify({
        name,
        report_key: params.report_key,
        kind,
        params,
        include_period: include ? include.checked : true,
        for_email: forEmail,
      }),
    });
    const data = await res.json().catch(() => ({}));
    alert(res.ok ? "View saved." : (data.error || "Save view failed (HTTP " + res.status + ")"));
    if (res.ok) closeOverlay("saveViewOverlay");
  });
  document.getElementById("savedViewsBtn").addEventListener("click", async () => {
    const params = collectParams();
    const res = await fetch("/api/views?report=" + encodeURIComponent(params.report_key));
    const data = await res.json().catch(() => ({}));
    const list = document.getElementById("savedViewsList");
    if (!res.ok) {
      list.textContent = data.error || "Could not load saved views (HTTP " + res.status + ")";
      openOverlay("savedViewsOverlay");
      return;
    }
    const views = data.views || [];
    if (!views.length) {
      list.textContent = "None yet. Save this view first.";
    } else {
      list.innerHTML = views.map((view) =>
        '<div class="recent-row"><a href="/reports/' + params.report_key + "?view=" + view.id + '">'
        + view.name + "</a> <span class='muted'>(" + view.kind + ")</span></div>"
      ).join("");
    }
    openOverlay("savedViewsOverlay");
  });
  document.getElementById("scheduleViewBtn").addEventListener("click", async () => {
    const params = collectParams();
    const res = await fetch("/api/views?report=" + encodeURIComponent(params.report_key));
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      alert(data.error || "Could not load views for schedule (HTTP " + res.status + ")");
      return;
    }
    if (!data.views || !data.views.length) {
      alert("Save a named view first, then Schedule.");
      return;
    }
    window.location.href = "/schedules?view=" + data.views[0].id;
  });
  const moreBtn = document.getElementById("moreBtn");
  const moreMenu = document.getElementById("moreMenu");
  if (moreBtn && moreMenu) {
    moreBtn.addEventListener("click", () => {
      moreMenu.hidden = !moreMenu.hidden;
      moreBtn.setAttribute("aria-expanded", moreMenu.hidden ? "false" : "true");
    });
  }
  const previewBtn = document.getElementById("previewBtn");
  if (previewBtn) {
    previewBtn.addEventListener("click", () => {
      const preview = document.getElementById("apiPreview");
      const wrap = document.getElementById("apiRunWrap");
      if (preview) {
        preview.hidden = false;
        preview.value = JSON.stringify(collectParams(), null, 2);
      }
      if (wrap) wrap.hidden = false;
    });
  }
  const apiRun = document.getElementById("apiRunBtn");
  if (apiRun) {
    apiRun.addEventListener("click", () => {
      const preview = document.getElementById("apiPreview");
      try {
        const body = JSON.parse(preview.value);
        runReport(body).catch(() => {});
      } catch (err) {
        setStatus("API body is not JSON (" + err.message + ").", false);
      }
    });
  }
  const refresh = document.getElementById("refreshBtn");
  if (refresh) {
    refresh.addEventListener("click", () => {
      runReport().catch(() => {});
    });
  }
  const resetLayout = document.getElementById("resetLayoutBtn");
  if (resetLayout) {
    resetLayout.addEventListener("click", () => {
      if (activeKey) showTab(activeKey);
    });
  }
  const groupBy = document.getElementById("groupBySelect");
  if (groupBy) {
    groupBy.addEventListener("change", () => {
      if (activeKey) showTab(activeKey);
    });
  }
  const columnsBtn = document.getElementById("columnsBtn");
  if (columnsBtn) {
    columnsBtn.addEventListener("click", () => {
      if (!table) {
        alert("Run the report first.");
        return;
      }
      const list = document.getElementById("columnsList");
      list.innerHTML = "<table class=\"simple-table\"><thead><tr><th>Column</th><th>Show</th><th>Freeze</th></tr></thead><tbody>"
        + table.getColumns().map((col) => {
          const field = col.getField();
          const title = col.getDefinition().title || field;
          const checked = col.isVisible() ? "checked" : "";
          const pinned = col.getDefinition().frozen ? "checked" : "";
          return "<tr><td>" + title + "</td>"
            + '<td><input type="checkbox" data-field="' + field + '" ' + checked + "></td>"
            + '<td><input type="checkbox" data-freeze="' + field + '" ' + pinned + "></td></tr>";
        }).join("")
        + "</tbody></table>";
      openOverlay("columnsOverlay");
      list.querySelectorAll("input[data-field]").forEach((box) => {
        box.addEventListener("change", () => {
          const col = table.getColumn(box.getAttribute("data-field"));
          if (!col) return;
          if (box.checked) col.show();
          else col.hide();
        });
      });
      list.querySelectorAll("input[data-freeze]").forEach((box) => {
        box.addEventListener("change", () => {
          frozenFields = new Set();
          list.querySelectorAll("input[data-freeze]").forEach((pin) => {
            if (pin.checked) frozenFields.add(pin.getAttribute("data-freeze"));
          });
          if (activeKey) showTab(activeKey);
        });
      });
    });
  }
  const help = document.getElementById("helpBtn");
  if (help) help.addEventListener("click", () => openOverlay("helpOverlay"));
  [
    ["helpClose", "helpOverlay"],
    ["columnsClose", "columnsOverlay"],
    ["columnsDone", "columnsOverlay"],
    ["savedViewsClose", "savedViewsOverlay"],
    ["saveViewClose", "saveViewOverlay"],
    ["saveViewCancel", "saveViewOverlay"],
    ["emailClose", "emailOverlay"],
    ["emailCancel", "emailOverlay"],
  ].forEach(([btnId, overlayId]) => {
    const btn = document.getElementById(btnId);
    if (btn) btn.addEventListener("click", () => closeOverlay(overlayId));
  });
  document.querySelectorAll(".help-btn[data-help]").forEach((btn) => {
    btn.addEventListener("click", () => openOverlay("helpOverlay"));
  });
  document.querySelectorAll(".modal-overlay").forEach((overlay) => {
    overlay.addEventListener("click", (evt) => {
      if (evt.target === overlay) overlay.hidden = true;
    });
  });
  runReport().catch(() => {});
});

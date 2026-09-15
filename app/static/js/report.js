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
  const customers = document.getElementById("customerSelect");
  if (customers) {
    params.customers = Array.from(customers.selectedOptions).map((opt) => opt.value);
  }
  params.report_key = controls.getAttribute("data-report-key");
  return params;
}

function columnsFromRows(rows) {
  const first = rows[0] || {};
  return Object.keys(first).map((field) => {
    const sample = first[field];
    const isNumber = typeof sample === "number";
    const moneyName = /total|amount|invoice|commission|percent|charge|sales|price|qty|open|ordered|fulfill/i.test(field)
      && !/count/i.test(field);
    return {
      title: field,
      field,
      hozAlign: isNumber ? "right" : "left",
      headerFilter: "input",
      formatter: isNumber && moneyName ? "money" : "plaintext",
    };
  });
}

let table = null;
let tabsByKey = {};
let activeKey = "";
let lastJobId = null;

function showCommissionCards(rows) {
  const wrap = document.getElementById("commissionCards");
  const grid = document.getElementById("reportTable");
  wrap.hidden = false;
  grid.style.display = "none";
  wrap.innerHTML = rows.map((row) => {
    const name = row.SalesmanName || row.Salesman || "";
    const pct = row.Percent != null ? Math.round(row.Percent * 1000) / 10 + "%" : "";
    const dollars = row.CommissionDollars != null ? row.CommissionDollars : "";
    return '<div class="settings-card"><h3>' + name + "</h3><p>" + pct + " · $" + dollars + "</p></div>";
  }).join("");
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
  grid.style.display = "";
  if (table) table.destroy();
  table = new Tabulator("#reportTable", {
    data: rows,
    layout: "fitDataStretch",
    placeholder: "No rows",
    columns: columnsFromRows(rows),
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

async function runReport() {
  const params = collectParams();
  const res = await fetch("/api/reports/" + params.report_key + "/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error("Could not load mock JSON");
  renderTabs(await res.json());
  const summary = document.getElementById("controlsSummary");
  if (summary && params.period) summary.textContent = params.period.replace(/_/g, " ");
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
  try {
    applySavedParams(JSON.parse(controls.getAttribute("data-view-params") || "{}"));
  } catch (_err) {
    /* ignore bad saved params */
  }
  document.getElementById("runBtn").addEventListener("click", () => {
    runReport().catch((err) => {
      document.getElementById("reportMeta").textContent = err.message;
      document.getElementById("reportSurface").hidden = false;
    });
  });
  document.getElementById("emailMeBtn").addEventListener("click", async () => {
    const params = collectParams();
    const res = await fetch("/api/reports/" + params.report_key + "/email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    const data = await res.json();
    alert(res.ok ? "Mock mail queued to " + data.recipients : (data.error || "Email failed"));
  });
  document.getElementById("exportBtn").addEventListener("click", (evt) => {
    evt.preventDefault();
    window.location.href = exportHref();
  });
  document.getElementById("keepBtn").addEventListener("click", async () => {
    if (!lastJobId) {
      alert("Run a report first.");
      return;
    }
    const name = prompt("Name this kept run", "Kept run");
    if (!name) return;
    await fetch("/api/jobs/" + lastJobId + "/keep", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    alert("Kept.");
  });
  document.getElementById("saveViewBtn").addEventListener("click", async () => {
    const name = prompt("Name this view");
    if (!name) return;
    const params = collectParams();
    const kind = document.body.dataset.canCompany === "1" && confirm("Save for Company? Cancel = just for me")
      ? "company"
      : "personal";
    await fetch("/api/views", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        report_key: params.report_key,
        kind,
        params,
        include_period: true,
      }),
    });
    alert("View saved.");
  });
  document.getElementById("savedViewsBtn").addEventListener("click", async () => {
    const params = collectParams();
    const res = await fetch("/api/views?report=" + encodeURIComponent(params.report_key));
    const data = await res.json();
    const names = (data.views || []).map((view) => view.id + ": " + view.name + " (" + view.kind + ")").join("\n");
    const picked = prompt("Open view id:\n" + (names || "(none)"));
    if (!picked) return;
    window.location.href = "/reports/" + params.report_key + "?view=" + encodeURIComponent(picked);
  });
  document.getElementById("scheduleViewBtn").addEventListener("click", async () => {
    const params = collectParams();
    const res = await fetch("/api/views?report=" + encodeURIComponent(params.report_key));
    const data = await res.json();
    if (!data.views || !data.views.length) {
      alert("Save a named view first, then Schedule.");
      return;
    }
    window.location.href = "/schedules?view=" + data.views[0].id;
  });
  const help = document.getElementById("helpBtn");
  if (help) {
    help.addEventListener("click", () => {
      document.getElementById("helpOverlay").style.display = "flex";
    });
  }
  runReport().catch((err) => {
    document.getElementById("reportMeta").textContent = err.message;
    document.getElementById("reportSurface").hidden = false;
  });
});

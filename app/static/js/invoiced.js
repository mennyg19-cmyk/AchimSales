const TAB_ORDER = [
  "summary_by_customer",
  "commissions",
  "full_details",
  "credits",
  "invoices",
];

let table = null;
let tabsByKey = {};
let activeKey = "";

function columnsFromRows(rows) {
  const first = rows[0] || {};
  return Object.keys(first).map((field) => {
    const sample = first[field];
    const isNumber = typeof sample === "number";
    const moneyName = /total|amount|invoice|commission|percent|charge/i.test(field)
      && !/count/i.test(field);
    return {
      title: field,
      field,
      hozAlign: isNumber ? "right" : "left",
      formatter: isNumber && moneyName ? "money" : "plaintext",
    };
  });
}

function showTab(key) {
  activeKey = key;
  const tab = tabsByKey[key];
  document.querySelectorAll(".report-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-key") === key);
  });
  const rows = (tab && tab.rows) || [];
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
  const keys = Object.keys(tabs).sort((a, b) => {
    const ia = TAB_ORDER.indexOf(a);
    const ib = TAB_ORDER.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
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
  meta.textContent = from && to ? from + " – " + to + " · mock data" : "mock data";
  document.getElementById("reportSurface").hidden = false;
  if (keys.length) showTab(keys[0]);
}

async function runReport() {
  const res = await fetch("/api/reports/invoiced/mock");
  if (!res.ok) throw new Error("Could not load mock Invoiced JSON");
  renderTabs(await res.json());
}

document.addEventListener("DOMContentLoaded", () => {
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
  document.getElementById("runBtn").addEventListener("click", () => {
    runReport().catch((err) => {
      document.getElementById("reportMeta").textContent = err.message;
    });
  });
  runReport().catch((err) => {
    document.getElementById("reportMeta").textContent = err.message;
  });
});

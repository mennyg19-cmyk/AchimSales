let table = null;
let tabsByKey = {};
let activeKey = "";
let tabViews = {};
let tabOrder = [];
let pendingActive = "";

function freshView() {
  return {
    hidden: new Set(),
    frozen: new Set(),
    order: null,
    sorters: null,
    columnFilters: {},
    group: [],
    groups_explicit: false,
    widths: {},
  };
}

function viewFor(key) {
  if (tabViews[key]) return tabViews[key];
  if (tabViews._default) {
    tabViews[key] = deserializeView(serializeView(tabViews._default));
    return tabViews[key];
  }
  tabViews[key] = freshView();
  return tabViews[key];
}

function serializeView(v) {
  return {
    hidden: [...v.hidden],
    frozen: [...v.frozen],
    order: v.order,
    sorters: v.sorters,
    columnFilters: v.columnFilters,
    group: v.group,
    groups_explicit: true,
    widths: v.widths,
  };
}

function deserializeView(o) {
  if (!o || typeof o !== "object") return freshView();
  let columnFilters = o.columnFilters || {};
  if (!o.columnFilters && Array.isArray(o.headerFilters)) {
    columnFilters = {};
    o.headerFilters.forEach((hf) => {
      if (hf && hf.field && String(hf.value || "").trim() !== "") {
        columnFilters[hf.field] = { op: "contains", v: String(hf.value), v2: "" };
      }
    });
  }
  return {
    hidden: new Set(o.hidden || []),
    frozen: new Set(o.frozen || []),
    order: o.order || null,
    sorters: o.sorters || null,
    columnFilters,
    group: Array.isArray(o.group) ? o.group.slice() : [],
    groups_explicit: !!o.groups_explicit || Array.isArray(o.group),
    widths: o.widths || {},
  };
}

const TEXT_OPS = [
  { op: "contains", label: "contains" },
  { op: "equals", label: "equals" },
  { op: "starts", label: "starts with" },
  { op: "ends", label: "ends with" },
  { op: "in", label: "is one of (comma-separated)" },
  { op: "empty", label: "is empty" },
  { op: "notEmpty", label: "is not empty" },
];
const NUM_OPS = [
  { op: "eq", label: "equals" },
  { op: "ne", label: "not equal to" },
  { op: "gt", label: "greater than" },
  { op: "ge", label: "greater than or equal" },
  { op: "lt", label: "less than" },
  { op: "le", label: "less than or equal" },
  { op: "between", label: "between" },
  { op: "empty", label: "is empty" },
  { op: "notEmpty", label: "is not empty" },
];
const DATE_OPS = [
  { op: "on", label: "on" },
  { op: "before", label: "before" },
  { op: "after", label: "after" },
  { op: "between", label: "between" },
  { op: "empty", label: "is empty" },
  { op: "notEmpty", label: "is not empty" },
];

function reportKey() {
  const data = (window._reportPayload && window._reportPayload.data) || {};
  if (data.report_key) return data.report_key;
  const el = document.getElementById("reportControls");
  return (el && el.getAttribute("data-report-key")) || "";
}

function columnSpec(field) {
  const cols = ((tabsByKey[activeKey] || {}).columns) || [];
  return cols.find((c) => c && c.field === field) || null;
}

function fieldType(field) {
  const spec = columnSpec(field);
  if (spec) {
    if (spec.type === "date") return "date";
    if (spec.type === "money" || spec.type === "int" || spec.type === "percent") return "number";
    return "text";
  }
  const rows = ((tabsByKey[activeKey] || {}).rows) || [];
  for (let i = 0; i < rows.length; i++) {
    const val = rows[i][field];
    if (val == null || val === "") continue;
    if (typeof val === "number") return "number";
    if (/^\d{4}-\d{2}-\d{2}/.test(String(val))) return "date";
    return "text";
  }
  return "text";
}

function operatorsFor(type) {
  if (type === "number") return NUM_OPS;
  if (type === "date") return DATE_OPS;
  return TEXT_OPS;
}

function opNeedsTwo(op) { return op === "between"; }
function opNeedsNone(op) { return op === "empty" || op === "notEmpty"; }

function filterArmed(f) {
  if (!f) return false;
  if (opNeedsNone(f.op)) return true;
  return String(f.v || "").trim() !== "";
}

function asNumber(x) {
  const s = String(x).replace(/[$,%\s]/g, "");
  if (s === "") return null;
  const n = Number(s);
  return isFinite(n) ? n : null;
}

function rowMatches(row, field, type, f) {
  const raw = row[field];
  if (f.op === "empty") return raw === "" || raw == null;
  if (f.op === "notEmpty") return !(raw === "" || raw == null);
  if (type === "number") {
    const x = asNumber(raw);
    const a = asNumber(f.v);
    if (x == null || a == null) return false;
    if (f.op === "eq") return x === a;
    if (f.op === "ne") return x !== a;
    if (f.op === "gt") return x > a;
    if (f.op === "ge") return x >= a;
    if (f.op === "lt") return x < a;
    if (f.op === "le") return x <= a;
    if (f.op === "between") {
      const b = asNumber(f.v2);
      return b == null ? x >= a : x >= a && x <= b;
    }
    return true;
  }
  if (type === "date") {
    const d = String(raw ?? "").slice(0, 10);
    const a = String(f.v ?? "").slice(0, 10);
    const b = String(f.v2 ?? "").slice(0, 10);
    if (f.op === "on") return d === a;
    if (f.op === "before") return !!d && d < a;
    if (f.op === "after") return !!d && d > a;
    if (f.op === "between") return (!a || d >= a) && (!b || d <= b);
    return true;
  }
  const s = String(raw ?? "").toLowerCase();
  const q = String(f.v ?? "").toLowerCase();
  if (f.op === "contains") return s.indexOf(q) !== -1;
  if (f.op === "equals") return s === q;
  if (f.op === "starts") return s.indexOf(q) === 0;
  if (f.op === "ends") return s.slice(-q.length) === q;
  if (f.op === "in") {
    return q.split(",").map((p) => p.trim()).filter(Boolean).indexOf(s) !== -1;
  }
  return s.indexOf(q) !== -1;
}

function armedFilters(v) {
  const out = [];
  Object.keys(v.columnFilters || {}).forEach((field) => {
    const f = v.columnFilters[field];
    if (filterArmed(f)) out.push({ field, type: fieldType(field), f });
  });
  return out;
}

function applyColumnFilters() {
  if (!table || !activeKey) return;
  const active = armedFilters(viewFor(activeKey));
  try {
    if (!active.length) table.clearFilter();
    else table.setFilter((row) => active.every((a) => rowMatches(row, a.field, a.type, a.f)));
  } catch (err) {
    /* table not ready */
  }
  updateFilterMarkers();
}

function updateFilterMarkers() {
  if (!table || !activeKey) return;
  const cf = viewFor(activeKey).columnFilters;
  table.getColumns().forEach((col) => {
    const el = col.getElement();
    if (!el) return;
    el.classList.toggle("has-col-filter", filterArmed(cf[col.getField()]));
  });
}

let colFilterPopover = null;
let colFilterClose = null;
function closeColumnFilterPopover() {
  if (colFilterPopover) colFilterPopover.remove();
  colFilterPopover = null;
  if (colFilterClose) {
    colFilterClose();
    colFilterClose = null;
  }
}

function openColumnFilterPopover(column) {
  closeColumnFilterPopover();
  if (!activeKey) return;
  const field = column.getField();
  const type = fieldType(field);
  const ops = operatorsFor(type);
  const cf = viewFor(activeKey).columnFilters;
  const current = cf[field] || { op: ops[0].op, v: "", v2: "" };
  const panel = document.createElement("div");
  panel.className = "col-filter-popover";
  const title = document.createElement("div");
  title.className = "col-filter-popover-title";
  title.textContent = (column.getDefinition() || {}).title || field;
  panel.appendChild(title);
  const opSel = document.createElement("select");
  ops.forEach((o) => {
    const opt = document.createElement("option");
    opt.value = o.op;
    opt.textContent = o.label;
    if (o.op === current.op) opt.selected = true;
    opSel.appendChild(opt);
  });
  panel.appendChild(opSel);
  const values = document.createElement("div");
  values.className = "cf-values";
  panel.appendChild(values);
  const inputType = type === "date" ? "date" : type === "number" ? "number" : "text";
  const v1 = document.createElement("input");
  v1.type = inputType;
  v1.value = current.v || "";
  const v2 = document.createElement("input");
  v2.type = inputType;
  v2.value = current.v2 || "";
  function syncValueInputs() {
    values.innerHTML = "";
    const op = opSel.value;
    if (opNeedsNone(op)) return;
    v1.placeholder = type === "text" && op === "in" ? "a, b, c" : "value";
    values.appendChild(v1);
    if (opNeedsTwo(op)) {
      v2.placeholder = "and";
      values.appendChild(v2);
    }
  }
  opSel.addEventListener("change", syncValueInputs);
  syncValueInputs();
  const foot = document.createElement("div");
  foot.className = "col-filter-popover-foot";
  const clear = document.createElement("button");
  clear.type = "button";
  clear.className = "btn btn-sm btn-outline";
  clear.textContent = "Clear";
  clear.addEventListener("click", () => {
    delete cf[field];
    applyColumnFilters();
    closeColumnFilterPopover();
  });
  const apply = document.createElement("button");
  apply.type = "button";
  apply.className = "btn btn-sm btn-primary";
  apply.textContent = "Apply";
  function doApply() {
    const op = opSel.value;
    if (opNeedsNone(op)) cf[field] = { op: op, v: "" };
    else if (v1.value.trim() === "") delete cf[field];
    else cf[field] = { op: op, v: v1.value.trim(), v2: opNeedsTwo(op) ? v2.value.trim() : "" };
    applyColumnFilters();
    closeColumnFilterPopover();
  }
  apply.addEventListener("click", doApply);
  [v1, v2].forEach((inp) => inp.addEventListener("keydown", (evt) => {
    if (evt.key === "Enter") doApply();
  }));
  foot.append(clear, apply);
  panel.appendChild(foot);
  const anchor = column.getElement();
  const r = anchor ? anchor.getBoundingClientRect() : { bottom: 80, left: 16 };
  panel.style.top = Math.round(r.bottom + 4) + "px";
  panel.style.left = Math.round(Math.min(r.left, window.innerWidth - 252)) + "px";
  document.body.appendChild(panel);
  colFilterPopover = panel;
  (opNeedsNone(opSel.value) ? opSel : v1).focus();
  setTimeout(() => {
    function onOut(evt) {
      if (colFilterPopover && !colFilterPopover.contains(evt.target)) closeColumnFilterPopover();
    }
    function onEsc(evt) {
      if (evt.key === "Escape") closeColumnFilterPopover();
    }
    document.addEventListener("click", onOut);
    document.addEventListener("keydown", onEsc);
    colFilterClose = function () {
      document.removeEventListener("click", onOut);
      document.removeEventListener("keydown", onEsc);
    };
  }, 0);
}

function headerMenu(key) {
  return [
    {
      label: "Filter this column",
      action: function (_e, column) {
        openColumnFilterPopover(column);
      },
    },
    {
      label: "Hide column",
      action: function (_e, column) {
        const field = column.getField();
        viewFor(key).hidden.add(field);
        column.hide();
      },
    },
    {
      label: "Freeze / unfreeze",
      action: function (_e, column) {
        const v = viewFor(key);
        const field = column.getField();
        if (v.frozen.has(field)) v.frozen.delete(field);
        else v.frozen.add(field);
        showTab(key);
      },
    },
    {
      label: "Group by this column",
      action: function (_e, column) {
        const v = viewFor(key);
        const field = column.getField();
        if (field) v.group = [field];
        v.groups_explicit = true;
        showTab(key);
      },
    },
    {
      label: "Add subgroup",
      action: function (_e, column) {
        const v = viewFor(key);
        const field = column.getField();
        if (field && v.group.indexOf(field) === -1) v.group.push(field);
        v.groups_explicit = true;
        showTab(key);
      },
    },
    {
      label: "Clear grouping",
      action: function () {
        const v = viewFor(key);
        v.group = [];
        v.groups_explicit = true;
        showTab(key);
      },
    },
  ];
}

function captureActive() {
  if (!table || !activeKey) return;
  const v = viewFor(activeKey);
  try {
    v.sorters = table.getSorters().map((s) => ({ column: s.field, dir: s.dir }));
    const cols = table.getColumns();
    v.order = cols.map((c) => c.getField()).filter(Boolean);
    v.hidden = new Set(cols.filter((c) => !c.isVisible()).map((c) => c.getField()));
    cols.forEach((c) => {
      const field = c.getField();
      const w = c.getWidth();
      if (field && w) v.widths[field] = w;
    });
    v.groups_explicit = true;
  } catch (err) {
    /* table not ready */
  }
}

function moneyParams(precision) {
  return { symbol: "$", precision: precision, thousand: ",", negativeSign: true };
}

function isoDate(value) {
  if (value == null || value === "") return "";
  if (value instanceof Date && !isNaN(value.getTime())) {
    const y = value.getUTCFullYear();
    const m = String(value.getUTCMonth() + 1).padStart(2, "0");
    const day = String(value.getUTCDate()).padStart(2, "0");
    return y + "-" + m + "-" + day;
  }
  const s = String(value).trim();
  if (!s) return "";
  const upper = s.toUpperCase();
  if (upper === "N/A" || upper === "NA" || upper === "NONE" || s === "-") return s;
  const iso = s.match(/^(\d{4}-\d{2}-\d{2})/);
  if (iso) return iso[1];
  const parsed = Date.parse(s);
  if (!isNaN(parsed)) {
    const d = new Date(parsed);
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, "0");
    const day = String(d.getUTCDate()).padStart(2, "0");
    return y + "-" + m + "-" + day;
  }
  return s;
}

function fulfillmentFillCss(score) {
  const s = Math.max(0, Math.min(1, score));
  const red = [255, 199, 206];
  const yellow = [255, 235, 156];
  const green = [198, 239, 206];
  let rgb;
  if (s <= 0) rgb = red;
  else if (s >= 1) rgb = green;
  else if (s < 0.5) {
    const t = s * 2;
    rgb = red.map((x, i) => Math.round(x + (yellow[i] - x) * t));
  } else {
    const t = (s - 0.5) * 2;
    rgb = yellow.map((x, i) => Math.round(x + (green[i] - x) * t));
  }
  return "rgb(" + rgb[0] + ", " + rgb[1] + ", " + rgb[2] + ")";
}

function isFulfillmentField(field) {
  return /fulfillment/i.test(String(field || "").replace(/[^a-z0-9%]/gi, ""));
}

function percentParts(raw) {
  const n = Number(raw);
  if (!isFinite(n) || raw === "" || raw == null) return null;
  const score = Math.abs(n) <= 1 ? n : n / 100;
  const text = (score * 100).toFixed(1) + "%";
  return { n: n, score: score, text: text };
}

function formatMoneyText(raw) {
  const n = Number(raw);
  if (!isFinite(n) || raw === "" || raw == null) return "";
  return n.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function salesmanBandIndex(col, colIndex) {
  if (typeof col.band === "number" && isFinite(col.band)) {
    return Math.min(Math.max(Math.trunc(col.band), 0), 2);
  }
  if (reportKey() === "salesman" && colIndex >= 4) {
    return Math.min(Math.floor((colIndex - 4) / 4), 2);
  }
  return -1;
}

function formatterFor(col, colIndex) {
  const band = salesmanBandIndex(col, colIndex);
  const bandColor = band === 0 ? "#0000CC" : band === 1 ? "#008000" : band === 2 ? "#800080" : null;
  switch (col.type) {
    case "money": {
      if (!bandColor) {
        return {
          formatter: "money",
          formatterParams: moneyParams(2),
          sorter: "number",
          hozAlign: "right",
        };
      }
      return {
        sorter: "number",
        hozAlign: "right",
        formatter: function (cell) {
          const text = formatMoneyText(cell.getValue());
          const n = Number(cell.getValue());
          const color = isFinite(n) && n < 0 ? "#FF0000" : bandColor;
          return color && text ? '<span style="color:' + color + '">' + text + "</span>" : text;
        },
      };
    }
    case "int":
      return {
        formatter: "money",
        formatterParams: { symbol: "", precision: 0, thousand: ",", negativeSign: true },
        sorter: "number",
        hozAlign: "right",
      };
    case "percent":
      return {
        sorter: "number",
        hozAlign: "right",
        formatter: function (cell) {
          const parts = percentParts(cell.getValue());
          const text = parts ? parts.text : "";
          const color = parts && parts.n < 0 ? "#FF0000" : bandColor;
          const inner = color && text ? '<span style="color:' + color + '">' + text + "</span>" : text;
          if (parts && isFulfillmentField(col.field)) {
            return '<span style="display:block;background:' + fulfillmentFillCss(parts.score) + ';margin:-8px;padding:8px">' + inner + "</span>";
          }
          return inner;
        },
      };
    case "date":
      return {
        sorter: "string",
        formatter: function (cell) { return isoDate(cell.getValue()); },
      };
    default:
      return { sorter: "string", formatter: "plaintext" };
  }
}

function canSumColumn(col) {
  if (col.sum === false) return false;
  if (col.field === "Net Price") return false;
  return col.type === "money" || col.type === "int";
}

function typedColumns(rows, tab, v, key) {
  const specs = Array.isArray(tab && tab.columns) ? tab.columns.slice() : [];
  const first = rows[0] || {};
  let fields = specs.map((c) => c.field).filter(Boolean);
  Object.keys(first).forEach((field) => {
    if (fields.indexOf(field) === -1) fields.push(field);
  });
  if (v.order && v.order.length) {
    const saved = v.order.filter((f) => fields.indexOf(f) !== -1);
    const savedSet = new Set(saved);
    fields = saved.concat(fields.filter((f) => !savedSet.has(f)));
  }
  const byField = {};
  specs.forEach((c) => { if (c && c.field) byField[c.field] = c; });
  return fields.map((field, idx) => {
    const col = byField[field] || { field: field, header: field, type: "text" };
    const fmt = formatterFor(col, idx);
    const frozen = v.frozen.size ? v.frozen.has(field) : idx === 0;
    const def = {
      title: col.header || field,
      field: field,
      visible: !v.hidden.has(field),
      frozen: frozen,
      width: v.widths[field],
      headerMenu: headerMenu(key),
      headerMenuIcon: "⋮",
      hozAlign: fmt.hozAlign || "left",
      sorter: fmt.sorter,
      formatter: fmt.formatter,
      formatterParams: fmt.formatterParams,
      bottomCalc: canSumColumn(col) ? "sum" : undefined,
    };
    if (col.type === "money") {
      def.bottomCalcFormatter = "money";
      def.bottomCalcFormatterParams = moneyParams(2);
    } else if (col.type === "int") {
      def.bottomCalcFormatter = "money";
      def.bottomCalcFormatterParams = { symbol: "", precision: 0, thousand: "," };
    }
    return def;
  });
}

function renderGroupPills(group, columns) {
  const host = document.getElementById("groupPills");
  if (!host) return;
  if (!group || !group.length) {
    host.hidden = true;
    host.innerHTML = "";
    return;
  }
  host.hidden = false;
  host.innerHTML = group.map((field) => {
    const title = (columns.find((c) => c.field === field) || {}).title || field;
    return '<span class="group-pill"><span>' + title + "</span>"
      + '<button type="button" class="group-pill-x" data-group-field="' + field + '" title="Remove this group">×</button></span>';
  }).join("");
  host.querySelectorAll("[data-group-field]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const v = viewFor(activeKey);
      v.group = v.group.filter((f) => f !== btn.getAttribute("data-group-field"));
      v.groups_explicit = true;
      showTab(activeKey);
    });
  });
}

let tableBuilding = false;

function showTab(key) {
  if (tableBuilding) return;
  if (activeKey && activeKey !== key) captureActive();
  activeKey = key;
  const tab = tabsByKey[key];
  document.querySelectorAll(".report-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-key") === key);
  });
  const rows = (tab && tab.rows) || [];
  const wrap = document.getElementById("commissionCards");
  const grid = document.getElementById("reportTable");
  if (key === "commissions") {
    if (table) {
      try { table.destroy(); } catch (err) { /* already gone */ }
      table = null;
    }
    wrap.hidden = false;
    grid.hidden = true;
    wrap.innerHTML = rows.map((row) => {
      const name = row.SalesmanName || row.Salesman || "";
      const pctParts = percentParts(row.Percent != null ? row.Percent : row["Commission %"]);
      const pct = pctParts ? pctParts.text : "";
      const dollars = formatMoneyText(row.CommissionDollars != null ? row.CommissionDollars : row.YTDCommission);
      return '<div class="settings-card"><h3>' + name + "</h3><p>" + pct + (dollars ? " · " + dollars : "") + "</p></div>";
    }).join("");
    return;
  }
  wrap.hidden = true;
  grid.hidden = false;
  if (table) {
    try { table.destroy(); } catch (err) { /* already gone */ }
    table = null;
  }
  closeColumnFilterPopover();
  const v = viewFor(key);
  const columns = typedColumns(rows, tab, v, key);
  renderGroupPills(v.group, columns);
  tableBuilding = true;
  try {
    table = new Tabulator("#reportTable", {
      data: rows,
      layout: "fitData",
      placeholder: "No rows",
      movableColumns: true,
      renderHorizontal: "virtual",
      groupBy: v.group.length ? v.group : false,
      initialSort: (v.sorters || []).filter((s) => s && s.column).map((s) => ({ column: s.column, dir: s.dir })),
      columns,
    });
    table.on("tableBuilt", () => {
      tableBuilding = false;
      applyColumnFilters();
    });
  } catch (err) {
    tableBuilding = false;
    throw err;
  }
}

function tabKeys(tabs) {
  const keys = Object.keys(tabs);
  const ordered = tabOrder.filter((key) => tabs[key]);
  if (!ordered.length) return keys;
  return ordered.concat(keys.filter((key) => ordered.indexOf(key) === -1));
}

function renderTabs(payload) {
  window._reportPayload = payload;
  const data = payload.data || {};
  const tabs = data.tabs || {};
  tabsByKey = tabs;
  const keys = tabKeys(tabs);
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
  const start = (pendingActive && tabs[pendingActive]) ? pendingActive : keys[0];
  pendingActive = "";
  if (start) showTab(start);
}

function serializeLayout() {
  captureActive();
  const views = {};
  Object.keys(tabViews).forEach((key) => {
    views[key] = serializeView(tabViews[key]);
  });
  return {
    active: activeKey,
    order: tabOrder.length ? tabOrder : Object.keys(tabsByKey),
    clones: [],
    views,
  };
}

function preloadLayout(layout) {
  if (!layout || typeof layout !== "object") return;
  if (layout.views && typeof layout.views === "object") {
    Object.keys(layout.views).forEach((key) => {
      tabViews[key] = deserializeView(layout.views[key]);
    });
  }
  tabOrder = Array.isArray(layout.order) ? layout.order.slice() : [];
  pendingActive = layout.active || "";
}

function resetLayout() {
  tabViews = {};
  tabOrder = [];
  pendingActive = "";
  if (activeKey) showTab(activeKey);
}

function setColumnVisible(field, visible) {
  if (!table) return;
  const col = table.getColumn(field);
  if (!col) return;
  const v = viewFor(activeKey);
  if (visible) {
    col.show();
    v.hidden.delete(field);
  } else {
    col.hide();
    v.hidden.add(field);
  }
}

function setFrozen(field, frozen) {
  const v = viewFor(activeKey);
  if (!v.frozen.size && table) {
    table.getColumns().forEach((col) => {
      if (col.getDefinition().frozen && col.getField()) v.frozen.add(col.getField());
    });
  }
  if (frozen) v.frozen.add(field);
  else v.frozen.delete(field);
  if (activeKey) showTab(activeKey);
}

function initGrid() {}

window.ReportGrid = {
  renderTabs,
  serializeLayout,
  preloadLayout,
  resetLayout,
  getTable: function () { return table; },
  setColumnVisible,
  setFrozen,
  init: initGrid,
};

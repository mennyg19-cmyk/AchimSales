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

function fieldType(field) {
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

function columnsFromRows(rows, v, key) {
  const first = rows[0] || {};
  let fields = Object.keys(first);
  if (v.order && v.order.length) {
    const saved = v.order.filter((f) => fields.indexOf(f) !== -1);
    const savedSet = new Set(saved);
    fields = saved.concat(fields.filter((f) => !savedSet.has(f)));
  }
  return fields.map((field, idx) => {
    const sample = first[field];
    const isNumber = typeof sample === "number";
    const moneyName = /total|amount|invoice|commission|percent|charge|sales|price|qty|open|ordered|fulfill/i.test(field)
      && !/count/i.test(field);
    const frozen = v.frozen.size ? v.frozen.has(field) : idx === 0;
    return {
      title: field,
      field,
      visible: !v.hidden.has(field),
      frozen,
      width: v.widths[field],
      hozAlign: isNumber ? "right" : "left",
      headerMenu: headerMenu(key),
      formatter: isNumber && moneyName ? "money" : "plaintext",
      bottomCalc: isNumber ? "sum" : undefined,
    };
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

function showTab(key) {
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
    wrap.hidden = false;
    grid.hidden = true;
    wrap.innerHTML = rows.map((row) => {
      const name = row.SalesmanName || row.Salesman || "";
      const pct = row.Percent != null ? Math.round(row.Percent * 1000) / 10 + "%" : "";
      const dollars = row.CommissionDollars != null ? row.CommissionDollars : "";
      return '<div class="settings-card"><h3>' + name + "</h3><p>" + pct + " · $" + dollars + "</p></div>";
    }).join("");
    return;
  }
  wrap.hidden = true;
  grid.hidden = false;
  if (table) table.destroy();
  closeColumnFilterPopover();
  const v = viewFor(key);
  const columns = columnsFromRows(rows, v, key);
  renderGroupPills(v.group, columns);
  table = new Tabulator("#reportTable", {
    data: rows,
    layout: "fitDataStretch",
    placeholder: "No rows",
    movableColumns: true,
    groupBy: v.group.length ? v.group : false,
    initialSort: (v.sorters || []).filter((s) => s && s.column).map((s) => ({ column: s.column, dir: s.dir })),
    columns,
  });
  table.on("tableBuilt", () => applyColumnFilters());
}

function tabKeys(tabs) {
  const keys = Object.keys(tabs);
  const ordered = tabOrder.filter((key) => tabs[key]);
  if (!ordered.length) return keys;
  return ordered.concat(keys.filter((key) => ordered.indexOf(key) === -1));
}

function renderTabs(payload) {
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

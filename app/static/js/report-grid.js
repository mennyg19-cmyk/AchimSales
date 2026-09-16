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

function headerMenu(key) {
  return [
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
    const filters = {};
    (table.getHeaderFilters() || []).forEach((hf) => {
      if (hf.field && String(hf.value || "").trim() !== "") {
        filters[hf.field] = { op: "contains", v: String(hf.value), v2: "" };
      }
    });
    v.columnFilters = filters;
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
      headerFilter: "input",
      headerMenu: headerMenu(key),
      formatter: isNumber && moneyName ? "money" : "plaintext",
      bottomCalc: isNumber ? "sum" : undefined,
    };
  });
}

function fillGroupBy(columns, group) {
  const wrap = document.getElementById("groupByWrap");
  const select = document.getElementById("groupBySelect");
  if (!wrap || !select) return;
  wrap.hidden = false;
  select.innerHTML = '<option value="">None</option>';
  columns.forEach((col) => {
    const opt = document.createElement("option");
    opt.value = col.field;
    opt.textContent = col.title;
    select.appendChild(opt);
  });
  select.value = (group && group[0]) || "";
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
  const v = viewFor(key);
  const columns = columnsFromRows(rows, v, key);
  fillGroupBy(columns, v.group);
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
  table.on("tableBuilt", () => {
    Object.keys(v.columnFilters || {}).forEach((field) => {
      const spec = v.columnFilters[field];
      if (spec && spec.v) table.setHeaderFilterValue(field, spec.v);
    });
  });
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

function initGrid() {
  const groupBy = document.getElementById("groupBySelect");
  if (groupBy) {
    groupBy.addEventListener("change", () => {
      if (!activeKey) return;
      const v = viewFor(activeKey);
      v.group = groupBy.value ? [groupBy.value] : [];
      v.groups_explicit = true;
      showTab(activeKey);
    });
  }
}

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

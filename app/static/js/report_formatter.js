const NEW_FORMAT = "__new__";
const FILTER_OPS = [
  { value: "contains", label: "contains" },
  { value: "equals", label: "equals" },
  { value: "starts", label: "starts with" },
  { value: "ends", label: "ends with" },
  { value: "empty", label: "is empty" },
  { value: "notEmpty", label: "is not empty" },
  { value: "gt", label: ">" },
  { value: "lt", label: "<" },
  { value: "between", label: "between" },
];

let filling = false;
let tabs = [];
let active = "";
let sheets = {};
let baseline = {};
let trayFor = "";
let dragField = "";

function root() {
  return document.getElementById("fmtRoot");
}
function attr(name) {
  return (root() && root().getAttribute(name)) || "";
}
function msg(text) {
  const el = document.getElementById("fmtMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
}
function blankLevel(kind) {
  return { kind: kind || "sort", column: "", dir: "asc", op: "contains", v: "", v2: "" };
}
function labelOf(col) {
  if (!col) return "a column";
  return col.header && col.header !== col.field ? col.header : (col.field || "a column");
}
function orderColumns(columns, savedOrder) {
  const list = columns || [];
  const by = {};
  list.forEach((col) => { by[col.field] = col; });
  const out = [];
  const seen = {};
  (savedOrder || []).forEach((field) => {
    const col = by[String(field)];
    if (col && !seen[col.field]) {
      out.push(col);
      seen[col.field] = true;
    }
  });
  list.forEach((col) => {
    if (!seen[col.field]) out.push(col);
  });
  return out;
}
function sheetFrom(view, order, key, columns) {
  const levels = [];
  const group = view && view.group;
  if (Array.isArray(group)) {
    group.forEach((column) => levels.push(Object.assign(blankLevel("group"), { column: column })));
  }
  ((view && view.sorters) || []).forEach((sorter) => {
    levels.push(Object.assign(blankLevel("sort"), {
      column: sorter.column || "",
      dir: sorter.dir === "desc" ? "desc" : "asc",
    }));
  });
  Object.entries((view && view.columnFilters) || {}).forEach(([column, spec]) => {
    levels.push(Object.assign(blankLevel("filter"), {
      column: column,
      op: spec.op || "contains",
      v: spec.v || "",
      v2: spec.v2 || "",
    }));
  });
  const hidden = Array.isArray(view && view.hidden) ? view.hidden.map(String) : [];
  const showTab = !order || order.indexOf(key) !== -1;
  const cols = orderColumns(columns, view && view.order);
  return { flat: Array.isArray(group) && group.length === 0, showTab: showTab, hidden: hidden, levels: levels, cols: cols };
}
function remember() {
  baseline = JSON.parse(JSON.stringify(sheets));
}
function levelSig(level) {
  return [level.kind, level.column, level.dir, level.op, level.v, level.v2].join("\u0001");
}
function levelLabel(sheet, level) {
  const col = (sheet.cols || []).find((item) => item.field === level.column);
  const name = level.column ? labelOf(col || { field: level.column, header: level.column }) : "a column";
  if (level.kind === "group") return "Group by " + name;
  if (level.kind === "filter") {
    const value = level.v ? " " + level.v : "";
    return "Filter " + name + " " + (level.op || "contains") + value;
  }
  return "Sort by " + name + (level.dir === "desc" ? " descending" : " ascending");
}
function changesFor(key) {
  const now = sheets[key];
  const was = baseline[key];
  if (!now || !was) return [];
  const lines = [];
  if (!!now.showTab !== !!was.showTab) lines.push(now.showTab ? "Show this tab" : "Hide this tab");
  if (!!now.flat !== !!was.flat) lines.push(now.flat ? "Flat list on" : "Flat list off");
  const wasHidden = {};
  (was.hidden || []).forEach((field) => { wasHidden[field] = true; });
  const nowHidden = {};
  (now.hidden || []).forEach((field) => { nowHidden[field] = true; });
  const names = {};
  (was.cols || []).concat(now.cols || []).forEach((col) => { names[col.field] = labelOf(col); });
  Object.keys(names).forEach((field) => {
    if (!!nowHidden[field] !== !!wasHidden[field]) {
      lines.push((nowHidden[field] ? "Hide " : "Show ") + names[field]);
    }
  });
  const wasAt = {};
  (was.cols || []).forEach((col, index) => { wasAt[col.field] = index; });
  (now.cols || []).forEach((col, index) => {
    const from = wasAt[col.field];
    if (from === undefined || from === index) return;
    lines.push("Moved " + (names[col.field] || col.field) + " from " + (from + 1) + " to " + (index + 1));
  });
  const a = was.levels || [];
  const b = now.levels || [];
  const count = Math.max(a.length, b.length);
  for (let i = 0; i < count; i++) {
    if (!a[i]) lines.push("Added " + levelLabel(now, b[i]));
    else if (!b[i]) lines.push("Removed " + levelLabel(was, a[i]));
    else if (levelSig(a[i]) !== levelSig(b[i])) lines.push(levelLabel(was, a[i]) + " → " + levelLabel(now, b[i]));
  }
  return lines;
}
function newNamePending() {
  const sel = document.getElementById("fmtName");
  if (!sel || sel.value !== NEW_FORMAT) return false;
  const input = document.getElementById("fmtNew");
  return !!(input && input.value.trim());
}
function changeTotal() {
  return tabs.reduce((sum, tab) => sum + changesFor(tab.key).length, 0);
}

function option(value, label, selected) {
  const opt = document.createElement("option");
  opt.value = value;
  opt.textContent = label;
  opt.selected = value === selected;
  return opt;
}

function columnSelect(columns, selected) {
  const sel = document.createElement("select");
  sel.className = "fmt-col";
  sel.setAttribute("aria-label", "Column");
  sel.appendChild(option("", "Column", selected));
  const seen = {};
  columns.forEach((col) => {
    seen[col.field] = true;
    sel.appendChild(option(col.field, labelOf(col), selected));
  });
  if (selected && !seen[selected]) sel.appendChild(option(selected, selected, selected));
  sel.value = selected;
  return sel;
}

function capture() {
  if (!active || !sheets[active]) return;
  const levels = [];
  document.querySelectorAll("#fmtRows .fmt-level").forEach((row) => {
    const kindEl = row.querySelector(".fmt-kind");
    const colEl = row.querySelector(".fmt-col");
    const dirEl = row.querySelector(".fmt-dir");
    const opEl = row.querySelector(".fmt-op");
    const vEl = row.querySelector(".fmt-v");
    const v2El = row.querySelector(".fmt-v2");
    levels.push({
      kind: (kindEl && kindEl.value) || "sort",
      column: (colEl && colEl.value) || "",
      dir: (dirEl && dirEl.value) || "asc",
      op: (opEl && opEl.value) || "contains",
      v: (vEl && vEl.value) || "",
      v2: (v2El && v2El.value) || "",
    });
  });
  const hidden = [];
  const cols = [];
  document.querySelectorAll("#fmtCols .fmt-col-row").forEach((row) => {
    const box = row.querySelector("input[data-field]");
    const field = box && box.dataset.field;
    if (!field) return;
    const name = row.querySelector(".fmt-col-name");
    cols.push({ field: field, header: (name && name.textContent) || field });
    if (!box.checked) hidden.push(field);
  });
  const show = document.getElementById("fmtShowTab");
  const flat = document.getElementById("fmtFlat");
  const prev = sheets[active];
  sheets[active] = {
    flat: !!(flat && flat.checked),
    showTab: show ? show.checked : true,
    hidden: cols.length ? hidden : (prev.hidden || []),
    levels: document.getElementById("fmtRows") ? levels : (prev.levels || []),
    cols: cols.length ? cols : (prev.cols || []),
  };
}

function moveCol(index, delta) {
  capture();
  const cols = sheets[active].cols;
  const next = index + delta;
  if (!cols || next < 0 || next >= cols.length) return;
  const row = cols.splice(index, 1)[0];
  cols.splice(next, 0, row);
  renderRows();
}

function renderColumns(sheet) {
  const host = document.getElementById("fmtCols");
  if (!host) return;
  host.replaceChildren();
  const hidden = {};
  (sheet.hidden || []).forEach((field) => { hidden[field] = true; });
  (sheet.cols || []).forEach((col, index) => {
    const row = document.createElement("div");
    row.className = "fmt-col-row";
    const grip = document.createElement("span");
    grip.className = "fmt-grip";
    grip.draggable = true;
    grip.textContent = "⋮⋮";
    grip.title = "Drag to reorder";
    grip.setAttribute("aria-hidden", "true");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.dataset.field = col.field;
    box.checked = !hidden[col.field];
    box.setAttribute("aria-label", "Show " + labelOf(col));
    box.addEventListener("change", () => refreshChrome());
    const text = document.createElement("span");
    text.className = "fmt-col-name";
    text.textContent = labelOf(col);
    const actions = document.createElement("div");
    actions.className = "fmt-row-actions";
    const up = document.createElement("button");
    up.type = "button";
    up.className = "btn btn-outline btn-sm";
    up.textContent = "↑";
    up.setAttribute("aria-label", "Move column up");
    up.disabled = index === 0;
    up.addEventListener("click", () => moveCol(index, -1));
    const down = document.createElement("button");
    down.type = "button";
    down.className = "btn btn-outline btn-sm";
    down.textContent = "↓";
    down.setAttribute("aria-label", "Move column down");
    down.disabled = index === sheet.cols.length - 1;
    down.addEventListener("click", () => moveCol(index, 1));
    grip.addEventListener("dragstart", (ev) => {
      dragField = col.field;
      row.classList.add("is-dragging");
      if (ev.dataTransfer) {
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", col.field);
      }
    });
    grip.addEventListener("dragend", () => row.classList.remove("is-dragging"));
    row.addEventListener("dragover", (ev) => {
      ev.preventDefault();
      row.classList.add("is-over");
    });
    row.addEventListener("dragleave", () => row.classList.remove("is-over"));
    row.addEventListener("drop", (ev) => {
      ev.preventDefault();
      row.classList.remove("is-over");
      const from = dragField || (ev.dataTransfer && ev.dataTransfer.getData("text/plain"));
      if (!from || from === col.field) return;
      capture();
      const list = sheets[active].cols || [];
      const fromIdx = list.findIndex((item) => item.field === from);
      const toIdx = list.findIndex((item) => item.field === col.field);
      if (fromIdx < 0 || toIdx < 0) return;
      const moved = list.splice(fromIdx, 1)[0];
      list.splice(toIdx, 0, moved);
      renderRows();
    });
    actions.append(up, down);
    row.append(grip, box, text, actions);
    host.appendChild(row);
  });
}

function renderRows() {
  const body = document.getElementById("fmtRows");
  const tab = tabs.find((item) => item.key === active);
  const sheet = sheets[active] || { flat: false, showTab: true, hidden: [], levels: [], cols: [] };
  const flat = document.getElementById("fmtFlat");
  const show = document.getElementById("fmtShowTab");
  if (!body || !tab) return;
  if (flat) flat.checked = sheet.flat;
  if (show) show.checked = sheet.showTab;
  renderColumns(sheet);
  body.replaceChildren();
  const columns = sheet.cols && sheet.cols.length ? sheet.cols : tab.columns;
  sheet.levels.forEach((level, index) => {
    const tr = document.createElement("div");
    tr.className = "fmt-level";
    const kind = document.createElement("select");
    kind.className = "fmt-kind";
    kind.setAttribute("aria-label", "Level type");
    kind.appendChild(option("sort", "Sort by", level.kind));
    kind.appendChild(option("group", "Group by", level.kind));
    kind.appendChild(option("filter", "Filter by", level.kind));
    kind.value = level.kind;
    kind.addEventListener("change", () => {
      capture();
      sheets[active].levels[index].kind = kind.value;
      renderRows();
    });
    tr.appendChild(kind);

    const col = columnSelect(columns, level.column);
    col.addEventListener("change", () => refreshChrome());
    tr.appendChild(col);

    const extraBox = document.createElement("div");
    extraBox.className = "fmt-extra";
    if (level.kind === "sort") {
      const dir = document.createElement("select");
      dir.className = "fmt-dir";
      dir.setAttribute("aria-label", "Order");
      dir.appendChild(option("asc", "Ascending", level.dir));
      dir.appendChild(option("desc", "Descending", level.dir));
      dir.value = level.dir;
      dir.addEventListener("change", () => refreshChrome());
      extraBox.appendChild(dir);
    } else if (level.kind === "filter") {
      const op = document.createElement("select");
      op.className = "fmt-op";
      op.setAttribute("aria-label", "Filter");
      FILTER_OPS.forEach((item) => op.appendChild(option(item.value, item.label, level.op)));
      op.value = FILTER_OPS.some((item) => item.value === level.op) ? level.op : "contains";
      extraBox.appendChild(op);
      const needsValue = op.value !== "empty" && op.value !== "notEmpty";
      if (needsValue) {
        const value = document.createElement("input");
        value.className = "fmt-v";
        value.value = level.v;
        value.placeholder = "Value";
        value.setAttribute("aria-label", "Filter value");
        value.addEventListener("input", () => refreshChrome());
        extraBox.appendChild(value);
      }
      if (op.value === "between") {
        const value2 = document.createElement("input");
        value2.className = "fmt-v2";
        value2.value = level.v2;
        value2.placeholder = "And";
        value2.setAttribute("aria-label", "Filter end value");
        value2.addEventListener("input", () => refreshChrome());
        extraBox.appendChild(value2);
      }
      op.addEventListener("change", () => {
        capture();
        renderRows();
      });
    }
    tr.appendChild(extraBox);

    const actions = document.createElement("div");
    actions.className = "fmt-row-actions";
    const up = document.createElement("button");
    up.type = "button";
    up.className = "btn btn-outline btn-sm";
    up.textContent = "↑";
    up.setAttribute("aria-label", "Move level up");
    up.disabled = index === 0;
    up.addEventListener("click", () => move(index, -1));
    const down = document.createElement("button");
    down.type = "button";
    down.className = "btn btn-outline btn-sm";
    down.textContent = "↓";
    down.setAttribute("aria-label", "Move level down");
    down.disabled = index === sheet.levels.length - 1;
    down.addEventListener("click", () => move(index, 1));
    const del = document.createElement("button");
    del.type = "button";
    del.className = "btn btn-outline btn-sm";
    del.textContent = "Delete";
    del.addEventListener("click", () => {
      capture();
      sheets[active].levels.splice(index, 1);
      renderRows();
    });
    actions.append(up, down, del);
    tr.appendChild(actions);
    body.appendChild(tr);
  });
  refreshChrome();
}

function move(index, delta) {
  capture();
  const levels = sheets[active].levels;
  const next = index + delta;
  if (next < 0 || next >= levels.length) return;
  const row = levels.splice(index, 1)[0];
  levels.splice(next, 0, row);
  renderRows();
}

function closeTray() {
  trayFor = "";
  const tray = document.getElementById("fmtChangeTray");
  if (tray) tray.hidden = true;
}

function openTray(key) {
  const tray = document.getElementById("fmtChangeTray");
  const list = document.getElementById("fmtChangeList");
  const title = document.getElementById("fmtTrayTitle");
  const tab = tabs.find((item) => item.key === key);
  if (!tray || !list) return;
  const lines = changesFor(key);
  if (!lines.length) {
    closeTray();
    return;
  }
  trayFor = key;
  if (title) title.textContent = (tab ? tab.name : "Tab") + " changes";
  list.replaceChildren();
  lines.forEach((text) => {
    const li = document.createElement("li");
    li.textContent = text;
    list.appendChild(li);
  });
  tray.hidden = false;
}

function syncSave() {
  const save = document.getElementById("fmtSave");
  if (!save) return;
  save.disabled = changeTotal() === 0 && !newNamePending();
}

function refreshChrome() {
  if (active) capture();
  syncSave();
  renderTabs();
  if (trayFor) openTray(trayFor);
}

function renderTabs() {
  const host = document.getElementById("fmtTabs");
  if (!host) return;
  host.replaceChildren();
  tabs.forEach((tab) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "report-tab" + (tab.key === active ? " active" : "");
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", tab.key === active ? "true" : "false");
    const label = document.createElement("span");
    label.textContent = tab.name;
    btn.appendChild(label);
    const count = changesFor(tab.key).length;
    if (count) {
      const badge = document.createElement("span");
      badge.className = "fmt-tab-count";
      badge.textContent = String(count);
      badge.setAttribute("role", "button");
      badge.setAttribute("aria-label", count + " changes on " + tab.name);
      badge.addEventListener("click", (ev) => {
        ev.stopPropagation();
        capture();
        active = tab.key;
        trayFor = tab.key;
        renderRows();
      });
      btn.appendChild(badge);
    }
    btn.addEventListener("click", () => {
      capture();
      active = tab.key;
      closeTray();
      renderRows();
    });
    host.appendChild(btn);
  });
}

function payloadTabs() {
  capture();
  return tabs.map((tab) => {
    const sheet = sheets[tab.key] || { flat: false, showTab: true, hidden: [], levels: [], cols: [] };
    const group = sheet.levels.filter((level) => level.kind === "group" && level.column).map((level) => level.column);
    const sorters = sheet.levels.filter((level) => level.kind === "sort" && level.column).map((level) => ({
      column: level.column, dir: level.dir,
    }));
    const filters = sheet.levels.filter((level) => level.kind === "filter" && level.column).map((level) => ({
      column: level.column, op: level.op, v: level.v, v2: level.v2,
    }));
    return {
      key: tab.key,
      show_tab: sheet.showTab,
      hidden: sheet.hidden,
      column_order: (sheet.cols || []).map((col) => col.field),
      set_group: sheet.flat || group.length > 0,
      group: sheet.flat ? [] : group,
      sorters: sorters,
      filters: filters,
    };
  });
}

function syncNew() {
  const sel = document.getElementById("fmtName");
  const wrap = document.getElementById("fmtNewWrap");
  if (wrap) wrap.hidden = !sel || sel.value !== NEW_FORMAT;
}

function fillFormats(formats, selected) {
  const sel = document.getElementById("fmtName");
  if (!sel) return;
  filling = true;
  sel.replaceChildren();
  const seen = {};
  (formats || []).forEach((row) => {
    if (!row.id || seen[row.id]) return;
    seen[row.id] = true;
    sel.appendChild(option(row.id, row.label, selected));
  });
  if (!seen.default) sel.insertBefore(option("default", "Default", selected), sel.firstChild);
  sel.appendChild(option(NEW_FORMAT, "New format…", selected));
  const want = selected === "Default" ? "default" : selected;
  const has = Array.from(sel.options).some((opt) => opt.value === want);
  sel.value = has ? want : "default";
  filling = false;
  syncNew();
}

function applyLayout(layout) {
  sheets = {};
  const order = Array.isArray(layout.order) ? layout.order.map(String) : null;
  const views = layout.views || {};
  tabs.forEach((tab) => {
    sheets[tab.key] = sheetFrom(views[tab.key], order, tab.key, tab.columns);
  });
  if (!tabs.some((tab) => tab.key === active)) active = (tabs[0] && tabs[0].key) || "";
  closeTray();
  remember();
  renderTabs();
  renderRows();
}

async function load(reportKey, formatName) {
  const params = new URLSearchParams({ report_key: reportKey });
  if (formatName && formatName !== NEW_FORMAT && formatName !== "Default" && formatName !== "default") {
    params.set("format", formatName);
  }
  const resp = await fetch(attr("data-format-url") + "?" + params.toString(), { headers: { Accept: "application/json" } });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    msg(data.error || "Could not load this format.");
    return;
  }
  const report = document.getElementById("fmtReport");
  if (report && report.options.length === 0) {
    (data.reports || []).forEach((item) => report.appendChild(option(item.key, item.title, data.report_key || reportKey)));
    report.value = data.report_key || reportKey;
  }
  tabs = data.tabs || [];
  fillFormats(data.formats || [], data.format_name || formatName);
  applyLayout(data.layout || {});
  msg("");
}

function chosenName() {
  const sel = document.getElementById("fmtName");
  if (sel && sel.value === NEW_FORMAT) {
    const input = document.getElementById("fmtNew");
    return (input && input.value.trim()) || "";
  }
  return (sel && sel.value) || "default";
}

async function save() {
  const saveBtn = document.getElementById("fmtSave");
  if (saveBtn && saveBtn.disabled) return;
  const formatName = chosenName();
  const reportEl = document.getElementById("fmtReport");
  const reportKey = (reportEl && reportEl.value) || "";
  if (!formatName) {
    msg("Type a name for the new format.");
    return;
  }
  const resp = await fetch(attr("data-format-url"), {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": attr("data-csrf") },
    body: JSON.stringify({ report_key: reportKey, format_name: formatName, tabs: payloadTabs() }),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    msg(data.error || "Save failed.");
    return;
  }
  const nameInput = document.getElementById("fmtNew");
  if (nameInput) nameInput.value = "";
  await load(reportKey, data.format_name || formatName);
  msg("Saved " + (data.format_name || formatName) + ".");
}

document.addEventListener("DOMContentLoaded", () => {
  const report = document.getElementById("fmtReport");
  if (report) {
    report.addEventListener("change", () => load(report.value, "default"));
  }
  const name = document.getElementById("fmtName");
  if (name) {
    name.addEventListener("change", () => {
      if (filling) return;
      syncNew();
      refreshChrome();
      if (name.value === NEW_FORMAT) return;
      const reportEl = document.getElementById("fmtReport");
      load((reportEl && reportEl.value) || "", name.value);
    });
  }
  const nameInput = document.getElementById("fmtNew");
  if (nameInput) nameInput.addEventListener("input", () => syncSave());
  const add = document.getElementById("fmtAdd");
  if (add) {
    add.addEventListener("click", () => {
      if (!active) return;
      capture();
      sheets[active].levels.push(blankLevel("sort"));
      renderRows();
    });
  }
  const flat = document.getElementById("fmtFlat");
  if (flat) flat.addEventListener("change", () => refreshChrome());
  const showTab = document.getElementById("fmtShowTab");
  if (showTab) {
    showTab.addEventListener("change", () => {
      if (!showTab.checked) {
        capture();
        const others = tabs.filter((tab) => tab.key !== active && sheets[tab.key] && sheets[tab.key].showTab).length;
        if (others === 0) {
          showTab.checked = true;
          sheets[active].showTab = true;
          return;
        }
      }
      refreshChrome();
    });
  }
  const trayClose = document.getElementById("fmtTrayClose");
  if (trayClose) trayClose.addEventListener("click", () => closeTray());
  const saveBtn = document.getElementById("fmtSave");
  if (saveBtn) saveBtn.addEventListener("click", () => save());
  load("ordered", "default");
});

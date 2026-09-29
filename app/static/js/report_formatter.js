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
function sheetFrom(view) {
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
  return { flat: Array.isArray(group) && group.length === 0, levels: levels };
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
    const label = col.header && col.header !== col.field ? col.header : col.field;
    sel.appendChild(option(col.field, label, selected));
  });
  if (selected && !seen[selected]) sel.appendChild(option(selected, selected, selected));
  sel.value = selected;
  return sel;
}

function capture() {
  if (!active) return;
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
  const flat = document.getElementById("fmtFlat");
  sheets[active] = { flat: !!(flat && flat.checked), levels: levels };
}

function renderRows() {
  const body = document.getElementById("fmtRows");
  const tab = tabs.find((item) => item.key === active);
  const sheet = sheets[active] || { flat: false, levels: [] };
  const flat = document.getElementById("fmtFlat");
  if (!body || !tab) return;
  if (flat) flat.checked = sheet.flat;
  body.replaceChildren();
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

    const col = columnSelect(tab.columns, level.column);
    col.addEventListener("change", () => capture());
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
        extraBox.appendChild(value);
      }
      if (op.value === "between") {
        const value2 = document.createElement("input");
        value2.className = "fmt-v2";
        value2.value = level.v2;
        value2.placeholder = "And";
        value2.setAttribute("aria-label", "Filter end value");
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

function renderTabs() {
  const host = document.getElementById("fmtTabs");
  if (!host) return;
  host.replaceChildren();
  tabs.forEach((tab) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "report-tab" + (tab.key === active ? " active" : "");
    btn.textContent = tab.name;
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", tab.key === active ? "true" : "false");
    btn.addEventListener("click", () => {
      if (tab.key === active) return;
      capture();
      active = tab.key;
      renderTabs();
      renderRows();
    });
    host.appendChild(btn);
  });
}

function payloadTabs() {
  capture();
  return tabs.map((tab) => {
    const sheet = sheets[tab.key] || { flat: false, levels: [] };
    const group = sheet.levels.filter((level) => level.kind === "group" && level.column).map((level) => level.column);
    const sorters = sheet.levels.filter((level) => level.kind === "sort" && level.column).map((level) => ({
      column: level.column, dir: level.dir,
    }));
    const filters = sheet.levels.filter((level) => level.kind === "filter" && level.column).map((level) => ({
      column: level.column, op: level.op, v: level.v, v2: level.v2,
    }));
    return {
      key: tab.key,
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
  tabs.forEach((tab) => {
    sheets[tab.key] = sheetFrom((layout.views || {})[tab.key]);
  });
  if (!tabs.some((tab) => tab.key === active)) active = (tabs[0] && tabs[0].key) || "";
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
      if (name.value === NEW_FORMAT) return;
      const reportEl = document.getElementById("fmtReport");
      load((reportEl && reportEl.value) || "", name.value);
    });
  }
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
  if (flat) flat.addEventListener("change", () => capture());
  const saveBtn = document.getElementById("fmtSave");
  if (saveBtn) saveBtn.addEventListener("click", () => save());
  load("ordered", "default");
});

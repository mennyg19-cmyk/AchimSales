type Column = { field: string; header: string };
type Tab = { key: string; name: string; columns: Column[] };
type Kind = "sort" | "group" | "filter";
type Level = { kind: Kind; column: string; dir: "asc" | "desc"; op: string; v: string; v2: string };
type Sheet = { flat: boolean; levels: Level[] };
type Layout = {
  views?: Record<string, {
    group?: string[];
    sorters?: { column: string; dir: string }[];
    columnFilters?: Record<string, { op?: string; v?: string; v2?: string }>;
  }>;
};

const NEW_FORMAT = "__new__";
const FILTER_OPS: { value: string; label: string }[] = [
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
let tabs: Tab[] = [];
let active = "";
let sheets: Record<string, Sheet> = {};

function root(): HTMLElement | null {
  return document.getElementById("fmtRoot");
}
function attr(name: string): string {
  return root()?.getAttribute(name) || "";
}
function msg(text: string): void {
  const el = document.getElementById("fmtMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
}
function blankLevel(kind: Kind = "sort"): Level {
  return { kind, column: "", dir: "asc", op: "contains", v: "", v2: "" };
}
function sheetFrom(view: {
  group?: string[];
  sorters?: { column: string; dir: string }[];
  columnFilters?: Record<string, { op?: string; v?: string; v2?: string }>;
} | undefined): Sheet {
  const levels: Level[] = [];
  const group = view?.group;
  if (Array.isArray(group)) {
    group.forEach((column) => levels.push({ ...blankLevel("group"), column }));
  }
  (view?.sorters || []).forEach((sorter) => {
    levels.push({
      ...blankLevel("sort"),
      column: sorter.column || "",
      dir: sorter.dir === "desc" ? "desc" : "asc",
    });
  });
  Object.entries(view?.columnFilters || {}).forEach(([column, spec]) => {
    levels.push({
      ...blankLevel("filter"),
      column,
      op: spec.op || "contains",
      v: spec.v || "",
      v2: spec.v2 || "",
    });
  });
  return { flat: Array.isArray(group) && group.length === 0, levels };
}

function option(value: string, label: string, selected: string): HTMLOptionElement {
  const opt = document.createElement("option");
  opt.value = value;
  opt.textContent = label;
  opt.selected = value === selected;
  return opt;
}

function columnSelect(columns: Column[], selected: string): HTMLSelectElement {
  const sel = document.createElement("select");
  sel.className = "fmt-col";
  sel.setAttribute("aria-label", "Column");
  sel.appendChild(option("", "Column", selected));
  const seen = new Set<string>();
  columns.forEach((col) => {
    seen.add(col.field);
    const label = col.header && col.header !== col.field ? col.header : col.field;
    sel.appendChild(option(col.field, label, selected));
  });
  if (selected && !seen.has(selected)) sel.appendChild(option(selected, selected, selected));
  sel.value = selected;
  return sel;
}

function capture(): void {
  if (!active) return;
  const levels: Level[] = [];
  document.querySelectorAll<HTMLElement>("#fmtRows .fmt-level").forEach((row) => {
    const kind = (row.querySelector(".fmt-kind") as HTMLSelectElement | null)?.value as Kind;
    const column = (row.querySelector(".fmt-col") as HTMLSelectElement | null)?.value || "";
    const dir = ((row.querySelector(".fmt-dir") as HTMLSelectElement | null)?.value || "asc") as "asc" | "desc";
    const op = (row.querySelector(".fmt-op") as HTMLSelectElement | null)?.value || "contains";
    const v = (row.querySelector(".fmt-v") as HTMLInputElement | null)?.value || "";
    const v2 = (row.querySelector(".fmt-v2") as HTMLInputElement | null)?.value || "";
    levels.push({ kind: kind || "sort", column, dir, op, v, v2 });
  });
  sheets[active] = {
    flat: (document.getElementById("fmtFlat") as HTMLInputElement | null)?.checked || false,
    levels,
  };
}

function renderRows(): void {
  const body = document.getElementById("fmtRows");
  const tab = tabs.find((item) => item.key === active);
  const sheet = sheets[active] || { flat: false, levels: [] };
  const flat = document.getElementById("fmtFlat") as HTMLInputElement | null;
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
      sheets[active].levels[index].kind = kind.value as Kind;
      renderRows();
    });
    tr.appendChild(kind);

    const col = columnSelect(tab.columns, level.column);
    col.addEventListener("change", () => {
      capture();
    });
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

function move(index: number, delta: number): void {
  capture();
  const levels = sheets[active].levels;
  const next = index + delta;
  if (next < 0 || next >= levels.length) return;
  const [row] = levels.splice(index, 1);
  levels.splice(next, 0, row);
  renderRows();
}

function renderTabs(): void {
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

function payloadTabs(): unknown[] {
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
      sorters,
      filters,
    };
  });
}

function syncNew(): void {
  const sel = document.getElementById("fmtName") as HTMLSelectElement | null;
  const wrap = document.getElementById("fmtNewWrap");
  if (wrap) wrap.hidden = sel?.value !== NEW_FORMAT;
}

function fillFormats(names: string[], selected: string): void {
  const sel = document.getElementById("fmtName") as HTMLSelectElement | null;
  if (!sel) return;
  filling = true;
  sel.replaceChildren();
  const seen = new Set<string>();
  const add = (name: string) => {
    if (!name || seen.has(name)) return;
    seen.add(name);
    sel.appendChild(option(name, name, selected));
  };
  add("Default");
  names.forEach(add);
  sel.appendChild(option(NEW_FORMAT, "New format…", selected));
  sel.value = [...sel.options].some((opt) => opt.value === selected) ? selected : "Default";
  filling = false;
  syncNew();
}

function applyLayout(layout: Layout): void {
  sheets = {};
  tabs.forEach((tab) => {
    sheets[tab.key] = sheetFrom((layout.views || {})[tab.key]);
  });
  if (!tabs.some((tab) => tab.key === active)) active = tabs[0]?.key || "";
  renderTabs();
  renderRows();
}

async function load(reportKey: string, formatName = "Default"): Promise<void> {
  const params = new URLSearchParams({ report_key: reportKey });
  if (formatName && formatName !== NEW_FORMAT && formatName !== "Default") params.set("format", formatName);
  const resp = await fetch(attr("data-format-url") + "?" + params.toString(), { headers: { Accept: "application/json" } });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    msg((data as { error?: string }).error || "Could not load this format.");
    return;
  }
  const body = data as {
    reports?: { key: string; title: string }[];
    formats?: { name: string }[];
    tabs?: Tab[];
    layout?: Layout;
    report_key?: string;
    format_name?: string;
  };
  const report = document.getElementById("fmtReport") as HTMLSelectElement | null;
  if (report && report.options.length === 0) {
    (body.reports || []).forEach((item) => report.appendChild(option(item.key, item.title, body.report_key || reportKey)));
    report.value = body.report_key || reportKey;
  }
  tabs = body.tabs || [];
  fillFormats((body.formats || []).map((row) => row.name), body.format_name || formatName);
  applyLayout(body.layout || {});
  msg("");
}

function chosenName(): string {
  const sel = document.getElementById("fmtName") as HTMLSelectElement | null;
  if (sel?.value === NEW_FORMAT) {
    return (document.getElementById("fmtNew") as HTMLInputElement | null)?.value.trim() || "";
  }
  return sel?.value || "Default";
}

async function save(): Promise<void> {
  const formatName = chosenName();
  const reportKey = (document.getElementById("fmtReport") as HTMLSelectElement | null)?.value || "";
  if (!formatName) {
    msg("Type a name for the new format.");
    return;
  }
  const resp = await fetch(attr("data-format-url"), {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": attr("data-csrf") },
    body: JSON.stringify({ report_key: reportKey, format_name: formatName, tabs: payloadTabs() }),
  });
  const data = await resp.json().catch(() => ({})) as { error?: string; format_name?: string };
  if (!resp.ok) {
    msg(data.error || "Save failed.");
    return;
  }
  const nameInput = document.getElementById("fmtNew") as HTMLInputElement | null;
  if (nameInput) nameInput.value = "";
  await load(reportKey, data.format_name || formatName);
  msg(`Saved ${data.format_name || formatName}.`);
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("fmtReport")?.addEventListener("change", () => {
    const report = (document.getElementById("fmtReport") as HTMLSelectElement).value;
    void load(report, "Default");
  });
  document.getElementById("fmtName")?.addEventListener("change", () => {
    if (filling) return;
    syncNew();
    const name = (document.getElementById("fmtName") as HTMLSelectElement).value;
    if (name === NEW_FORMAT) return;
    const report = (document.getElementById("fmtReport") as HTMLSelectElement).value;
    void load(report, name);
  });
  document.getElementById("fmtAdd")?.addEventListener("click", () => {
    if (!active) return;
    capture();
    sheets[active].levels.push(blankLevel("sort"));
    renderRows();
  });
  document.getElementById("fmtFlat")?.addEventListener("change", () => {
    capture();
  });
  document.getElementById("fmtSave")?.addEventListener("click", () => void save());
  void load("ordered");
});

export {};

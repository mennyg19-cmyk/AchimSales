function root(): HTMLElement | null {
  return document.getElementById("dbxRoot");
}

function attr(name: string): string {
  return root()?.getAttribute(name) || "";
}

function csrf(): string {
  return attr("data-csrf");
}

function dbName(): string {
  return (document.getElementById("dbxDb") as HTMLSelectElement | null)?.value || "precious";
}

function searchQ(): string {
  return (document.getElementById("dbxSearch") as HTMLInputElement | null)?.value || "";
}

function colFilter(): string {
  return (document.getElementById("dbxCol") as HTMLSelectElement | null)?.value || "";
}

function colQ(): string {
  return (document.getElementById("dbxColQ") as HTMLInputElement | null)?.value || "";
}

function show(text: string): void {
  const el = document.getElementById("dbxMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
}

type Col = { name: string; type?: string };
type GridData = {
  table?: string | null;
  columns: Col[];
  primary_key: string | null;
  rows: Record<string, unknown>[];
  total: number;
  page?: number;
  per_page?: number;
  truncated?: boolean;
  error?: string;
};

let currentTable: string | null = null;
let currentPage = 1;
let jsonEdit: { table: string; column: string; pk: unknown } | null = null;

function looksJson(colName: string, value: unknown): boolean {
  if (colName.toLowerCase().endsWith("_json")) return true;
  const s = String(value ?? "").trim();
  return (s.startsWith("{") && s.endsWith("}")) || (s.startsWith("[") && s.endsWith("]"));
}

function prettyJson(raw: string): string {
  const s = raw.trim();
  if (!s) return "";
  try {
    return JSON.stringify(JSON.parse(s), null, 2);
  } catch {
    return raw;
  }
}

function compactJson(raw: string): string {
  const s = raw.trim();
  if (!s) return "{}";
  return JSON.stringify(JSON.parse(s));
}

function fillColumnSelect(cols: Col[]): void {
  const sel = document.getElementById("dbxCol") as HTMLSelectElement | null;
  if (!sel) return;
  const keep = sel.value;
  sel.replaceChildren();
  const any = document.createElement("option");
  any.value = "";
  any.textContent = "Any column";
  sel.appendChild(any);
  cols.forEach((c) => {
    const o = document.createElement("option");
    o.value = c.name;
    o.textContent = c.name;
    sel.appendChild(o);
  });
  if (keep && [...sel.options].some((o) => o.value === keep)) sel.value = keep;
}

async function loadTables(): Promise<void> {
  const host = document.getElementById("dbxTables");
  if (!host) return;
  const url = attr("data-tables-url") + "?db=" + encodeURIComponent(dbName());
  const data = await fetch(url, { headers: { Accept: "application/json" } }).then((r) => r.json());
  host.replaceChildren();
  for (const t of (data.tables || []) as { name: string; row_count: number | null }[]) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "dbx-table-btn";
    btn.dataset.table = t.name;
    btn.textContent = t.name;
    const n = document.createElement("span");
    n.textContent = t.row_count == null ? "" : String(t.row_count);
    btn.appendChild(n);
    btn.addEventListener("click", () => {
      host.querySelectorAll(".dbx-table-btn").forEach((b) => b.classList.remove("is-on"));
      btn.classList.add("is-on");
      currentTable = t.name;
      currentPage = 1;
      void loadRows(t.name, 1);
    });
    host.appendChild(btn);
  }
  applyTableFilter();
}

function applyTableFilter(): void {
  const q = ((document.getElementById("dbxTableFilter") as HTMLInputElement | null)?.value || "")
    .trim().toLowerCase();
  document.querySelectorAll<HTMLElement>("#dbxTables .dbx-table-btn").forEach((btn) => {
    const name = (btn.dataset.table || "").toLowerCase();
    btn.hidden = !!q && !name.includes(q);
  });
}

async function loadRows(table: string, page: number): Promise<void> {
  currentTable = table;
  currentPage = page;
  const params = new URLSearchParams({
    db: dbName(), page: String(page), q: searchQ(),
  });
  if (colFilter() && colQ()) {
    params.set("col", colFilter());
    params.set("colq", colQ());
  }
  const url = attr("data-table-url").replace("__T__", encodeURIComponent(table)) + "?" + params.toString();
  const data = await fetch(url, { headers: { Accept: "application/json" } }).then((r) => r.json()) as GridData;
  renderGrid(data, table, page, true);
}

function renderGrid(data: GridData, table: string | null, page: number, paged: boolean): void {
  const grid = document.getElementById("dbxGrid");
  if (!grid) return;
  if (data.error) { show(data.error); return; }
  show(data.truncated ? `Showing first ${data.rows.length} rows.` : "");
  fillColumnSelect(data.columns || []);
  const pk = data.primary_key;
  const tableEl = document.createElement("table");
  tableEl.className = "simple-table";
  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  for (const c of data.columns) {
    const th = document.createElement("th");
    th.textContent = c.name;
    hr.appendChild(th);
  }
  const thAct = document.createElement("th");
  thAct.textContent = "";
  hr.appendChild(thAct);
  thead.appendChild(hr);
  tableEl.appendChild(thead);
  const tbody = document.createElement("tbody");
  for (const row of data.rows) {
    const tr = document.createElement("tr");
    for (const c of data.columns) {
      const td = document.createElement("td");
      const raw = row[c.name] == null ? "" : String(row[c.name]);
      if (looksJson(c.name, raw)) {
        td.appendChild(jsonCell(table, c.name, pk ? row[pk] : null, raw, !!pk && !!table));
      } else {
        const input = document.createElement("input");
        input.className = "dbx-cell";
        input.value = raw;
        input.dataset.orig = raw;
        input.addEventListener("change", () => {
          if (!pk || !table) return;
          void saveCell(table, c.name, row[pk], input.value).then((ok) => {
            if (ok) input.dataset.orig = input.value;
            else input.value = input.dataset.orig || "";
          });
        });
        if (!pk || !table) input.disabled = true;
        td.appendChild(input);
      }
      tr.appendChild(td);
    }
    const tdDel = document.createElement("td");
    if (pk && table && paged) {
      const del = document.createElement("button");
      del.type = "button";
      del.className = "btn btn-outline btn-sm";
      del.textContent = "Delete";
      del.addEventListener("click", () => {
        if (!window.confirm("Delete this row?")) return;
        void deleteRow(table, row[pk], () => loadRows(table, page));
      });
      tdDel.appendChild(del);
    }
    tr.appendChild(tdDel);
    tbody.appendChild(tr);
  }
  tableEl.appendChild(tbody);
  grid.replaceChildren(tableEl);
  if (!paged) return;
  const pages = Math.max(1, Math.ceil((data.total || 0) / (data.per_page || 50)));
  if (pages > 1 && table) {
    const nav = document.createElement("p");
    nav.className = "flag-desc";
    nav.textContent = `Page ${page} of ${pages} (${data.total} rows)`;
    const prev = document.createElement("button");
    prev.type = "button";
    prev.className = "btn btn-outline btn-sm";
    prev.textContent = "Prev";
    prev.disabled = page <= 1;
    prev.addEventListener("click", () => void loadRows(table, page - 1));
    const next = document.createElement("button");
    next.type = "button";
    next.className = "btn btn-outline btn-sm";
    next.textContent = "Next";
    next.disabled = page >= pages;
    next.addEventListener("click", () => void loadRows(table, page + 1));
    grid.appendChild(nav);
    grid.appendChild(prev);
    grid.appendChild(next);
  }
}

function jsonCell(
  table: string | null, column: string, pk: unknown, raw: string, canSave: boolean,
): HTMLElement {
  const wrap = document.createElement("div");
  wrap.className = "dbx-json-cell";
  const pre = document.createElement("pre");
  pre.className = "dbx-json-preview";
  pre.textContent = prettyJson(raw) || "(empty)";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn btn-outline btn-sm";
  btn.textContent = canSave ? "Expand / edit" : "Expand";
  btn.addEventListener("click", () => openJson(table, column, pk, raw, canSave));
  wrap.appendChild(pre);
  wrap.appendChild(btn);
  return wrap;
}

function jsonMsg(text: string, isError: boolean): void {
  const el = document.getElementById("dbxJsonMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
  el.className = "modal-msg" + (isError ? " modal-msg-error" : "");
}

function openJson(
  table: string | null, column: string, pk: unknown, raw: string, canSave: boolean,
): void {
  jsonEdit = canSave && table ? { table, column, pk } : null;
  const modal = document.getElementById("dbxJsonModal");
  const title = document.getElementById("dbxJsonTitle");
  const meta = document.getElementById("dbxJsonMeta");
  const text = document.getElementById("dbxJsonText") as HTMLTextAreaElement | null;
  const save = document.getElementById("dbxJsonSave") as HTMLButtonElement | null;
  if (title) title.textContent = column;
  if (meta) {
    meta.textContent = table
      ? `${table} · ${canSave ? "edit and save" : "read only"}`
      : "Read only (run a single-table SELECT that includes the primary key to edit)";
  }
  if (text) {
    text.value = prettyJson(raw);
    text.readOnly = !canSave;
  }
  if (save) save.disabled = !canSave;
  jsonMsg("", false);
  if (modal) modal.hidden = false;
  text?.focus();
}

function closeJson(): void {
  const modal = document.getElementById("dbxJsonModal");
  if (modal) modal.hidden = true;
  jsonEdit = null;
}

function formatJsonEditor(): void {
  const text = document.getElementById("dbxJsonText") as HTMLTextAreaElement | null;
  if (!text) return;
  try {
    text.value = JSON.stringify(JSON.parse(text.value.trim() || "null"), null, 2);
    jsonMsg("", false);
  } catch (err) {
    jsonMsg((err as Error).message || "Invalid JSON.", true);
  }
}

async function saveJsonEditor(): Promise<void> {
  const text = document.getElementById("dbxJsonText") as HTMLTextAreaElement | null;
  if (!text || !jsonEdit) return;
  let compact: string;
  try {
    compact = compactJson(text.value);
  } catch (err) {
    jsonMsg((err as Error).message || "Invalid JSON — not saved.", true);
    return;
  }
  const ok = await saveCell(jsonEdit.table, jsonEdit.column, jsonEdit.pk, compact);
  if (!ok) return;
  jsonMsg("Saved.", false);
  if (currentTable) void loadRows(currentTable, currentPage);
}

async function saveCell(table: string, column: string, pk: unknown, value: string): Promise<boolean> {
  const url = attr("data-cell-url").replace("__T__", encodeURIComponent(table));
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
    body: JSON.stringify({ db: dbName(), column, pk, value }),
  });
  const data = await resp.json().catch(() => ({})) as { error?: string };
  if (!resp.ok) {
    const msg = data.error || "Could not save cell.";
    show(msg);
    jsonMsg(msg, true);
    return false;
  }
  show("");
  return true;
}

async function deleteRow(table: string, pk: unknown, after: () => void): Promise<void> {
  const url = attr("data-row-url").replace("__T__", encodeURIComponent(table));
  const resp = await fetch(url, {
    method: "DELETE",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
    body: JSON.stringify({ db: dbName(), pk }),
  });
  if (!resp.ok) show("Could not delete row.");
  else after();
}

function sqlLooksWrite(sql: string): boolean {
  const head = sql.trim().replace(/^\(+/, "").split(/\s+/, 1)[0]?.toUpperCase() || "";
  return head === "INSERT" || head === "UPDATE" || head === "DELETE";
}

async function runSql(): Promise<void> {
  const sql = ((document.getElementById("dbxSql") as HTMLTextAreaElement | null)?.value || "").trim();
  if (!sql) { show("Type a SQL statement first."); return; }
  if (sqlLooksWrite(sql)
      && !window.confirm("This will change the database. There is no undo. Run it?")) {
    return;
  }
  const resp = await fetch(attr("data-sql-url"), {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
    body: JSON.stringify({ db: dbName(), sql }),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    show((data as { error?: string }).error || "SQL failed.");
    return;
  }
  if ((data as { kind?: string }).kind === "exec") {
    show(`Statement ran. ${Number((data as { rowcount?: number }).rowcount) || 0} row(s) changed.`);
    if (currentTable) void loadRows(currentTable, currentPage);
    return;
  }
  const grid = data as GridData;
  currentTable = grid.table || currentTable;
  renderGrid(grid, grid.table || null, 1, false);
}

function reloadCurrent(): void {
  if (currentTable) void loadRows(currentTable, 1);
}

type FormatColumn = { field: string; header: string };
type FormatTab = { key: string; name: string; columns: FormatColumn[] };
type FormatLayout = {
  views?: Record<string, {
    group?: string[];
    sorters?: { column: string; dir: string }[];
    columnFilters?: Record<string, { op?: string; v?: string; v2?: string }>;
  }>;
};

const FILTER_OPS: { value: string; label: string }[] = [
  { value: "contains", label: "contains" },
  { value: "equals", label: "equals" },
  { value: "starts", label: "starts with" },
  { value: "ends", label: "ends with" },
  { value: "empty", label: "is empty" },
  { value: "notEmpty", label: "is not empty" },
  { value: "gt", label: "greater than" },
  { value: "lt", label: "less than" },
  { value: "between", label: "between" },
  { value: "on", label: "on date" },
  { value: "before", label: "before" },
  { value: "after", label: "after" },
];

function formatMsg(text: string): void {
  const el = document.getElementById("dbxFormatMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
}

function columnSelect(columns: FormatColumn[], selected: string, label: string): HTMLSelectElement {
  const sel = document.createElement("select");
  sel.setAttribute("aria-label", label);
  const blank = document.createElement("option");
  blank.value = "";
  blank.textContent = "Column";
  sel.appendChild(blank);
  const seen = new Set<string>();
  columns.forEach((col) => {
    seen.add(col.field);
    const opt = document.createElement("option");
    opt.value = col.field;
    opt.textContent = col.header && col.header !== col.field ? `${col.header} (${col.field})` : col.field;
    sel.appendChild(opt);
  });
  if (selected && !seen.has(selected)) {
    const extra = document.createElement("option");
    extra.value = selected;
    extra.textContent = selected;
    sel.appendChild(extra);
  }
  sel.value = selected;
  return sel;
}

function addLevelButton(label: string, onClick: () => void): HTMLButtonElement {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn btn-outline dbx-format-add";
  btn.textContent = "+ " + label;
  btn.addEventListener("click", onClick);
  return btn;
}

function renderFormat(tabs: FormatTab[], layout: FormatLayout): void {
  const host = document.getElementById("dbxFormatTabs");
  if (!host) return;
  host.replaceChildren();
  const views = layout.views || {};
  tabs.forEach((tab) => {
    const saved = views[tab.key] || {};
    const box = document.createElement("fieldset");
    box.className = "dbx-format-tab";
    box.dataset.tab = tab.key;
    const legend = document.createElement("legend");
    legend.textContent = tab.name;
    box.appendChild(legend);

    const groupOn = document.createElement("input");
    groupOn.type = "checkbox";
    groupOn.className = "dbx-set-group";
    groupOn.checked = Array.isArray(saved.group);
    const groupLabel = document.createElement("label");
    groupLabel.appendChild(groupOn);
    groupLabel.appendChild(document.createTextNode(" Set grouping"));
    box.appendChild(groupLabel);

    const groups = document.createElement("div");
    groups.className = "dbx-format-levels";
    const paintGroup = (column: string) => {
      const row = document.createElement("div");
      row.className = "dbx-format-row";
      row.appendChild(columnSelect(tab.columns, column, `${tab.name} group by`));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn btn-outline";
      remove.textContent = "Remove";
      remove.addEventListener("click", () => row.remove());
      row.appendChild(remove);
      groups.appendChild(row);
    };
    (saved.group || []).forEach((column) => paintGroup(column));
    box.appendChild(groups);
    box.appendChild(addLevelButton("group level", () => paintGroup("")));

    const sorters = document.createElement("div");
    sorters.className = "dbx-format-levels dbx-sorters";
    const paintSort = (column: string, dir: string) => {
      const row = document.createElement("div");
      row.className = "dbx-format-row";
      row.appendChild(columnSelect(tab.columns, column, `${tab.name} sort by`));
      const direction = document.createElement("select");
      direction.className = "dbx-sort-dir";
      direction.setAttribute("aria-label", `${tab.name} sort direction`);
      ["asc", "desc"].forEach((value) => {
        const opt = document.createElement("option");
        opt.value = value;
        opt.textContent = value === "asc" ? "A to Z" : "Z to A";
        direction.appendChild(opt);
      });
      direction.value = dir === "desc" ? "desc" : "asc";
      row.appendChild(direction);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn btn-outline";
      remove.textContent = "Remove";
      remove.addEventListener("click", () => row.remove());
      row.appendChild(remove);
      sorters.appendChild(row);
    };
    (saved.sorters || []).forEach((sorter) => paintSort(sorter.column || "", sorter.dir || "asc"));
    box.appendChild(sorters);
    box.appendChild(addLevelButton("sort level", () => paintSort("", "asc")));

    const filters = document.createElement("div");
    filters.className = "dbx-format-levels dbx-filters";
    const paintFilter = (column: string, op: string, v: string, v2: string) => {
      const row = document.createElement("div");
      row.className = "dbx-format-row";
      row.appendChild(columnSelect(tab.columns, column, `${tab.name} filter by`));
      const opSel = document.createElement("select");
      opSel.className = "dbx-filter-op";
      opSel.setAttribute("aria-label", `${tab.name} filter operator`);
      FILTER_OPS.forEach((item) => {
        const opt = document.createElement("option");
        opt.value = item.value;
        opt.textContent = item.label;
        opSel.appendChild(opt);
      });
      opSel.value = FILTER_OPS.some((item) => item.value === op) ? op : "contains";
      row.appendChild(opSel);
      const value = document.createElement("input");
      value.className = "dbx-filter-v";
      value.value = v;
      value.placeholder = "Value";
      value.setAttribute("aria-label", `${tab.name} filter value`);
      row.appendChild(value);
      const value2 = document.createElement("input");
      value2.className = "dbx-filter-v2";
      value2.value = v2;
      value2.placeholder = "And";
      value2.setAttribute("aria-label", `${tab.name} filter second value`);
      row.appendChild(value2);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn btn-outline";
      remove.textContent = "Remove";
      remove.addEventListener("click", () => row.remove());
      row.appendChild(remove);
      filters.appendChild(row);
    };
    Object.entries(saved.columnFilters || {}).forEach(([column, spec]) => {
      paintFilter(column, spec.op || "contains", spec.v || "", spec.v2 || "");
    });
    box.appendChild(filters);
    box.appendChild(addLevelButton("filter", () => paintFilter("", "contains", "", "")));
    host.appendChild(box);
  });
}

async function loadFormat(reportKey: string): Promise<void> {
  const url = attr("data-format-url") + "?report_key=" + encodeURIComponent(reportKey);
  const resp = await fetch(url, { headers: { Accept: "application/json" } });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    formatMsg((data as { error?: string }).error || "Could not load report format.");
    return;
  }
  const body = data as { reports?: { key: string; title: string }[]; tabs?: FormatTab[]; layout?: FormatLayout; report_key?: string };
  const sel = document.getElementById("dbxFormatReport") as HTMLSelectElement | null;
  if (sel && sel.options.length === 0) {
    (body.reports || []).forEach((report) => {
      const opt = document.createElement("option");
      opt.value = report.key;
      opt.textContent = report.title;
      sel.appendChild(opt);
    });
    sel.value = body.report_key || reportKey;
    sel.addEventListener("change", () => { void loadFormat(sel.value); });
  }
  renderFormat(body.tabs || [], body.layout || {});
  formatMsg("");
}

function collectFormat(): { report_key: string; tabs: unknown[] } {
  const report = (document.getElementById("dbxFormatReport") as HTMLSelectElement | null)?.value || "";
  const tabs: unknown[] = [];
  document.querySelectorAll<HTMLElement>("#dbxFormatTabs .dbx-format-tab").forEach((box) => {
    const group: string[] = [];
    box.querySelectorAll<HTMLSelectElement>(":scope > .dbx-format-levels:not(.dbx-sorters):not(.dbx-filters) select").forEach((sel) => {
      if (sel.value) group.push(sel.value);
    });
    const sorters: { column: string; dir: string }[] = [];
    box.querySelectorAll<HTMLElement>(":scope > .dbx-sorters .dbx-format-row").forEach((row) => {
      const column = row.querySelector("select")?.value || "";
      const dir = row.querySelector<HTMLSelectElement>(".dbx-sort-dir")?.value || "asc";
      if (column) sorters.push({ column, dir });
    });
    const filters: { column: string; op: string; v: string; v2: string }[] = [];
    box.querySelectorAll<HTMLElement>(":scope > .dbx-filters .dbx-format-row").forEach((row) => {
      const column = row.querySelector("select")?.value || "";
      const op = row.querySelector<HTMLSelectElement>(".dbx-filter-op")?.value || "contains";
      const v = row.querySelector<HTMLInputElement>(".dbx-filter-v")?.value || "";
      const v2 = row.querySelector<HTMLInputElement>(".dbx-filter-v2")?.value || "";
      if (column) filters.push({ column, op, v, v2 });
    });
    tabs.push({
      key: box.dataset.tab,
      set_group: box.querySelector<HTMLInputElement>(".dbx-set-group")?.checked || false,
      group, sorters, filters,
    });
  });
  return { report_key: report, tabs };
}

async function saveFormat(): Promise<void> {
  const payload = collectFormat();
  const resp = await fetch(attr("data-format-url"), {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
    body: JSON.stringify(payload),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    formatMsg((data as { error?: string }).error || "Save failed.");
    return;
  }
  await loadFormat(payload.report_key);
  formatMsg("Saved the company Default format.");
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("dbxDb")?.addEventListener("change", () => {
    currentTable = null;
    void loadTables();
  });
  document.getElementById("dbxTableFilter")?.addEventListener("input", applyTableFilter);
  let t: number | undefined;
  const bounce = () => {
    window.clearTimeout(t);
    t = window.setTimeout(reloadCurrent, 250);
  };
  document.getElementById("dbxSearch")?.addEventListener("input", bounce);
  document.getElementById("dbxCol")?.addEventListener("change", reloadCurrent);
  document.getElementById("dbxColQ")?.addEventListener("input", bounce);
  document.getElementById("dbxSqlRun")?.addEventListener("click", () => void runSql());
  document.getElementById("dbxSql")?.addEventListener("keydown", (e) => {
    if ((e as KeyboardEvent).key === "Enter" && (e as KeyboardEvent).ctrlKey) {
      e.preventDefault();
      void runSql();
    }
  });
  document.getElementById("dbxJsonFormat")?.addEventListener("click", formatJsonEditor);
  document.getElementById("dbxJsonSave")?.addEventListener("click", () => void saveJsonEditor());
  document.getElementById("dbxJsonClose")?.addEventListener("click", closeJson);
  document.getElementById("dbxJsonCloseX")?.addEventListener("click", closeJson);
  document.getElementById("dbxJsonModal")?.addEventListener("click", (e) => {
    if (e.target === document.getElementById("dbxJsonModal")) closeJson();
  });
  void loadTables();
  document.getElementById("dbxFormatSave")?.addEventListener("click", () => void saveFormat());
  const first = (document.getElementById("dbxFormatReport") as HTMLSelectElement | null)?.value || "ordered";
  void loadFormat(first);
});

export {};

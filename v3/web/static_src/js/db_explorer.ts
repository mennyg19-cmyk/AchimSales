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
        input.addEventListener("change", () => {
          if (!pk || !table) return;
          void saveCell(table, c.name, row[pk], input.value);
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
  await saveCell(jsonEdit.table, jsonEdit.column, jsonEdit.pk, compact);
  jsonMsg("Saved.", false);
  if (currentTable) void loadRows(currentTable, currentPage);
}

async function saveCell(table: string, column: string, pk: unknown, value: string): Promise<void> {
  const url = attr("data-cell-url").replace("__T__", encodeURIComponent(table));
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
    body: JSON.stringify({ db: dbName(), column, pk, value }),
  });
  if (!resp.ok) show("Could not save cell.");
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
});

export {};

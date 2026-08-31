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

function show(text: string): void {
  const el = document.getElementById("dbxMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
}

type Col = { name: string; type: string; pk: number };
type GridState = { table: string; page: number; columns: Col[] };

let grid: GridState | null = null;

async function apiJson(url: string, init?: RequestInit): Promise<{ ok: boolean; data: Record<string, unknown> }> {
  const resp = await fetch(url, init);
  const data = await resp.json().catch(() => ({})) as Record<string, unknown>;
  return { ok: resp.ok, data };
}

function headers(): Record<string, string> {
  return { "Content-Type": "application/json", "X-CSRF-Token": csrf() };
}

async function loadTables(): Promise<void> {
  const host = document.getElementById("dbxTables");
  if (!host) return;
  const url = attr("data-tables-url") + "?db=" + encodeURIComponent(dbName());
  const { data } = await apiJson(url);
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
      void loadRows(t.name, 1);
    });
    host.appendChild(btn);
  }
}

function cellInput(value: unknown): HTMLInputElement {
  const input = document.createElement("input");
  input.className = "dbx-cell";
  input.value = value == null ? "" : String(value);
  return input;
}

function rowValues(tr: HTMLTableRowElement, columns: Col[]): Record<string, string> {
  const values: Record<string, string> = {};
  columns.forEach((c, i) => {
    const input = tr.cells[i]?.querySelector("input");
    values[c.name] = input ? input.value : "";
  });
  return values;
}

function actionCell(buttons: HTMLButtonElement[]): HTMLTableCellElement {
  const td = document.createElement("td");
  td.className = "dbx-actions";
  buttons.forEach((b) => td.appendChild(b));
  return td;
}

function btn(label: string, className: string, onClick: () => void): HTMLButtonElement {
  const b = document.createElement("button");
  b.type = "button";
  b.className = className;
  b.textContent = label;
  b.addEventListener("click", onClick);
  return b;
}

async function loadRows(table: string, page: number): Promise<void> {
  const wrap = document.getElementById("dbxGrid");
  if (!wrap) return;
  const q = (document.getElementById("dbxSearch") as HTMLInputElement | null)?.value || "";
  const url = attr("data-table-url").replace("__T__", encodeURIComponent(table))
    + `?db=${encodeURIComponent(dbName())}&page=${page}&q=${encodeURIComponent(q)}`;
  const { ok, data } = await apiJson(url);
  if (!ok || data.error) { show(String(data.error || "Could not load table.")); return; }
  show("");
  const columns = (data.columns || []) as Col[];
  grid = { table, page, columns };
  const addBtn = document.getElementById("dbxAdd") as HTMLButtonElement | null;
  if (addBtn) addBtn.disabled = false;

  const tableEl = document.createElement("table");
  tableEl.className = "simple-table";
  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  for (const c of columns) {
    const th = document.createElement("th");
    th.textContent = c.pk > 0 ? `${c.name} (pk)` : c.name;
    hr.appendChild(th);
  }
  hr.appendChild(document.createElement("th"));
  thead.appendChild(hr);
  tableEl.appendChild(thead);
  const tbody = document.createElement("tbody");
  tbody.id = "dbxBody";
  for (const row of (data.rows || []) as Record<string, unknown>[]) {
    tbody.appendChild(existingRow(columns, row, table, page));
  }
  tableEl.appendChild(tbody);
  wrap.replaceChildren(tableEl);
  const pages = Math.max(1, Math.ceil(Number(data.total || 0) / Number(data.per_page || 50)));
  if (pages > 1) {
    const nav = document.createElement("p");
    nav.className = "flag-desc";
    nav.textContent = `Page ${page} of ${pages}`;
    wrap.appendChild(nav);
    const prev = btn("Prev", "btn btn-outline btn-sm", () => { void loadRows(table, page - 1); });
    prev.disabled = page <= 1;
    const next = btn("Next", "btn btn-outline btn-sm", () => { void loadRows(table, page + 1); });
    next.disabled = page >= pages;
    wrap.appendChild(prev);
    wrap.appendChild(next);
  }
}

function existingRow(columns: Col[], row: Record<string, unknown>, table: string, page: number): HTMLTableRowElement {
  const tr = document.createElement("tr");
  if (row._oid != null) tr.dataset.oid = String(row._oid);
  for (const c of columns) {
    const td = document.createElement("td");
    td.appendChild(cellInput(row[c.name]));
    tr.appendChild(td);
  }
  tr.appendChild(actionCell([
    btn("Save", "btn btn-primary btn-sm", () => { void saveExisting(tr, table, page); }),
    btn("Delete", "btn btn-outline btn-sm", () => {
      if (!window.confirm("Delete this row? There is no undo.")) return;
      void deleteExisting(tr, table, page);
    }),
  ]));
  return tr;
}

function newRow(columns: Col[], table: string, page: number): HTMLTableRowElement {
  const tr = document.createElement("tr");
  tr.className = "dbx-row-new";
  for (const _c of columns) {
    const td = document.createElement("td");
    td.appendChild(cellInput(""));
    tr.appendChild(td);
  }
  tr.appendChild(actionCell([
    btn("Save", "btn btn-primary btn-sm", () => { void saveNew(tr, table, page); }),
    btn("Cancel", "btn btn-outline btn-sm", () => { tr.remove(); }),
  ]));
  return tr;
}

async function saveExisting(tr: HTMLTableRowElement, table: string, page: number): Promise<void> {
  if (!grid) return;
  const oid = tr.dataset.oid;
  const { ok, data } = await apiJson(attr("data-row-url").replace("__T__", encodeURIComponent(table)), {
    method: "PUT",
    headers: headers(),
    body: JSON.stringify({ db: dbName(), oid, values: rowValues(tr, grid.columns) }),
  });
  if (!ok) { show(String(data.error || "Could not save row.")); return; }
  show("Saved.");
  void loadRows(table, page);
  void loadTables();
}

async function saveNew(tr: HTMLTableRowElement, table: string, page: number): Promise<void> {
  if (!grid) return;
  const { ok, data } = await apiJson(attr("data-row-url").replace("__T__", encodeURIComponent(table)), {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ db: dbName(), values: rowValues(tr, grid.columns) }),
  });
  if (!ok) { show(String(data.error || "Could not add row.")); return; }
  show("Row added.");
  void loadRows(table, page);
  void loadTables();
}

async function deleteExisting(tr: HTMLTableRowElement, table: string, page: number): Promise<void> {
  const { ok, data } = await apiJson(attr("data-row-url").replace("__T__", encodeURIComponent(table)), {
    method: "DELETE",
    headers: headers(),
    body: JSON.stringify({ db: dbName(), oid: tr.dataset.oid }),
  });
  if (!ok) { show(String(data.error || "Could not delete row.")); return; }
  show("Deleted.");
  void loadRows(table, page);
  void loadTables();
}

function addRow(): void {
  if (!grid) { show("Pick a table first."); return; }
  const body = document.getElementById("dbxBody");
  if (!body) return;
  const tr = newRow(grid.columns, grid.table, grid.page);
  body.prepend(tr);
  tr.querySelector("input")?.focus();
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("dbxDb")?.addEventListener("change", () => {
    grid = null;
    const addBtn = document.getElementById("dbxAdd") as HTMLButtonElement | null;
    if (addBtn) addBtn.disabled = true;
    void loadTables();
    document.getElementById("dbxGrid")?.replaceChildren();
  });
  document.getElementById("dbxAdd")?.addEventListener("click", addRow);
  let t: number | undefined;
  document.getElementById("dbxSearch")?.addEventListener("input", () => {
    window.clearTimeout(t);
    t = window.setTimeout(() => {
      if (grid) void loadRows(grid.table, 1);
    }, 250);
  });
  void loadTables();
});

export {};

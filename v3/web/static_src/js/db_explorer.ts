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
      void loadRows(t.name, 1);
    });
    host.appendChild(btn);
  }
}

async function loadRows(table: string, page: number): Promise<void> {
  const grid = document.getElementById("dbxGrid");
  if (!grid) return;
  const q = (document.getElementById("dbxSearch") as HTMLInputElement | null)?.value || "";
  const url = attr("data-table-url").replace("__T__", encodeURIComponent(table))
    + `?db=${encodeURIComponent(dbName())}&page=${page}&q=${encodeURIComponent(q)}`;
  const data = await fetch(url, { headers: { Accept: "application/json" } }).then((r) => r.json());
  if (data.error) { show(data.error); return; }
  show("");
  const tableEl = document.createElement("table");
  tableEl.className = "simple-table";
  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  for (const c of data.columns as { name: string }[]) {
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
  const pk = data.primary_key as string | null;
  for (const row of data.rows as Record<string, unknown>[]) {
    const tr = document.createElement("tr");
    for (const c of data.columns as { name: string }[]) {
      const td = document.createElement("td");
      const input = document.createElement("input");
      input.className = "dbx-cell";
      input.setAttribute("aria-label", c.name);
      input.value = row[c.name] == null ? "" : String(row[c.name]);
      input.addEventListener("focus", () => {
        input.dataset.prev = input.value;
      });
      input.addEventListener("change", () => {
        if (!pk) return;
        void saveCell(table, c.name, row[pk], input.value, input);
      });
      td.appendChild(input);
      tr.appendChild(td);
    }
    const tdDel = document.createElement("td");
    if (pk) {
      const del = document.createElement("button");
      del.type = "button";
      del.className = "btn btn-outline btn-sm";
      del.textContent = "Delete";
      del.setAttribute("aria-label", "Delete this row");
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
  const pages = Math.max(1, Math.ceil((data.total || 0) / (data.per_page || 50)));
  if (pages > 1) {
    const nav = document.createElement("p");
    nav.className = "flag-desc";
    nav.textContent = `Page ${page} of ${pages}`;
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

async function saveCell(
  table: string, column: string, pk: unknown, value: string, input: HTMLInputElement,
): Promise<void> {
  const prev = input.dataset.prev ?? "";
  const url = attr("data-cell-url").replace("__T__", encodeURIComponent(table));
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
    body: JSON.stringify({ db: dbName(), column, pk, value }),
  });
  if (!resp.ok) {
    input.value = prev;
    show("Could not save cell. Value restored.");
    return;
  }
  show("Saved. Undo restores the previous value.");
  const undo = document.createElement("button");
  undo.type = "button";
  undo.className = "btn btn-outline btn-sm";
  undo.textContent = "Undo";
  undo.addEventListener("click", () => {
    input.value = prev;
    void saveCell(table, column, pk, prev, input);
  });
  const msg = document.getElementById("dbxMsg");
  if (msg) {
    msg.appendChild(document.createTextNode(" "));
    msg.appendChild(undo);
  }
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

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("dbxDb")?.addEventListener("change", () => void loadTables());
  let t: number | undefined;
  document.getElementById("dbxSearch")?.addEventListener("input", () => {
    window.clearTimeout(t);
    t = window.setTimeout(() => {
      const on = document.querySelector<HTMLElement>(".dbx-table-btn.is-on");
      const name = on?.dataset.table;
      if (name) void loadRows(name, 1);
    }, 250);
  });
  void loadTables();
});

export {};

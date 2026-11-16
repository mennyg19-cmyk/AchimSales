/**
 * Warehouse dashboard list page: Tabulator grid with search, status filter,
 * sorting, and column show/hide.
 */

declare const Tabulator: any;

function readJson<T>(id: string, fallback: T): T {
  const el = document.getElementById(id);
  if (!el || !el.textContent) return fallback;
  try {
    return JSON.parse(el.textContent) as T;
  } catch {
    return fallback;
  }
}

function tableHeight(): string | number {
  const top = document.getElementById("whTable")?.getBoundingClientRect().top ?? 220;
  const h = window.innerHeight - top - 24;
  return Math.max(320, h);
}

function init(): void {
  const host = document.getElementById("whTable");
  if (!host || typeof Tabulator === "undefined") return;

  const rows = readJson<Record<string, unknown>[]>("whTableData", []);
  const columns = readJson<string[]>("whColumns", []);
  const defaults = new Set(readJson<string[]>("whDefaultVisible", []));
  const statusColumn = readJson<string>("whStatusColumn", "");

  const tabColumns = columns.map((field) => ({
    title: field,
    field,
    headerSort: true,
    visible: defaults.size === 0 ? true : defaults.has(field),
    minWidth: 90,
  }));

  const table = new Tabulator(host, {
    data: rows,
    columns: tabColumns,
    layout: "fitDataStretch",
    movableColumns: true,
    resizableColumns: true,
    height: tableHeight(),
    placeholder: "No open rows for this filter.",
    initialSort: statusColumn
      ? [{ column: statusColumn, dir: "asc" }]
      : [],
  });

  const search = document.getElementById("whSearch") as HTMLInputElement | null;
  const statusSel = document.getElementById("whStatusFilter") as HTMLSelectElement | null;
  const columnsBtn = document.getElementById("whColumnsBtn");
  const columnsPanel = document.getElementById("whColumnsPanel");
  const columnsList = document.getElementById("whColumnsList");

  function applyFilters(): void {
    const q = (search?.value || "").trim().toLowerCase();
    const status = statusSel?.value || "";
    table.setFilter((rowData: Record<string, unknown>) => {
      if (status && String(rowData[statusColumn] ?? "") !== status) return false;
      if (!q) return true;
      return columns.some((col) => {
        const v = rowData[col];
        return v != null && String(v).toLowerCase().includes(q);
      });
    });
  }

  search?.addEventListener("input", applyFilters);
  statusSel?.addEventListener("change", applyFilters);

  if (columnsList) {
    columns.forEach((field) => {
      const label = document.createElement("label");
      label.className = "wh-column-toggle";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = defaults.size === 0 ? true : defaults.has(field);
      cb.addEventListener("change", () => {
        if (cb.checked) table.showColumn(field);
        else table.hideColumn(field);
      });
      label.appendChild(cb);
      label.appendChild(document.createTextNode(" " + field));
      columnsList.appendChild(label);
    });
  }

  columnsBtn?.addEventListener("click", () => {
    if (!columnsPanel) return;
    columnsPanel.hidden = !columnsPanel.hidden;
  });

  window.addEventListener("resize", () => {
    table.setHeight(tableHeight());
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

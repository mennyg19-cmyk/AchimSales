/**
 * Report viewer.
 *
 * Gathers filters, enqueues a durable run, polls the job, then renders the
 * returned tabs in an interactive Tabulator grid. The server owns all math +
 * scope; this file is pure presentation + polling + per-tab view state.
 *
 * Behaviour parity with the v2 test app (WHAT, not HOW): one grid per tab,
 * natural-width table that scrolls horizontally, multi-sort, per-column
 * header filters, hide/show + reorder + freeze columns, group-by with totals,
 * a special card layout for Commissions, duplicate/hide tabs, reset/refresh,
 * and a WYSIWYG Excel export that mirrors exactly what's on screen.
 */

declare const Tabulator: any;

interface Column {
  field: string;
  header: string;
  type?: "text" | "money" | "percent" | "int" | "date";
}

interface CommissionMonth {
  month_label: string;
  subtotal_invoices: number;
  total_invoices: number;
  credits: number;
  net_commission: number;
  commission: number;
}
interface CommissionSalesman {
  salesman_number: string;
  salesman_name: string;
  commission_pct: number;
  monthly: CommissionMonth[];
  ytd: Record<string, number>;
}

interface Tab {
  key: string;
  name: string;
  columns: Column[];
  rows: Record<string, unknown>[];
  layout?: string;
  // Commission-card extras (only present when layout === "commission_cards").
  salesmen?: CommissionSalesman[];
  grand?: Record<string, number>;
  month_labels?: string[];
}

interface Payload {
  report_key: string;
  tabs: Tab[];
  row_count?: number;
  generated_at?: string;
}

/** Captured, re-applyable view state for one tab. */
interface ViewState {
  hidden: Set<string>;
  frozen: Set<string>;
  order: string[] | null;
  sorters: { column: string; dir: string }[] | null;
  headerFilters: { field: string; value: unknown }[] | null;
  group: string[];
}

const root = document.getElementById("reportRoot");

function attr(name: string): string {
  return root?.getAttribute(name) || "";
}

function $(id: string): HTMLElement | null {
  return document.getElementById(id);
}

function setStatus(msg: string, kind: "info" | "error" = "info"): void {
  const el = $("reportStatus");
  if (!el) return;
  el.textContent = msg;
  el.className = "report-status report-status-" + kind;
  el.hidden = false;
}

function clearStatus(): void {
  const el = $("reportStatus");
  if (el) el.hidden = true;
}

function money(precision: number) {
  return {
    formatter: "money",
    formatterParams: { symbol: "$", precision, thousand: ",", negativeSign: true },
    sorter: "number",
    hozAlign: "right",
  };
}

function formatterFor(col: Column): Record<string, unknown> {
  switch (col.type) {
    case "money":
      return money(2);
    case "int":
      return {
        formatter: "money",
        formatterParams: { symbol: "", precision: 0, thousand: "," },
        sorter: "number",
        hozAlign: "right",
      };
    case "percent":
      return {
        sorter: "number",
        hozAlign: "right",
        formatter: (cell: any) => {
          const n = Number(cell.getValue());
          return isFinite(n) && cell.getValue() !== "" ? (n * 100).toFixed(1) + "%" : "";
        },
      };
    case "date":
      return {
        sorter: "string",
        formatter: (cell: any) => {
          const v = String(cell.getValue() || "");
          const m = v.match(/^(\d{4})-(\d{2})-(\d{2})/);
          return m ? `${Number(m[2])}/${Number(m[3])}/${m[1]}` : v;
        },
      };
    default:
      return { sorter: "string" };
  }
}

function isNumericType(t?: string): boolean {
  return t === "money" || t === "int" || t === "percent";
}

// --------------------------------------------------------------------------
// State
// --------------------------------------------------------------------------

const state: {
  tabs: Record<string, Tab>;
  order: string[];
  active: string | null;
  views: Record<string, ViewState>;
  table: any;
  jobId: string | null;
} = { tabs: {}, order: [], active: null, views: {}, table: null, jobId: null };

function freshView(): ViewState {
  return { hidden: new Set(), frozen: new Set(), order: null, sorters: null, headerFilters: null, group: [] };
}

// --------------------------------------------------------------------------
// Column building (applies the tab's current view state)
// --------------------------------------------------------------------------

function headerMenu(tab: Tab): any[] {
  return [
    {
      label: "Hide column",
      action: (_e: any, column: any) => {
        view(tab.key).hidden.add(column.getField());
        column.hide();
        syncColumnsButton(tab);
      },
    },
    {
      label: "Freeze / unfreeze",
      action: (_e: any, column: any) => {
        const f = view(tab.key).frozen;
        const field = column.getField();
        f.has(field) ? f.delete(field) : f.add(field);
        rebuild(tab);
      },
    },
    {
      label: "Group by this column",
      action: (_e: any, column: any) => {
        view(tab.key).group = [column.getField()];
        state.table?.setGroupBy(column.getField());
      },
    },
    {
      label: "Clear grouping",
      action: () => {
        view(tab.key).group = [];
        state.table?.setGroupBy(false);
      },
    },
  ];
}

function buildColumns(tab: Tab): any[] {
  const v = view(tab.key);
  let ordered = tab.columns;
  if (v.order) {
    // Saved order first (only fields that still exist), then any columns the
    // payload gained since the order was captured, in server order.
    const saved = v.order.filter((f) => tab.columns.some((c) => c.field === f));
    const savedSet = new Set(saved);
    const byField = new Map(tab.columns.map((c) => [c.field, c]));
    ordered = [
      ...saved.map((f) => byField.get(f)!),
      ...tab.columns.filter((c) => !savedSet.has(c.field)),
    ];
  }
  return ordered.map((c) => ({
    title: c.header,
    field: c.field,
    visible: !v.hidden.has(c.field),
    frozen: v.frozen.has(c.field),
    headerFilter: "input",
    headerFilterPlaceholder: "filter…",
    headerMenu: headerMenu(tab),
    bottomCalc: isNumericType(c.type) && c.type !== "percent" ? "sum" : undefined,
    bottomCalcFormatter: c.type === "money" ? "money" : undefined,
    bottomCalcFormatterParams: c.type === "money" ? { symbol: "$", precision: 2, thousand: "," } : undefined,
    ...formatterFor(c),
  }));
}

function view(key: string): ViewState {
  if (!state.views[key]) state.views[key] = freshView();
  return state.views[key];
}

// --------------------------------------------------------------------------
// View-state capture / restore
// --------------------------------------------------------------------------

function captureActive(): void {
  if (!state.table || !state.active) return;
  const t = state.tabs[state.active];
  if (!t || t.layout === "commission_cards") return;
  const v = view(state.active);
  try {
    v.sorters = state.table.getSorters().map((s: any) => ({ column: s.field, dir: s.dir }));
    v.headerFilters = state.table.getHeaderFilters();
    const cols = state.table.getColumns();
    v.order = cols.map((c: any) => c.getField()).filter(Boolean);
    v.hidden = new Set(cols.filter((c: any) => !c.isVisible()).map((c: any) => c.getField()));
  } catch {
    /* table not ready */
  }
}

// --------------------------------------------------------------------------
// Rendering
// --------------------------------------------------------------------------

function renderMeta(tab: Tab): void {
  const meta = $("reportMeta");
  if (!meta) return;
  const gen = state.tabs.__generated_at__ as unknown as string | undefined;
  const parts = [`${tab.rows.length.toLocaleString()} rows`];
  if (gen) parts.push(`as of ${gen}`);
  meta.textContent = parts.join(" · ");
  meta.hidden = false;
}

function rebuild(tab: Tab): void {
  buildTable(tab);
}

function buildTable(tab: Tab): void {
  const host = $("reportTable");
  if (!host) return;
  closeColumnsPanel(); // panel belongs to whichever tab was active before
  if (state.table) {
    try { state.table.destroy(); } catch { /* noop */ }
    state.table = null;
  }
  host.innerHTML = "";

  if (tab.layout === "commission_cards") {
    renderCommissionCards(tab, host);
    renderMeta(tab);
    return;
  }

  const v = view(tab.key);
  state.table = new Tabulator(host, {
    data: tab.rows,
    columns: buildColumns(tab),
    layout: "fitDataTable",
    movableColumns: true,
    columnCalcs: "both",
    height: "62vh",
    nestedFieldSeparator: false, // fields contain "." (e.g. "Cust. #")
    placeholder: "No data for these filters.",
    initialSort: v.sorters?.map((s) => ({ column: s.column, dir: s.dir })),
    initialHeaderFilter: v.headerFilters || undefined,
    groupBy: v.group.length ? v.group : undefined,
  });
  if (v.group.length) {
    state.table.on("tableBuilt", () => state.table.setGroupBy(v.group));
  }
  renderMeta(tab);
}

function n(v: unknown): number {
  const x = Number(v);
  return isFinite(x) ? x : 0;
}
function fmtMoney(v: unknown): string {
  return n(v).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function renderCommissionCards(tab: Tab, host: HTMLElement): void {
  const labels = tab.month_labels || [];
  const wrap = document.createElement("div");
  wrap.className = "commission-cards";

  (tab.salesmen || []).forEach((s) => {
    const card = document.createElement("div");
    card.className = "commission-card";

    const head = document.createElement("div");
    head.className = "commission-card-head";
    const title = document.createElement("div");
    title.className = "commission-card-title";
    title.textContent = `${s.salesman_number} - ${s.salesman_name}`;
    const payable = document.createElement("div");
    payable.className = "commission-card-payable";
    payable.innerHTML = `<span>Total payable</span><strong>${fmtMoney(s.ytd.total_payable ?? s.ytd.commission)}</strong>`;
    head.appendChild(title);
    head.appendChild(payable);
    card.appendChild(head);

    const sub = document.createElement("div");
    sub.className = "commission-card-sub";
    sub.textContent = `Commission ${(n(s.commission_pct) * 100).toFixed(1)}%`;
    card.appendChild(sub);

    const table = document.createElement("table");
    table.className = "commission-month-table";
    table.innerHTML =
      "<thead><tr><th>Month</th><th>Net commission</th><th>Commission</th></tr></thead>";
    const tbody = document.createElement("tbody");
    s.monthly.forEach((m) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${m.month_label}</td><td>${fmtMoney(m.net_commission)}</td><td>${fmtMoney(m.commission)}</td>`;
      tbody.appendChild(tr);
    });
    const tfoot = document.createElement("tfoot");
    tfoot.innerHTML = `<tr><td>YTD</td><td>${fmtMoney(s.ytd.net_commission)}</td><td>${fmtMoney(s.ytd.commission)}</td></tr>`;
    table.appendChild(tbody);
    table.appendChild(tfoot);
    card.appendChild(table);
    wrap.appendChild(card);
  });

  if (!wrap.childElementCount) {
    host.innerHTML = '<div class="empty-state">No commissions for this period.</div>';
    return;
  }
  host.appendChild(wrap);
}

// --------------------------------------------------------------------------
// Tabs
// --------------------------------------------------------------------------

function renderTabs(): void {
  const tabsEl = $("reportTabs");
  if (!tabsEl) return;
  tabsEl.innerHTML = "";
  state.order.forEach((key) => {
    const tab = state.tabs[key];
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "report-tab" + (key === state.active ? " active" : "");
    const nameSpan = document.createElement("span");
    nameSpan.textContent = tab.name;
    btn.appendChild(nameSpan);
    const caret = document.createElement("span");
    caret.className = "report-tab-caret";
    caret.textContent = "\u25be";
    caret.title = "Tab options";
    caret.addEventListener("click", (e) => {
      e.stopPropagation();
      const r = caret.getBoundingClientRect();
      openTabMenuAt(key, r.left + window.scrollX, r.bottom + window.scrollY);
    });
    btn.appendChild(caret);
    btn.addEventListener("click", () => activateTab(key));
    btn.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      openTabMenuAt(key, (e as MouseEvent).pageX, (e as MouseEvent).pageY);
    });
    tabsEl.appendChild(btn);
  });
  tabsEl.hidden = state.order.length === 0;
}

function activateTab(key: string): void {
  if (!state.tabs[key]) return;
  captureActive();
  state.active = key;
  renderTabs();
  buildTable(state.tabs[key]);
  syncColumnsButton(state.tabs[key]);
}

let tabMenuEl: HTMLElement | null = null;
function closeTabMenu(): void {
  tabMenuEl?.remove();
  tabMenuEl = null;
}
function openTabMenuAt(key: string, x: number, y: number): void {
  closeTabMenu();
  const tab = state.tabs[key];
  const menu = document.createElement("div");
  menu.className = "tab-context-menu";
  menu.style.left = x + "px";
  menu.style.top = y + "px";

  const mk = (label: string, fn: () => void, danger = false) => {
    const b = document.createElement("button");
    b.className = "tab-context-item" + (danger ? " danger" : "");
    b.textContent = label;
    b.addEventListener("click", () => { closeTabMenu(); fn(); });
    menu.appendChild(b);
  };
  mk("Duplicate tab", () => duplicateTab(key));
  if ((tab as any)._isDuplicate) {
    mk("Delete tab", () => deleteTab(key), true);
  }
  document.body.appendChild(menu);
  tabMenuEl = menu;
  setTimeout(() => document.addEventListener("click", closeTabMenu, { once: true }), 0);
}

function duplicateTab(key: string): void {
  if (state.active === key) captureActive(); // snapshot the live view we're cloning
  const src = state.tabs[key];
  let i = 2;
  let newKey = `${key}__copy`;
  while (state.tabs[newKey]) newKey = `${key}__copy${i++}`;
  const clone: Tab = JSON.parse(JSON.stringify(src));
  clone.key = newKey;
  clone.name = `${src.name} (copy)`;
  (clone as any)._isDuplicate = true;
  // Track the underlying server tab so a Refresh can re-clone with fresh data.
  (clone as any)._baseKey = (src as any)._baseKey || src.key;
  state.tabs[newKey] = clone;
  state.views[newKey] = cloneView(view(key));
  const idx = state.order.indexOf(key);
  state.order.splice(idx + 1, 0, newKey);
  activateTab(newKey);
}

function deleteTab(key: string): void {
  if (!(state.tabs[key] as any)?._isDuplicate) return;
  const idx = state.order.indexOf(key);
  delete state.tabs[key];
  delete state.views[key];
  state.order.splice(idx, 1);
  activateTab(state.order[Math.max(0, idx - 1)] || state.order[0]);
}

// --------------------------------------------------------------------------
// Columns show/hide panel
// --------------------------------------------------------------------------

function syncColumnsButton(tab: Tab): void {
  const btn = $("columnsBtn") as HTMLButtonElement | null;
  if (!btn) return;
  btn.disabled = tab.layout === "commission_cards";
}

let columnsPanel: HTMLElement | null = null;
function closeColumnsPanel(): void {
  if (columnsPanel) { columnsPanel.remove(); columnsPanel = null; }
  document.removeEventListener("click", onColumnsOutside);
}
function toggleColumnsPanel(): void {
  if (columnsPanel) { closeColumnsPanel(); return; }
  if (!state.active) return;
  const tab = state.tabs[state.active];
  if (tab.layout === "commission_cards") return;
  const v = view(tab.key);
  const anchor = $("columnsBtn");
  const panel = document.createElement("div");
  panel.className = "columns-panel";
  const rect = anchor?.getBoundingClientRect();
  if (rect) { panel.style.top = rect.bottom + 6 + "px"; panel.style.left = rect.left + "px"; }

  tab.columns.forEach((c) => {
    const label = document.createElement("label");
    label.className = "columns-panel-item";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = !v.hidden.has(c.field);
    cb.addEventListener("change", () => {
      if (cb.checked) { v.hidden.delete(c.field); state.table?.showColumn(c.field); }
      else { v.hidden.add(c.field); state.table?.hideColumn(c.field); }
    });
    label.appendChild(cb);
    const span = document.createElement("span");
    span.textContent = c.header;
    label.appendChild(span);
    panel.appendChild(label);
  });
  const restore = document.createElement("button");
  restore.className = "btn btn-sm btn-outline columns-panel-restore";
  restore.textContent = "Show all";
  restore.addEventListener("click", () => {
    v.hidden.clear();
    tab.columns.forEach((c) => state.table?.showColumn(c.field));
    panel.querySelectorAll("input").forEach((i) => ((i as HTMLInputElement).checked = true));
  });
  panel.appendChild(restore);
  document.body.appendChild(panel);
  columnsPanel = panel;
  setTimeout(() => document.addEventListener("click", onColumnsOutside), 0);
}
function onColumnsOutside(e: MouseEvent): void {
  if (columnsPanel && !columnsPanel.contains(e.target as Node) && (e.target as HTMLElement).id !== "columnsBtn") {
    closeColumnsPanel();
  }
}

// --------------------------------------------------------------------------
// Reset / Export
// --------------------------------------------------------------------------

function resetView(): void {
  if (!state.active) return;
  state.views[state.active] = freshView();
  buildTable(state.tabs[state.active]);
}

function exportExcel(): void {
  if (!state.active) return;
  const tab = state.tabs[state.active];
  // Commission cards have no grid; fall back to the server payload export.
  if (tab.layout === "commission_cards" || !state.table) {
    if (state.jobId) window.location.href = attr("data-export-url").replace("__ID__", state.jobId);
    return;
  }
  const name = `${attr("data-report-key")}-${tab.key}`;
  // WYSIWYG: Tabulator exports the current sort/filter/column view. Needs the
  // SheetJS global; if its CDN failed, fall back to the server payload export.
  if (typeof (window as any).XLSX === "undefined") {
    if (state.jobId) window.location.href = attr("data-export-url").replace("__ID__", state.jobId);
    else setStatus("Excel export library didn't load — check your connection and retry.", "error");
    return;
  }
  try {
    state.table.download("xlsx", `${name}.xlsx`, { sheetName: tab.name.slice(0, 28) });
  } catch {
    if (state.jobId) window.location.href = attr("data-export-url").replace("__ID__", state.jobId);
    else setStatus("Could not export this view. Please try again.", "error");
  }
}

// --------------------------------------------------------------------------
// Run + poll
// --------------------------------------------------------------------------

function collectParams(): Record<string, unknown> {
  const form = $("filterForm") as HTMLFormElement | null;
  const out: Record<string, unknown> = {};
  if (!form) return out;
  new FormData(form).forEach((value, key) => {
    const v = String(value).trim();
    if (v) out[key] = v;
  });
  // The customer multi-select isn't a native form control; inject its picks as
  // an array so the server pushes a CSV of accounts to the SP.
  const customers = [...selectedCustomers.keys()];
  if (customers.length) out.customers = customers;
  return out;
}

function loadPayload(payload: Payload, render = true): void {
  state.tabs = {};
  state.order = [];
  state.views = {};
  (state.tabs as any).__generated_at__ = payload.generated_at;
  payload.tabs.forEach((tab) => {
    state.tabs[tab.key] = tab;
    state.order.push(tab.key);
    state.views[tab.key] = freshView();
  });
  state.active = state.order[0] || null;
  setToolbarEnabled(true);
  if (render) {
    renderTabs();
    if (state.active) {
      buildTable(state.tabs[state.active]);
      syncColumnsButton(state.tabs[state.active]);
    }
  }
}

/**
 * Swap in fresh data while keeping the user where they were: same active tab,
 * same tab order, the same per-tab layout (sort/filter/columns/group), and any
 * duplicated tabs re-created from their (now-refreshed) source tab.
 */
function loadPayloadPreserving(payload: Payload): void {
  const prevViews = state.views;
  const prevActive = state.active;
  const prevOrder = [...state.order];
  const duplicates = state.order
    .filter((k) => (state.tabs[k] as any)?._isDuplicate)
    .map((k) => ({
      key: k,
      name: state.tabs[k].name,
      baseKey: (state.tabs[k] as any)._baseKey as string,
      view: prevViews[k],
    }));

  loadPayload(payload, false); // resets to the fresh server tabs (no render yet)

  // Re-create duplicates from their refreshed base tab, preserving their views.
  duplicates.forEach((d) => {
    const base = state.tabs[d.baseKey];
    if (!base) return; // base tab dropped from the payload -> drop the duplicate
    const clone: Tab = JSON.parse(JSON.stringify(base));
    clone.key = d.key;
    clone.name = d.name;
    (clone as any)._isDuplicate = true;
    (clone as any)._baseKey = d.baseKey;
    state.tabs[d.key] = clone;
    state.views[d.key] = d.view || freshView();
  });

  // Restore saved views for surviving server tabs.
  Object.keys(prevViews).forEach((k) => {
    if (state.tabs[k] && !(state.tabs[k] as any)._isDuplicate) state.views[k] = prevViews[k];
  });

  // Restore order: previous keys that still exist, then any newly-added tabs.
  const restored = prevOrder.filter((k) => state.tabs[k]);
  state.order.forEach((k) => { if (!restored.includes(k)) restored.push(k); });
  state.order = restored;

  state.active = prevActive && state.tabs[prevActive] ? prevActive : state.order[0] || null;
  renderTabs();
  if (state.active) {
    buildTable(state.tabs[state.active]);
    syncColumnsButton(state.tabs[state.active]);
  }
}

function cloneView(v: ViewState): ViewState {
  return {
    hidden: new Set(v.hidden),
    frozen: new Set(v.frozen),
    order: v.order ? [...v.order] : null,
    sorters: v.sorters ? v.sorters.map((s) => ({ ...s })) : null,
    headerFilters: v.headerFilters ? v.headerFilters.map((f) => ({ ...f })) : null,
    group: [...v.group],
  };
}

async function poll(jobId: string, opts: { preserveLayout?: boolean } = {}): Promise<void> {
  const jobUrl = attr("data-job-url").replace("__ID__", jobId);
  const resultUrl = attr("data-result-url").replace("__ID__", jobId);

  for (let i = 0; i < 600; i++) {
    const res = await fetch(jobUrl, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error("Lost track of the job (it may have expired) — try running again.");
    const job = await res.json();
    if (job.status === "success") {
      const r = await fetch(resultUrl, { headers: { Accept: "application/json" } });
      if (!r.ok) throw new Error("The report finished but the result couldn't be loaded — re-run to refresh it.");
      const payload: Payload = await r.json();
      state.jobId = jobId;
      clearStatus();
      if (opts.preserveLayout) loadPayloadPreserving(payload);
      else loadPayload(payload);
      return;
    }
    if (job.status === "failure") throw new Error(friendlyError(job.error));
    if (job.status === "cancelled") throw new Error("The run was cancelled.");
    setStatus(`Building report… ${job.progress || 0}%`);
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("Timed out waiting for the report (over 10 minutes). Try a narrower date range.");
}

function friendlyError(raw: unknown): string {
  const s = String(raw || "").trim();
  if (!s) return "The report failed to build. Please try again.";
  // Surface the on-prem API's own message when present, trimmed of stack noise.
  return s.split("\n")[0].slice(0, 300);
}

async function run(opts: { preserveLayout?: boolean } = {}): Promise<void> {
  if (opts.preserveLayout) captureActive();
  setToolbarEnabled(false);
  setStatus(opts.preserveLayout ? "Refreshing data…" : "Starting…");
  try {
    const res = await fetch(attr("data-run-url"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": attr("data-csrf") },
      body: JSON.stringify(collectParams()),
    });
    if (!res.ok) throw new Error(`Could not start the report (HTTP ${res.status}).`);
    const { job_id } = await res.json();
    await poll(job_id, opts);
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Something went wrong.", "error");
  } finally {
    const runBtn = $("runBtn") as HTMLButtonElement | null;
    if (runBtn) runBtn.disabled = false;
  }
}

function setToolbarEnabled(hasData: boolean): void {
  (["refreshBtn", "resetBtn", "exportBtn", "columnsBtn"] as const).forEach((id) => {
    const b = $(id) as HTMLButtonElement | null;
    if (b) b.disabled = !hasData;
  });
  const runBtn = $("runBtn") as HTMLButtonElement | null;
  if (runBtn) runBtn.disabled = false;
}

// --------------------------------------------------------------------------
// Filters / boot
// --------------------------------------------------------------------------

function initCustomRangeToggle(): void {
  const sel = $("periodSelect") as HTMLSelectElement | null;
  if (!sel) return;
  const customs = Array.from(document.querySelectorAll<HTMLElement>("[data-custom]"));
  const sync = () => customs.forEach((c) => (c.hidden = sel.value !== "custom"));
  sel.addEventListener("change", sync);
  sync();
}

// --------------------------------------------------------------------------
// Lookups: salesman dropdown + searchable customer multi-select, deep-links,
// and the live API-preview panel. Lists load non-blocking and the form polls
// lookup-status until the server-side warm-up is ready.
// --------------------------------------------------------------------------

interface LookupRow { key: string; name: string; salesman?: string; }

const selectedCustomers = new Map<string, string>(); // account -> display name
let customerOptions: LookupRow[] = [];
let lookupPollTimer: number | null = null;

function hasFilter(id: string): boolean {
  return !!$(id);
}

async function getJSON<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

async function loadSalesmen(): Promise<void> {
  const sel = $("salesmanSelect") as HTMLSelectElement | null;
  if (!sel) return;
  const data = await getJSON<{ salesmen: LookupRow[] }>(attr("data-salesmen-url"));
  const rows = data?.salesmen || [];
  const current = sel.value;
  sel.innerHTML = '<option value="">All salesmen</option>';
  rows.forEach((r) => {
    const o = document.createElement("option");
    o.value = r.key;
    o.textContent = r.name;
    sel.appendChild(o);
  });
  if (current && rows.some((r) => r.key === current)) sel.value = current;
}

async function loadCustomers(): Promise<void> {
  if (!hasFilter("customerPicker")) return;
  const sel = $("salesmanSelect") as HTMLSelectElement | null;
  const salesman = sel?.value ? `?salesman=${encodeURIComponent(sel.value)}` : "";
  const data = await getJSON<{ customers: LookupRow[] }>(attr("data-customers-url") + salesman);
  customerOptions = data?.customers || [];
  renderCustomerPicker();
}

function renderCustomerPicker(filterText = ""): void {
  const host = $("customerPicker");
  if (!host) return;
  const q = filterText.trim().toLowerCase();
  const matches = q
    ? customerOptions.filter(
        (c) => c.name.toLowerCase().includes(q) || c.key.toLowerCase().includes(q),
      )
    : customerOptions;

  host.innerHTML = "";

  const chips = document.createElement("div");
  chips.className = "customer-chips";
  if (selectedCustomers.size === 0) {
    const ph = document.createElement("span");
    ph.className = "customer-placeholder";
    ph.textContent = host.dataset.placeholder || "All";
    chips.appendChild(ph);
  } else {
    selectedCustomers.forEach((name, key) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "customer-chip";
      chip.textContent = `${name} ✕`;
      chip.title = `Remove ${key}`;
      chip.addEventListener("click", () => {
        selectedCustomers.delete(key);
        renderCustomerPicker(search.value);
      });
      chips.appendChild(chip);
    });
  }
  host.appendChild(chips);

  const search = document.createElement("input");
  search.type = "text";
  search.className = "customer-search";
  search.placeholder = "Search customers…";
  search.value = filterText;
  search.addEventListener("input", () => renderCustomerPicker(search.value));
  host.appendChild(search);

  const list = document.createElement("div");
  list.className = "customer-options";
  matches.slice(0, 200).forEach((c) => {
    const row = document.createElement("label");
    row.className = "customer-option";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = selectedCustomers.has(c.key);
    cb.addEventListener("change", () => {
      if (cb.checked) selectedCustomers.set(c.key, c.name);
      else selectedCustomers.delete(c.key);
      // Re-render chips without losing the search box focus/value.
      renderChipsOnly();
    });
    row.appendChild(cb);
    const text = document.createElement("span");
    text.textContent = `${c.key} — ${c.name}`;
    row.appendChild(text);
    list.appendChild(row);
  });
  if (!matches.length) {
    const empty = document.createElement("div");
    empty.className = "customer-empty";
    empty.textContent = customerOptions.length ? "No matches" : "Loading…";
    list.appendChild(empty);
  }
  host.appendChild(list);

  // Keep focus in the search box after a re-render triggered by typing.
  if (filterText) {
    search.focus();
    search.setSelectionRange(filterText.length, filterText.length);
  }

  function renderChipsOnly(): void {
    renderCustomerPicker(search.value);
  }
}

function setLookupStatusText(text: string): void {
  ["salesmanStatus", "customerStatus"].forEach((id) => {
    const el = $(id);
    if (el) el.textContent = text;
  });
}

function pollLookupStatus(): void {
  const url = attr("data-lookup-status-url");
  if (!url) return;
  const tick = async () => {
    const s = await getJSON<any>(url);
    if (!s) return;
    if (s.status === "ready" || (s.cached_row_count || 0) > 0) {
      setLookupStatusText("");
      if (lookupPollTimer) { window.clearInterval(lookupPollTimer); lookupPollTimer = null; }
      await loadSalesmen();
      await loadCustomers();
      return;
    }
    if (s.status === "loading") setLookupStatusText("(loading…)");
    else if (s.status === "error") setLookupStatusText("(using cached list)");
    else if (!s.configured) setLookupStatusText("");
  };
  tick();
  lookupPollTimer = window.setInterval(tick, 2500);
}

async function initLookups(): Promise<void> {
  if (!hasFilter("salesmanSelect") && !hasFilter("customerPicker")) return;
  if (hasFilter("salesmanSelect")) {
    await loadSalesmen();
    $("salesmanSelect")?.addEventListener("change", () => {
      selectedCustomers.clear();
      loadCustomers();
    });
  }
  if (hasFilter("customerPicker")) {
    renderCustomerPicker();
    await loadCustomers();
  }
  pollLookupStatus();
}

// --- bookmarkable deep-links --------------------------------------------- //

function applyDeepLink(): void {
  const q = new URLSearchParams(window.location.search);
  if (![...q.keys()].length) return;
  (["period", "status", "year"] as const).forEach((name) => {
    const el = document.querySelector<HTMLSelectElement | HTMLInputElement>(`[name="${name}"]`);
    if (el && q.has(name)) el.value = q.get(name) || "";
  });
  const sm = $("salesmanSelect") as HTMLSelectElement | null;
  if (sm && q.has("salesman")) sm.value = q.get("salesman") || "";
  const sd = document.querySelector<HTMLInputElement>('[name="start_date"]');
  const ed = document.querySelector<HTMLInputElement>('[name="end_date"]');
  if (sd && q.has("start_date")) sd.value = q.get("start_date") || "";
  if (ed && q.has("end_date")) ed.value = q.get("end_date") || "";
  const custs = q.get("customers");
  if (custs) custs.split(",").forEach((c) => { const k = c.trim(); if (k) selectedCustomers.set(k, k); });
}

function updateDeepLink(): void {
  const params = collectParams();
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    q.set(k, Array.isArray(v) ? v.join(",") : String(v));
  });
  const url = `${window.location.pathname}?${q.toString()}`;
  window.history.replaceState(null, "", url);
}

// --- live API preview ----------------------------------------------------- //

async function showApiPreview(): Promise<void> {
  const panel = $("apiPreview");
  if (!panel) return;
  if (!panel.hidden) { panel.hidden = true; return; }
  panel.hidden = false;
  panel.textContent = "Loading preview…";
  try {
    const res = await fetch(attr("data-preview-url"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": attr("data-csrf") },
      body: JSON.stringify(collectParams()),
    });
    const data = await res.json();
    panel.textContent = JSON.stringify(data, null, 2);
  } catch {
    panel.textContent = "Could not load the API preview.";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (!root) return;
  initCustomRangeToggle();
  applyDeepLink();
  initLookups();
  $("runBtn")?.addEventListener("click", () => { updateDeepLink(); run(); });
  $("refreshBtn")?.addEventListener("click", () => run({ preserveLayout: true }));
  $("resetBtn")?.addEventListener("click", resetView);
  $("exportBtn")?.addEventListener("click", exportExcel);
  $("columnsBtn")?.addEventListener("click", (e) => { e.stopPropagation(); toggleColumnsPanel(); });
  $("previewBtn")?.addEventListener("click", showApiPreview);
  setToolbarEnabled(false);
});

export {};

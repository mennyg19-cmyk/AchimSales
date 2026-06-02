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
 * and a styled Excel export (built server-side by openpyxl) of every tab that
 * reflects each tab's on-screen view, with live-style formatting + group totals.
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

/** One Excel-style per-column filter: an operator plus up to two values. */
interface ColFilter { op: string; v: string; v2?: string; }

/** Captured, re-applyable view state for one tab. */
interface ViewState {
  hidden: Set<string>;
  frozen: Set<string>;
  order: string[] | null;
  sorters: { column: string; dir: string }[] | null;
  columnFilters: Record<string, ColFilter>;
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

function fmtElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
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
  return { hidden: new Set(), frozen: new Set(), order: null, sorters: null, columnFilters: {}, group: [] };
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
    titleFormatter: () => columnHeaderEl(tab, c),
    headerMenu: headerMenu(tab),
    bottomCalc: isNumericType(c.type) && c.type !== "percent" ? "sum" : undefined,
    bottomCalcFormatter: c.type === "money" ? "money" : undefined,
    bottomCalcFormatterParams: c.type === "money" ? { symbol: "$", precision: 2, thousand: "," } : undefined,
    ...formatterFor(c),
  }));
}

/** A header cell: the column label plus an Excel-style filter funnel button. */
const FUNNEL_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon></svg>';

function columnHeaderEl(tab: Tab, col: Column): HTMLElement {
  const wrap = document.createElement("div");
  wrap.className = "col-header-inner";
  const label = document.createElement("span");
  label.className = "col-header-label";
  label.textContent = col.header;
  wrap.appendChild(label);

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "col-filter-btn";
  btn.dataset.field = col.field;
  btn.title = "Filter this column";
  btn.innerHTML = FUNNEL_SVG;
  if (view(tab.key).columnFilters[col.field]) btn.classList.add("has-active-filter");
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation(); // don't trigger the column sort
    openColumnFilterPopover(col, btn);
  });
  wrap.appendChild(btn);
  return wrap;
}

function view(key: string): ViewState {
  if (!state.views[key]) state.views[key] = freshView();
  return state.views[key];
}

// --------------------------------------------------------------------------
// Excel-style per-column filters (operator + value), applied client-side via a
// single Tabulator function filter so totals recalc on the filtered rows.
// --------------------------------------------------------------------------

interface OpDef { op: string; label: string; }
const TEXT_OPS: OpDef[] = [
  { op: "contains", label: "contains" },
  { op: "equals", label: "equals" },
  { op: "starts", label: "starts with" },
  { op: "ends", label: "ends with" },
  { op: "in", label: "is one of (comma-separated)" },
  { op: "empty", label: "is empty" },
  { op: "notEmpty", label: "is not empty" },
];
const NUM_OPS: OpDef[] = [
  { op: "eq", label: "equals" },
  { op: "ne", label: "not equal to" },
  { op: "gt", label: "greater than" },
  { op: "ge", label: "greater than or equal" },
  { op: "lt", label: "less than" },
  { op: "le", label: "less than or equal" },
  { op: "between", label: "between" },
  { op: "empty", label: "is empty" },
  { op: "notEmpty", label: "is not empty" },
];
const DATE_OPS: OpDef[] = [
  { op: "on", label: "on" },
  { op: "before", label: "before" },
  { op: "after", label: "after" },
  { op: "between", label: "between" },
  { op: "empty", label: "is empty" },
  { op: "notEmpty", label: "is not empty" },
];

function operatorsFor(type?: string): OpDef[] {
  if (isNumericType(type)) return NUM_OPS;
  if (type === "date") return DATE_OPS;
  return TEXT_OPS;
}
function opNeedsTwoValues(op: string): boolean { return op === "between"; }
function opNeedsNoValue(op: string): boolean { return op === "empty" || op === "notEmpty"; }

function num(x: unknown): number | null {
  // Strict: reject "12abc" so this stays in lock-step with the server-side
  // parser in delivery/layout.py (which uses Python float()).
  const s = String(x).replace(/[$,%\s]/g, "");
  if (s === "") return null;
  const v = Number(s);
  return isFinite(v) ? v : null;
}

/** Does one row pass one column's filter? */
function rowMatches(row: Record<string, unknown>, field: string, type: string | undefined, f: ColFilter): boolean {
  const raw = row[field];
  if (f.op === "empty") return raw === "" || raw == null;
  if (f.op === "notEmpty") return !(raw === "" || raw == null);

  if (isNumericType(type)) {
    const x = num(raw);
    const a = num(f.v);
    if (x == null || a == null) return false;
    switch (f.op) {
      case "eq": return x === a;
      case "ne": return x !== a;
      case "gt": return x > a;
      case "ge": return x >= a;
      case "lt": return x < a;
      case "le": return x <= a;
      case "between": { const b = num(f.v2); return b == null ? x >= a : x >= a && x <= b; }
    }
    return true;
  }
  if (type === "date") {
    const d = String(raw ?? "").slice(0, 10);
    const a = String(f.v ?? "").slice(0, 10);
    const b = String(f.v2 ?? "").slice(0, 10);
    switch (f.op) {
      case "on": return d === a;
      case "before": return !!d && d < a;
      case "after": return !!d && d > a;
      case "between": return (!a || d >= a) && (!b || d <= b);
    }
    return true;
  }
  const s = String(raw ?? "").toLowerCase();
  const q = String(f.v ?? "").toLowerCase();
  switch (f.op) {
    case "contains": return s.includes(q);
    case "equals": return s === q;
    case "starts": return s.startsWith(q);
    case "ends": return s.endsWith(q);
    case "in": return q.split(",").map((p) => p.trim()).filter(Boolean).includes(s);
  }
  return s.includes(q);
}

/** Filters that are actually "armed" (have the value(s) their operator needs). */
function activeColumnFilters(tab: Tab): { field: string; type?: string; f: ColFilter }[] {
  const cf = view(tab.key).columnFilters;
  const typeByField = new Map(tab.columns.map((c) => [c.field, c.type]));
  const out: { field: string; type?: string; f: ColFilter }[] = [];
  Object.keys(cf).forEach((field) => {
    const f = cf[field];
    if (!f) return;
    if (opNeedsNoValue(f.op)) out.push({ field, type: typeByField.get(field), f });
    else if (f.v !== "" && f.v != null) out.push({ field, type: typeByField.get(field), f });
  });
  return out;
}

function applyColumnFilters(): void {
  if (!state.table || !state.active) return;
  const tab = state.tabs[state.active];
  if (!tab || tab.layout === "commission_cards") return;
  const active = activeColumnFilters(tab);
  try {
    if (!active.length) state.table.clearFilter();
    else state.table.setFilter((row: Record<string, unknown>) => active.every((a) => rowMatches(row, a.field, a.type, a.f)));
  } catch { /* table not ready */ }
  updateFunnelStates();
}

function updateFunnelStates(): void {
  if (!state.active) return;
  const cf = view(state.active).columnFilters;
  document.querySelectorAll<HTMLElement>(".col-filter-btn").forEach((btn) => {
    btn.classList.toggle("has-active-filter", !!cf[btn.dataset.field || ""]);
  });
}

let colFilterPopover: HTMLElement | null = null;
let colFilterAbort: AbortController | null = null;
function closeColumnFilterPopover(): void {
  colFilterPopover?.remove();
  colFilterPopover = null;
  colFilterAbort?.abort(); // drops the Escape + outside-click listeners
  colFilterAbort = null;
}

function openColumnFilterPopover(col: Column, anchor: HTMLElement): void {
  // Clicking the same funnel toggles closed; a different funnel switches to it.
  const sameField = colFilterPopover?.dataset.field === col.field;
  closeColumnFilterPopover();
  if (sameField || !state.active) return;
  const cf = view(state.active).columnFilters;
  const ops = operatorsFor(col.type);
  const current: ColFilter = cf[col.field] || { op: ops[0].op, v: "", v2: "" };

  const panel = document.createElement("div");
  panel.className = "col-filter-popover";
  panel.dataset.field = col.field;

  const title = document.createElement("div");
  title.className = "col-filter-popover-title";
  title.textContent = col.header;
  panel.appendChild(title);

  const opSel = document.createElement("select");
  ops.forEach((o) => {
    const opt = document.createElement("option");
    opt.value = o.op;
    opt.textContent = o.label;
    if (o.op === current.op) opt.selected = true;
    opSel.appendChild(opt);
  });
  panel.appendChild(opSel);

  const values = document.createElement("div");
  values.className = "cf-values";
  panel.appendChild(values);

  const inputType = col.type === "date" ? "date" : isNumericType(col.type) ? "number" : "text";
  const v1 = document.createElement("input");
  v1.type = inputType;
  v1.value = current.v || "";
  const v2 = document.createElement("input");
  v2.type = inputType;
  v2.value = current.v2 || "";

  const syncValueInputs = () => {
    values.innerHTML = "";
    const op = opSel.value;
    if (opNeedsNoValue(op)) return;
    v1.placeholder = col.type === "text" || !col.type ? (op === "in" ? "a, b, c" : "value") : "";
    values.appendChild(v1);
    if (opNeedsTwoValues(op)) { v2.placeholder = "and"; values.appendChild(v2); }
  };
  opSel.addEventListener("change", syncValueInputs);
  syncValueInputs();

  const foot = document.createElement("div");
  foot.className = "col-filter-popover-foot";
  const clear = document.createElement("button");
  clear.type = "button";
  clear.className = "btn btn-sm btn-outline";
  clear.textContent = "Clear";
  clear.addEventListener("click", () => {
    delete cf[col.field];
    applyColumnFilters();
    closeColumnFilterPopover();
  });
  const apply = document.createElement("button");
  apply.type = "button";
  apply.className = "btn btn-sm btn-primary";
  apply.textContent = "Apply";
  const doApply = () => {
    const op = opSel.value;
    if (opNeedsNoValue(op)) cf[col.field] = { op, v: "" };
    else if (v1.value.trim() === "") delete cf[col.field];
    else cf[col.field] = { op, v: v1.value.trim(), v2: opNeedsTwoValues(op) ? v2.value.trim() : "" };
    applyColumnFilters();
    closeColumnFilterPopover();
  };
  apply.addEventListener("click", doApply);
  [v1, v2].forEach((i) => i.addEventListener("keydown", (e) => { if ((e as KeyboardEvent).key === "Enter") doApply(); }));
  foot.append(clear, apply);
  panel.appendChild(foot);

  // Anchor under the funnel, nudged left so a 240px panel stays on screen.
  const r = anchor.getBoundingClientRect();
  panel.style.top = `${Math.round(r.bottom + 4)}px`;
  panel.style.left = `${Math.round(Math.min(r.left, window.innerWidth - 252))}px`;
  document.body.appendChild(panel);
  colFilterPopover = panel;
  colFilterAbort = new AbortController();
  const { signal } = colFilterAbort;
  (opNeedsNoValue(opSel.value) ? opSel : v1).focus();
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeColumnFilterPopover(); }, { signal });
  // The funnel handler stops propagation, so this bubble-phase listener fires
  // only for clicks elsewhere; the timeout skips the opening click itself.
  setTimeout(() => {
    document.addEventListener("click", (e) => {
      if (colFilterPopover && !colFilterPopover.contains(e.target as Node)) closeColumnFilterPopover();
    }, { signal });
  }, 0);
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
  const table = new Tabulator(host, {
    data: tab.rows,
    columns: buildColumns(tab),
    layout: "fitDataTable",
    movableColumns: true,
    columnCalcs: "both",
    height: "calc(100vh - 230px)",
    nestedFieldSeparator: false, // fields contain "." (e.g. "Cust. #")
    placeholder: "No data for these filters.",
    initialSort: v.sorters?.map((s) => ({ column: s.column, dir: s.dir })),
    groupBy: v.group.length ? v.group : undefined,
  });
  state.table = table;
  table.on("tableBuilt", () => {
    // A build from a previous tab can fire late; ignore it if we've moved on.
    if (state.table !== table || state.active !== tab.key) return;
    if (v.group.length) table.setGroupBy(v.group);
    applyColumnFilters(); // replay any saved per-column filters
  });
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

/** Export every tab as a styled workbook. The server (openpyxl) owns the look -
 *  bold grey headers, currency/percent/date formats, and per-group + grand
 *  totals - so it matches the live app's exports. The server builds it in the
 *  BACKGROUND (streaming openpyxl) so a huge report no longer blocks/times out
 *  the request; we kick off the job, show a live timer, auto-download when ready,
 *  and keep it in "Recent exports" so the user can navigate away and grab it
 *  later in seconds. */

/** Map an export HTTP failure to a human, actionable message. Flask abort()
 *  bodies are HTML, so we key off the status rather than parsing the body. */
function exportErrorFor(status: number): string {
  switch (status) {
    case 404: return "The report result expired \u2014 re-run the report, then export.";
    case 409: return "The report isn't ready yet \u2014 run it first, then export.";
    case 413: return "This export is too large \u2014 hide some columns or narrow the date range.";
    default:  return `Could not start the export (HTTP ${status}). Please try again.`;
  }
}

async function exportExcel(): Promise<void> {
  if (!state.jobId) { setStatus("Run the report first, then export.", "error"); return; }
  const url = attr("data-export-url").replace("__ID__", state.jobId);
  exportPageKey = attr("data-report-key");  // lock the auto-download to this page
  try {
    const res = await fetch(url, {
      method: "POST", headers: csrfHeaders(), body: JSON.stringify(serializeLayout()),
    });
    if (!res.ok) throw new Error(exportErrorFor(res.status));
    const { export_id } = await res.json();
    setStatus("Your Excel file is building in the background \u2014 see Recent exports.");
    loadExports();                 // surface it immediately as "building"
    pollExport(export_id, true);   // auto-download when ready (if still on this page)
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Could not start the export.", "error");
  }
}

// --- Recent exports (durable background jobs) ---------------------------- //

interface ExportRow {
  export_id: string; status: string; progress: number; report_title: string;
  filename: string; size_bytes: number; built_at: string; ready: boolean; error: string;
}

let exportsPollTimer: number | null = null;
const autoDownloaded = new Set<string>();

function downloadExportUrl(id: string): string {
  return attr("data-export-download-url").replace("__ID__", id);
}

function triggerDownload(id: string): void {
  const a = document.createElement("a");
  a.href = downloadExportUrl(id);
  a.download = "";  // let the server's Content-Disposition name it
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** The report key of the page at the time the user clicked Export. Checked
 *  before auto-downloading so a navigation to a different report doesn't
 *  trigger a stale download (the user can still grab it from Recent exports). */
let exportPageKey: string | null = null;

/** True when the user is still on the same report page they started the export
 *  from AND the page is visible. If they navigated away within the SPA-like
 *  shell or switched to a hidden tab, the auto-download is suppressed. */
function isExportPageActive(): boolean {
  return document.visibilityState === "visible"
    && exportPageKey === attr("data-report-key");
}

/** Poll one export job to completion; auto-download ONLY if the user is still
 *  on the same report page (visible). If they navigated away, the file is in
 *  Recent exports for manual download — no surprise file appearing later. */
async function pollExport(id: string, autoDownload: boolean): Promise<void> {
  const jobUrl = attr("data-job-url").replace("__ID__", id);
  for (let i = 0; i < 600; i++) {
    const res = await fetch(jobUrl, { headers: { Accept: "application/json" } });
    if (!res.ok) break;
    const job = await res.json();
    loadExports();
    if (job.status === "success") {
      if (autoDownload && !autoDownloaded.has(id) && isExportPageActive()) {
        autoDownloaded.add(id);
        triggerDownload(id);
      }
      if (exportStatusActive()) clearStatus();
      return;
    }
    if (job.status === "failure" || job.status === "cancelled") {
      if (exportStatusActive()) setStatus(job.error || "The export failed. Please try again.", "error");
      return;
    }
    await new Promise((r) => setTimeout(r, 1500));
  }
}

/** True while the status line is showing the export message (so a poll result
 *  doesn't stomp on an unrelated run/refresh status). */
function exportStatusActive(): boolean {
  const el = $("reportStatus");
  return !!el && !el.hidden && el.textContent !== null && el.textContent.indexOf("Excel") >= 0;
}

function fmtBytes(n: number): string {
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

async function loadExports(): Promise<void> {
  const list = $("exportsList");
  if (!list) return;
  const data = await getJSON<{ exports: ExportRow[] }>(attr("data-exports-url"));
  const rows = data?.exports || [];
  renderExports(rows);
  // Keep polling the list while anything is still building.
  const building = rows.some((r) => r.status === "queued" || r.status === "running");
  if (building && exportsPollTimer == null) {
    exportsPollTimer = window.setInterval(loadExports, 2000);
  } else if (!building && exportsPollTimer != null) {
    window.clearInterval(exportsPollTimer);
    exportsPollTimer = null;
  }
}

function renderExports(rows: ExportRow[]): void {
  const list = $("exportsList");
  if (!list) return;
  list.innerHTML = "";
  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "exports-empty";
    empty.textContent = "No exports yet. Click Export to build one.";
    list.appendChild(empty);
    return;
  }
  rows.forEach((r) => {
    const item = document.createElement("div");
    item.className = "exports-item";
    const label = document.createElement("span");
    label.className = "exports-item-label";
    label.textContent = r.report_title || r.filename || "Export";
    item.appendChild(label);
    const meta = document.createElement("span");
    meta.className = "exports-item-meta";
    if (r.status === "success" && r.ready) {
      const dl = document.createElement("a");
      dl.className = "btn btn-outline btn-sm";
      dl.href = downloadExportUrl(r.export_id);
      dl.textContent = `Download${r.size_bytes ? ` (${fmtBytes(r.size_bytes)})` : ""}`;
      meta.appendChild(dl);
    } else if (r.status === "success") {
      // Job done but the blob was reaped/expired - re-export rebuilds it.
      meta.textContent = "Expired \u2014 export again";
      meta.classList.add("exports-item-failed");
    } else if (r.status === "failure" || r.status === "cancelled") {
      meta.textContent = r.error ? `Failed: ${r.error}` : "Failed";
      meta.classList.add("exports-item-failed");
    } else {
      meta.textContent = `Building\u2026 ${r.progress || 0}%`;
    }
    item.appendChild(meta);
    list.appendChild(item);
  });
}

function toggleExportsPanel(): void {
  const panel = $("exportsPanel");
  if (!panel) return;
  panel.hidden = !panel.hidden;
  if (!panel.hidden) loadExports();
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
    const v = freshView();
    if (Array.isArray((tab as any).default_group) && (tab as any).default_group.length) {
      v.group = [...(tab as any).default_group];
    }
    state.views[tab.key] = v;
  });
  state.active = state.order[0] || null;
  setToolbarEnabled(true);
  if (render) {
    renderTabs();
    if (state.active) {
      buildTable(state.tabs[state.active]);
      syncColumnsButton(state.tabs[state.active]);
    }
    showReportSurface();
    setControlsCollapsed(true);
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
  showReportSurface();
  setControlsCollapsed(true);
}

function cloneView(v: ViewState): ViewState {
  return {
    hidden: new Set(v.hidden),
    frozen: new Set(v.frozen),
    order: v.order ? [...v.order] : null,
    sorters: v.sorters ? v.sorters.map((s) => ({ ...s })) : null,
    columnFilters: JSON.parse(JSON.stringify(v.columnFilters || {})),
    group: [...v.group],
  };
}

async function poll(jobId: string, opts: { preserveLayout?: boolean } = {}): Promise<void> {
  const jobUrl = attr("data-job-url").replace("__ID__", jobId);
  const resultUrl = attr("data-result-url").replace("__ID__", jobId);
  const started = Date.now();

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
      if (pendingLayout) { applyLayout(pendingLayout); pendingLayout = null; }
      return;
    }
    if (job.status === "failure") throw new Error(friendlyError(job.error));
    if (job.status === "cancelled") throw new Error("The run was cancelled.");
    setStatus(`Building report… ${job.progress || 0}% (${fmtElapsed(Date.now() - started)})`);
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

async function run(opts: { preserveLayout?: boolean; overrideParams?: Record<string, unknown> } = {}): Promise<void> {
  if (opts.preserveLayout) captureActive();
  setToolbarEnabled(false);
  setStatus(opts.preserveLayout ? "Refreshing data…" : "Starting…");
  try {
    const params = opts.overrideParams ?? collectParams();
    const res = await fetch(attr("data-run-url"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": attr("data-csrf") },
      body: JSON.stringify(params),
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
  (["refreshBtn", "resetBtn", "exportBtn", "columnsBtn", "saveViewBtn", "emailBtn", "scheduleBtn"] as const).forEach((id) => {
    const b = $(id) as HTMLButtonElement | null;
    if (b) b.disabled = !hasData;
  });
  const runBtn = $("runBtn") as HTMLButtonElement | null;
  if (runBtn) runBtn.disabled = false;
}

// --------------------------------------------------------------------------
// Collapsible "Filters & options" panel: once a report is showing, fold the
// controls into a one-line summary so the grid takes most of the screen.
// --------------------------------------------------------------------------

function showReportSurface(): void {
  const s = $("reportSurface");
  if (s) s.hidden = false;
}

function setControlsCollapsed(collapsed: boolean): void {
  const c = $("reportControls");
  if (!c) return;
  c.classList.toggle("collapsed", collapsed);
  $("controlsToggle")?.setAttribute("aria-expanded", String(!collapsed));
  if (collapsed) updateControlsSummary();
}

function updateControlsSummary(): void {
  const el = $("controlsSummary");
  if (!el) return;
  const parts: string[] = [];
  document.querySelectorAll<HTMLSelectElement>("#filterForm select").forEach((sel) => {
    const opt = sel.options[sel.selectedIndex];
    if (opt && opt.textContent) parts.push(opt.textContent.trim());
  });
  const sd = (document.querySelector('[name="start_date"]') as HTMLInputElement | null)?.value;
  const ed = (document.querySelector('[name="end_date"]') as HTMLInputElement | null)?.value;
  if (sd || ed) parts.push(`${sd || "…"} – ${ed || "…"}`);
  if (selectedCustomers.size) parts.push(`${selectedCustomers.size} customer${selectedCustomers.size > 1 ? "s" : ""}`);
  el.textContent = parts.filter(Boolean).join("  ·  ");
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
let customerPickerOpen = false;       // is the options dropdown showing?
let customerHandlersBound = false;    // document/window listeners bound once
let lookupPollTimer: number | null = null;
let pendingSalesman: string | null = null; // deep-link salesman, applied after options load
let previewTimer: number | null = null;
let pendingLayout: SavedLayout | null = null; // preset layout to apply after the next run
let autoRunRequested = false;                 // ?preset=<id> deep-link wants an auto-run

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

/** Position the options list as a fixed overlay under the search field, so no
 *  overflow ancestor (the filter row) can clip it. */
function positionCustomerOptions(): void {
  const host = $("customerPicker");
  const search = host?.querySelector<HTMLElement>(".customer-search");
  const list = host?.querySelector<HTMLElement>(".customer-options");
  if (!search || !list || list.hidden) return;
  const r = search.getBoundingClientRect();
  list.style.position = "fixed";
  list.style.top = `${Math.round(r.bottom + 2)}px`;
  list.style.left = `${Math.round(r.left)}px`;
  list.style.width = `${Math.round(r.width)}px`;
}

/** Bind document/window listeners that close + reposition the picker. Once. */
function ensureCustomerHandlers(): void {
  if (customerHandlersBound) return;
  customerHandlersBound = true;
  const inside = (t: Node) => {
    const p = $("customerPicker");
    const pills = $("customerPills");
    return !!((p && p.contains(t)) || (pills && pills.contains(t)));
  };
  document.addEventListener("click", (e) => {
    if (customerPickerOpen && !inside(e.target as Node)) closeCustomerOptions();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && customerPickerOpen) closeCustomerOptions();
  });
  window.addEventListener("scroll", positionCustomerOptions, true);
  window.addEventListener("resize", positionCustomerOptions);
}

/** Build the persistent search input + (hidden) options list once. */
function ensureCustomerInput(): HTMLInputElement | null {
  const host = $("customerPicker");
  if (!host) return null;
  let search = host.querySelector<HTMLInputElement>(".customer-search");
  if (search) return search;
  host.innerHTML = "";
  search = document.createElement("input");
  search.type = "text";
  search.className = "customer-search";
  search.placeholder = host.dataset.placeholder || "All customers";
  search.setAttribute("role", "combobox");
  search.addEventListener("focus", () => { customerPickerOpen = true; renderCustomerOptions(); });
  search.addEventListener("input", () => { customerPickerOpen = true; renderCustomerOptions(); });
  host.appendChild(search);
  const list = document.createElement("div");
  list.className = "customer-options";
  list.hidden = true;
  host.appendChild(list);
  return search;
}

function closeCustomerOptions(): void {
  customerPickerOpen = false;
  const list = $("customerPicker")?.querySelector<HTMLElement>(".customer-options");
  if (list) list.hidden = true;
}

/** Render the open dropdown of matching customers (checkbox per row). */
function renderCustomerOptions(): void {
  const host = $("customerPicker");
  const search = ensureCustomerInput();
  const list = host?.querySelector<HTMLElement>(".customer-options");
  if (!host || !search || !list) return;
  if (!customerPickerOpen) { list.hidden = true; return; }

  const q = search.value.trim().toLowerCase();
  const matches = q
    ? customerOptions.filter(
        (c) => c.name.toLowerCase().includes(q) || c.key.toLowerCase().includes(q),
      )
    : customerOptions;

  list.innerHTML = "";
  matches.slice(0, 200).forEach((c) => {
    const row = document.createElement("label");
    row.className = "customer-option";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = selectedCustomers.has(c.key);
    cb.addEventListener("change", () => {
      if (cb.checked) selectedCustomers.set(c.key, c.name);
      else selectedCustomers.delete(c.key);
      renderCustomerPills();
      refreshPreviewIfOpen();
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
  list.hidden = false;
  positionCustomerOptions();
}

/** Render the selected customers as removable pills (separate from the field). */
function renderCustomerPills(): void {
  const host = $("customerPills");
  if (!host) return;
  host.innerHTML = "";
  selectedCustomers.forEach((name, key) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "customer-chip";
    chip.textContent = `${name} ✕`;
    chip.title = `Remove ${key}`;
    chip.addEventListener("click", () => {
      selectedCustomers.delete(key);
      renderCustomerPills();
      if (customerPickerOpen) renderCustomerOptions();
      refreshPreviewIfOpen();
    });
    host.appendChild(chip);
  });
}

function renderCustomerPicker(): void {
  if (!hasFilter("customerPicker")) return;
  ensureCustomerHandlers();
  ensureCustomerInput();
  renderCustomerPills();
  renderCustomerOptions();
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
    // Apply a deep-linked salesman now that its <option> exists (setting .value
    // before load is silently dropped). Don't clear deep-linked customers here.
    const sel = $("salesmanSelect") as HTMLSelectElement | null;
    if (sel && pendingSalesman != null) {
      sel.value = pendingSalesman;
      pendingSalesman = null;
    }
    sel?.addEventListener("change", () => {
      selectedCustomers.clear();
      loadCustomers();
      refreshPreviewIfOpen();
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
  // The salesman <option>s aren't loaded yet; stash the value and apply it in
  // initLookups() after the list arrives (setting .value now would be lost).
  if (q.has("salesman")) pendingSalesman = q.get("salesman") || "";
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

async function renderApiPreview(): Promise<void> {
  const panel = $("apiPreview");
  if (!panel || panel.hidden) return;
  panel.textContent = "Loading preview…";
  try {
    const res = await fetch(attr("data-preview-url"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": attr("data-csrf") },
      body: JSON.stringify(collectParams()),
    });
    const data = await res.json();
    // Show ONLY the request body (the PascalCase SP params), not the method /
    // url / wrapper - that's the part the owner cares about.
    const body = data && typeof data === "object" && "body" in data ? data.body : data;
    let out = JSON.stringify(body, null, 2);
    if (data && data.warning) out = `// ${data.warning}\n${out}`;
    panel.textContent = out;
  } catch {
    panel.textContent = "Could not load the API preview.";
  }
}

function showApiPreview(): void {
  const panel = $("apiPreview");
  if (!panel) return;
  const wrap = $("apiRunWrap");
  panel.hidden = !panel.hidden;
  if (wrap) wrap.hidden = panel.hidden;
  if (!panel.hidden) renderApiPreview();
}

/** Keep the preview panel in sync with the current filters while it's open. */
function refreshPreviewIfOpen(): void {
  const panel = $("apiPreview");
  if (!panel || panel.hidden) return;
  if (previewTimer) window.clearTimeout(previewTimer);
  previewTimer = window.setTimeout(renderApiPreview, 300);
}

// --------------------------------------------------------------------------
// Saved views (presets): capture filters + per-tab layout, restore on demand.
// --------------------------------------------------------------------------

interface SavedLayout {
  active: string | null;
  views: Record<string, unknown>;
  order?: string[];
  clones?: { key: string; baseKey: string; name: string }[];
}

function serializeView(v: ViewState): unknown {
  return {
    hidden: [...v.hidden], frozen: [...v.frozen], order: v.order,
    sorters: v.sorters, columnFilters: v.columnFilters, group: v.group,
  };
}

function deserializeView(o: any): ViewState {
  // Back-compat: presets saved before Excel-style filters stored a flat
  // `headerFilters` list of substring matches. Map them to "contains".
  let columnFilters: Record<string, ColFilter> = o?.columnFilters || {};
  if (!o?.columnFilters && Array.isArray(o?.headerFilters)) {
    columnFilters = {};
    o.headerFilters.forEach((hf: any) => {
      if (hf?.field && String(hf.value ?? "").trim() !== "") {
        columnFilters[hf.field] = { op: "contains", v: String(hf.value), v2: "" };
      }
    });
  }
  return {
    hidden: new Set<string>(o?.hidden || []), frozen: new Set<string>(o?.frozen || []),
    order: o?.order || null, sorters: o?.sorters || null,
    columnFilters, group: o?.group || [],
  };
}

function serializeLayout(): SavedLayout {
  captureActive();
  const views: Record<string, unknown> = {};
  Object.keys(state.views).forEach((k) => { views[k] = serializeView(state.views[k]); });
  // Report duplicated (client-only) tabs so a server-side export/delivery can
  // recreate them, and the on-screen tab order so sheets come out in order.
  const clones = state.order
    .map((k) => state.tabs[k])
    .filter((t): t is Tab => !!t && !!(t as any)._isDuplicate)
    .map((t) => ({ key: t.key, baseKey: (t as any)._baseKey || t.key, name: t.name }));
  return { active: state.active, order: [...state.order], clones, views };
}

function applyLayout(layout: SavedLayout | null): void {
  if (!layout || !layout.views) return;
  Object.keys(layout.views).forEach((k) => {
    if (state.tabs[k]) state.views[k] = deserializeView(layout.views[k]);
  });
  if (layout.active && state.tabs[layout.active]) state.active = layout.active;
  renderTabs();
  if (state.active) { buildTable(state.tabs[state.active]); syncColumnsButton(state.tabs[state.active]); }
}

function presetUrl(id: number | string): string {
  return attr("data-preset-url").replace(/\/0$/, `/${id}`);
}

const csrfHeaders = () => ({ "Content-Type": "application/json", "X-CSRF-Token": attr("data-csrf") });

async function saveView(): Promise<void> {
  const name = window.prompt("Save this view as:");
  if (!name || !name.trim()) return;
  try {
    const res = await fetch(attr("data-presets-url"), {
      method: "POST", headers: csrfHeaders(),
      body: JSON.stringify({ name: name.trim(), params: collectParams(), layout: serializeLayout() }),
    });
    if (!res.ok) throw new Error();
    setStatus(`Saved “${name.trim()}”.`);
  } catch {
    setStatus("Could not save this view. Please try again.", "error");
  }
}

function applyParamsObject(params: Record<string, unknown>): void {
  (["period", "status", "year"] as const).forEach((name) => {
    const el = document.querySelector<HTMLSelectElement | HTMLInputElement>(`[name="${name}"]`);
    if (el && params[name] != null) el.value = String(params[name]);
  });
  const sd = document.querySelector<HTMLInputElement>('[name="start_date"]');
  const ed = document.querySelector<HTMLInputElement>('[name="end_date"]');
  if (sd && params.start_date != null) sd.value = String(params.start_date);
  if (ed && params.end_date != null) ed.value = String(params.end_date);
  const sel = $("salesmanSelect") as HTMLSelectElement | null;
  if (params.salesman != null) {
    const val = String(params.salesman);
    if (sel && [...sel.options].some((o) => o.value === val)) sel.value = val;
    else pendingSalesman = val;
  }
  selectedCustomers.clear();
  const custs = params.customers;
  const list = Array.isArray(custs) ? custs : (custs ? String(custs).split(",") : []);
  list.forEach((c) => { const k = String(c).trim(); if (k) selectedCustomers.set(k, k); });
  if (hasFilter("customerPicker")) renderCustomerPicker();
  // Re-sync custom-range field visibility via the listener bound at boot.
  ($("periodSelect") as HTMLSelectElement | null)?.dispatchEvent(new Event("change"));
}

function closePresetsPanel(): void {
  $("presetsPanel")?.remove();
  document.removeEventListener("click", onPresetsOutside, true);
}

function onPresetsOutside(e: MouseEvent): void {
  const panel = $("presetsPanel");
  if (panel && !panel.contains(e.target as Node) && (e.target as HTMLElement).id !== "presetsBtn") {
    closePresetsPanel();
  }
}

async function togglePresetsPanel(): Promise<void> {
  if ($("presetsPanel")) { closePresetsPanel(); return; }
  const data = await getJSON<{ presets: any[] }>(attr("data-presets-url"));
  const presets = data?.presets || [];
  const panel = document.createElement("div");
  panel.id = "presetsPanel";
  panel.className = "presets-panel";
  if (!presets.length) {
    panel.innerHTML = '<div class="presets-empty">No saved views yet. Use “Save view”.</div>';
  } else {
    presets.forEach((p) => {
      const row = document.createElement("div");
      row.className = "presets-row";
      const open = document.createElement("button");
      open.type = "button";
      open.className = "presets-open";
      open.textContent = p.name;
      open.addEventListener("click", () => { closePresetsPanel(); loadPreset(p); });
      const del = document.createElement("button");
      del.type = "button";
      del.className = "presets-del";
      del.textContent = "✕";
      del.title = "Delete this view";
      del.addEventListener("click", async () => {
        if (!window.confirm(`Delete “${p.name}”?`)) return;
        await fetch(presetUrl(p.id), { method: "DELETE", headers: csrfHeaders() });
        row.remove();
      });
      row.append(open, del);
      panel.appendChild(row);
    });
  }
  ($("presetsBtn") as HTMLElement)?.insertAdjacentElement("afterend", panel);
  setTimeout(() => document.addEventListener("click", onPresetsOutside, true), 0);
}

function loadPreset(preset: { params?: Record<string, unknown>; layout?: SavedLayout }): void {
  applyParamsObject(preset.params || {});
  pendingLayout = preset.layout || null;
  updateDeepLink();
  run();
}

async function autoOpenPresetIfRequested(): Promise<void> {
  const id = new URLSearchParams(window.location.search).get("preset");
  if (!id) return;
  const preset = await getJSON<any>(presetUrl(id));
  // Apply the preset's saved filters too (don't rely on the home-page URL also
  // duplicating them into the query string) and then its layout.
  if (preset?.params) applyParamsObject(preset.params);
  if (preset?.layout) pendingLayout = preset.layout;
  autoRunRequested = true;
}

// --------------------------------------------------------------------------
// Email delivery + SharePoint folder picker
// --------------------------------------------------------------------------

// A SharePoint folder picker bound to a set of element ids. Used by both the
// email and schedule modals; each instance tracks its own selected path.
interface SpPickerEls { section: string; breadcrumb: string; picker: string; selected: string; status: string; }

function makeSpPicker(els: SpPickerEls) {
  let cur = "";
  let selected: string | null = null;

  async function init(): Promise<void> {
    const section = $(els.section);
    if (!section) return;
    selected = null;
    cur = "";
    const sel = $(els.selected);
    if (sel) sel.textContent = "";
    const st = await getJSON<{ enabled: boolean; configured: boolean }>(attr("data-sp-status-url"));
    if (!st || !st.enabled) { section.hidden = true; return; }
    section.hidden = false;
    const status = $(els.status);
    if (status) status.textContent = st.configured ? "" : "(mock folders in dev)";
    load("");
  }

  async function load(path: string): Promise<void> {
    cur = path;
    const url = attr("data-sp-folders-url") + "?path=" + encodeURIComponent(path);
    const data = await getJSON<{ folders: { name: string; path: string }[] }>(url);
    renderBreadcrumb(path);
    renderFolders((data && data.folders) || []);
  }

  function renderBreadcrumb(path: string): void {
    const bc = $(els.breadcrumb);
    if (!bc) return;
    bc.innerHTML = "";
    const crumb = (label: string, target: string) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "sp-crumb";
      b.textContent = label;
      b.addEventListener("click", () => load(target));
      return b;
    };
    bc.appendChild(crumb("Root", ""));
    let acc = "";
    (path ? path.split("/") : []).forEach((p) => {
      acc = acc ? `${acc}/${p}` : p;
      bc.appendChild(document.createTextNode(" / "));
      bc.appendChild(crumb(p, acc));
    });
    const use = document.createElement("button");
    use.type = "button";
    use.className = "sp-use";
    use.textContent = "Use this folder";
    use.addEventListener("click", () => {
      selected = cur;
      const sel = $(els.selected);
      if (sel) sel.textContent = `Will save to: ${cur || "Direct Reports (root)"}`;
    });
    bc.appendChild(use);
  }

  function renderFolders(folders: { name: string; path: string }[]): void {
    const picker = $(els.picker);
    if (!picker) return;
    picker.innerHTML = "";
    if (!folders.length) { picker.innerHTML = '<div class="sp-empty">No subfolders here.</div>'; return; }
    folders.forEach((f) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "sp-folder";
      b.textContent = f.name;
      b.addEventListener("click", () => load(f.path));
      picker.appendChild(b);
    });
  }

  return { init, path: () => selected };
}

const emailSp = makeSpPicker({ section: "spSection", breadcrumb: "spBreadcrumb",
  picker: "spPicker", selected: "spSelected", status: "spStatus" });

function emailMsg(text: string, isError: boolean): void {
  const el = $("emailMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
  el.className = "modal-msg" + (isError ? " modal-msg-error" : "");
}

function openEmailModal(): void {
  const modal = $("emailModal");
  if (!modal) return;
  (($("emailSubject") as HTMLInputElement)).value = document.title || "Report";
  (($("emailRecipients") as HTMLInputElement)).value = "";
  emailMsg("", false);
  modal.hidden = false;
  emailSp.init();
}

function closeEmailModal(): void {
  const modal = $("emailModal");
  if (modal) modal.hidden = true;
}

async function sendEmail(): Promise<void> {
  const recipients = (($("emailRecipients") as HTMLInputElement)).value.trim();
  const subject = (($("emailSubject") as HTMLInputElement)).value.trim();
  if (!recipients && !emailSp.path()) {
    emailMsg("Enter at least one recipient or pick a SharePoint folder.", true);
    return;
  }
  const sendBtn = $("emailSend") as HTMLButtonElement | null;
  if (sendBtn) sendBtn.disabled = true;
  emailMsg("Sending…", false);
  try {
    const res = await fetch(attr("data-email-url"), {
      method: "POST", headers: csrfHeaders(),
      body: JSON.stringify({
        recipients, subject, sharepoint_path: emailSp.path() || "",
        params: collectParams(), layout: serializeLayout(),
      }),
    });
    if (res.status !== 202) {
      const e = await res.json().catch(() => ({}));
      throw new Error((e as any).error || "Could not queue the email.");
    }
    const { job_id } = await res.json();
    await pollEmailJob(job_id);
  } catch (e) {
    emailMsg((e as Error).message || "Could not send.", true);
  } finally {
    if (sendBtn) sendBtn.disabled = false;
  }
}

async function pollEmailJob(jobId: string): Promise<void> {
  const jobUrl = attr("data-job-url").replace("__ID__", jobId);
  for (let i = 0; i < 60; i++) {
    const j = await getJSON<{ status: string; error: string }>(jobUrl);
    if (!j) break;
    if (j.status === "success") {
      emailMsg("Delivered.", false);
      setTimeout(closeEmailModal, 1200);
      return;
    }
    if (j.status === "failure" || j.status === "cancelled") {
      emailMsg(j.error || "Delivery failed.", true);
      return;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  emailMsg("Still processing — check the outbox shortly.", false);
}

// -- schedule modal ---------------------------------------------------------

const scheduleSp = makeSpPicker({ section: "schedSpSection", breadcrumb: "schedSpBreadcrumb",
  picker: "schedSpPicker", selected: "schedSpSelected", status: "schedSpStatus" });

function schedMsg(text: string, isError: boolean): void {
  const el = $("schedMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
  el.className = "modal-msg" + (isError ? " modal-msg-error" : "");
}

function syncCadenceFields(): void {
  const freq = ($("schedFreq") as HTMLSelectElement | null)?.value || "daily";
  const wd = $("schedWeekdays");
  const md = $("schedMonthdayField");
  if (wd) wd.hidden = freq !== "weekly";
  if (md) md.hidden = freq !== "monthly";
}

function openScheduleModal(): void {
  const modal = $("scheduleModal");
  if (!modal) return;
  (($("schedRecipients") as HTMLInputElement)).value = "";
  schedMsg("", false);
  syncCadenceFields();
  modal.hidden = false;
  scheduleSp.init();
}

function closeScheduleModal(): void {
  const modal = $("scheduleModal");
  if (modal) modal.hidden = true;
}

function collectCadence(): { ok: boolean; cadence?: any; error?: string } {
  const freq = ($("schedFreq") as HTMLSelectElement).value;
  const time = ($("schedTime") as HTMLInputElement).value || "08:00";
  const cadence: any = { freq, time };
  if (freq === "weekly") {
    const days = [...document.querySelectorAll<HTMLInputElement>("#schedWeekdays input:checked")]
      .map((c) => Number(c.value));
    if (!days.length) return { ok: false, error: "Pick at least one day of the week." };
    cadence.weekdays = days;
  } else if (freq === "monthly") {
    cadence.monthday = Number(($("schedMonthday") as HTMLInputElement).value) || 1;
  }
  return { ok: true, cadence };
}

async function saveSchedule(): Promise<void> {
  const recipients = (($("schedRecipients") as HTMLInputElement)).value.trim();
  if (!recipients && !scheduleSp.path()) {
    schedMsg("Enter recipients or pick a SharePoint folder.", true);
    return;
  }
  const cad = collectCadence();
  if (!cad.ok) { schedMsg(cad.error || "Invalid cadence.", true); return; }
  const btn = $("schedSave") as HTMLButtonElement | null;
  if (btn) btn.disabled = true;
  schedMsg("Saving…", false);
  try {
    const res = await fetch(attr("data-schedules-url"), {
      method: "POST", headers: csrfHeaders(),
      body: JSON.stringify({
        report_key: attr("data-report-key"), recipients,
        sharepoint_path: scheduleSp.path() || "", cadence: cad.cadence,
        params: collectParams(), layout: serializeLayout(),
      }),
    });
    if (res.status !== 201) {
      const e = await res.json().catch(() => ({}));
      throw new Error((e as any).error || "Could not save the schedule.");
    }
    schedMsg("Schedule saved. Manage it under Schedules.", false);
    setTimeout(closeScheduleModal, 1400);
  } catch (e) {
    schedMsg((e as Error).message || "Could not save.", true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  if (!root) return;
  // Apply deep-links BEFORE wiring the custom-range toggle so a period=custom
  // link reveals the date inputs when the toggle does its initial sync.
  applyDeepLink();
  initCustomRangeToggle();
  $("controlsToggle")?.addEventListener("click", () => {
    setControlsCollapsed(!$("reportControls")?.classList.contains("collapsed"));
  });
  $("runBtn")?.addEventListener("click", () => { updateDeepLink(); run(); });
  $("apiRunBtn")?.addEventListener("click", () => {
    const panel = $("apiPreview") as HTMLTextAreaElement | null;
    if (!panel) return;
    try {
      const parsed = JSON.parse(panel.value);
      run({ overrideParams: parsed });
    } catch {
      setStatus("Invalid JSON in the API preview. Fix it and try again.", "error");
    }
  });
  $("refreshBtn")?.addEventListener("click", () => run({ preserveLayout: true }));
  $("resetBtn")?.addEventListener("click", resetView);
  $("exportBtn")?.addEventListener("click", exportExcel);
  $("exportsBtn")?.addEventListener("click", (e) => { e.stopPropagation(); toggleExportsPanel(); });
  $("columnsBtn")?.addEventListener("click", (e) => { e.stopPropagation(); toggleColumnsPanel(); });
  $("saveViewBtn")?.addEventListener("click", saveView);
  $("presetsBtn")?.addEventListener("click", (e) => { e.stopPropagation(); togglePresetsPanel(); });
  $("emailBtn")?.addEventListener("click", openEmailModal);
  $("emailClose")?.addEventListener("click", closeEmailModal);
  $("emailCancel")?.addEventListener("click", closeEmailModal);
  $("emailSend")?.addEventListener("click", sendEmail);
  $("emailModal")?.addEventListener("click", (e) => { if (e.target === $("emailModal")) closeEmailModal(); });
  $("scheduleBtn")?.addEventListener("click", openScheduleModal);
  $("schedClose")?.addEventListener("click", closeScheduleModal);
  $("schedCancel")?.addEventListener("click", closeScheduleModal);
  $("schedFreq")?.addEventListener("change", syncCadenceFields);
  $("schedSave")?.addEventListener("click", saveSchedule);
  $("scheduleModal")?.addEventListener("click", (e) => { if (e.target === $("scheduleModal")) closeScheduleModal(); });
  $("previewBtn")?.addEventListener("click", showApiPreview);
  $("filterForm")?.addEventListener("input", refreshPreviewIfOpen);
  $("filterForm")?.addEventListener("change", refreshPreviewIfOpen);
  setToolbarEnabled(false);
  loadExports();  // pick up any in-flight exports started before a navigation/reload
  await initLookups();
  await autoOpenPresetIfRequested();
  if (autoRunRequested) { autoRunRequested = false; run(); }
});

export {};

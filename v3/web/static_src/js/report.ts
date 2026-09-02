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

import { DEFAULT_FILENAME_TEMPLATE, previewFilename } from "./filename_preview";

declare const Tabulator: any;

interface Column {
  field: string;
  header: string;
  type?: "text" | "money" | "percent" | "int" | "date";
  /** 0=blue month YoY, 1=green YTD, 2=purple full year. Follows the field, not col index. */
  band?: number;
}

interface CommissionMonth {
  month: number;
  month_label: string;
  subtotal_invoices: number;
  tariff_charges: number;
  freight_charges: number;
  cc_charges: number;
  misc_charges: number;
  total_invoices: number;
  credits: number;
  net_commission: number;
  commission: number;
}
interface CommissionSalesman {
  salesman?: string;
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
  year?: number;
  end_month?: number;
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
  widths: Record<string, number>; // field -> user-dragged column width (px)
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
  // Write into the text span so the Cancel button living in the same bar isn't
  // wiped out by setting textContent on the whole status element.
  const txt = $("reportStatusText");
  if (txt) txt.textContent = msg; else el.textContent = msg;
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

/** Normalize any date-ish cell to YYYY-MM-DD (matches report_engine.lib.iso_date). */
function isoDate(value: unknown): string {
  if (value == null || value === "") return "";
  if (value instanceof Date && !isNaN(value.getTime())) {
    const y = value.getUTCFullYear();
    const m = String(value.getUTCMonth() + 1).padStart(2, "0");
    const day = String(value.getUTCDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }
  const s = String(value).trim();
  if (!s) return "";
  const upper = s.toUpperCase();
  if (upper === "N/A" || upper === "NA" || upper === "NONE" || s === "-") return s;
  const iso = s.match(/^(\d{4}-\d{2}-\d{2})/);
  if (iso) return iso[1];
  const parsed = Date.parse(s);
  if (!isNaN(parsed)) {
    const d = new Date(parsed);
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, "0");
    const day = String(d.getUTCDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }
  return s;
}

const SALESMAN_ID_FIELDS = new Set(["Sort Number", "Salesman", "Cust. #", "Customer Name", "SalesmanNumber"]);

function salesmanBandIndex(col: Column, colIndex: number): number {
  if (SALESMAN_ID_FIELDS.has(col.field)) return -1;
  if (typeof col.band === "number" && isFinite(col.band)) {
    return Math.min(Math.max(Math.trunc(col.band), 0), 2);
  }
  // Older cached payloads have no band on the column; fall back to schema index.
  if (attr("data-report-key") === "salesman" && colIndex >= 4) {
    return Math.min(Math.floor((colIndex - 4) / 4), 2);
  }
  return -1;
}

function formatterFor(col: Column, colIndex = -1): Record<string, unknown> {
  const band = salesmanBandIndex(col, colIndex);
  const bandColor = band === 0 ? "#0000CC" : band === 1 ? "#008000" : band === 2 ? "#800080" : null;

  switch (col.type) {
    case "money": {
      if (!bandColor) return money(2);
      return {
        sorter: "number",
        hozAlign: "right",
        formatter: (cell: any) => {
          const n = Number(cell.getValue());
          const text = isFinite(n) && cell.getValue() !== "" && cell.getValue() != null
            ? n.toLocaleString(undefined, { style: "currency", currency: "USD" })
            : "";
          const color = (isFinite(n) && n < 0) ? "#FF0000" : bandColor;
          return color && text ? `<span style="color:${color}">${text}</span>` : text;
        },
      };
    }
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
          const raw = cell.getValue();
          const n = Number(raw);
          const text = isFinite(n) && raw !== "" && raw != null ? (n * 100).toFixed(1) + "%" : "";
          if (col.field === "Fulfillment %" && isFinite(n) && raw !== "" && raw != null) {
            try { cell.getElement().style.backgroundColor = fulfillmentFillCss(n); } catch { /* cell gone */ }
          }
          const color = (isFinite(n) && n < 0) ? "#FF0000" : bandColor;
          return color && text ? `<span style="color:${color}">${text}</span>` : text;
        },
      };
    case "date":
      return {
        sorter: "string",
        formatter: (cell: any) => isoDate(cell.getValue()),
      };
    default:
      return { sorter: "string" };
  }
}

function isNumericType(t?: string): boolean {
  return t === "money" || t === "int" || t === "percent";
}

/** Red (0) → yellow (0.5) → green (1). Same RGB as the old Ordered Excel writer. */
function fulfillmentFillCss(score: number): string {
  const s = Math.max(0, Math.min(1, score));
  const red = [255, 199, 206], yellow = [255, 235, 156], green = [198, 239, 206];
  let rgb: number[];
  if (s <= 0) rgb = red;
  else if (s >= 1) rgb = green;
  else if (s < 0.5) {
    const t = s * 2;
    rgb = red.map((x, i) => Math.round(x + (yellow[i] - x) * t));
  } else {
    const t = (s - 0.5) * 2;
    rgb = yellow.map((x, i) => Math.round(x + (green[i] - x) * t));
  }
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}

// --------------------------------------------------------------------------
// State
// --------------------------------------------------------------------------

const state: {
  tabs: Record<string, Tab>;
  order: string[];
  catalogOrder: string[];
  active: string | null;
  views: Record<string, ViewState>;
  table: any;
  jobId: string | null;
  removed: Set<string>;
  generatedAt: string | undefined;
} = { tabs: {}, order: [], catalogOrder: [], active: null, views: {}, table: null, jobId: null, removed: new Set<string>(), generatedAt: undefined };

function freshView(): ViewState {
  return { hidden: new Set(), frozen: new Set(), order: null, sorters: null, columnFilters: {}, group: [], widths: {} };
}

function addGroupField(tab: Tab, field: string): void {
  const g = view(tab.key).group;
  if (!field || g.includes(field)) return;
  g.push(field);
  rebuild(tab);
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
        addGroupField(tab, column.getField());
      },
    },
    {
      label: "Add subgroup",
      action: (_e: any, column: any) => {
        addGroupField(tab, column.getField());
      },
    },
    {
      label: "Clear grouping",
      action: () => {
        view(tab.key).group = [];
        rebuild(tab);
      },
    },
  ];
}

const NUMBER4_TRAILING = ["Total Qty", "Total $", "Avg Price", "Book Price", "Salesman"];
const MONTH_ABBR: Record<string, number> = {
  jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
  jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
};

function isMonthField(field: string): boolean {
  if (NUMBER4_TRAILING.includes(field)) return false;
  return monthSortKey(field)[0] !== 9999;
}

function monthSortKey(field: string): [number, number, number] {
  const labeled = field.match(/^([A-Za-z]{3,9})[-/ ]+(\d{2,4}) (Qty|\$)$/);
  if (labeled) {
    const mon = MONTH_ABBR[labeled[1].slice(0, 3).toLowerCase()] || 99;
    let yy = parseInt(labeled[2], 10);
    if (yy < 100) yy += 2000;
    return [yy, mon, labeled[3] === "$" ? 1 : 0];
  }
  const iso = field.match(/^(\d{4})-(\d{2}) (Qty|\$)$/);
  if (iso) {
    return [parseInt(iso[1], 10), parseInt(iso[2], 10), iso[3] === "$" ? 1 : 0];
  }
  return [9999, 99, 9];
}

function looksLikeNumber4(cols: Column[]): boolean {
  return cols.some((c) => c.field === "Avg Price" || c.field === "Book Price" || isMonthField(c.field));
}

function orderNumber4Columns(cols: Column[]): Column[] {
  if (!looksLikeNumber4(cols)) return cols;
  const trailingSet = new Set(NUMBER4_TRAILING);
  const byField = new Map(cols.map((c) => [c.field, c]));
  const lead: Column[] = [];
  const months: Column[] = [];
  for (const col of cols) {
    if (trailingSet.has(col.field)) continue;
    if (isMonthField(col.field)) months.push(col);
    else lead.push(col);
  }
  months.sort((a, b) => {
    const ka = monthSortKey(a.field);
    const kb = monthSortKey(b.field);
    return ka[0] - kb[0] || ka[1] - kb[1] || ka[2] - kb[2];
  });
  const trailing = NUMBER4_TRAILING.map((f) => byField.get(f)).filter(Boolean) as Column[];
  return [...lead, ...months, ...trailing];
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
  ordered = orderNumber4Columns(ordered);
  return ordered.map((c, i) => ({
    title: c.header,
    field: c.field,
    visible: !v.hidden.has(c.field),
    frozen: v.frozen.has(c.field),
    width: v.widths[c.field],
    titleFormatter: () => columnHeaderEl(tab, c),
    headerMenu: headerMenu(tab),
    bottomCalc: isNumericType(c.type) && c.type !== "percent" ? "sum" : undefined,
    bottomCalcFormatter: c.type === "money" ? "money" : undefined,
    bottomCalcFormatterParams: c.type === "money" ? { symbol: "$", precision: 2, thousand: "," } : undefined,
    ...formatterFor(c, i),
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
    cols.forEach((c: any) => {
      const field = c.getField();
      const w = c.getWidth();
      if (field && w) v.widths[field] = w;
    });
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
  const gen = state.generatedAt;
  const parts = [`${tab.rows.length.toLocaleString()} rows`];
  if (gen) parts.push(`as of ${gen}`);
  meta.textContent = parts.join(" · ");
  meta.hidden = false;
}

function renderGroupPills(tab: Tab): void {
  const host = $("groupPills");
  if (!host) return;
  host.innerHTML = "";
  const g = tab.layout === "commission_cards" ? [] : view(tab.key).group;
  if (!g.length) { host.hidden = true; return; }
  host.hidden = false;
  g.forEach((field) => {
    const pill = document.createElement("span");
    pill.className = "group-pill";
    const lab = document.createElement("span");
    lab.textContent = tab.columns.find((c) => c.field === field)?.header || field;
    const x = document.createElement("button");
    x.type = "button";
    x.className = "group-pill-x";
    x.textContent = "\u00d7";
    x.title = "Remove this group";
    x.addEventListener("click", () => {
      view(tab.key).group = view(tab.key).group.filter((f) => f !== field);
      rebuild(tab);
    });
    pill.append(lab, x);
    host.appendChild(pill);
  });
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
    renderGroupPills(tab);
    return;
  }

  const v = view(tab.key);
  const table = new Tabulator(host, {
    data: tab.rows,
    columns: buildColumns(tab),
    layout: "fitDataTable",
    movableColumns: true,
    resizableColumns: true, // drag a column border to set its width
    columnCalcs: "both",
    height: tableHeight(),
    nestedFieldSeparator: false, // fields contain "." (e.g. "Cust. #")
    placeholder: "No data for these filters.",
    initialSort: v.sorters?.map((s) => ({ column: s.column, dir: s.dir })),
    groupBy: v.group.length ? v.group : undefined,
  });
  state.table = table;
  // Remember a width the moment the user drags it, so it survives a re-run.
  table.on("columnResized", (column: any) => {
    const field = column.getField();
    if (field) view(tab.key).widths[field] = column.getWidth();
  });
  table.on("tableBuilt", () => {
    // A build from a previous tab can fire late; ignore it if we've moved on.
    if (state.table !== table || state.active !== tab.key) return;
    if (v.group.length) table.setGroupBy(v.group);
    applyColumnFilters(); // replay any saved per-column filters
    requestAnimationFrame(fitTableHeight); // size once the grid is laid out
  });
  renderMeta(tab);
  renderGroupPills(tab);
}

// The grid should fill the screen from where it starts down to the bottom,
// with its own vertical scrollbar -- never push the whole page taller. The
// start point moves when the filters panel opens/closes, so this recomputes.
function tableHeight(): number {
  const host = $("reportTable");
  const top = host ? host.getBoundingClientRect().top : 230;
  const bottomGap = 16; // breathing room under the grid
  // The bottom nav is fixed over the viewport, so the grid (and its horizontal
  // scrollbar) must stop above it -- otherwise the bottom row hides behind the
  // nav and you'd have to scroll the whole page to reach the side-scrollbar.
  const nav = document.querySelector(".bottom-nav");
  const floor = nav ? nav.getBoundingClientRect().top : window.innerHeight;
  return Math.max(220, Math.round(floor - top - bottomGap));
}

function fitTableHeight(): void {
  if (!state.table) return;
  try { state.table.setHeight(tableHeight()); } catch { /* table gone */ }
}

function n(v: unknown): number {
  const x = Number(v);
  return isFinite(x) ? x : 0;
}
function fmtMoney(v: unknown): string {
  return n(v).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function monthHeaderLabel(month: number, year: number | undefined): string {
  const abbr = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][month - 1] || `M${month}`;
  if (!year) return abbr;
  return `${abbr}-${String(year).slice(-2)}`;
}

function renderCommissionCards(tab: Tab, host: HTMLElement): void {
  // Live Excel layout: metrics as rows, months as columns, no future months.
  // Data already stops at end_month from the builder.
  const salesmen = tab.salesmen || [];
  if (!salesmen.length) {
    host.innerHTML = '<div class="empty-state">No commissions for this period.</div>';
    return;
  }

  const wrap = document.createElement("div");
  wrap.className = "commission-live";
  wrap.style.height = `${tableHeight()}px`;

  const title = document.createElement("div");
  title.className = "commission-live-title";
  title.textContent = tab.year
    ? `Commissions Summary (${tab.year})`
    : "Commissions Summary";
  wrap.appendChild(title);

  const metricRows: { label: string; field: string; kind: "money" | "net" | "comm" | "pay" }[] = [
    { label: "SubTotal Invoices:", field: "subtotal_invoices", kind: "money" },
    { label: "Total Tariff Charges:", field: "tariff_charges", kind: "money" },
    { label: "Total Freight Charges:", field: "freight_charges", kind: "money" },
    { label: "Total CC Charges:", field: "cc_charges", kind: "money" },
    { label: "Total Invoices: (SubTotal+Tariff+Freight+CC)", field: "total_invoices", kind: "money" },
    { label: "Total Credits:", field: "credits", kind: "money" },
    { label: "Net Commission Amount (Less Freight and CC)", field: "net_commission", kind: "net" },
    { label: "Commission:", field: "commission", kind: "comm" },
  ];

  salesmen.forEach((s) => {
    const months = s.monthly || [];
    const num = String(s.salesman_number || s.salesman || "").trim();
    const name = String(s.salesman_name || "").trim();
    const titleText = `${num} - ${name}`.replace(/^ - | - $/g, "").trim() || name || num;

    const block = document.createElement("div");
    block.className = "commission-live-block";

    const table = document.createElement("table");
    table.className = "commission-live-table";

    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    const thName = document.createElement("th");
    thName.className = "comm-label";
    thName.textContent = titleText;
    hr.appendChild(thName);
    const thPct = document.createElement("th");
    thPct.className = "comm-pct";
    thPct.textContent = "";
    hr.appendChild(thPct);
    months.forEach((m) => {
      const th = document.createElement("th");
      th.textContent = monthHeaderLabel(m.month || 0, tab.year);
      hr.appendChild(th);
    });
    const thYtd = document.createElement("th");
    thYtd.textContent = "YTD Total";
    hr.appendChild(thYtd);
    thead.appendChild(hr);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    metricRows.forEach((mr) => {
      const tr = document.createElement("tr");
      if (mr.kind === "net") tr.className = "comm-row-net";
      if (mr.kind === "comm") tr.className = "comm-row-comm";
      const tdLab = document.createElement("td");
      tdLab.className = "comm-label";
      tdLab.textContent = mr.label;
      tr.appendChild(tdLab);
      const tdPct = document.createElement("td");
      tdPct.className = "comm-pct";
      if (mr.kind === "comm") {
        tdPct.textContent = `${(n(s.commission_pct) * 100).toFixed(2)}%`;
      }
      tr.appendChild(tdPct);
      months.forEach((m) => {
        const td = document.createElement("td");
        const val = (m as unknown as Record<string, unknown>)[mr.field];
        td.textContent = fmtMoney(val);
        tr.appendChild(td);
      });
      const tdYtd = document.createElement("td");
      tdYtd.textContent = fmtMoney(s.ytd?.[mr.field]);
      tr.appendChild(tdYtd);
      tbody.appendChild(tr);
    });

    const pay = document.createElement("tr");
    pay.className = "comm-row-pay";
    const payLab = document.createElement("td");
    payLab.className = "comm-label";
    payLab.colSpan = 2;
    payLab.textContent = `Total Payable: ${titleText}`;
    pay.appendChild(payLab);
    months.forEach(() => {
      const td = document.createElement("td");
      td.textContent = "";
      pay.appendChild(td);
    });
    const payYtd = document.createElement("td");
    payYtd.textContent = fmtMoney(s.ytd?.total_payable ?? s.ytd?.commission);
    pay.appendChild(payYtd);
    tbody.appendChild(pay);

    table.appendChild(tbody);
    block.appendChild(table);
    wrap.appendChild(block);
  });

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
    if (!tab) return;
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
  if (!tab) return;
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
  if ((tab as any)._isDuplicate) mk("Rename tab", () => renameTab(key));
  if (state.order.length > 1) {
    mk((tab as any)._isDuplicate ? "Delete tab" : "Remove tab", () => deleteTab(key), true);
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

function renameTab(key: string): void {
  const tab = state.tabs[key];
  if (!tab || !(tab as any)._isDuplicate) return;
  const name = window.prompt("Rename this tab:", tab.name);
  if (name == null) return;
  const trimmed = name.trim();
  if (!trimmed) return;
  tab.name = trimmed;
  renderTabs();
}

function deleteTab(key: string): void {
  if (state.order.length <= 1) return;
  const tab = state.tabs[key];
  if (!tab) return;
  const isDup = !!(tab as any)._isDuplicate;
  if (isDup) {
    delete state.tabs[key];
    delete state.views[key];
  } else {
    state.removed.add(key);
  }
  const idx = state.order.indexOf(key);
  state.order.splice(idx, 1);
  if (state.active === key) {
    activateTab(state.order[Math.max(0, idx - 1)] || state.order[0]);
  } else {
    renderTabs();
  }
}

function restoreTab(key: string): void {
  const tab = state.tabs[key];
  if (!tab || state.order.includes(key)) return;
  state.removed.delete(key);
  const cat = state.catalogOrder;
  const want = cat.indexOf(key);
  let insertAt = state.order.length;
  if (want >= 0) {
    for (let i = 0; i < state.order.length; i++) {
      const oi = cat.indexOf(state.order[i]);
      if (oi === -1 || oi > want) { insertAt = i; break; }
    }
  }
  state.order.splice(insertAt, 0, key);
  renderTabs();
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

  const originalKeys = Object.keys(state.tabs).filter((k) => state.tabs[k] && !(state.tabs[k] as any)._isDuplicate);
  if (originalKeys.length) {
    const heading = document.createElement("div");
    heading.className = "columns-panel-heading";
    heading.textContent = "Tabs";
    panel.appendChild(heading);
    originalKeys.forEach((key) => {
      const t = state.tabs[key];
      const label = document.createElement("label");
      label.className = "columns-panel-item";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.dataset.kind = "tab";
      cb.checked = state.order.includes(key);
      cb.addEventListener("change", () => {
        if (cb.checked) restoreTab(key);
        else if (state.order.length > 1) deleteTab(key);
        else cb.checked = true;
      });
      label.appendChild(cb);
      const span = document.createElement("span");
      span.textContent = t.name;
      label.appendChild(span);
      panel.appendChild(label);
    });
    const colHeading = document.createElement("div");
    colHeading.className = "columns-panel-heading";
    colHeading.textContent = "Columns";
    panel.appendChild(colHeading);
  }

  tab.columns.forEach((c) => {
    const label = document.createElement("label");
    label.className = "columns-panel-item";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.dataset.kind = "column";
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
    panel.querySelectorAll<HTMLInputElement>("input[data-kind=column]").forEach((i) => { i.checked = true; });
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
    showExportsPanel();
    setExportBuildingStatus();
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

function showExportsPanel(): void {
  const panel = $("exportsPanel");
  if (!panel) return;
  panel.hidden = false;
  loadExports();
  panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function setExportBuildingStatus(): void {
  const el = $("reportStatus");
  const txt = $("reportStatusText");
  if (!el || !txt) return;
  txt.replaceChildren();
  txt.append("Your Excel file is building in the background \u2014 ");
  const link = document.createElement("button");
  link.type = "button";
  link.className = "status-link";
  link.textContent = "Recent exports";
  link.addEventListener("click", () => showExportsPanel());
  txt.append(link);
  txt.append(".");
  el.className = "report-status report-status-info";
  el.hidden = false;
}

function toggleExportsPanel(): void {
  const panel = $("exportsPanel");
  if (!panel) return;
  if (panel.hidden) showExportsPanel();
  else panel.hidden = true;
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
  // Lookups may still be empty when a preset auto-runs, so the <select> has
  // no matching <option> and FormData omits salesman. Keep the saved value.
  if (!out.salesman && pendingSalesman) out.salesman = pendingSalesman;
  return out;
}

const VIEW_WINDOW_KEYS = new Set(["period", "start_date", "end_date", "from", "to"]);

function collectCompanyViewParams(): Record<string, unknown> {
  // Company schedules own YTD / MTD / yesterday. Saving the view must not
  // stamp the period you used to preview the layout.
  const out: Record<string, unknown> = {};
  Object.entries(collectParams()).forEach(([key, val]) => {
    if (!VIEW_WINDOW_KEYS.has(key)) out[key] = val;
  });
  return out;
}

function mapPeriodValue(raw: string): string {
  const v = raw.trim();
  return v.toLowerCase() === "yesterday" ? "daily" : v;
}

function periodIsRunnable(params?: Record<string, unknown> | null): boolean {
  const p = String(params?.period || "").trim().toLowerCase();
  if (!p) return false;
  if (p === "custom") {
    const start = String(params?.start_date || params?.from || "").trim();
    const end = String(params?.end_date || params?.to || "").trim();
    return !!(start && end);
  }
  return true;
}

function loadPayload(payload: Payload, render = true): void {
  state.tabs = {};
  state.order = [];
  state.catalogOrder = [];
  state.views = {};
  state.removed = new Set();
  state.generatedAt = payload.generated_at;
  const tabs = attr("data-hide-commissions") === "1"
    ? payload.tabs.filter((t) => t.key !== "commissions")
    : payload.tabs;
  tabs.forEach((tab) => {
    state.tabs[tab.key] = tab;
    state.order.push(tab.key);
    state.catalogOrder.push(tab.key);
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
    // Show + collapse the panels FIRST so the grid is built into its final
    // on-screen position; otherwise its height is measured while hidden and
    // comes out way too tall.
    showReportSurface();
    setControlsCollapsed(true);
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
  const prevRemoved = new Set(state.removed);
  const duplicates = state.order
    .filter((k) => (state.tabs[k] as any)?._isDuplicate)
    .map((k) => ({
      key: k,
      name: state.tabs[k].name,
      baseKey: (state.tabs[k] as any)._baseKey as string,
      view: prevViews[k],
    }));

  loadPayload(payload, false); // resets to the fresh server tabs (no render yet)
  state.removed = prevRemoved;

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

  // Restore order: previous keys that still exist, then any newly-added tabs
  // the user did not explicitly remove (e.g. Audit that only appears some days).
  const restored = prevOrder.filter((k) => state.tabs[k]);
  state.order.forEach((k) => {
    if (!restored.includes(k) && !state.removed.has(k)) restored.push(k);
  });
  state.order = restored;

  state.active = prevActive && state.tabs[prevActive] ? prevActive : state.order[0] || null;
  renderTabs();
  showReportSurface();
  setControlsCollapsed(true);
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
    columnFilters: JSON.parse(JSON.stringify(v.columnFilters || {})),
    group: [...v.group],
    widths: { ...(v.widths || {}) },
  };
}

// The in-flight run's job id (so Cancel knows what to stop), and a flag the
// poll loop checks so a cancel stops the screen waiting right away.
let activeRunJobId: string | null = null;
let runAborted = false;

function showCancel(visible: boolean): void {
  const btn = $("cancelRunBtn") as HTMLButtonElement | null;
  if (btn) { btn.hidden = !visible; btn.disabled = false; }
}

async function cancelRun(): Promise<void> {
  const jobId = activeRunJobId;
  runAborted = true;        // the poll loop bails on its next tick
  showCancel(false);
  if (!jobId) { clearStatus(); return; }
  setStatus("Cancelling…");
  try {
    await fetch(attr("data-cancel-url").replace("__ID__", jobId), {
      method: "POST", headers: csrfHeaders(),
    });
  } catch {
    // Even if the cancel request fails, we've already stopped watching the job.
  }
  setStatus("Run cancelled.");
}

async function poll(jobId: string, opts: { preserveLayout?: boolean; elapsedMs?: number } = {}): Promise<void> {
  const jobUrl = attr("data-job-url").replace("__ID__", jobId);
  const resultUrl = attr("data-result-url").replace("__ID__", jobId);
  // Count from when the job really started (passed in when reconnecting to a
  // run from a prior visit) so the timer doesn't reset to zero on return.
  const started = Date.now() - (opts.elapsedMs || 0);

  // One failed check-in (a brief gateway blip while the server is busy) must not
  // kill a run that's still going on the server. Only give up after several
  // failures in a row; any good response resets the count.
  const maxConsecutiveErrors = 5;
  let consecutiveErrors = 0;

  for (let i = 0; i < 600; i++) {
    if (runAborted) return; // user cancelled; cancelRun() owns the status line
    let job: { status?: string; progress?: number; error?: unknown };
    try {
      const res = await fetch(jobUrl, { headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error(`status ${res.status}`);
      job = await res.json();
      consecutiveErrors = 0;
    } catch {
      consecutiveErrors++;
      if (consecutiveErrors >= maxConsecutiveErrors) {
        throw new Error("Lost track of the job (it may have expired) — try running again.");
      }
      setStatus(`Building report… reconnecting (${fmtElapsed(Date.now() - started)})`);
      await new Promise((r) => setTimeout(r, 1000));
      continue;
    }
    if (job.status === "success") {
      const r = await fetch(resultUrl, { headers: { Accept: "application/json" } });
      if (!r.ok) throw new Error("The report finished but the result couldn't be loaded — re-run to refresh it.");
      const payload: Payload = await r.json();
      state.jobId = jobId;
      clearStatus();
      if (opts.preserveLayout) loadPayloadPreserving(payload);
      else loadPayload(payload);
      applyPendingOrDefaultLayout();
      return;
    }
    if (job.status === "failure") throw new Error(friendlyError(job.error));
    if (job.status === "cancelled") throw new Error("The run was cancelled.");
    // Only offer Cancel once the job is actually running on the server; a
    // queued job hasn't started, so there's nothing to stop yet.
    showCancel(job.status === "running");
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

/** Is a report already on screen (so a new run keeps the user's layout)? */
function isReportShown(): boolean {
  return !!state.active && !($("reportSurface")?.hidden ?? true);
}

async function run(opts: { preserveLayout?: boolean; overrideParams?: Record<string, unknown> } = {}): Promise<void> {
  if (opts.preserveLayout) {
    captureActive();
    // Empty the old rows right away so the user isn't staring at stale data
    // while the new run builds; the columns/format stay put and refill on success.
    try { state.table?.clearData(); } catch { /* table not ready */ }
  }
  setToolbarEnabled(false);
  setStatus(opts.preserveLayout ? "Refreshing data…" : "Starting…");
  runAborted = false;
  try {
    const params = opts.overrideParams ?? collectParams();
    const res = await fetch(attr("data-run-url"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": attr("data-csrf") },
      body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error(`Could not start the report (HTTP ${res.status}).`);
    const { job_id } = await res.json();
    activeRunJobId = job_id;
    await poll(job_id, opts);
  } catch (err) {
    if (!runAborted) setStatus(err instanceof Error ? err.message : "Something went wrong.", "error");
  } finally {
    showCancel(false);
    activeRunJobId = null;
    const runBtn = $("runBtn") as HTMLButtonElement | null;
    if (runBtn) runBtn.disabled = false;
  }
}

/** Reconnect to a job that's already on the server (started in a prior visit),
 *  reusing the same poll loop -- it shows progress for a running job and loads
 *  the result for one that already finished. */
async function resumeJob(jobId: string, elapsedMs = 0): Promise<void> {
  setToolbarEnabled(false);
  setStatus("Reconnecting to your report…");
  runAborted = false;
  activeRunJobId = jobId;
  try {
    await poll(jobId, { elapsedMs });
  } catch (err) {
    if (!runAborted) setStatus(err instanceof Error ? err.message : "Something went wrong.", "error");
  } finally {
    showCancel(false);
    activeRunJobId = null;
    const runBtn = $("runBtn") as HTMLButtonElement | null;
    if (runBtn) runBtn.disabled = false;
  }
}

/** On page load, pick up a report this user was running (or just finished) for
 *  THIS report and show it, so leaving and coming back doesn't lose the run.
 *  A home-page preset (?preset=) must start a new run instead of replaying
 *  the last job for this report. ?job= still wins when both are present.
 *  Returns true if it found and resumed one. */
async function resumeInFlight(): Promise<boolean> {
  const url = attr("data-active-url");
  const key = attr("data-report-key");
  if (!url || !key) return false;
  const q = new URLSearchParams(window.location.search);
  const wanted = q.get("job");
  if ((q.get("preset") || q.get("cview")) && !wanted) return false;
  let jobs: { job_id: string; report_key: string | null; status: string; age_seconds: number | null }[];
  try {
    const data = await fetch(url, { headers: { Accept: "application/json" } }).then((r) => r.json());
    jobs = (data && data.jobs) || [];
  } catch {
    return false;
  }
  const mine = wanted
    ? jobs.find((j) => j.job_id === wanted && j.report_key === key)
    : jobs.find((j) => j.report_key === key &&
      (j.status === "running" || j.status === "queued" || j.status === "success"));
  if (!mine) return false;
  state.jobId = mine.job_id;
  await resumeJob(mine.job_id, (mine.age_seconds || 0) * 1000);
  return true;
}

function setToolbarEnabled(hasData: boolean): void {
  (["refreshBtn", "resetBtn", "keepBtn", "columnsBtn", "emailBtn", "scheduleBtn", "exportMenuBtn"] as const).forEach((id) => {
    const b = $(id) as HTMLButtonElement | null;
    if (b) b.disabled = !hasData;
  });
  const save = $("saveViewBtn") as HTMLButtonElement | null;
  if (save) {
    // Company views are layout templates; schedules own YTD/MTD/yesterday.
    // Edit must be saveable without first running a preview period.
    save.disabled = !(hasData || (isCompanyViewId(editingPresetId) && !!editingPresetName));
  }
  const runBtn = $("runBtn") as HTMLButtonElement | null;
  if (runBtn) runBtn.disabled = false;
}

// --------------------------------------------------------------------------
// Export / More dropdown menus
// --------------------------------------------------------------------------

function closeExportMenu(): void {
  const menu = $("exportMenu");
  if (!menu || menu.hidden) return;
  menu.hidden = true;
  $("exportMenuBtn")?.setAttribute("aria-expanded", "false");
  document.removeEventListener("click", onExportMenuOutside, true);
}

function onExportMenuOutside(e: MouseEvent): void {
  const wrap = $("exportMenuWrap");
  if (wrap && !wrap.contains(e.target as Node)) closeExportMenu();
}

function toggleExportMenu(e: MouseEvent): void {
  e.stopPropagation();
  const menu = $("exportMenu");
  const btn = $("exportMenuBtn") as HTMLButtonElement | null;
  if (!menu || !btn || btn.disabled) return;
  const opening = menu.hidden;
  closeMoreMenu();
  if (!opening) { closeExportMenu(); return; }
  menu.hidden = false;
  btn.setAttribute("aria-expanded", "true");
  setTimeout(() => document.addEventListener("click", onExportMenuOutside, true), 0);
}

function closeMoreMenu(): void {
  const menu = $("moreMenu");
  if (!menu || menu.hidden) return;
  menu.hidden = true;
  $("moreBtn")?.setAttribute("aria-expanded", "false");
  document.removeEventListener("click", onMoreMenuOutside, true);
}

function onMoreMenuOutside(e: MouseEvent): void {
  const wrap = $("moreMenuWrap");
  if (wrap && !wrap.contains(e.target as Node)) closeMoreMenu();
}

function toggleMoreMenu(e: MouseEvent): void {
  e.stopPropagation();
  const menu = $("moreMenu");
  const btn = $("moreBtn");
  if (!menu || !btn) return;
  const opening = menu.hidden;
  closeExportMenu();
  if (!opening) { closeMoreMenu(); return; }
  menu.hidden = false;
  btn.setAttribute("aria-expanded", "true");
  syncScheduleButton();
  setTimeout(() => document.addEventListener("click", onMoreMenuOutside, true), 0);
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
  // The grid's top edge just moved; regrow/shrink it to the new free space
  // once the panel has finished folding.
  setTimeout(fitTableHeight, 60);
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
let editingPresetId: number | string | null = null;
let editingPresetName: string | null = null;
let autoRunRequested = false;                 // ?preset=<id> deep-link wants an auto-run
const DEFAULT_VIEW_ID = "default";
const COMPANY_VIEW_PREFIX = "c-";
let companyDefaultLayout: SavedLayout | null = null;
let companyDefaultParams: Record<string, unknown> = {};

type LoadedNamedView = {
  id: number;
  name: string;
  paramsSnap: string;
  layoutSnap: string;
  layoutReady: boolean;
};
let loadedNamedView: LoadedNamedView | null = null;

function stableJson(v: unknown): string {
  return JSON.stringify(v ?? null);
}

function isCustomPeriod(params: Record<string, unknown> | null | undefined): boolean {
  const raw = params || {};
  const period = String(raw.period || "").trim().toLowerCase();
  if (period === "custom") return true;
  if (period) return false;
  return !!(raw.from && raw.to);
}

function isNamedPersonalPreset(preset: { id?: number | string; name?: string }): boolean {
  if (preset.id == null || isDefaultViewId(preset.id) || isCompanyViewId(preset.id)) return false;
  const name = (preset.name || "").trim();
  return !!name && name.toLowerCase() !== "default";
}

function rememberNamedView(preset: {
  id?: number | string; name?: string;
  params?: Record<string, unknown>;
}): void {
  const key = attr("data-report-key");
  if (key === "customer_activity" || !isNamedPersonalPreset(preset) || isCustomPeriod(preset.params)) {
    loadedNamedView = null;
    syncScheduleButton();
    return;
  }
  loadedNamedView = {
    id: Number(preset.id),
    name: String(preset.name || ""),
    paramsSnap: stableJson(collectParams()),
    layoutSnap: "",
    layoutReady: false,
  };
  syncScheduleButton();
}

function isLoadedViewDirty(): boolean {
  if (!loadedNamedView) return false;
  if (stableJson(collectParams()) !== loadedNamedView.paramsSnap) return true;
  if (!loadedNamedView.layoutReady || !isReportShown()) return false;
  return stableJson(serializeLayout()) !== loadedNamedView.layoutSnap;
}

function syncScheduleButton(): void {
  const btn = $("scheduleBtn") as HTMLButtonElement | null;
  const hint = $("scheduleHint");
  if (!btn) return;
  const key = attr("data-report-key");
  let note = "";
  let on = false;
  if (key === "customer_activity") {
    note = "Customer Activity isn’t on the schedule list yet.";
  } else if (!loadedNamedView) {
    note = "Load a named saved view (not Default) to schedule it.";
  } else if (isLoadedViewDirty()) {
    note = "Save this view first. Unsaved changes aren’t scheduled.";
  } else {
    on = true;
  }
  btn.disabled = !on;
  if (hint) {
    hint.textContent = note;
    hint.hidden = !note;
  }
}

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
  const keep = pendingSalesman || sel.value;
  sel.innerHTML = '<option value="">All salesmen</option>';
  rows.forEach((r) => {
    const o = document.createElement("option");
    o.value = r.key;
    o.textContent = r.name;
    sel.appendChild(o);
  });
  if (keep) applySalesman(keep);
}

/** Match a saved salesman value to a dropdown option (key or display name). */
function resolveSalesmanOption(sel: HTMLSelectElement, val: string): string | null {
  const want = val.trim().toLowerCase();
  if (!want) return null;
  const opts = [...sel.options].filter((o) => o.value);
  const byKey = opts.find((o) => o.value.toLowerCase() === want);
  if (byKey) return byKey.value;
  const byName = opts.find((o) => (o.textContent || "").trim().toLowerCase() === want);
  if (byName) return byName.value;
  const byPrefix = opts.find((o) => {
    const name = (o.textContent || "").trim().toLowerCase();
    return name.startsWith(want + " ") || name.startsWith(want + ",");
  });
  return byPrefix ? byPrefix.value : null;
}

function applySalesman(val: string): void {
  const sel = $("salesmanSelect") as HTMLSelectElement | null;
  const raw = String(val ?? "").trim();
  if (!raw) {
    if (sel) sel.value = "";
    pendingSalesman = null;
    return;
  }
  pendingSalesman = raw;
  if (!sel) return;
  const matched = resolveSalesmanOption(sel, raw);
  if (matched) {
    sel.value = matched;
    pendingSalesman = null;
  }
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
    // Apply a deep-linked / preset salesman once options exist. Do not clear
    // pendingSalesman if the list is still empty — collectParams needs it.
    if (pendingSalesman != null) applySalesman(pendingSalesman);
    ($("salesmanSelect") as HTMLSelectElement | null)?.addEventListener("change", () => {
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

// --- inbound deep-links ---------------------------------------------------- //
// Other pages (dashboard cards, preset links) link in with query params; we
// read them once on load to seed the filters. We deliberately do NOT write
// filter state back into the URL -- the report runs on the page, so the
// address bar stays clean.

function applyDeepLink(): void {
  const q = new URLSearchParams(window.location.search);
  if (![...q.keys()].length) return;
  (["period", "status", "year", "mode"] as const).forEach((name) => {
    const el = document.querySelector<HTMLSelectElement | HTMLInputElement>(`[name="${name}"]`);
    if (!el || !q.has(name)) return;
    let v = q.get(name) || "";
    if (name === "period") v = mapPeriodValue(v);
    if (el.tagName === "SELECT" && v && ![...(el as HTMLSelectElement).options].some((o) => o.value === v)) {
      return;
    }
    el.value = v;
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
    widths: v.widths,
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
    columnFilters, group: o?.group || [], widths: o?.widths || {},
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

function layoutForCompanySave(): SavedLayout {
  if (isReportShown()) return serializeLayout();
  return pendingLayout && layoutIsUsable(pendingLayout) ? pendingLayout : serializeLayout();
}

function applyLayout(layout: SavedLayout | null): void {
  if (!layout) return;
  if (Array.isArray(layout.clones)) {
    layout.clones.forEach((c) => {
      if (!c?.key || !c?.baseKey || state.tabs[c.key]) return;
      const base = state.tabs[c.baseKey];
      if (!base) return;
      const clone: Tab = JSON.parse(JSON.stringify(base));
      clone.key = c.key;
      clone.name = c.name || `${base.name} (copy)`;
      (clone as any)._isDuplicate = true;
      (clone as any)._baseKey = c.baseKey;
      state.tabs[c.key] = clone;
      if (!state.views[c.key]) state.views[c.key] = freshView();
    });
  }
  if (layout.views) {
    Object.keys(layout.views).forEach((k) => {
      if (state.tabs[k]) state.views[k] = deserializeView(layout.views[k]);
    });
  }
  if (layout.active && state.tabs[layout.active]) state.active = layout.active;
  if (Array.isArray(layout.order) && layout.order.length) {
    const wanted = layout.order.filter((k) => state.tabs[k]);
    if (wanted.length) {
      Object.keys(state.tabs).forEach((k) => {
        if (!wanted.includes(k) && !(state.tabs[k] as any)?._isDuplicate) {
          state.removed.add(k);
        }
      });
      state.order = wanted;
    }
  }
  renderTabs();
  const active = state.active ? state.tabs[state.active] : undefined;
  if (active) { buildTable(active); syncColumnsButton(active); }
}

function presetUrl(id: number | string): string {
  return attr("data-preset-url").replace(/\/0$/, `/${id}`);
}

const csrfHeaders = () => ({ "Content-Type": "application/json", "X-CSRF-Token": attr("data-csrf") });

function companyViewGetUrl(id: number | string): string {
  return attr("data-company-view-url").replace(/\/0$/, `/${id}`);
}

async function saveView(): Promise<void> {
  if (isDefaultViewId(editingPresetId) || editingPresetName === "Default") {
    if (attr("data-can-edit-default") !== "1") {
      setStatus("Only managers and admins can change the Default view.", "error");
      return;
    }
    try {
      const layout = serializeLayout();
      const params = collectParams();
      const res = await fetch(attr("data-default-url"), {
        method: "PUT", headers: csrfHeaders(),
        body: JSON.stringify({ params, layout }),
      });
      if (!res.ok) throw new Error();
      companyDefaultLayout = layout;
      companyDefaultParams = params;
      setStatus("Updated Default.");
    } catch {
      setStatus("Could not save Default. Please try again.", "error");
    }
    return;
  }
  if (isCompanyViewId(editingPresetId) && editingPresetName) {
    if (attr("data-can-edit-default") !== "1") {
      setStatus("Only managers and admins can change company views.", "error");
      return;
    }
    try {
      const res = await fetch(attr("data-company-views-url"), {
        method: "PUT", headers: csrfHeaders(),
        body: JSON.stringify({
          name: editingPresetName, params: collectCompanyViewParams(),
          layout: layoutForCompanySave(),
        }),
      });
      if (!res.ok) throw new Error();
      setStatus(`Updated “${editingPresetName}”.`);
    } catch {
      setStatus("Could not save this company view. Please try again.", "error");
    }
    return;
  }
  const suggested = editingPresetName || "";
  const name = window.prompt(
    editingPresetId
      ? "Save this view as (same name overwrites this view):"
      : "Save this view as:",
    suggested,
  );
  if (name == null || !name.trim()) return;
  const trimmed = name.trim();
  const overwrite = !!(editingPresetId && trimmed === editingPresetName);
  try {
    const res = overwrite
      ? await fetch(presetUrl(editingPresetId!), {
          method: "PATCH", headers: csrfHeaders(),
          body: JSON.stringify({ name: trimmed, params: collectParams(), layout: serializeLayout() }),
        })
      : await fetch(attr("data-presets-url"), {
          method: "POST", headers: csrfHeaders(),
          body: JSON.stringify({ name: trimmed, params: collectParams(), layout: serializeLayout() }),
        });
    if (!res.ok) throw new Error();
    const data = await res.json().catch(() => ({}));
    if (overwrite) setStatus(`Updated “${trimmed}”.`);
    else {
      editingPresetId = (data as any).id ?? null;
      editingPresetName = trimmed;
      setStatus(`Saved “${trimmed}”.`);
    }
    rememberNamedView({
      id: editingPresetId == null ? undefined : editingPresetId,
      name: trimmed,
      params: collectParams(),
    });
    if (loadedNamedView && isReportShown()) {
      loadedNamedView.layoutSnap = stableJson(serializeLayout());
      loadedNamedView.layoutReady = true;
    }
    syncScheduleButton();
  } catch {
    setStatus("Could not save this view. Please try again.", "error");
  }
}

function applyParamsObject(params: Record<string, unknown>): void {
  (["period", "year", "mode"] as const).forEach((name) => {
    const el = document.querySelector<HTMLSelectElement | HTMLInputElement>(`[name="${name}"]`);
    if (!el || params[name] == null) return;
    let v = String(params[name]);
    if (name === "period") v = mapPeriodValue(v);
    if (el.tagName === "SELECT" && v && ![...(el as HTMLSelectElement).options].some((o) => o.value === v)) {
      return;
    }
    el.value = v;
  });
  const statusEl = document.querySelector<HTMLSelectElement>('[name="status"]');
  if (statusEl && params.status != null) {
    const raw = String(params.status);
    const aliases: Record<string, string> = { open: "Open order" };
    const mapped = aliases[raw.trim().toLowerCase()] || raw;
    if ([...statusEl.options].some((o) => o.value === mapped)) statusEl.value = mapped;
    else statusEl.value = raw;
  }
  const sd = document.querySelector<HTMLInputElement>('[name="start_date"]');
  const ed = document.querySelector<HTMLInputElement>('[name="end_date"]');
  if (sd && params.start_date != null) sd.value = String(params.start_date);
  if (ed && params.end_date != null) ed.value = String(params.end_date);
  if (params.salesman != null) applySalesman(String(params.salesman));
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

function layoutIsUsable(layout: SavedLayout | null | undefined): layout is SavedLayout {
  if (!layout) return false;
  const views = layout.views && typeof layout.views === "object" ? Object.keys(layout.views).length : 0;
  return views > 0 || (!!layout.order && layout.order.length > 0)
    || (!!layout.clones && layout.clones.length > 0);
}

function isDefaultViewId(id: unknown): boolean {
  return id === DEFAULT_VIEW_ID || id === "Default";
}

function isCompanyViewId(id: unknown): boolean {
  return typeof id === "string" && id.startsWith(COMPANY_VIEW_PREFIX);
}

function applyPendingOrDefaultLayout(): void {
  if (pendingLayout) {
    applyLayout(pendingLayout);
    pendingLayout = null;
  } else if (layoutIsUsable(companyDefaultLayout)) {
    applyLayout(companyDefaultLayout);
  }
  if (loadedNamedView && isReportShown()) {
    loadedNamedView.layoutSnap = stableJson(serializeLayout());
    loadedNamedView.layoutReady = true;
  }
  syncScheduleButton();
}

async function loadCompanyDefault(): Promise<void> {
  const url = attr("data-default-url");
  if (!url) return;
  const data = await getJSON<{ params?: Record<string, unknown>; layout?: SavedLayout }>(url);
  if (!data) return;
  companyDefaultParams = data.params || {};
  companyDefaultLayout = data.layout || null;
}

function appendPresetRow(
  panel: HTMLElement,
  preset: { id?: number | string; name: string; params?: Record<string, unknown>; layout?: SavedLayout; can_edit?: boolean },
  opts: { canDelete: boolean; canEdit: boolean },
): void {
  const row = document.createElement("div");
  row.className = "presets-row";
  const open = document.createElement("button");
  open.type = "button";
  open.className = "presets-open";
  open.textContent = preset.name;
  open.title = isDefaultViewId(preset.id)
    ? "Run the Default view"
    : (isCompanyViewId(preset.id) ? "Run this company view" : "Run this saved view");
  open.addEventListener("click", () => { closePresetsPanel(); loadPreset(preset); });
  row.appendChild(open);
  if (isCompanyViewId(preset.id)) {
    const tag = document.createElement("span");
    tag.className = "presets-kind";
    tag.textContent = "company";
    row.appendChild(tag);
  }
  if (opts.canEdit) {
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "presets-edit";
    edit.textContent = "Edit";
    edit.title = "Open this view’s filters and layout, then save";
    edit.addEventListener("click", (ev) => {
      ev.stopPropagation();
      closePresetsPanel();
      loadPreset(preset, {
        run: !isReportShown() && periodIsRunnable(preset.params),
        edit: true,
      });
      setStatus(`Editing “${preset.name}”. Change filters or layout, then Save this view.`);
    });
    row.appendChild(edit);
  }
  if (opts.canDelete) {
    const del = document.createElement("button");
    del.type = "button";
    del.className = "presets-del";
    del.textContent = "Delete";
    del.title = "Delete this view";
    del.addEventListener("click", async () => {
      if (!window.confirm(`Delete “${preset.name}”?`)) return;
      await fetch(presetUrl(preset.id!), { method: "DELETE", headers: csrfHeaders() });
      row.remove();
    });
    row.appendChild(del);
  }
  panel.appendChild(row);
}

function appendPresetFold(panel: HTMLElement, title: string): HTMLElement {
  const wrap = document.createElement("details");
  wrap.className = "presets-fold";
  const head = document.createElement("summary");
  head.className = "presets-section";
  head.textContent = title;
  wrap.appendChild(head);
  panel.appendChild(wrap);
  return wrap;
}

async function togglePresetsPanel(): Promise<void> {
  if ($("presetsPanel")) { closePresetsPanel(); return; }
  const data = await getJSON<{
    default?: { name?: string; params?: Record<string, unknown>; layout?: SavedLayout; can_edit?: boolean };
    company?: any[];
    presets: any[];
  }>(attr("data-presets-url"));
  const company = data?.company || [];
  const presets = data?.presets || [];
  const panel = document.createElement("div");
  panel.id = "presetsPanel";
  panel.className = "presets-panel";
  const canEditDefault = attr("data-can-edit-default") === "1" || !!data?.default?.can_edit;
  appendPresetRow(panel, {
    id: DEFAULT_VIEW_ID,
    name: "Default",
    params: data?.default?.params || companyDefaultParams,
    layout: data?.default?.layout || companyDefaultLayout || undefined,
    can_edit: canEditDefault,
  }, { canDelete: false, canEdit: canEditDefault });
  if (company.length) {
    const fold = appendPresetFold(panel, "Company views");
    company.forEach((p) => {
      appendPresetRow(fold, { ...p, id: `${COMPANY_VIEW_PREFIX}${p.id}` }, {
        canDelete: false, canEdit: !!p.can_edit,
      });
    });
  }
  if (!presets.length) {
    if (!company.length) {
      const empty = document.createElement("div");
      empty.className = "presets-empty";
      empty.textContent = "No other saved views yet. Use “Save this view”.";
      panel.appendChild(empty);
    }
  } else {
    const fold = appendPresetFold(panel, "My views");
    presets.forEach((p) => {
      appendPresetRow(fold, p, { canDelete: true, canEdit: true });
    });
  }
  ($("presetsBtn") as HTMLElement)?.insertAdjacentElement("afterend", panel);
  setTimeout(() => document.addEventListener("click", onPresetsOutside, true), 0);
}

function loadPreset(preset: {
  id?: number | string; name?: string;
  params?: Record<string, unknown>; layout?: SavedLayout;
}, opts?: { run?: boolean; edit?: boolean }): void {
  applyParamsObject(preset.params || {});
  pendingLayout = preset.layout || (isDefaultViewId(preset.id) ? companyDefaultLayout : null);
  if (opts?.edit) {
    editingPresetId = isDefaultViewId(preset.id) ? DEFAULT_VIEW_ID : (preset.id ?? null);
    editingPresetName = preset.name || null;
  } else {
    editingPresetId = null;
    editingPresetName = null;
  }
  rememberNamedView(preset);
  if (opts?.edit) setToolbarEnabled(isReportShown());
  if (opts?.run === false) {
    if (isReportShown() && pendingLayout) {
      applyLayout(pendingLayout);
      pendingLayout = null;
    }
    if (loadedNamedView && isReportShown()) {
      loadedNamedView.layoutSnap = stableJson(serializeLayout());
      loadedNamedView.layoutReady = true;
    }
    syncScheduleButton();
    return;
  }
  run();
}

async function autoOpenPresetIfRequested(): Promise<void> {
  const q = new URLSearchParams(window.location.search);
  const cview = q.get("cview");
  if (cview) {
    const view = await getJSON<any>(companyViewGetUrl(cview));
    if (!view) return;
    if (view?.params) applyParamsObject(view.params);
    if (view?.layout) pendingLayout = view.layout;
    loadedNamedView = null;
    syncScheduleButton();
    autoRunRequested = periodIsRunnable(view?.params);
    return;
  }
  const id = q.get("preset");
  if (!id) return;
  if (id === DEFAULT_VIEW_ID) {
    await loadCompanyDefault();
    applyParamsObject(companyDefaultParams);
    pendingLayout = companyDefaultLayout;
    loadedNamedView = null;
    syncScheduleButton();
    autoRunRequested = true;
    return;
  }
  const preset = await getJSON<any>(presetUrl(id));
  if (preset?.params) applyParamsObject(preset.params);
  if (preset?.layout) pendingLayout = preset.layout;
  rememberNamedView({
    id: Number(id), name: preset?.name, params: preset?.params, layout: preset?.layout,
  });
  autoRunRequested = true;
}

// --------------------------------------------------------------------------
// Email delivery + SharePoint folder picker
// --------------------------------------------------------------------------

// A SharePoint folder picker bound to a set of element ids. Used by both the
// email and schedule modals; each instance tracks its own selected path.
interface SpPickerEls {
  section: string; breadcrumb: string; picker: string; selected: string; status: string;
  statusAttr?: string; foldersAttr?: string; rootLabel?: string;
}

function makeSpPicker(els: SpPickerEls) {
  let cur = "";
  let selected: string | null = null;
  const statusAttr = els.statusAttr || "data-sp-status-url";
  const foldersAttr = els.foldersAttr || "data-sp-folders-url";
  const rootLabel = els.rootLabel || "Root";

  async function init(): Promise<void> {
    const section = $(els.section);
    if (!section) return;
    selected = null;
    cur = "";
    const sel = $(els.selected);
    if (sel) sel.textContent = "";
    const st = await getJSON<{ enabled: boolean; configured: boolean }>(attr(statusAttr));
    if (!st || !st.enabled) { section.hidden = true; return; }
    section.hidden = false;
    const status = $(els.status);
    if (status) status.textContent = st.configured ? "" : "(mock folders in dev)";
    load("");
  }

  async function load(path: string): Promise<void> {
    cur = path;
    const url = attr(foldersAttr) + "?path=" + encodeURIComponent(path);
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
    bc.appendChild(crumb(rootLabel, ""));
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
      if (sel) sel.textContent = `Will save to: ${cur || rootLabel}`;
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

async function postEmailNow(recipients: string, subject: string, sharepointPath: string): Promise<string> {
  const res = await fetch(attr("data-email-url"), {
    method: "POST", headers: csrfHeaders(),
    body: JSON.stringify({
      recipients, subject, sharepoint_path: sharepointPath,
      params: collectParams(), layout: serializeLayout(),
    }),
  });
  if (res.status !== 202) {
    const e = await res.json().catch(() => ({}));
    throw new Error((e as any).error || "Could not queue the email.");
  }
  const { job_id } = await res.json();
  return job_id as string;
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
    const jobId = await postEmailNow(recipients, subject, emailSp.path() || "");
    await pollEmailJob(jobId);
  } catch (e) {
    emailMsg((e as Error).message || "Could not send.", true);
  } finally {
    if (sendBtn) sendBtn.disabled = false;
  }
}

async function emailMe(): Promise<void> {
  const me = attr("data-user-email").trim();
  if (!me) {
    setStatus("This account has no email address.", "error");
    return;
  }
  const btn = $("emailMeBtn") as HTMLButtonElement | null;
  if (btn) btn.disabled = true;
  setStatus("Emailing you…");
  try {
    const jobId = await postEmailNow(me, attr("data-report-title") || "Report", "");
    const jobUrl = attr("data-job-url").replace("__ID__", jobId);
    for (let i = 0; i < 60; i++) {
      const j = await getJSON<{ status: string; error: string }>(jobUrl);
      if (!j) break;
      if (j.status === "success") {
        setStatus("Sent to " + me + ".");
        return;
      }
      if (j.status === "failure" || j.status === "cancelled") {
        setStatus(j.error || "Could not send the email.", "error");
        return;
      }
      await new Promise((r) => setTimeout(r, 1000));
    }
    setStatus("Still sending — check your inbox shortly.");
  } catch (e) {
    setStatus((e as Error).message || "Could not send.", "error");
  } finally {
    if (btn) btn.disabled = false;
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

const scheduleOd = makeSpPicker({
  section: "schedOdSection", breadcrumb: "schedOdBreadcrumb",
  picker: "schedOdPicker", selected: "schedOdSelected", status: "schedOdStatus",
  statusAttr: "data-od-status-url", foldersAttr: "data-od-folders-url", rootLabel: "OneDrive",
});
const scheduleSp = makeSpPicker({
  section: "schedSpSection", breadcrumb: "schedSpBreadcrumb",
  picker: "schedSpPicker", selected: "schedSpSelected", status: "schedSpStatus",
  statusAttr: "data-sp-status-url", foldersAttr: "data-sp-folders-url", rootLabel: "SharePoint",
});

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

async function keepCurrentRun(): Promise<void> {
  const jobId = state.jobId;
  if (!jobId) {
    setStatus("Run a report first, then Keep it.", "error");
    return;
  }
  const name = window.prompt("Name this kept run (optional):", "");
  if (name === null) return;
  const url = attr("data-keep-url").replace(/__ID__/g, jobId);
  try {
    const res = await fetch(url, {
      method: "POST", headers: csrfHeaders(),
      body: JSON.stringify({ name: name.trim() }),
    });
    if (!res.ok) throw new Error();
    const data = await res.json();
    const until = String(data.kept_until || "").slice(0, 10);
    const label = String(data.keep_name || "").trim();
    setStatus(label
      ? `Kept as “${label}” until ${until} (30 days, max 5 Kept).`
      : `Kept until ${until} (30 days, max 5 Kept).`);
  } catch {
    setStatus("Could not Keep this run.", "error");
  }
}

function openScheduleModal(): void {
  const modal = $("scheduleModal");
  if (!modal) return;
  const owner = $("schedEmailOwner") as HTMLInputElement | null;
  if (owner) owner.checked = true;
  const rec = $("schedRecipients") as HTMLInputElement | null;
  if (rec) rec.value = "";
  const noRec = $("schedNoDataRecipients") as HTMLInputElement | null;
  const noMe = $("schedNoDataMeOnly") as HTMLInputElement | null;
  if (noRec) noRec.checked = false;
  if (noMe) noMe.checked = false;
  const fn = $("schedFilename") as HTMLInputElement | null;
  if (fn && !fn.value) fn.value = DEFAULT_FILENAME_TEMPLATE;
  updateSchedFilenamePreview();
  schedMsg("", false);
  syncCadenceFields();
  modal.hidden = false;
  scheduleOd.init();
  if (attr("data-has-sharepoint") === "1") scheduleSp.init();
}

function updateSchedFilenamePreview(): void {
  const input = $("schedFilename") as HTMLInputElement | null;
  const prev = $("schedFilenamePreview");
  if (!input || !prev) return;
  const report = attr("data-report-title") || attr("data-report-key") || "Report";
  const period = String((document.querySelector('[name="period"]') as HTMLSelectElement | null)?.value || "");
  prev.textContent = previewFilename(input.value, { report, schedule: report, period });
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
    cadence.monthday = Number(($("schedMonthday") as HTMLSelectElement).value);
  }
  return { ok: true, cadence };
}

function collectScheduleRecipients(): { extras: string } {
  return { extras: (($("schedRecipients") as HTMLInputElement | null)?.value || "").trim() };
}

async function saveSchedule(): Promise<void> {
  if (!loadedNamedView || isLoadedViewDirty()) {
    schedMsg("Load a named saved view and save any edits first.", true);
    return;
  }
  const emailOn = !!($("schedEmailOwner") as HTMLInputElement | null)?.checked;
  const extras = collectScheduleRecipients().extras;
  const odPath = scheduleOd.path() || "";
  const spPath = attr("data-has-sharepoint") === "1" ? (scheduleSp.path() || "") : "";
  if (!emailOn && !odPath && !spPath) {
    schedMsg("Pick Email to the owner or a folder.", true);
    return;
  }
  const cad = collectCadence();
  if (!cad.ok) { schedMsg(cad.error || "Invalid cadence.", true); return; }
  const btn = $("schedSave") as HTMLButtonElement | null;
  if (btn) btn.disabled = true;
  schedMsg("Saving…", false);
  const privileged = attr("data-is-privileged") === "1";
  const body: Record<string, unknown> = {
    saved_report_id: loadedNamedView.id,
    cadence: cad.cadence,
    email_to_owner: emailOn,
    filename_template: (($("schedFilename") as HTMLInputElement | null)?.value || "").trim(),
    email_on_no_data: !!($("schedNoDataRecipients") as HTMLInputElement | null)?.checked,
    onedrive_path: spPath ? "" : odPath,
    sharepoint_path: spPath,
    folder_kind: spPath ? "sharepoint" : (odPath ? "onedrive" : ""),
  };
  if (privileged) {
    body.recipients = extras;
    body.email_on_no_data_me_only = !!($("schedNoDataMeOnly") as HTMLInputElement | null)?.checked;
  }
  try {
    const res = await fetch(attr("data-schedules-url"), {
      method: "POST", headers: csrfHeaders(),
      body: JSON.stringify(body),
    });
    if (res.status !== 201) {
      const e = await res.json().catch(() => ({}));
      throw new Error((e as any).error || (e as any).description || "Could not save the schedule.");
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
  $("runBtn")?.addEventListener("click", () => run({ preserveLayout: isReportShown() }));
  let resizeTimer = 0;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(fitTableHeight, 120);
  });
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
  $("cancelRunBtn")?.addEventListener("click", cancelRun);
  $("refreshBtn")?.addEventListener("click", () => run({ preserveLayout: true }));
  $("resetBtn")?.addEventListener("click", resetView);
  $("exportMenuBtn")?.addEventListener("click", toggleExportMenu);
  $("exportBtn")?.addEventListener("click", () => { closeExportMenu(); exportExcel(); });
  $("keepBtn")?.addEventListener("click", keepCurrentRun);
  $("exportsBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    closeExportMenu();
    toggleExportsPanel();
  });
  $("columnsBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    closeExportMenu();
    closeMoreMenu();
    toggleColumnsPanel();
  });
  $("saveViewBtn")?.addEventListener("click", saveView);
  $("presetsBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    closeExportMenu();
    closeMoreMenu();
    togglePresetsPanel();
  });
  $("moreBtn")?.addEventListener("click", toggleMoreMenu);
  $("emailBtn")?.addEventListener("click", openEmailModal);
  $("emailMeBtn")?.addEventListener("click", () => { void emailMe(); });
  $("emailClose")?.addEventListener("click", closeEmailModal);
  $("emailCancel")?.addEventListener("click", closeEmailModal);
  $("emailSend")?.addEventListener("click", sendEmail);
  $("emailModal")?.addEventListener("click", (e) => { if (e.target === $("emailModal")) closeEmailModal(); });
  $("scheduleBtn")?.addEventListener("click", () => { closeMoreMenu(); openScheduleModal(); });
  $("schedClose")?.addEventListener("click", closeScheduleModal);
  $("schedCancel")?.addEventListener("click", closeScheduleModal);
  $("schedFreq")?.addEventListener("change", syncCadenceFields);
  $("schedSave")?.addEventListener("click", saveSchedule);
  $("schedFilename")?.addEventListener("input", updateSchedFilenamePreview);
  document.querySelectorAll<HTMLButtonElement>(".js-fn-token").forEach((b) => {
    b.addEventListener("click", () => {
      const input = $("schedFilename") as HTMLInputElement | null;
      if (!input) return;
      input.value = (input.value || "") + (b.dataset.token || "");
      updateSchedFilenamePreview();
      input.focus();
    });
  });
  $("scheduleModal")?.addEventListener("click", (e) => { if (e.target === $("scheduleModal")) closeScheduleModal(); });
  $("previewBtn")?.addEventListener("click", () => { closeMoreMenu(); showApiPreview(); });
  $("filterForm")?.addEventListener("input", () => { refreshPreviewIfOpen(); syncScheduleButton(); });
  $("filterForm")?.addEventListener("change", () => { refreshPreviewIfOpen(); syncScheduleButton(); });
  setToolbarEnabled(false);
  loadExports();  // pick up any in-flight exports started before a navigation/reload
  await Promise.all([initLookups(), loadCompanyDefault()]);
  // If this user was already running (or just finished) this report, reconnect
  // to it instead of starting fresh -- leaving the page and coming back keeps it.
  const resumed = await resumeInFlight();
  if (!resumed) {
    await autoOpenPresetIfRequested();
    if (autoRunRequested) { autoRunRequested = false; run(); }
  }
});

export {};

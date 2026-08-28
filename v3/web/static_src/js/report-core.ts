/**
 * Shared types, DOM helpers, and viewer state for the report page.
 * Other report-* modules import from here; they must not import each other
 * at top-level for values that run at load time (functions are fine).
 */

export interface Column {
  field: string;
  header: string;
  type?: "text" | "money" | "percent" | "int" | "date";
}

export interface CommissionMonth {
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
export interface CommissionSalesman {
  salesman?: string;
  salesman_number: string;
  salesman_name: string;
  commission_pct: number;
  monthly: CommissionMonth[];
  ytd: Record<string, number>;
}

export interface Tab {
  key: string;
  name: string;
  columns: Column[];
  rows: Record<string, unknown>[];
  layout?: string;
  salesmen?: CommissionSalesman[];
  grand?: Record<string, number>;
  month_labels?: string[];
  year?: number;
  end_month?: number;
}

export interface Payload {
  report_key: string;
  tabs: Tab[];
  row_count?: number;
  generated_at?: string;
}

export interface ColFilter { op: string; v: string; v2?: string; }

export interface ViewState {
  hidden: Set<string>;
  frozen: Set<string>;
  order: string[] | null;
  sorters: { column: string; dir: string }[] | null;
  columnFilters: Record<string, ColFilter>;
  group: string[];
  widths: Record<string, number>;
}

export interface SavedLayout {
  active: string | null;
  views: Record<string, unknown>;
  order?: string[];
  clones?: { key: string; baseKey: string; name: string }[];
}

export interface LookupRow { key: string; name: string; salesman?: string; }

export const root = document.getElementById("reportRoot");

export function attr(name: string): string {
  return root?.getAttribute(name) || "";
}

export function $(id: string): HTMLElement | null {
  return document.getElementById(id);
}

export function setStatus(msg: string, kind: "info" | "error" = "info"): void {
  const el = $("reportStatus");
  if (!el) return;
  const txt = $("reportStatusText");
  if (txt) txt.textContent = msg; else el.textContent = msg;
  el.className = "report-status report-status-" + kind;
  el.hidden = false;
}

export function clearStatus(): void {
  const el = $("reportStatus");
  if (el) el.hidden = true;
}

export function fmtElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

export function money(precision: number) {
  return {
    formatter: "money",
    formatterParams: { symbol: "$", precision, thousand: ",", negativeSign: true },
    sorter: "number",
    hozAlign: "right",
  };
}

export function isoDate(value: unknown): string {
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

export function formatterFor(col: Column, colIndex = -1): Record<string, unknown> {
  const band = attr("data-report-key") === "salesman" && colIndex >= 4
    ? Math.min(Math.floor((colIndex - 4) / 4), 2)
    : -1;
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

export function isNumericType(t?: string): boolean {
  return t === "money" || t === "int" || t === "percent";
}

export function fulfillmentFillCss(score: number): string {
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

export const state: {
  tabs: Record<string, Tab>;
  order: string[];
  catalogOrder: string[];
  active: string | null;
  views: Record<string, ViewState>;
  table: any;
  jobId: string | null;
  removed: Set<string>;
} = { tabs: {}, order: [], catalogOrder: [], active: null, views: {}, table: null, jobId: null, removed: new Set<string>() };

export function freshView(): ViewState {
  return { hidden: new Set(), frozen: new Set(), order: null, sorters: null, columnFilters: {}, group: [], widths: {} };
}

export function view(key: string): ViewState {
  if (!state.views[key]) state.views[key] = freshView();
  return state.views[key];
}

export const csrfHeaders = () => ({ "Content-Type": "application/json", "X-CSRF-Token": attr("data-csrf") });

export async function getJSON<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export const selectedCustomers = new Map<string, string>();
export let customerOptions: LookupRow[] = [];
export function setCustomerOptions(rows: LookupRow[]): void { customerOptions = rows; }
export let customerPickerOpen = false;
export function setCustomerPickerOpen(v: boolean): void { customerPickerOpen = v; }
export let customerHandlersBound = false;
export function setCustomerHandlersBound(v: boolean): void { customerHandlersBound = v; }
export let lookupPollTimer: number | null = null;
export function setLookupPollTimer(v: number | null): void { lookupPollTimer = v; }
export let pendingSalesman: string | null = null;
export function setPendingSalesman(v: string | null): void { pendingSalesman = v; }
export let previewTimer: number | null = null;
export function setPreviewTimer(v: number | null): void { previewTimer = v; }
export let pendingLayout: SavedLayout | null = null;
export function setPendingLayout(v: SavedLayout | null): void { pendingLayout = v; }
export let editingPresetId: number | string | null = null;
export function setEditingPresetId(v: number | string | null): void { editingPresetId = v; }
export let editingPresetName: string | null = null;
export function setEditingPresetName(v: string | null): void { editingPresetName = v; }
export let autoRunRequested = false;
export function setAutoRunRequested(v: boolean): void { autoRunRequested = v; }
export const DEFAULT_VIEW_ID = "default";
export const COMPANY_VIEW_PREFIX = "c-";
export let companyDefaultLayout: SavedLayout | null = null;
export function setCompanyDefaultLayout(v: SavedLayout | null): void { companyDefaultLayout = v; }
export let companyDefaultParams: Record<string, unknown> = {};
export function setCompanyDefaultParams(v: Record<string, unknown>): void { companyDefaultParams = v; }
export let activeRunJobId: string | null = null;
export function setActiveRunJobId(v: string | null): void { activeRunJobId = v; }
export let runAborted = false;
export function setRunAborted(v: boolean): void { runAborted = v; }

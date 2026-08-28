/** Column filters, form params, lookups. */
import {
  $, attr, csrfHeaders, clearStatus, fmtElapsed, formatterFor, freshView,
  isoDate, isNumericType, money, setStatus, state, view,
  selectedCustomers, customerOptions, setCustomerOptions,
  customerPickerOpen, setCustomerPickerOpen,
  customerHandlersBound, setCustomerHandlersBound,
  lookupPollTimer, setLookupPollTimer,
  pendingSalesman, setPendingSalesman,
  previewTimer, setPreviewTimer,
  pendingLayout, setPendingLayout,
  editingPresetId, setEditingPresetId,
  editingPresetName, setEditingPresetName,
  autoRunRequested, setAutoRunRequested,
  DEFAULT_VIEW_ID, COMPANY_VIEW_PREFIX,
  companyDefaultLayout, setCompanyDefaultLayout,
  companyDefaultParams, setCompanyDefaultParams,
  activeRunJobId, setActiveRunJobId,
  runAborted, setRunAborted,
  getJSON,
} from "./report-core";
import type { Column, ColFilter, LookupRow, Payload, SavedLayout, Tab, ViewState } from "./report-core";

import { rebuild } from "./report-grid";
import { hiddenPollMs } from "./dialog";

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

export function operatorsFor(type?: string): OpDef[] {
  if (isNumericType(type)) return NUM_OPS;
  if (type === "date") return DATE_OPS;
  return TEXT_OPS;
}
export function opNeedsTwoValues(op: string): boolean { return op === "between"; }
export function opNeedsNoValue(op: string): boolean { return op === "empty" || op === "notEmpty"; }

export function num(x: unknown): number | null {
  // Strict: reject "12abc" so this stays in lock-step with the server-side
  // parser in delivery/layout.py (which uses Python float()).
  const s = String(x).replace(/[$,%\s]/g, "");
  if (s === "") return null;
  const v = Number(s);
  return isFinite(v) ? v : null;
}

/** Does one row pass one column's filter? */
export function rowMatches(row: Record<string, unknown>, field: string, type: string | undefined, f: ColFilter): boolean {
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
export function activeColumnFilters(tab: Tab): { field: string; type?: string; f: ColFilter }[] {
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

export function applyColumnFilters(): void {
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

export function updateFunnelStates(): void {
  if (!state.active) return;
  const cf = view(state.active).columnFilters;
  document.querySelectorAll<HTMLElement>(".col-filter-btn").forEach((btn) => {
    btn.classList.toggle("has-active-filter", !!cf[btn.dataset.field || ""]);
  });
}

let colFilterPopover: HTMLElement | null = null;
let colFilterAbort: AbortController | null = null;
export function closeColumnFilterPopover(): void {
  colFilterPopover?.remove();
  colFilterPopover = null;
  colFilterAbort?.abort(); // drops the Escape + outside-click listeners
  colFilterAbort = null;
}

export function openColumnFilterPopover(col: Column, anchor: HTMLElement): void {
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

export function collectParams(): Record<string, unknown> {
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

export function initCustomRangeToggle(): void {
  const sel = $("periodSelect") as HTMLSelectElement | null;
  if (!sel) return;
  const customs = Array.from(document.querySelectorAll<HTMLElement>("[data-custom]"));
  const sync = () => customs.forEach((c) => (c.hidden = sel.value !== "custom"));
  sel.addEventListener("change", sync);
  sync();
}

// --------------------------------------------------------------------------

export function hasFilter(id: string): boolean {
  return !!$(id);
}

export async function loadSalesmen(): Promise<void> {
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
export function resolveSalesmanOption(sel: HTMLSelectElement, val: string): string | null {
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

export function applySalesman(val: string): void {
  const sel = $("salesmanSelect") as HTMLSelectElement | null;
  const raw = String(val ?? "").trim();
  if (!raw) {
    if (sel) sel.value = "";
    setPendingSalesman( null);
    return;
  }
  setPendingSalesman( raw);
  if (!sel) return;
  const matched = resolveSalesmanOption(sel, raw);
  if (matched) {
    sel.value = matched;
    setPendingSalesman( null);
  }
}

export async function loadCustomers(): Promise<void> {
  if (!hasFilter("customerPicker")) return;
  const sel = $("salesmanSelect") as HTMLSelectElement | null;
  const salesman = sel?.value ? `?salesman=${encodeURIComponent(sel.value)}` : "";
  const data = await getJSON<{ customers: LookupRow[] }>(attr("data-customers-url") + salesman);
  setCustomerOptions( data?.customers || []);
  renderCustomerPicker();
}

/** Position the options list as a fixed overlay under the search field, so no
 *  overflow ancestor (the filter row) can clip it. */
export function positionCustomerOptions(): void {
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
export function ensureCustomerHandlers(): void {
  if (customerHandlersBound) return;
  setCustomerHandlersBound( true);
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
export function ensureCustomerInput(): HTMLInputElement | null {
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
  search.addEventListener("focus", () => { setCustomerPickerOpen(true); renderCustomerOptions(); });
  search.addEventListener("input", () => { setCustomerPickerOpen(true); renderCustomerOptions(); });
  host.appendChild(search);
  const list = document.createElement("div");
  list.className = "customer-options";
  list.hidden = true;
  host.appendChild(list);
  return search;
}

export function closeCustomerOptions(): void {
  setCustomerPickerOpen( false);
  const list = $("customerPicker")?.querySelector<HTMLElement>(".customer-options");
  if (list) list.hidden = true;
}

/** Render the open dropdown of matching customers (checkbox per row). */
export function renderCustomerOptions(): void {
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
export function renderCustomerPills(): void {
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

export function renderCustomerPicker(): void {
  if (!hasFilter("customerPicker")) return;
  ensureCustomerHandlers();
  ensureCustomerInput();
  renderCustomerPills();
  renderCustomerOptions();
}

export function setLookupStatusText(text: string): void {
  ["salesmanStatus", "customerStatus"].forEach((id) => {
    const el = $(id);
    if (el) el.textContent = text;
  });
}

export function pollLookupStatus(): void {
  const url = attr("data-lookup-status-url");
  if (!url) return;
  const tick = async () => {
    const s = await getJSON<any>(url);
    if (!s) return;
    if (s.status === "ready" || (s.cached_row_count || 0) > 0) {
      setLookupStatusText("");
      if (lookupPollTimer) { window.clearInterval(lookupPollTimer); setLookupPollTimer(null); }
      await loadSalesmen();
      await loadCustomers();
      return;
    }
    if (s.status === "loading") setLookupStatusText("(loading…)");
    else if (s.status === "error") setLookupStatusText("(using cached list)");
    else if (!s.configured) setLookupStatusText("");
  };
  tick();
  setLookupPollTimer( window.setInterval(tick, hiddenPollMs(2500)));
}

export async function initLookups(): Promise<void> {
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

export function applyDeepLink(): void {
  const q = new URLSearchParams(window.location.search);
  if (![...q.keys()].length) return;
  (["period", "status", "year", "mode"] as const).forEach((name) => {
    const el = document.querySelector<HTMLSelectElement | HTMLInputElement>(`[name="${name}"]`);
    if (el && q.has(name)) el.value = q.get(name) || "";
  });
  // The salesman <option>s aren't loaded yet; stash the value and apply it in
  // initLookups() after the list arrives (setting .value now would be lost).
  if (q.has("salesman")) setPendingSalesman(q.get("salesman") || "");
  const sd = document.querySelector<HTMLInputElement>('[name="start_date"]');
  const ed = document.querySelector<HTMLInputElement>('[name="end_date"]');
  if (sd && q.has("start_date")) sd.value = q.get("start_date") || "";
  if (ed && q.has("end_date")) ed.value = q.get("end_date") || "";
  const custs = q.get("customers");
  if (custs) custs.split(",").forEach((c) => { const k = c.trim(); if (k) selectedCustomers.set(k, k); });
}

// --- live API preview ----------------------------------------------------- //

export async function renderApiPreview(): Promise<void> {
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

export function showApiPreview(): void {
  const panel = $("apiPreview");
  if (!panel) return;
  const wrap = $("apiRunWrap");
  panel.hidden = !panel.hidden;
  if (wrap) wrap.hidden = panel.hidden;
  if (!panel.hidden) renderApiPreview();
}

/** Keep the preview panel in sync with the current filters while it's open. */
export function refreshPreviewIfOpen(): void {
  const panel = $("apiPreview");
  if (!panel || panel.hidden) return;
  if (previewTimer) window.clearTimeout(previewTimer);
  setPreviewTimer( window.setTimeout(renderApiPreview, 300));
}

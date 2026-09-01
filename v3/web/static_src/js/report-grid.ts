/** Viewer grid, tabs, and payload load. */
import {
  $, attr, csrfHeaders, clearStatus, fmtElapsed, formatterFor, freshView,
  isoDate, isNumericType, money, setStatus, state, view,
  selectedCustomers, customerOptions, setCustomerOptions,
  customerPickerOpen, setCustomerPickerOpen,
  customerHandlersBound, setCustomerHandlersBound,
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
} from "./report-core";
import type { Column, ColFilter, LookupRow, Payload, SavedLayout, Tab, ViewState } from "./report-core";
import { openColumnFilterPopover, updateFunnelStates, applyColumnFilters } from "./report-filters";
import { setControlsCollapsed, setToolbarEnabled, showReportSurface } from "./report-jobs";
import { applyLayout } from "./report-views";

declare const Tabulator: any;

export function addGroupField(tab: Tab, field: string): void {
  const g = view(tab.key).group;
  if (!field || g.includes(field)) return;
  g.push(field);
  rebuild(tab);
}

// --------------------------------------------------------------------------
// Column building (applies the tab's current view state)
// --------------------------------------------------------------------------

export function headerMenu(tab: Tab): any[] {
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

export function buildColumns(tab: Tab): any[] {
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

export function columnHeaderEl(tab: Tab, col: Column): HTMLElement {
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


// --------------------------------------------------------------------------
// View-state capture / restore
// --------------------------------------------------------------------------

export function captureActive(): void {
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

export function renderMeta(tab: Tab): void {
  const meta = $("reportMeta");
  if (!meta) return;
  const gen = state.tabs.__generated_at__ as unknown as string | undefined;
  const parts = [`${tab.rows.length.toLocaleString()} rows`];
  if (gen) parts.push(`as of ${gen}`);
  meta.textContent = parts.join(" · ");
  meta.hidden = false;
}

export function renderGroupPills(tab: Tab): void {
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

export function rebuild(tab: Tab): void {
  buildTable(tab);
}

export function buildTable(tab: Tab): void {
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
export function tableHeight(): number {
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

export function fitTableHeight(): void {
  if (!state.table) return;
  try { state.table.setHeight(tableHeight()); } catch { /* table gone */ }
}

export function n(v: unknown): number {
  const x = Number(v);
  return isFinite(x) ? x : 0;
}
export function fmtMoney(v: unknown): string {
  return n(v).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export function monthHeaderLabel(month: number, year: number | undefined): string {
  const abbr = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][month - 1] || `M${month}`;
  if (!year) return abbr;
  return `${abbr}-${String(year).slice(-2)}`;
}

export function renderCommissionCards(tab: Tab, host: HTMLElement): void {
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

export function renderTabs(): void {
  const tabsEl = $("reportTabs");
  if (!tabsEl) return;
  tabsEl.innerHTML = "";
  state.order.forEach((key) => {
    const tab = state.tabs[key];
    const btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("role", "tab");
    btn.id = `tab-${key}`;
    btn.setAttribute("aria-selected", key === state.active ? "true" : "false");
    btn.setAttribute("aria-controls", "reportPanel");
    btn.tabIndex = key === state.active ? 0 : -1;
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
  if (!tabsEl.dataset.keysBound) {
    tabsEl.dataset.keysBound = "1";
    tabsEl.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const keys = state.order;
      if (!state.active) return;
      const i = keys.indexOf(state.active);
      if (i < 0) return;
      const next = e.key === "ArrowRight"
        ? keys[(i + 1) % keys.length]
        : keys[(i - 1 + keys.length) % keys.length];
      if (!next) return;
      e.preventDefault();
      activateTab(next);
      document.getElementById(`tab-${next}`)?.focus();
    });
  }
}

export function activateTab(key: string): void {
  if (!state.tabs[key]) return;
  captureActive();
  state.active = key;
  renderTabs();
  buildTable(state.tabs[key]);
  syncColumnsButton(state.tabs[key]);
}

let tabMenuEl: HTMLElement | null = null;
export function closeTabMenu(): void {
  tabMenuEl?.remove();
  tabMenuEl = null;
}
export function openTabMenuAt(key: string, x: number, y: number): void {
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
  if ((tab as any)._isDuplicate) mk("Rename tab", () => renameTab(key));
  if (state.order.length > 1) {
    mk((tab as any)._isDuplicate ? "Delete tab" : "Remove tab", () => deleteTab(key), true);
  }
  document.body.appendChild(menu);
  tabMenuEl = menu;
  setTimeout(() => document.addEventListener("click", closeTabMenu, { once: true }), 0);
}

export function duplicateTab(key: string): void {
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

export function renameTab(key: string): void {
  const tab = state.tabs[key];
  if (!tab || !(tab as any)._isDuplicate) return;
  const name = window.prompt("Rename this tab:", tab.name);
  if (name == null) return;
  const trimmed = name.trim();
  if (!trimmed) return;
  tab.name = trimmed;
  renderTabs();
}

export function deleteTab(key: string): void {
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

export function restoreTab(key: string): void {
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

export function syncColumnsButton(tab: Tab): void {
  const btn = $("columnsBtn") as HTMLButtonElement | null;
  if (!btn) return;
  btn.disabled = tab.layout === "commission_cards";
}

let columnsPanel: HTMLElement | null = null;
export function closeColumnsPanel(): void {
  if (columnsPanel) { columnsPanel.remove(); columnsPanel = null; }
  document.removeEventListener("click", onColumnsOutside);
}
export function toggleColumnsPanel(): void {
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

  const originalKeys = Object.keys(state.tabs).filter((k) => !(state.tabs[k] as any)._isDuplicate);
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
export function onColumnsOutside(e: MouseEvent): void {
  if (columnsPanel && !columnsPanel.contains(e.target as Node) && (e.target as HTMLElement).id !== "columnsBtn") {
    closeColumnsPanel();
  }
}

export function loadPayload(payload: Payload, render = true): void {
  state.tabs = {};
  state.order = [];
  state.catalogOrder = [];
  state.views = {};
  state.removed = new Set();
  (state.tabs as any).__generated_at__ = payload.generated_at;
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
export function loadPayloadPreserving(payload: Payload): void {
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

export function cloneView(v: ViewState): ViewState {
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

/** Saved views, default view, layout serialize. */
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

import { buildTable, captureActive, renderTabs, syncColumnsButton } from "./report-grid";
import { applySalesman, collectParams, hasFilter, loadCustomers, renderCustomerPicker } from "./report-filters";
import { isReportShown, run } from "./report-jobs";

export function serializeView(v: ViewState): unknown {
  return {
    hidden: [...v.hidden], frozen: [...v.frozen], order: v.order,
    sorters: v.sorters, columnFilters: v.columnFilters, group: v.group,
    widths: v.widths,
  };
}

export function deserializeView(o: any): ViewState {
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

export function serializeLayout(): SavedLayout {
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

export function applyLayout(layout: SavedLayout | null): void {
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
        if (!wanted.includes(k) && !(state.tabs[k] as any)._isDuplicate) {
          state.removed.add(k);
        }
      });
      state.order = wanted;
    }
  }
  renderTabs();
  if (state.active) { buildTable(state.tabs[state.active]); syncColumnsButton(state.tabs[state.active]); }
}

export function presetUrl(id: number | string): string {
  return attr("data-preset-url").replace(/\/0$/, `/${id}`);
}

export function companyViewGetUrl(id: number | string): string {
  return attr("data-company-view-url").replace(/\/0$/, `/${id}`);
}

export async function saveView(): Promise<void> {
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
      setCompanyDefaultLayout( layout);
      setCompanyDefaultParams( params);
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
          name: editingPresetName, params: collectParams(), layout: serializeLayout(),
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
    if (overwrite) setStatus(`Updated “${trimmed}”.`);
    else {
      setEditingPresetId( null);
      setEditingPresetName( trimmed);
      setStatus(`Saved “${trimmed}”.`);
    }
  } catch {
    setStatus("Could not save this view. Please try again.", "error");
  }
}

export function applyParamsObject(params: Record<string, unknown>): void {
  (["period", "year", "mode"] as const).forEach((name) => {
    const el = document.querySelector<HTMLSelectElement | HTMLInputElement>(`[name="${name}"]`);
    if (el && params[name] != null) el.value = String(params[name]);
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

export function closePresetsPanel(): void {
  $("presetsPanel")?.remove();
  document.removeEventListener("click", onPresetsOutside, true);
}

export function onPresetsOutside(e: MouseEvent): void {
  const panel = $("presetsPanel");
  if (panel && !panel.contains(e.target as Node) && (e.target as HTMLElement).id !== "presetsBtn") {
    closePresetsPanel();
  }
}

export function layoutIsUsable(layout: SavedLayout | null | undefined): layout is SavedLayout {
  if (!layout) return false;
  const views = layout.views && typeof layout.views === "object" ? Object.keys(layout.views).length : 0;
  return views > 0 || (!!layout.order && layout.order.length > 0)
    || (!!layout.clones && layout.clones.length > 0);
}

export function isDefaultViewId(id: unknown): boolean {
  return id === DEFAULT_VIEW_ID || id === "Default";
}

export function isCompanyViewId(id: unknown): boolean {
  return typeof id === "string" && id.startsWith(COMPANY_VIEW_PREFIX);
}

export function applyPendingOrDefaultLayout(): void {
  if (pendingLayout) {
    applyLayout(pendingLayout);
    setPendingLayout( null);
    return;
  }
  if (layoutIsUsable(companyDefaultLayout)) applyLayout(companyDefaultLayout);
}

export async function loadCompanyDefault(): Promise<void> {
  const url = attr("data-default-url");
  if (!url) return;
  const data = await getJSON<{ params?: Record<string, unknown>; layout?: SavedLayout }>(url);
  if (!data) return;
  setCompanyDefaultParams( data.params || {});
  setCompanyDefaultLayout( data.layout || null);
}

export function appendPresetRow(
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
      loadPreset(preset, { run: !isReportShown(), edit: true });
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

export async function togglePresetsPanel(): Promise<void> {
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
    const head = document.createElement("div");
    head.className = "presets-section";
    head.textContent = "Company views";
    panel.appendChild(head);
    company.forEach((p) => {
      appendPresetRow(panel, { ...p, id: `${COMPANY_VIEW_PREFIX}${p.id}` }, {
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
    const head = document.createElement("div");
    head.className = "presets-section";
    head.textContent = "Saved views";
    panel.appendChild(head);
    presets.forEach((p) => {
      appendPresetRow(panel, p, { canDelete: true, canEdit: true });
    });
  }
  ($("presetsBtn") as HTMLElement)?.insertAdjacentElement("afterend", panel);
  setTimeout(() => document.addEventListener("click", onPresetsOutside, true), 0);
}

export function loadPreset(preset: {
  id?: number | string; name?: string;
  params?: Record<string, unknown>; layout?: SavedLayout;
}, opts?: { run?: boolean; edit?: boolean }): void {
  applyParamsObject(preset.params || {});
  setPendingLayout( preset.layout || (isDefaultViewId(preset.id) ? companyDefaultLayout : null));
  if (opts?.edit) {
    setEditingPresetId( isDefaultViewId(preset.id) ? DEFAULT_VIEW_ID : (preset.id ?? null));
    setEditingPresetName( preset.name || null);
  } else {
    setEditingPresetId( null);
    setEditingPresetName( null);
  }
  if (opts?.run === false) {
    if (isReportShown() && pendingLayout) {
      applyLayout(pendingLayout);
      setPendingLayout( null);
    }
    return;
  }
  run();
}

export async function autoOpenPresetIfRequested(): Promise<void> {
  const q = new URLSearchParams(window.location.search);
  const cview = q.get("cview");
  if (cview) {
    const view = await getJSON<any>(companyViewGetUrl(cview));
    if (view?.params) applyParamsObject(view.params);
    if (view?.layout) setPendingLayout(view.layout);
    setAutoRunRequested( true);
    return;
  }
  const id = q.get("preset");
  if (!id) return;
  if (id === DEFAULT_VIEW_ID) {
    await loadCompanyDefault();
    applyParamsObject(companyDefaultParams);
    setPendingLayout( companyDefaultLayout);
    setAutoRunRequested( true);
    return;
  }
  const preset = await getJSON<any>(presetUrl(id));
  // Apply the preset's saved filters too (don't rely on the home-page URL also
  // duplicating them into the query string) and then its layout.
  if (preset?.params) applyParamsObject(preset.params);
  if (preset?.layout) setPendingLayout(preset.layout);
  setAutoRunRequested( true);
}


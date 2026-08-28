/** Run, poll, export, keep, menus. */
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

import { bindMenu, hiddenPollMs } from "./dialog";
import { buildTable, captureActive, fitTableHeight, loadPayload, loadPayloadPreserving, renderTabs, syncColumnsButton, toggleColumnsPanel } from "./report-grid";
import { collectParams } from "./report-filters";
import { applyLayout, applyPendingOrDefaultLayout, serializeLayout } from "./report-views";

export function resetView(): void {
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
export function exportErrorFor(status: number): string {
  switch (status) {
    case 404: return "The report result expired \u2014 re-run the report, then export.";
    case 409: return "The report isn't ready yet \u2014 run it first, then export.";
    case 413: return "This export is too large \u2014 hide some columns or narrow the date range.";
    default:  return `Could not start the export (HTTP ${status}). Please try again.`;
  }
}

export async function exportExcel(): Promise<void> {
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

export function downloadExportUrl(id: string): string {
  return attr("data-export-download-url").replace("__ID__", id);
}

export function triggerDownload(id: string): void {
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
export function isExportPageActive(): boolean {
  return document.visibilityState === "visible"
    && exportPageKey === attr("data-report-key");
}

/** Poll one export job to completion; auto-download ONLY if the user is still
 *  on the same report page (visible). If they navigated away, the file is in
 *  Recent exports for manual download — no surprise file appearing later. */
export async function pollExport(id: string, autoDownload: boolean): Promise<void> {
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
    await new Promise((r) => setTimeout(r, hiddenPollMs(1500)));
  }
}

/** True while the status line is showing the export message (so a poll result
 *  doesn't stomp on an unrelated run/refresh status). */
export function exportStatusActive(): boolean {
  const el = $("reportStatus");
  return !!el && !el.hidden && el.textContent !== null && el.textContent.indexOf("Excel") >= 0;
}

export function fmtBytes(n: number): string {
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export async function loadExports(): Promise<void> {
  const list = $("exportsList");
  if (!list) return;
  const data = await getJSON<{ exports: ExportRow[] }>(attr("data-exports-url"));
  const rows = data?.exports || [];
  renderExports(rows);
  // Keep polling the list while anything is still building.
  const building = rows.some((r) => r.status === "queued" || r.status === "running");
  if (building && exportsPollTimer == null) {
    exportsPollTimer = window.setInterval(loadExports, hiddenPollMs(2000));
  } else if (!building && exportsPollTimer != null) {
    window.clearInterval(exportsPollTimer);
    exportsPollTimer = null;
  }
}

export function renderExports(rows: ExportRow[]): void {
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

export function showExportsPanel(): void {
  const panel = $("exportsPanel");
  if (!panel) return;
  panel.hidden = false;
  loadExports();
  panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

export function setExportBuildingStatus(): void {
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

export function toggleExportsPanel(): void {
  const panel = $("exportsPanel");
  if (!panel) return;
  if (panel.hidden) showExportsPanel();
  else panel.hidden = true;
}


export function showCancel(visible: boolean): void {
  const btn = $("cancelRunBtn") as HTMLButtonElement | null;
  if (btn) { btn.hidden = !visible; btn.disabled = false; }
}

export async function cancelRun(): Promise<void> {
  const jobId = activeRunJobId;
  setRunAborted(true); // the poll loop bails on its next tick
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

export async function poll(jobId: string, opts: { preserveLayout?: boolean; elapsedMs?: number } = {}): Promise<void> {
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
      await new Promise((r) => setTimeout(r, hiddenPollMs(1000)));
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
    await new Promise((r) => setTimeout(r, hiddenPollMs(1000)));
  }
  throw new Error("Timed out waiting for the report (over 10 minutes). Try a narrower date range.");
}

export function friendlyError(raw: unknown): string {
  const s = String(raw || "").trim();
  if (!s) return "The report failed to build. Please try again.";
  // Surface the on-prem API's own message when present, trimmed of stack noise.
  return s.split("\n")[0].slice(0, 300);
}

/** Is a report already on screen (so a new run keeps the user's layout)? */
export function isReportShown(): boolean {
  return !!state.active && !($("reportSurface")?.hidden ?? true);
}

export async function run(opts: { preserveLayout?: boolean; overrideParams?: Record<string, unknown> } = {}): Promise<void> {
  if (opts.preserveLayout) {
    captureActive();
    // Empty the old rows right away so the user isn't staring at stale data
    // while the new run builds; the columns/format stay put and refill on success.
    try { state.table?.clearData(); } catch { /* table not ready */ }
  }
  setToolbarEnabled(false);
  setStatus(opts.preserveLayout ? "Refreshing data…" : "Starting…");
  setRunAborted( false);
  try {
    const params = opts.overrideParams ?? collectParams();
    const res = await fetch(attr("data-run-url"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": attr("data-csrf") },
      body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error(`Could not start the report (HTTP ${res.status}).`);
    const { job_id } = await res.json();
    setActiveRunJobId( job_id);
    await poll(job_id, opts);
  } catch (err) {
    if (!runAborted) setStatus(err instanceof Error ? err.message : "Something went wrong.", "error");
  } finally {
    showCancel(false);
    setActiveRunJobId( null);
    const runBtn = $("runBtn") as HTMLButtonElement | null;
    if (runBtn) runBtn.disabled = false;
  }
}

/** Reconnect to a job that's already on the server (started in a prior visit),
 *  reusing the same poll loop -- it shows progress for a running job and loads
 *  the result for one that already finished. */
export async function resumeJob(jobId: string, elapsedMs = 0): Promise<void> {
  setToolbarEnabled(false);
  setStatus("Reconnecting to your report…");
  setRunAborted( false);
  setActiveRunJobId( jobId);
  try {
    await poll(jobId, { elapsedMs });
  } catch (err) {
    if (!runAborted) setStatus(err instanceof Error ? err.message : "Something went wrong.", "error");
  } finally {
    showCancel(false);
    setActiveRunJobId( null);
    const runBtn = $("runBtn") as HTMLButtonElement | null;
    if (runBtn) runBtn.disabled = false;
  }
}

/** On page load, pick up a report this user was running (or just finished) for
 *  THIS report and show it, so leaving and coming back doesn't lose the run.
 *  A home-page preset (?preset=) must start a new run instead of replaying
 *  the last job for this report. ?job= still wins when both are present.
 *  Returns true if it found and resumed one. */
export async function resumeInFlight(): Promise<boolean> {
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

export function setToolbarEnabled(hasData: boolean): void {
  (["refreshBtn", "resetBtn", "keepBtn", "columnsBtn", "saveViewBtn", "emailBtn", "exportMenuBtn"] as const).forEach((id) => {
    const b = $(id) as HTMLButtonElement | null;
    if (b) b.disabled = !hasData;
  });
  const runBtn = $("runBtn") as HTMLButtonElement | null;
  if (runBtn) runBtn.disabled = false;
}

// --------------------------------------------------------------------------
// Export / More dropdown menus
// --------------------------------------------------------------------------

export function closeExportMenu(): void {
  const menu = $("exportMenu");
  if (!menu || menu.hidden) return;
  menu.hidden = true;
  $("exportMenuBtn")?.setAttribute("aria-expanded", "false");
  document.removeEventListener("click", onExportMenuOutside, true);
}

export function onExportMenuOutside(e: MouseEvent): void {
  const wrap = $("exportMenuWrap");
  if (wrap && !wrap.contains(e.target as Node)) closeExportMenu();
}

export function toggleExportMenu(e: MouseEvent): void {
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

export function closeMoreMenu(): void {
  const menu = $("moreMenu");
  if (!menu || menu.hidden) return;
  menu.hidden = true;
  $("moreBtn")?.setAttribute("aria-expanded", "false");
  document.removeEventListener("click", onMoreMenuOutside, true);
}

export function onMoreMenuOutside(e: MouseEvent): void {
  const wrap = $("moreMenuWrap");
  if (wrap && !wrap.contains(e.target as Node)) closeMoreMenu();
}

export function toggleMoreMenu(e: MouseEvent): void {
  e.stopPropagation();
  const menu = $("moreMenu");
  const btn = $("moreBtn");
  if (!menu || !btn) return;
  const opening = menu.hidden;
  closeExportMenu();
  if (!opening) { closeMoreMenu(); return; }
  menu.hidden = false;
  btn.setAttribute("aria-expanded", "true");
  setTimeout(() => document.addEventListener("click", onMoreMenuOutside, true), 0);
}

// --------------------------------------------------------------------------
// Collapsible "Filters & options" panel: once a report is showing, fold the
// controls into a one-line summary so the grid takes most of the screen.
// --------------------------------------------------------------------------

export function showReportSurface(): void {
  const s = $("reportSurface");
  if (s) s.hidden = false;
}

export function setControlsCollapsed(collapsed: boolean): void {
  const c = $("reportControls");
  if (!c) return;
  c.classList.toggle("collapsed", collapsed);
  $("controlsToggle")?.setAttribute("aria-expanded", String(!collapsed));
  if (collapsed) updateControlsSummary();
  // The grid's top edge just moved; regrow/shrink it to the new free space
  // once the panel has finished folding.
  setTimeout(fitTableHeight, 60);
}

export function updateControlsSummary(): void {
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


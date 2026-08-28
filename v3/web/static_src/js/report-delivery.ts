/** Email now, SharePoint picker, schedule wizard handoff. */
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

import { hiddenPollMs, openDialog } from "./dialog";
import { collectParams } from "./report-filters";
import { closeMoreMenu } from "./report-jobs";
import { serializeLayout } from "./report-views";

// --------------------------------------------------------------------------
// Email delivery + SharePoint folder picker
// --------------------------------------------------------------------------

// A SharePoint folder picker bound to a set of element ids. Used by both the
// email and schedule modals; each instance tracks its own selected path.
interface SpPickerEls {
  section: string; breadcrumb: string; picker: string; selected: string; status: string;
  statusAttr?: string; foldersAttr?: string; rootLabel?: string;
}

export function makeSpPicker(els: SpPickerEls) {
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

export function emailMsg(text: string, isError: boolean): void {
  const el = $("emailMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
  el.className = "modal-msg" + (isError ? " modal-msg-error" : "");
}

let closeEmailDlg: (() => void) | null = null;

export function openEmailModal(): void {
  const modal = $("emailModal");
  if (!modal) return;
  (($("emailSubject") as HTMLInputElement)).value = document.title || "Report";
  (($("emailRecipients") as HTMLInputElement)).value = "";
  emailMsg("", false);
  closeEmailDlg = openDialog(modal, { initial: $("emailRecipients") });
  emailSp.init();
}

export function closeEmailModal(): void {
  closeEmailDlg?.();
  closeEmailDlg = null;
}

export async function postEmailNow(recipients: string, subject: string, sharepointPath: string): Promise<string> {
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

export async function sendEmail(): Promise<void> {
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

export async function emailMe(): Promise<void> {
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
      await new Promise((r) => setTimeout(r, hiddenPollMs(1000)));
    }
    setStatus("Still sending — check your inbox shortly.");
  } catch (e) {
    setStatus((e as Error).message || "Could not send.", "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

export async function pollEmailJob(jobId: string): Promise<void> {
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
    await new Promise((r) => setTimeout(r, hiddenPollMs(1000)));
  }
  emailMsg("Still processing — check the outbox shortly.", false);
}

// -- schedule: same wizard as the Schedules page ----------------------------

const SCHEDULE_DRAFT_KEY = "v3-schedule-from-report";

export async function keepCurrentRun(): Promise<void> {
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

export function openScheduleWizard(): void {
  closeMoreMenu();
  try {
    sessionStorage.setItem(SCHEDULE_DRAFT_KEY, JSON.stringify({
      report_key: attr("data-report-key"),
      params: collectParams(),
      layout: serializeLayout(),
    }));
  } catch { /* private mode */ }
  const page = attr("data-schedules-page") || "/schedules";
  const join = page.includes("?") ? "&" : "?";
  window.location.href = `${page}${join}from_report=1`;
}

// 3-step personal schedule wizard: named view → when → where.

import { DEFAULT_FILENAME_TEMPLATE, previewFilename } from "./filename_preview";
import { esc, jsonHeaders } from "./http";

type ViewRow = {
  id: number | string;
  name: string;
  report_key: string;
  report_title: string;
};
type ViewGroup = {
  user_id: number;
  name: string;
  email: string;
  views: ViewRow[];
};

const TOTAL = 3;
let step = 1;
let odSelected: string | null = null;
let viewCache: ViewGroup[] = [];
// Converted custom-date views stay off the picker; keep them selectable on edit.
let lockedView: { view: ViewRow; owner: ViewGroup } | null = null;

function wiz(): HTMLElement | null {
  return document.getElementById("psWizard");
}

function formEl(): HTMLFormElement | null {
  return document.getElementById("psForm") as HTMLFormElement | null;
}

function privileged(): boolean {
  return wiz()?.getAttribute("data-privileged") === "1";
}

function msg(text: string, isError: boolean): void {
  const el = document.getElementById("psMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
  el.className = "ms-msg" + (isError ? " ms-msg-error" : "");
}

function selectedView(): { view: ViewRow; owner: ViewGroup } | null {
  const sel = document.getElementById("psViewSelect") as HTMLSelectElement | null;
  const raw = sel?.value || "";
  if (!raw) return lockedView;
  if (lockedView && String(lockedView.view.id) === raw) return lockedView;
  for (const g of viewCache) {
    const view = g.views.find((v) => String(v.id) === raw);
    if (view) return { view, owner: g };
  }
  return lockedView;
}

function showStep(n: number): void {
  step = n;
  const root = wiz();
  if (!root) return;
  root.querySelectorAll<HTMLElement>(".ms-pane").forEach((p) => {
    p.hidden = Number(p.dataset.pane) !== n;
  });
  root.querySelectorAll<HTMLElement>(".ms-step").forEach((s) => {
    const i = Number(s.dataset.step);
    s.classList.toggle("is-active", i === n);
    s.classList.toggle("is-done", i < n);
  });
  const back = document.getElementById("psBackBtn");
  const next = document.getElementById("psNextBtn");
  const submit = document.getElementById("psSubmitBtn");
  if (back) back.hidden = n === 1;
  if (next) next.hidden = n === TOTAL;
  if (submit) submit.hidden = n !== TOTAL;
  if (n === 3) syncOwnerLabel();
  const title = root.querySelector<HTMLElement>(".ms-pane:not([hidden]) .ms-pane-title");
  title?.focus();
}

function syncCadence(): void {
  const form = formEl();
  if (!form) return;
  const freq = form.querySelector<HTMLInputElement>('input[name="freq"]:checked')?.value || "daily";
  const w = document.getElementById("psWeekdays");
  const m = document.getElementById("psMonthday");
  if (w) w.hidden = freq !== "weekly";
  if (m) m.hidden = freq !== "monthly";
}

function cadence(form: HTMLFormElement): { ok: boolean; cadence?: any; error?: string } {
  const freq = form.querySelector<HTMLInputElement>('input[name="freq"]:checked')?.value || "daily";
  const time = (form.elements.namedItem("time") as HTMLInputElement).value || "08:00";
  const out: any = { freq, time };
  if (freq === "weekly") {
    const days = [...form.querySelectorAll<HTMLInputElement>('input[name="weekday"]:checked')]
      .map((c) => Number(c.value));
    if (!days.length) return { ok: false, error: "Pick at least one day of the week." };
    out.weekdays = days;
  } else if (freq === "monthly") {
    const days = [...form.querySelectorAll<HTMLInputElement>('input[name="monthday"]:checked')]
      .map((c) => Number(c.value));
    if (!days.length) return { ok: false, error: "Pick at least one day of the month." };
    out.monthdays = days;
  }
  return { ok: true, cadence: out };
}

function syncOwnerLabel(): void {
  const picked = selectedView();
  const mine = wiz()?.getAttribute("data-user-name") || "";
  const name = picked && picked.owner.user_id !== 0
    ? (picked.owner.name || picked.owner.email || "")
    : mine;
  const el = document.getElementById("psOwnerName");
  if (el) el.textContent = name || "the owner";
}

function validate(n: number, form: HTMLFormElement): string | null {
  if (n === 1 && !selectedView()) return "Pick a saved view.";
  if (n === 2) {
    const cad = cadence(form);
    return cad.ok ? null : (cad.error || "Check the schedule.");
  }
  if (n === 3) {
    const emailOn = (document.getElementById("psEmailOwner") as HTMLInputElement | null)?.checked;
    const odOn = (document.getElementById("psWantOnedrive") as HTMLInputElement | null)?.checked;
    const spOn = (document.getElementById("psWantSharepoint") as HTMLInputElement | null)?.checked;
    if (!emailOn && !odOn && !spOn) return "Pick Email to the owner or a folder.";
    if (odOn && !odSelected && !(document.getElementById("psOdSelected")?.textContent || "").trim()) {
      // Folder can be OneDrive root; empty path is allowed if they checked OneDrive
      // and clicked Use this folder. If they never picked, treat as root.
    }
  }
  return null;
}

function ownerKey(g: ViewGroup): string {
  return String(g.user_id);
}

function fillViewSelect(group: ViewGroup | undefined, selectedId: string): void {
  const sel = document.getElementById("psViewSelect") as HTMLSelectElement | null;
  if (!sel) return;
  sel.innerHTML = "";
  const views = [...(group?.views || [])];
  if (lockedView && group && ownerKey(group) === ownerKey(lockedView.owner)
      && !views.some((v) => String(v.id) === String(lockedView!.view.id))) {
    views.unshift(lockedView.view);
  }
  if (!views.length) {
    const o = document.createElement("option");
    o.value = "";
    o.textContent = "No views";
    sel.appendChild(o);
    return;
  }
  views.forEach((v) => {
    const o = document.createElement("option");
    o.value = String(v.id);
    o.textContent = `${v.name} — ${v.report_title}`;
    if (String(v.id) === selectedId) o.selected = true;
    sel.appendChild(o);
  });
}

function renderViews(groups: ViewGroup[], selectedId: string): void {
  const ownerSel = document.getElementById("psOwnerSelect") as HTMLSelectElement | null;
  const empty = document.getElementById("psViewEmpty");
  if (!ownerSel) return;
  ownerSel.innerHTML = "";
  const ownerGroups = [...groups];
  if (lockedView && !ownerGroups.some((g) => ownerKey(g) === ownerKey(lockedView!.owner))) {
    ownerGroups.unshift(lockedView.owner);
  }
  const flat = ownerGroups.flatMap((g) => g.views);
  if (!flat.length && !lockedView) {
    if (empty) empty.hidden = false;
    fillViewSelect(undefined, "");
    return;
  }
  if (empty) empty.hidden = true;
  const picked = selectedId
    ? ownerGroups.find((g) => g.views.some((v) => String(v.id) === selectedId)
      || (lockedView && String(lockedView.view.id) === selectedId && ownerKey(g) === ownerKey(lockedView.owner)))
    : ownerGroups[0];
  ownerGroups.forEach((g) => {
    const o = document.createElement("option");
    o.value = ownerKey(g);
    o.textContent = g.email ? `${g.name} (${g.email})` : g.name;
    if (picked && ownerKey(g) === ownerKey(picked)) o.selected = true;
    ownerSel.appendChild(o);
  });
  const group = ownerGroups.find((g) => ownerKey(g) === ownerSel.value) || ownerGroups[0];
  fillViewSelect(group, selectedId);
  syncOwnerLabel();
}

function onOwnerChange(): void {
  const ownerSel = document.getElementById("psOwnerSelect") as HTMLSelectElement | null;
  const group = viewCache.find((g) => ownerKey(g) === (ownerSel?.value || ""))
    || (lockedView && ownerKey(lockedView.owner) === (ownerSel?.value || "") ? lockedView.owner : undefined);
  fillViewSelect(group, "");
  syncOwnerLabel();
  updateFilenamePreview();
}

async function loadViews(selectedId: string): Promise<void> {
  const url = wiz()?.getAttribute("data-views-url") || "";
  if (!url) return;
  try {
    const res = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
    const data = await res.json().catch(() => ({}));
    viewCache = (data.groups || []) as ViewGroup[];
  } catch {
    viewCache = [];
  }
  renderViews(viewCache, selectedId);
}

function updateFilenamePreview(): void {
  const input = document.getElementById("psFilename") as HTMLInputElement | null;
  const prev = document.getElementById("psFilenamePreview");
  if (!input || !prev) return;
  const picked = selectedView();
  prev.textContent = previewFilename(input.value, {
    report: picked?.view.report_title || "Report",
    schedule: picked?.view.name || "Schedule",
    period: "",
  });
}

function insertAtCursor(el: HTMLInputElement, token: string): void {
  const start = el.selectionStart ?? el.value.length;
  const end = el.selectionEnd ?? start;
  el.value = el.value.slice(0, start) + token + el.value.slice(end);
  const pos = start + token.length;
  el.setSelectionRange(pos, pos);
  el.focus();
}

function insertInEditor(token: string): void {
  const ed = document.getElementById("psEmailBody");
  if (!ed) return;
  ed.focus();
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || !ed.contains(sel.anchorNode)) {
    ed.append(document.createTextNode(token));
    return;
  }
  const range = sel.getRangeAt(0);
  range.deleteContents();
  const node = document.createTextNode(token);
  range.insertNode(node);
  range.setStartAfter(node);
  range.collapse(true);
  sel.removeAllRanges();
  sel.addRange(range);
}

function emailHtml(): string {
  const ed = document.getElementById("psEmailBody");
  if (!ed) return "";
  const html = (ed.innerHTML || "").replace(/&nbsp;/g, " ").trim();
  if (!html || html === "<br>" || html === "<p><br></p>" || html === "<div><br></div>") return "";
  return html;
}

function setEmailHtml(html: string): void {
  const ed = document.getElementById("psEmailBody");
  if (ed) ed.innerHTML = html || "";
}

function wrapSharePointLink(): void {
  const ed = document.getElementById("psEmailBody");
  if (!ed) return;
  ed.focus();
  const sel = window.getSelection();
  const text = (sel && sel.rangeCount && ed.contains(sel.anchorNode))
    ? sel.toString() : "";
  const label = esc(text.trim() || "Open in SharePoint");
  const html = `<a href="{SharePointUrl}">${label}</a>`;
  if (sel && sel.rangeCount && ed.contains(sel.anchorNode) && text) {
    document.execCommand("insertHTML", false, html);
    return;
  }
  ed.insertAdjacentHTML("beforeend", html);
}

function resetMailFields(): void {
  setText("psEmailSubject", "");
  setEmailHtml("");
}

function destOn(id: string): boolean {
  return !!(document.getElementById(id) as HTMLInputElement | null)?.checked;
}

function setText(id: string, value: string): void {
  const el = document.getElementById(id) as HTMLInputElement | null;
  if (el) el.value = value;
}

function resetPrivilegedMail(): void {
  setText("psExtras", "");
  setText("psCc", "");
  setText("psBcc", "");
}

function resetNewScheduleDefaults(): void {
  resetPrivilegedMail();
  setText("psFilename", DEFAULT_FILENAME_TEMPLATE);
  resetMailFields();
  updateFilenamePreview();
}

function xorFolders(changed: "od" | "sp"): void {
  if (changed === "od" && destOn("psWantOnedrive")) {
    const sp = document.getElementById("psWantSharepoint") as HTMLInputElement | null;
    if (sp) sp.checked = false;
  }
  if (changed === "sp" && destOn("psWantSharepoint")) {
    const od = document.getElementById("psWantOnedrive") as HTMLInputElement | null;
    if (od) od.checked = false;
  }
  const odSec = document.getElementById("psOdSection");
  const spSec = document.getElementById("psSpSection");
  if (odSec) odSec.hidden = !destOn("psWantOnedrive");
  if (spSec) spSec.hidden = !destOn("psWantSharepoint");
  if (destOn("psWantOnedrive")) void initOdPicker();
}

function openWizard(): void {
  const root = wiz();
  if (!root) return;
  root.hidden = false;
  root.scrollIntoView({ behavior: "smooth", block: "start" });
}

function closeWizard(): void {
  const root = wiz();
  if (root) root.hidden = true;
  const id = document.getElementById("psEditingId") as HTMLInputElement | null;
  if (id) id.value = "";
  const title = document.getElementById("psFormTitle");
  if (title) title.textContent = "Add a schedule";
  lockedView = null;
  resetNewScheduleDefaults();
  msg("", false);
  showStep(1);
}

function ownerEmailInRecipients(recipients: string, email: string): boolean {
  const mine = email.trim().toLowerCase();
  if (!mine) return false;
  return recipients.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean).includes(mine);
}

function extrasFromRecipients(recipients: string, email: string): string {
  const mine = email.trim().toLowerCase();
  return recipients.split(",").map((s) => s.trim()).filter((s) => s && s.toLowerCase() !== mine).join(", ");
}

async function enterEdit(row: HTMLTableRowElement): Promise<void> {
  const form = formEl();
  if (!form) return;
  (document.getElementById("psEditingId") as HTMLInputElement).value = row.dataset.id || "";
  const title = document.getElementById("psFormTitle");
  if (title) title.textContent = "Edit schedule";
  lockedView = null;
  const selectedId = row.dataset.savedReportId || "";
  await loadViews(selectedId);
  if (selectedId && !selectedView()) {
    lockedView = {
      view: {
        id: (selectedId.startsWith("default:") || selectedId.startsWith("company:"))
          ? selectedId : Number(selectedId),
        name: row.dataset.viewName || "Imported view",
        report_key: row.dataset.reportKey || "",
        report_title: row.dataset.name || "",
      },
      owner: {
        user_id: 0,
        name: row.dataset.ownerName || "",
        email: row.dataset.ownerEmail || "",
        views: [],
      },
    };
    renderViews(viewCache, selectedId);
  }
  const cad = JSON.parse(row.dataset.cadence || "{}");
  const freq = cad.freq || "daily";
  form.querySelectorAll<HTMLInputElement>('input[name="freq"]').forEach((r) => {
    r.checked = r.value === freq;
  });
  const time = form.elements.namedItem("time") as HTMLInputElement;
  if (time) time.value = cad.time || "08:00";
  form.querySelectorAll<HTMLInputElement>('input[name="weekday"]').forEach((c) => {
    c.checked = Array.isArray(cad.weekdays) && cad.weekdays.map(Number).includes(Number(c.value));
  });
  const monthdays = cad.monthdays || (cad.monthday != null ? [cad.monthday] : []);
  form.querySelectorAll<HTMLInputElement>('input[name="monthday"]').forEach((c) => {
    c.checked = monthdays.map(Number).includes(Number(c.value));
  });
  syncCadence();
  const params = JSON.parse(row.dataset.params || "{}");
  const fn = document.getElementById("psFilename") as HTMLInputElement | null;
  if (fn) fn.value = row.dataset.filenameTemplate || DEFAULT_FILENAME_TEMPLATE;
  setText("psEmailSubject", String(params.email_subject || ""));
  setEmailHtml(String(params.email_html || ""));
  const ownerEmail = row.dataset.ownerEmail || "";
  const rec = row.dataset.recipients || "";
  const emailCb = document.getElementById("psEmailOwner") as HTMLInputElement | null;
  if (emailCb) emailCb.checked = ownerEmailInRecipients(rec, ownerEmail) || (!rec && !row.dataset.sharepointPath);
  setText("psExtras", extrasFromRecipients(rec, ownerEmail));
  setText("psCc", String(params.email_cc || ""));
  setText("psBcc", String(params.email_bcc || ""));
  const folder = row.dataset.sharepointPath || "";
  const kind = row.dataset.folderKind || "onedrive";
  const odCb = document.getElementById("psWantOnedrive") as HTMLInputElement | null;
  const spCb = document.getElementById("psWantSharepoint") as HTMLInputElement | null;
  if (kind === "sharepoint" && folder) {
    if (spCb) spCb.checked = true;
    if (odCb) odCb.checked = false;
    const spIn = document.getElementById("spPathInput") as HTMLInputElement | null;
    if (spIn) spIn.value = folder;
  } else if (folder) {
    if (odCb) odCb.checked = true;
    if (spCb) spCb.checked = false;
    odSelected = folder;
    const sel = document.getElementById("psOdSelected");
    if (sel) sel.textContent = `Will save to: ${folder}`;
  } else {
    if (odCb) odCb.checked = false;
    if (spCb) spCb.checked = false;
    odSelected = null;
  }
  xorFolders(kind === "sharepoint" ? "sp" : "od");
  const noMe = document.getElementById("psNoDataMe") as HTMLInputElement | null;
  if (noMe) noMe.checked = !!params.email_on_no_data;
  const noTest = document.getElementById("psNoDataTest") as HTMLInputElement | null;
  if (noTest) noTest.checked = !!params.email_on_no_data_me_only;
  updateFilenamePreview();
  openWizard();
  showStep(1);
  syncOwnerLabel();
}

async function initOdPicker(): Promise<void> {
  const root = wiz();
  const section = document.getElementById("psOdSection");
  const statusUrl = root?.getAttribute("data-od-status-url") || "";
  if (!section || !statusUrl) return;
  try {
    const st = await fetch(statusUrl, {
      credentials: "same-origin", headers: { Accept: "application/json" },
    }).then((r) => r.json());
    const status = document.getElementById("psOdStatus");
    if (status) status.textContent = st?.configured ? "" : "(mock folders in dev)";
  } catch { /* keep picker */ }
  await loadOdFolders("");
}

async function loadOdFolders(path: string): Promise<void> {
  const root = wiz();
  const url = (root?.getAttribute("data-od-folders-url") || "") + "?path=" + encodeURIComponent(path);
  let folders: { name: string; path: string }[] = [];
  let error = "";
  try {
    const res = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) error = data.error || "Could not load OneDrive folders.";
    else folders = data.folders || [];
  } catch (e: any) {
    error = e?.message || "Could not load OneDrive folders.";
  }
  const bc = document.getElementById("psOdBreadcrumb");
  if (bc) {
    bc.innerHTML = "";
    const crumb = (label: string, target: string) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "sp-crumb";
      b.textContent = label;
      b.addEventListener("click", () => { void loadOdFolders(target); });
      return b;
    };
    bc.appendChild(crumb("OneDrive", ""));
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
      odSelected = path;
      const sel = document.getElementById("psOdSelected");
      if (sel) sel.textContent = `Will save to: ${path || "OneDrive root"}`;
    });
    bc.appendChild(use);
  }
  const picker = document.getElementById("psOdPicker");
  if (!picker) return;
  picker.innerHTML = "";
  if (error) {
    picker.innerHTML = `<div class="sp-empty sp-picker-error">${esc(error)}</div>`;
    return;
  }
  folders.forEach((f) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "sp-folder";
    b.textContent = f.name;
    b.addEventListener("click", () => { void loadOdFolders(f.path); });
    picker.appendChild(b);
  });
}

export function bindPersonalWizard(): void {
  const form = formEl();
  const root = wiz();
  if (!form || !root) return;

  document.getElementById("psStartBtn")?.addEventListener("click", () => {
    if ((document.getElementById("psStartBtn") as HTMLButtonElement).disabled) return;
    (document.getElementById("psEditingId") as HTMLInputElement).value = "";
    const title = document.getElementById("psFormTitle");
    if (title) title.textContent = "Add a schedule";
    lockedView = null;
    resetNewScheduleDefaults();
    void loadViews("").then(() => {
      openWizard();
      showStep(1);
    });
  });
  document.getElementById("psCancelBtn")?.addEventListener("click", closeWizard);
  document.getElementById("psBackBtn")?.addEventListener("click", () => {
    if (step > 1) showStep(step - 1);
  });
  document.getElementById("psNextBtn")?.addEventListener("click", () => {
    const err = validate(step, form);
    if (err) { msg(err, true); return; }
    msg("", false);
    if (step < TOTAL) showStep(step + 1);
    updateFilenamePreview();
  });
  document.getElementById("psOwnerSelect")?.addEventListener("change", onOwnerChange);
  document.getElementById("psViewSelect")?.addEventListener("change", () => {
    syncOwnerLabel();
    updateFilenamePreview();
  });
  form.querySelectorAll<HTMLInputElement>('input[name="freq"]').forEach((r) => {
    r.addEventListener("change", syncCadence);
  });
  document.getElementById("psWantOnedrive")?.addEventListener("change", () => xorFolders("od"));
  document.getElementById("psWantSharepoint")?.addEventListener("change", () => xorFolders("sp"));
  document.getElementById("psFilename")?.addEventListener("input", updateFilenamePreview);
  document.querySelectorAll<HTMLButtonElement>(".js-ps-fn-token").forEach((b) => {
    b.addEventListener("click", () => {
      const input = document.getElementById("psFilename") as HTMLInputElement | null;
      if (!input) return;
      insertAtCursor(input, b.dataset.token || "");
      updateFilenamePreview();
    });
  });
  document.querySelectorAll<HTMLButtonElement>(".js-ps-subj-token").forEach((b) => {
    b.addEventListener("click", () => {
      const input = document.getElementById("psEmailSubject") as HTMLInputElement | null;
      if (input) insertAtCursor(input, b.dataset.token || "");
    });
  });
  document.querySelectorAll<HTMLButtonElement>(".js-ps-body-token").forEach((b) => {
    b.addEventListener("click", () => insertInEditor(b.dataset.token || ""));
  });
  document.getElementById("psMailDownload")?.addEventListener("click", () => {
    insertInEditor("{DownloadButton}");
  });
  document.getElementById("psMailBold")?.addEventListener("click", () => {
    document.getElementById("psEmailBody")?.focus();
    document.execCommand("bold");
  });
  document.getElementById("psMailLink")?.addEventListener("click", wrapSharePointLink);
  document.getElementById("psEmailBody")?.addEventListener("paste", (ev) => {
    ev.preventDefault();
    const text = ev.clipboardData?.getData("text/plain") || "";
    document.execCommand("insertText", false, text);
  });
  document.querySelectorAll<HTMLButtonElement>(".js-edit").forEach((b) => {
    b.addEventListener("click", () => {
      const row = b.closest("tr") as HTMLTableRowElement | null;
      if (row?.dataset.kind === "personal") void enterEdit(row);
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    for (let s = 1; s <= TOTAL; s++) {
      const err = validate(s, form);
      if (err) { showStep(s); msg(err, true); return; }
    }
    const cad = cadence(form);
    if (!cad.ok) { msg(cad.error || "Check the schedule.", true); return; }
    const picked = selectedView();
    if (!picked) { msg("Pick a saved view.", true); return; }
    const emailOn = !!(document.getElementById("psEmailOwner") as HTMLInputElement | null)?.checked;
    const odOn = destOn("psWantOnedrive");
    const spOn = destOn("psWantSharepoint");
    const odPath = odOn ? (odSelected || "") : "";
    const spPath = spOn
      ? ((document.getElementById("spPathInput") as HTMLInputElement | null)?.value.trim() || "")
      : "";
    const body: Record<string, unknown> = {
      saved_report_id: picked.view.id,
      cadence: cad.cadence,
      email_to_owner: emailOn,
      filename_template: (document.getElementById("psFilename") as HTMLInputElement | null)?.value.trim() || "",
      email_subject: (document.getElementById("psEmailSubject") as HTMLInputElement | null)?.value.trim() || "",
      email_html: emailHtml(),
      email_on_no_data: !!(document.getElementById("psNoDataMe") as HTMLInputElement | null)?.checked,
      onedrive_path: odPath,
      sharepoint_path: spOn ? spPath : "",
      folder_kind: spOn ? "sharepoint" : (odOn ? "onedrive" : ""),
    };
    if (String(picked.view.id).startsWith("default:")) {
      body.view_name = "Default";
      body.report_key = picked.view.report_key;
    }
    if (privileged()) {
      body.recipients = (document.getElementById("psExtras") as HTMLInputElement | null)?.value.trim() || "";
      body.email_cc = (document.getElementById("psCc") as HTMLInputElement | null)?.value.trim() || "";
      body.email_bcc = (document.getElementById("psBcc") as HTMLInputElement | null)?.value.trim() || "";
      body.email_on_no_data_me_only = !!(document.getElementById("psNoDataTest") as HTMLInputElement | null)?.checked;
    }
    const editId = (document.getElementById("psEditingId") as HTMLInputElement).value;
    const submit = document.getElementById("psSubmitBtn") as HTMLButtonElement;
    submit.disabled = true;
    msg("Saving…", false);
    try {
      const url = editId
        ? (root.getAttribute("data-update-url-tpl") || "").replace("/0", "/" + editId)
        : (root.getAttribute("data-create-url") || "");
      const res = await fetch(url, {
        method: editId ? "PUT" : "POST",
        headers: jsonHeaders(),
        body: JSON.stringify(body),
      });
      if (res.ok || res.status === 201) {
        location.reload();
        return;
      }
      const err = await res.json().catch(() => ({}));
      msg((err as any).error || (err as any).description || "Could not save.", true);
    } catch {
      msg("Could not save. Check your connection and try again.", true);
    } finally {
      submit.disabled = false;
    }
  });

  syncCadence();
  updateFilenamePreview();
  showStep(1);
}

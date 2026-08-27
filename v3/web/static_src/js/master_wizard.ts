// Master schedule wizard (admin page).

import { DEFAULT_FILENAME_TEMPLATE, previewFilename, previewFolder } from "./filename_preview";
import { esc, jsonHeaders } from "./http";
import { pickerFromSelect, SearchablePicker, type PickerItem } from "./searchable_picker";

const TOTAL_STEPS = 5;
let wizardStep = 1;

interface LookupRow { key: string; name: string; }
interface SalesmanEmailRow extends LookupRow { email: string; }

let statusPicker: SearchablePicker | null = null;
let salesmanPicker: SearchablePicker | null = null;
let emailSalesmanPicker: SearchablePicker | null = null;
let customerPicker: SearchablePicker | null = null;
let salesmanEmailOptions: SalesmanEmailRow[] = [];
let lookupsStarted = false;
let lookupPollTimer: number | null = null;
let pendingSalesmen: string[] = [];
let pendingLayout: Record<string, unknown> = {};
let pendingEmailSalesmen: string[] = [];
let pendingCustomers: string[] = [];
let odSelected: string | null = null;

function wizardRoot(): HTMLElement | null {
  return document.getElementById("msWizard");
}

/** Set a <select> only to a real option. daily and yesterday are the same period. */
function setSelectValue(el: HTMLSelectElement, raw: string): void {
  const wanted = String(raw);
  const values = [...el.options].map((o) => o.value);
  if (values.includes(wanted)) {
    el.value = wanted;
    return;
  }
  const aliases: Record<string, string> = { yesterday: "daily", daily: "yesterday" };
  const mapped = aliases[wanted.trim().toLowerCase()] || "";
  if (mapped && values.includes(mapped)) el.value = mapped;
}

function canSeeCompany(): boolean {
  return wizardRoot()?.getAttribute("data-can-company") === "1";
}

function isPrivileged(): boolean {
  return wizardRoot()?.getAttribute("data-privileged") === "1";
}

function usesReportLookups(): boolean {
  return !wizardRoot()?.getAttribute("data-salesmen-url");
}

function lookupUrl(attr: string, tplAttr: string): string {
  const root = wizardRoot();
  if (!root) return "";
  const direct = root.getAttribute(attr) || "";
  if (direct) return direct;
  const tpl = root.getAttribute(tplAttr) || "";
  const form = masterForm();
  const key = form ? selectedReportKey(form) : "";
  return tpl && key ? tpl.replace("__KEY__", encodeURIComponent(key)) : "";
}

function masterForm(): HTMLFormElement | null {
  return document.getElementById("masterCreateForm") as HTMLFormElement | null;
}

function masterMsg(text: string, isError: boolean): void {
  const el = document.getElementById("masterMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
  el.className = "ms-msg" + (isError ? " ms-msg-error" : "");
  el.setAttribute("role", isError ? "alert" : "status");
}

function reportFilters(): Record<string, string[]> {
  try {
    return JSON.parse(wizardRoot()?.getAttribute("data-report-filters") || "{}");
  } catch {
    return {};
  }
}

function selectedReportKey(form: HTMLFormElement): string {
  const checked = form.querySelector<HTMLInputElement>('input[name="report_key"]:checked');
  return checked?.value || "";
}

function selectedReportTitle(form: HTMLFormElement): string {
  const checked = form.querySelector<HTMLInputElement>('input[name="report_key"]:checked');
  const card = checked?.closest(".ms-report-card");
  return card?.querySelector(".ms-report-name")?.textContent?.trim() || selectedReportKey(form);
}

function syncCadenceVisibility(form: HTMLFormElement): void {
  const freq = (form.querySelector<HTMLInputElement>('input[name="freq"]:checked')?.value) || "daily";
  const wd = document.getElementById("mWeekdays");
  const md = document.getElementById("mMonthday");
  if (wd) wd.hidden = freq !== "weekly";
  if (md) md.hidden = freq !== "monthly";
}

function syncParamsVisibility(form: HTMLFormElement): void {
  const key = selectedReportKey(form);
  const needed = reportFilters()[key] || [];
  const none = document.getElementById("msParamsNone");
  const fields = document.getElementById("msParamsFields");
  const intro = document.getElementById("msParamsIntro");
  form.querySelectorAll<HTMLElement>("[data-param]").forEach((el) => {
    const param = el.getAttribute("data-param") || "";
    el.hidden = !needed.includes(param);
  });
  const empty = needed.length === 0;
  if (none) none.hidden = !empty;
  if (fields) fields.hidden = empty;
  if (intro) intro.hidden = empty;
  void ensureLookups();
}

function syncDeliveryOptionsVisibility(form: HTMLFormElement): void {
  const key = selectedReportKey(form);
  const hasSalesmanFilter = (reportFilters()[key] || []).includes("salesman");
  const wrapper = document.getElementById("msSalesmanDelivery");
  const filtered = document.getElementById("msFilteredSalesmanEmail");
  const unfiltered = document.getElementById("msUnfilteredSalesmanSplit");
  const selectedSalesmen = salesmanPicker?.selectedKeys() || [];
  const showSplit = canSeeCompany() && hasSalesmanFilter;
  if (wrapper) wrapper.hidden = !showSplit;
  if (filtered) filtered.hidden = !showSplit || selectedSalesmen.length === 0;
  if (unfiltered) unfiltered.hidden = !showSplit || selectedSalesmen.length > 0;
  if (!showSplit) {
    const emailToSalesmen = document.getElementById("msEmailToSalesmen") as HTMLInputElement | null;
    const splitBySalesman = document.getElementById("msSplitBySalesman") as HTMLInputElement | null;
    if (emailToSalesmen) emailToSalesmen.checked = false;
    if (splitBySalesman) splitBySalesman.checked = false;
    emailSalesmanPicker?.setSelected([]);
  }
  syncDestVisibility();
  void ensureLookups();
}

function destOn(id: string): boolean {
  return !!(document.getElementById(id) as HTMLInputElement | null)?.checked;
}

function setDest(id: string, on: boolean): void {
  const el = document.getElementById(id) as HTMLInputElement | null;
  if (el) el.checked = on;
}

function syncDestVisibility(): void {
  const emailOn = destOn("msWantEmail");
  const cloudOn = destOn("msWantCloud");
  const odOn = cloudOn && destOn("msWantOnedrive");
  const spOn = cloudOn && destOn("msWantSharepoint");
  const emailPanel = document.getElementById("msEmailPanel");
  const cloudPanel = document.getElementById("msCloudPanel");
  const odSection = document.getElementById("msOdSection");
  const spSection = document.getElementById("msSpSection");
  if (emailPanel) emailPanel.hidden = !emailOn;
  if (cloudPanel) cloudPanel.hidden = !cloudOn;
  if (odSection) odSection.hidden = !odOn;
  if (spSection) spSection.hidden = !spOn;
}

async function loadSavedViews(reportKey: string): Promise<void> {
  const sel = document.getElementById("msSavedView") as HTMLSelectElement | null;
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = '<option value="default">Default</option>';
  if (!reportKey) {
    sel.value = "default";
    return;
  }
  const data = await getJSON<{
    default?: { layout?: Record<string, unknown> };
    company?: { id: number; name: string; params?: Record<string, unknown>; layout?: Record<string, unknown> }[];
    presets: { id: number; name: string; params?: Record<string, unknown>; layout?: Record<string, unknown> }[];
  }>(
    `/api/reports/${encodeURIComponent(reportKey)}/presets`,
  );
  const defLayout = (data?.default?.layout && typeof data.default.layout === "object")
    ? data.default.layout : {};
  sel.options[0].dataset.preset = JSON.stringify({ params: {}, layout: defLayout });
  const company = data?.company || [];
  if (company.length) {
    const group = document.createElement("optgroup");
    group.label = "Company views";
    company.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = `c-${p.id}`;
      opt.textContent = p.name;
      opt.dataset.preset = JSON.stringify(p);
      group.appendChild(opt);
    });
    sel.appendChild(group);
  }
  (data?.presets || []).forEach((p) => {
    const opt = document.createElement("option");
    opt.value = String(p.id);
    opt.textContent = p.name;
    opt.dataset.preset = JSON.stringify(p);
    sel.appendChild(opt);
  });
  if (current === "custom" && ![...sel.options].some((o) => o.value === "custom")) {
    const custom = document.createElement("option");
    custom.value = "custom";
    custom.textContent = "Custom";
    sel.appendChild(custom);
  }
  if ([...sel.options].some((o) => o.value === current)) sel.value = current;
  else sel.value = "default";
}

function applySavedViewFromSelect(): void {
  const sel = document.getElementById("msSavedView") as HTMLSelectElement | null;
  const form = masterForm();
  if (!sel || !form || sel.value === "custom") return;
  if (!sel.value || sel.value === "default") {
    pendingLayout = {};
    return;
  }
  const raw = sel.selectedOptions[0]?.dataset.preset;
  if (!raw) return;
  const preset = JSON.parse(raw) as { params?: Record<string, unknown>; layout?: Record<string, unknown> };
  const params = preset.params || {};
  const periodEl = form.elements.namedItem("period") as HTMLSelectElement | null;
  if (periodEl) setSelectValue(periodEl, String(params.period || ""));
  const yearEl = form.elements.namedItem("year") as HTMLSelectElement | null;
  if (yearEl) yearEl.value = params.year != null ? String(params.year) : "";
  ensurePickers();
  statusPicker?.setSelected(asStringList(params.status));
  pendingSalesmen = asStringList(params.salesman);
  salesmanPicker?.setSelected(pendingSalesmen);
  pendingCustomers = asStringList(params.customers);
  customerPicker?.setSelected(pendingCustomers);
  pendingLayout = (preset.layout && typeof preset.layout === "object") ? preset.layout : {};
  syncParamsVisibility(form);
  syncDeliveryOptionsVisibility(form);
}

function restoreSavedViewSelect(viewName: string): void {
  const sel = document.getElementById("msSavedView") as HTMLSelectElement | null;
  if (!sel) return;
  const wanted = viewName.trim() || "Default";
  if (wanted === "Default") {
    sel.value = "default";
    pendingLayout = {};
    return;
  }
  const byText = [...sel.options].find((o) => (o.textContent || "").trim() === wanted);
  if (byText) {
    sel.value = byText.value;
    return;
  }
  let custom = sel.querySelector<HTMLOptionElement>('option[value="custom"]');
  if (!custom) {
    custom = document.createElement("option");
    custom.value = "custom";
    sel.appendChild(custom);
  }
  custom.textContent = wanted === "Custom" ? "Custom" : wanted;
  sel.value = "custom";
}

function selectedViewName(): string {
  const sel = document.getElementById("msSavedView") as HTMLSelectElement | null;
  if (!sel || !sel.value || sel.value === "default") return "Default";
  if (sel.value === "custom") return (sel.selectedOptions[0]?.textContent || "Custom").trim() || "Custom";
  return (sel.selectedOptions[0]?.textContent || "Custom").trim() || "Custom";
}

function suggestName(form: HTMLFormElement): void {
  const nameEl = form.elements.namedItem("name") as HTMLInputElement | null;
  if (!nameEl || nameEl.value.trim()) return;
  const title = selectedReportTitle(form);
  if (title) nameEl.value = title + " schedule";
}

function masterCadence(form: HTMLFormElement): { ok: boolean; cadence?: any; error?: string } {
  const freq = form.querySelector<HTMLInputElement>('input[name="freq"]:checked')?.value || "daily";
  const time = (form.elements.namedItem("time") as HTMLInputElement).value || "08:00";
  const cadence: any = { freq, time };
  if (freq === "weekly") {
    const days = [...form.querySelectorAll<HTMLInputElement>('input[name="weekday"]:checked')]
      .map((c) => Number(c.value));
    if (!days.length) return { ok: false, error: "Pick at least one day of the week." };
    cadence.weekdays = days;
  } else if (freq === "monthly") {
    const days = [...form.querySelectorAll<HTMLInputElement>('input[name="monthday"]:checked')]
      .map((c) => Number(c.value));
    if (!days.length) return { ok: false, error: "Pick at least one day of the month." };
    cadence.monthdays = days;
  }
  return { ok: true, cadence };
}

function asStringList(raw: unknown): string[] {
  if (raw == null) return [];
  if (Array.isArray(raw)) return raw.map((x) => String(x).trim()).filter(Boolean);
  const s = String(raw).trim();
  if (!s) return [];
  if (s.includes(",")) return s.split(",").map((p) => p.trim()).filter(Boolean);
  return s.split(/\s+/).map((p) => p.trim()).filter(Boolean);
}

function collectParams(form: HTMLFormElement): Record<string, unknown> {
  const key = selectedReportKey(form);
  const needed = reportFilters()[key] || [];
  const out: Record<string, unknown> = {};
  if (needed.includes("period")) {
    const v = (form.elements.namedItem("period") as HTMLSelectElement).value.trim();
    if (v) out.period = v;
  }
  if (needed.includes("status")) {
    const vals = statusPicker?.selectedKeys() || [];
    if (vals.length) out.status = vals;
  }
  if (needed.includes("salesman")) {
    const vals = salesmanPicker?.selectedKeys() || [];
    if (vals.length) out.salesman = vals;
    if (canSeeCompany()) {
      const emailToSalesmen = document.getElementById("msEmailToSalesmen") as HTMLInputElement | null;
      const splitBySalesman = document.getElementById("msSplitBySalesman") as HTMLInputElement | null;
      const emailKeys = emailSalesmanPicker?.selectedKeys() || [];
      out.email_to_salesmen = vals.length > 0 && !!emailToSalesmen?.checked;
      out.split_by_salesman = vals.length === 0 && (!!splitBySalesman?.checked || emailKeys.length > 0);
      out.email_salesman_keys = vals.length === 0 ? emailKeys : [];
    }
  }
  if (needed.includes("customers")) {
    const vals = customerPicker?.selectedKeys() || [];
    if (vals.length) out.customers = vals;
  }
  if (needed.includes("year")) {
    const v = (form.elements.namedItem("year") as HTMLSelectElement).value.trim();
    if (v) out.year = v;
  }
  return out;
}

function collectExtraParams(): Record<string, unknown> {
  return {
    email_cc: (document.getElementById("msCc") as HTMLInputElement | null)?.value.trim() || "",
    email_bcc: (document.getElementById("msBcc") as HTMLInputElement | null)?.value.trim() || "",
    email_on_no_data: !!(document.getElementById("msNoDataAll") as HTMLInputElement | null)?.checked,
    email_on_no_data_me_only: !!(document.getElementById("msNoDataMe") as HTMLInputElement | null)?.checked,
  };
}

function weekdayLabels(days: number[]): string {
  const names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  return days.map((d) => names[d] || String(d)).join(", ");
}

function listLabel(raw: unknown): string {
  const vals = asStringList(raw);
  return vals.join(", ");
}

function fillReview(form: HTMLFormElement): void {
  const review = document.getElementById("msReview");
  if (!review) return;
  const cad = masterCadence(form);
  const freq = cad.cadence?.freq || "daily";
  let when = "Every day";
  if (freq === "weekly") when = "Weekly on " + weekdayLabels(cad.cadence.weekdays || []);
  if (freq === "monthly") {
    const days = Array.isArray(cad.cadence.monthdays) && cad.cadence.monthdays.length
      ? cad.cadence.monthdays
      : [cad.cadence.monthday ?? 1];
    const labels = days.map((d: number) => (d === -1 ? "last day" : `day ${d}`));
    when = "Monthly on " + labels.join(", ");
  }
  when += ` at ${cad.cadence?.time || "08:00"} Eastern`;

  const params = collectParams(form);
  const paramBits: string[] = [];
  if (params.period) paramBits.push(String(params.period).replace(/_/g, " "));
  if (params.status) paramBits.push("status " + listLabel(params.status));
  if (params.salesman) paramBits.push("salesman " + listLabel(params.salesman));
  if (params.email_to_salesmen) paramBits.push("email selected salesmen their files");
  if (params.email_salesman_keys && asStringList(params.email_salesman_keys).length) {
    paramBits.push("email salesmen " + listLabel(params.email_salesman_keys));
  } else if (params.split_by_salesman) {
    paramBits.push("split by salesman");
  }
  if (params.customers) paramBits.push("customers " + listLabel(params.customers));
  if (params.year) paramBits.push("year " + params.year);

  const recipients = (form.elements.namedItem("recipients") as HTMLInputElement).value.trim();
  const sp = (document.getElementById("spPathInput") as HTMLInputElement)?.value.trim() || "";
  const extra = collectExtraParams();
  const od = odSelected || "";
  const shared = canSeeCompany()
    && (form.querySelector<HTMLInputElement>('input[name="is_shared"]:checked')?.value === "1");
  const runAs = (document.getElementById("msRunAs") as HTMLSelectElement | null);
  const runAsLabel = runAs?.selectedOptions[0]?.textContent?.trim() || "";

  const rows: [string, string][] = [
    ["Name", (form.elements.namedItem("name") as HTMLInputElement).value.trim() || selectedReportTitle(form)],
    ["Report", selectedReportTitle(form)],
    ["View", selectedViewName()],
    ["When", when],
    ["Options", paramBits.length ? paramBits.join(", ") : "defaults (everything)"],
    ["Email", recipients || "—"],
  ];
  if (extra.email_cc) rows.push(["CC", String(extra.email_cc)]);
  if (extra.email_bcc) rows.push(["BCC", String(extra.email_bcc)]);
  rows.push(["OneDrive", od || "—"]);
  if (canSeeCompany()) rows.push(["SharePoint", sp || "—"]);
  if (canSeeCompany()) rows.push(["Visibility", shared ? "shared with admins and managers" : "private"]);
  if (isPrivileged() && runAsLabel) rows.push(["Run as", runAsLabel]);
  if (extra.email_on_no_data) rows.push(["No data", "email recipients"]);
  if (extra.email_on_no_data_me_only) rows.push(["No data", "email test addresses"]);
  review.innerHTML = rows.map(([k, v]) =>
    `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("");
}

async function getJSON<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function ensurePickers(): void {
  const form = masterForm();
  const src = document.getElementById("msStatusSource") as HTMLSelectElement | null;
  const statusHost = document.getElementById("msStatusPicker");
  const statusPills = document.getElementById("msStatusPills");
  if (!statusPicker && src && statusHost && statusPills) {
    statusPicker = pickerFromSelect(src, statusHost, statusPills, {
      placeholder: "Search statuses…",
    });
  }
  const smHost = document.getElementById("msSalesmanPicker");
  const smPills = document.getElementById("msSalesmanPills");
  if (!salesmanPicker && smHost && smPills) {
    salesmanPicker = new SearchablePicker({
      host: smHost, pills: smPills, placeholder: "Search salesmen…",
      onChange: () => { if (form) syncDeliveryOptionsVisibility(form); },
    });
  }
  const emHost = document.getElementById("msEmailSalesmanPicker");
  const emPills = document.getElementById("msEmailSalesmanPills");
  if (!emailSalesmanPicker && emHost && emPills) {
    emailSalesmanPicker = new SearchablePicker({
      host: emHost, pills: emPills, placeholder: "Search salesmen to email…",
      formatOption: (i) => i.name,
    });
  }
  const cuHost = document.getElementById("msCustomerPicker");
  const cuPills = document.getElementById("msCustomerPills");
  if (!customerPicker && cuHost && cuPills) {
    customerPicker = new SearchablePicker({
      host: cuHost, pills: cuPills, placeholder: "Search customers…",
      formatOption: (i) => `${i.key} — ${i.name}`,
    });
  }
}

async function loadSalesmen(): Promise<void> {
  ensurePickers();
  const hint = document.getElementById("msSalesmanHint");
  const url = lookupUrl("data-salesmen-url", "data-salesmen-url-tpl");
  if (!salesmanPicker || !url) return;
  const data = await getJSON<{ salesmen: LookupRow[] }>(url);
  const rows = data?.salesmen || [];
  const keep = pendingSalesmen.length ? pendingSalesmen : salesmanPicker.selectedKeys();
  salesmanPicker.setOptions(rows);
  pendingSalesmen = salesmanPicker.applyPending(keep);
  if (hint) {
    hint.textContent = rows.length
      ? "Search and check salesmen. Leave empty for all."
      : "Loading salesmen from customer master…";
  }
}

async function loadSalesmenWithEmails(): Promise<void> {
  ensurePickers();
  const hint = document.getElementById("msEmailSalesmanHint");
  const url = wizardRoot()?.getAttribute("data-salesmen-emails-url") || "";
  if (!emailSalesmanPicker || !url) return;
  const data = await getJSON<{ salesmen: SalesmanEmailRow[] }>(url);
  salesmanEmailOptions = data?.salesmen || [];
  const rows: PickerItem[] = salesmanEmailOptions.map((r) => ({
    key: r.key, name: `${r.name} <${r.email}>`,
  }));
  const keep = pendingEmailSalesmen.length ? pendingEmailSalesmen : emailSalesmanPicker.selectedKeys();
  emailSalesmanPicker.setOptions(rows);
  pendingEmailSalesmen = emailSalesmanPicker.applyPending(keep);
  if (hint) {
    hint.textContent = salesmanEmailOptions.length
      ? "Pick who should receive a split workbook. Only salesmen with saved emails appear."
      : "No salesmen with emails found yet.";
  }
}

async function loadCustomers(): Promise<void> {
  ensurePickers();
  const hint = document.getElementById("msCustomerHint");
  const url = lookupUrl("data-customers-url", "data-customers-url-tpl");
  if (!customerPicker || !url) return;
  const data = await getJSON<{ customers: LookupRow[] }>(url);
  const rows = data?.customers || [];
  customerPicker.setOptions(rows);
  pendingCustomers = customerPicker.applyPending(pendingCustomers);
  if (hint) {
    hint.textContent = rows.length
      ? "Search and check customers. Leave empty for all."
      : "Loading customers from customer master…";
  }
}

function stopLookupPoll(): void {
  if (lookupPollTimer != null) {
    window.clearInterval(lookupPollTimer);
    lookupPollTimer = null;
  }
}

function pollLookupStatus(): void {
  const url = wizardRoot()?.getAttribute("data-lookup-status-url") || "";
  if (!url) return;
  const tick = async () => {
    const s = await getJSON<{
      status?: string;
      cached_row_count?: number;
      mirror_row_count?: number;
      configured?: boolean;
    }>(url);
    if (!s) return;
    const ready = s.status === "ready"
      || (s.cached_row_count || 0) > 0
      || (s.mirror_row_count || 0) > 0;
    if (ready) {
      stopLookupPoll();
      await loadSalesmen();
      if (canSeeCompany()) await loadSalesmenWithEmails();
      await loadCustomers();
      return;
    }
    const smHint = document.getElementById("msSalesmanHint");
    const cuHint = document.getElementById("msCustomerHint");
    const msg = s.status === "loading"
      ? "Loading from customer master…"
      : s.status === "error"
        ? "Customer master still warming — retrying…"
        : (!s.configured ? "Customer master is not configured." : "Waiting for customer master…");
    if (smHint && !(salesmanPicker && salesmanPicker.optionCount())) {
      smHint.textContent = msg;
    }
    const emHint = document.getElementById("msEmailSalesmanHint");
    if (emHint && !salesmanEmailOptions.length) emHint.textContent = msg;
    if (cuHint && !(customerPicker && customerPicker.optionCount())) cuHint.textContent = msg;
  };
  void tick();
  stopLookupPoll();
  lookupPollTimer = window.setInterval(() => { void tick(); }, 2500);
}

async function ensureLookups(): Promise<void> {
  const form = masterForm();
  const key = form ? selectedReportKey(form) : "";
  if (usesReportLookups() && !key) return;
  if (lookupsStarted && !usesReportLookups()) return;
  lookupsStarted = true;
  const jobs: Promise<void>[] = [loadSalesmen(), loadCustomers()];
  if (canSeeCompany()) jobs.push(loadSalesmenWithEmails());
  await Promise.all(jobs);
  pollLookupStatus();
}

function clearMultiFilters(): void {
  statusPicker?.clear();
  salesmanPicker?.clear();
  emailSalesmanPicker?.clear();
  customerPicker?.clear();
  const emailToSalesmen = document.getElementById("msEmailToSalesmen") as HTMLInputElement | null;
  const splitBySalesman = document.getElementById("msSplitBySalesman") as HTMLInputElement | null;
  if (emailToSalesmen) emailToSalesmen.checked = false;
  if (splitBySalesman) splitBySalesman.checked = false;
}

function showStep(step: number): void {
  const root = wizardRoot();
  if (!root) return;
  wizardStep = step;
  root.querySelectorAll<HTMLElement>(".ms-pane").forEach((pane) => {
    const n = Number(pane.getAttribute("data-pane"));
    pane.hidden = n !== step;
  });
  root.querySelectorAll<HTMLElement>(".ms-step").forEach((el) => {
    const n = Number(el.getAttribute("data-step"));
    el.classList.toggle("is-active", n === step);
    el.classList.toggle("is-done", n < step);
    if (n === step) el.setAttribute("aria-current", "step");
    else el.removeAttribute("aria-current");
  });
  const pane = root.querySelector<HTMLElement>(`.ms-pane[data-pane="${step}"]`);
  pane?.querySelector<HTMLElement>(".ms-pane-title")?.focus({ preventScroll: true });
  const back = document.getElementById("msBackBtn");
  const next = document.getElementById("msNextBtn");
  const save = document.getElementById("formSubmitBtn");
  if (back) back.hidden = step <= 1;
  if (next) next.hidden = step >= TOTAL_STEPS;
  if (save) save.hidden = step < TOTAL_STEPS;
  masterMsg("", false);

  const form = masterForm();
  if (!form) return;
  if (step === 2) syncCadenceVisibility(form);
  if (step === 3) {
    syncParamsVisibility(form);
    void loadSavedViews(selectedReportKey(form));
  }
  if (step === 4) {
    syncDeliveryOptionsVisibility(form);
    syncDestVisibility();
  }
  if (step === 5) fillReview(form);
}

function validateStep(step: number, form: HTMLFormElement): string | null {
  if (step === 1) {
    if (!selectedReportKey(form)) return "Pick which report this schedule should send.";
    if (canSeeCompany() && !(form.elements.namedItem("name") as HTMLInputElement).value.trim()) {
      return "Give the schedule a name so you can find it later.";
    }
  }
  if (step === 2) {
    const cad = masterCadence(form);
    if (!cad.ok) return cad.error || "Check the schedule timing.";
  }
  if (step === 4) {
    const emailOn = destOn("msWantEmail");
    const cloudOn = destOn("msWantCloud");
    const recipients = emailOn
      ? (form.elements.namedItem("recipients") as HTMLInputElement).value.trim()
      : "";
    const sp = (cloudOn && destOn("msWantSharepoint"))
      ? ((document.getElementById("spPathInput") as HTMLInputElement)?.value.trim() || "")
      : "";
    const od = (cloudOn && destOn("msWantOnedrive")) ? (odSelected || "") : "";
    const params = collectParams(form);
    const selectedSalesmen = asStringList(params.salesman);
    const salesmanDelivery = emailOn && canSeeCompany() && (
      (selectedSalesmen.length > 0 && !!params.email_to_salesmen)
      || asStringList(params.email_salesman_keys).length > 0
    );
    if (!recipients && !sp && !od && !salesmanDelivery) {
      return canSeeCompany()
        ? "Add an email address, pick a folder, or choose salesmen to email."
        : "Add an email address or pick a OneDrive folder.";
    }
    if (canSeeCompany() && emailOn && !selectedSalesmen.length && params.split_by_salesman
        && !asStringList(params.email_salesman_keys).length) {
      return "Pick at least one salesman to email.";
    }
  }
  return null;
}

function openWizard(): void {
  const wiz = wizardRoot();
  if (!wiz) return;
  wiz.hidden = false;
  document.getElementById("msEmpty")?.setAttribute("hidden", "");
  wiz.scrollIntoView({ behavior: "smooth", block: "start" });
  void initOdPicker();
}

function closeWizard(): void {
  const wiz = wizardRoot();
  const form = masterForm();
  if (!wiz || !form) return;
  form.reset();
  clearMultiFilters();
  pendingSalesmen = [];
  pendingEmailSalesmen = [];
  pendingCustomers = [];
  salesmanEmailOptions = [];
  pendingLayout = {};
  odSelected = null;
  const odSel = document.getElementById("msOdSelected");
  if (odSel) odSel.textContent = "";
  stopLookupPoll();
  lookupsStarted = false;
  const fn = document.getElementById("msFilename") as HTMLInputElement | null;
  if (fn) fn.value = DEFAULT_FILENAME_TEMPLATE;
  updateMsFilenamePreview();
  updateMsFolderPreview();
  (document.getElementById("editingId") as HTMLInputElement).value = "";
  const kindClear = document.getElementById("editingKind") as HTMLInputElement | null;
  if (kindClear) kindClear.value = "";
  (document.getElementById("spPathInput") as HTMLInputElement).value = "";
  document.getElementById("formTitle")!.textContent = "Add a schedule";
  document.getElementById("formSubmitBtn")!.textContent = "Save schedule";
  wiz.hidden = true;
  showStep(1);
  masterMsg("", false);
  if (!document.querySelector(".ms-table-wrap")) {
    document.getElementById("msEmpty")?.removeAttribute("hidden");
  }
}

async function enterEditMode(row: HTMLTableRowElement): Promise<void> {
  const form = masterForm();
  if (!form) return;
  const id = row.dataset.id!;
  const cad = JSON.parse(row.dataset.cadence || "{}");
  const params = JSON.parse(row.dataset.params || "{}");

  (document.getElementById("editingId") as HTMLInputElement).value = id;
  const kindEl = document.getElementById("editingKind") as HTMLInputElement | null;
  if (kindEl) kindEl.value = row.dataset.kind || "master";
  (form.elements.namedItem("name") as HTMLInputElement).value = row.dataset.name || "";
  const fn = document.getElementById("msFilename") as HTMLInputElement | null;
  if (fn) fn.value = row.dataset.filenameTemplate || DEFAULT_FILENAME_TEMPLATE;

  const reportKey = row.dataset.reportKey || "";
  form.querySelectorAll<HTMLInputElement>('input[name="report_key"]').forEach((r) => {
    r.checked = r.value === reportKey;
  });

  const freq = cad.freq || "daily";
  form.querySelectorAll<HTMLInputElement>('input[name="freq"]').forEach((r) => {
    r.checked = r.value === freq;
  });
  (form.elements.namedItem("time") as HTMLInputElement).value = cad.time || "08:00";
  form.querySelectorAll<HTMLInputElement>('input[name="weekday"]').forEach((c) => {
    c.checked = Array.isArray(cad.weekdays) && cad.weekdays.includes(Number(c.value));
  });
  const monthdays = Array.isArray(cad.monthdays) && cad.monthdays.length
    ? cad.monthdays.map(Number)
    : (cad.monthday != null ? [Number(cad.monthday)] : []);
  form.querySelectorAll<HTMLInputElement>('input[name="monthday"]').forEach((c) => {
    c.checked = monthdays.includes(Number(c.value));
  });

  setSelectValue(form.elements.namedItem("period") as HTMLSelectElement, String(params.period || ""));
  ensurePickers();
  statusPicker?.setSelected(asStringList(params.status));
  pendingSalesmen = asStringList(params.salesman);
  pendingEmailSalesmen = asStringList(params.email_salesman_keys);
  salesmanPicker?.setSelected(pendingSalesmen);
  emailSalesmanPicker?.setSelected(pendingEmailSalesmen);
  const emailToSalesmen = document.getElementById("msEmailToSalesmen") as HTMLInputElement | null;
  const splitBySalesman = document.getElementById("msSplitBySalesman") as HTMLInputElement | null;
  if (emailToSalesmen) emailToSalesmen.checked = !!params.email_to_salesmen;
  if (splitBySalesman) splitBySalesman.checked = !!params.split_by_salesman;
  pendingCustomers = asStringList(params.customers);
  customerPicker?.setSelected(pendingCustomers);
  (form.elements.namedItem("year") as HTMLSelectElement).value =
    params.year != null ? String(params.year) : "";

  (form.elements.namedItem("recipients") as HTMLInputElement).value = row.dataset.recipients || "";
  const folderKind = String(params.folder_kind || "");
  const folderPath = row.dataset.sharepointPath || "";
  const shared = row.dataset.isShared === "1";
  form.querySelectorAll<HTMLInputElement>('input[name="is_shared"]').forEach((r) => {
    r.checked = r.value === (shared ? "1" : "0");
  });
  const runAs = document.getElementById("msRunAs") as HTMLSelectElement | null;
  if (runAs) runAs.value = row.dataset.runAs || "";
  const cc = document.getElementById("msCc") as HTMLInputElement | null;
  const bcc = document.getElementById("msBcc") as HTMLInputElement | null;
  if (cc) cc.value = String(params.email_cc || "");
  if (bcc) bcc.value = String(params.email_bcc || "");
  const noAll = document.getElementById("msNoDataAll") as HTMLInputElement | null;
  const noMe = document.getElementById("msNoDataMe") as HTMLInputElement | null;
  if (noAll) noAll.checked = !!params.email_on_no_data;
  if (noMe) noMe.checked = !!params.email_on_no_data_me_only;
  const useOd = folderKind === "onedrive" || (!shared && folderKind !== "sharepoint" && !!folderPath);
  const hasEmail = !!(row.dataset.recipients || "").trim()
    || !!params.email_to_salesmen || !!params.split_by_salesman
    || asStringList(params.email_salesman_keys).length > 0;
  setDest("msWantEmail", hasEmail);
  setDest("msWantCloud", !!folderPath);
  setDest("msWantOnedrive", useOd && !!folderPath);
  setDest("msWantSharepoint", !useOd && !!folderPath);
  if (useOd) {
    odSelected = folderPath;
    const sel = document.getElementById("msOdSelected");
    if (sel) sel.textContent = folderPath ? `Will save to: ${folderPath}` : "Will save to: OneDrive root";
    (document.getElementById("spPathInput") as HTMLInputElement).value = "";
  } else {
    odSelected = null;
    (document.getElementById("spPathInput") as HTMLInputElement).value = folderPath;
  }

  document.getElementById("formTitle")!.textContent = "Edit schedule";
  document.getElementById("formSubmitBtn")!.textContent = "Save changes";
  syncCadenceVisibility(form);
  lookupsStarted = false;
  stopLookupPoll();
  openWizard();
  showStep(1);
  syncParamsVisibility(form);
  await ensureLookups();
  await loadSavedViews(selectedReportKey(form));
  restoreSavedViewSelect(row.dataset.viewName || "Default");
  updateMsFilenamePreview();
  updateMsFolderPreview();
}

export function bindMasterWizard(): void {
  const form = masterForm();
  const wiz = wizardRoot();
  if (!form || !wiz) return;
  ensurePickers();

  document.getElementById("msStartBtn")?.addEventListener("click", () => {
    closeWizard();
    openWizard();
    showStep(1);
  });
  document.getElementById("msCancelBtn")?.addEventListener("click", closeWizard);
  document.getElementById("msBackBtn")?.addEventListener("click", () => {
    if (wizardStep > 1) showStep(wizardStep - 1);
  });
  document.getElementById("msNextBtn")?.addEventListener("click", () => {
    const err = validateStep(wizardStep, form);
    if (err) { masterMsg(err, true); return; }
    if (wizardStep === 1) suggestName(form);
    if (wizardStep < TOTAL_STEPS) showStep(wizardStep + 1);
    updateMsFilenamePreview();
    updateMsFolderPreview();
  });

  form.querySelectorAll<HTMLInputElement>('input[name="freq"]').forEach((r) => {
    r.addEventListener("change", () => syncCadenceVisibility(form));
  });
  form.querySelectorAll<HTMLInputElement>('input[name="report_key"]').forEach((r) => {
    r.addEventListener("change", () => {
      if (usesReportLookups()) {
        lookupsStarted = false;
        stopLookupPoll();
      }
      syncParamsVisibility(form);
      syncDeliveryOptionsVisibility(form);
      suggestName(form);
      pendingLayout = {};
      void loadSavedViews(selectedReportKey(form));
      updateMsFilenamePreview();
      updateMsFolderPreview();
    });
  });
  ["msWantEmail", "msWantCloud"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", () => syncDestVisibility());
  });
  document.getElementById("msWantOnedrive")?.addEventListener("change", () => {
    if (destOn("msWantOnedrive")) setDest("msWantSharepoint", false);
    syncDestVisibility();
  });
  document.getElementById("msWantSharepoint")?.addEventListener("change", () => {
    if (destOn("msWantSharepoint")) setDest("msWantOnedrive", false);
    syncDestVisibility();
  });
  document.getElementById("msSavedView")?.addEventListener("change", () => applySavedViewFromSelect());
  document.getElementById("msName")?.addEventListener("input", () => {
    updateMsFilenamePreview();
    updateMsFolderPreview();
  });
  document.getElementById("msPeriod")?.addEventListener("change", () => {
    updateMsFilenamePreview();
    updateMsFolderPreview();
  });
  document.getElementById("msSplitBySalesman")?.addEventListener("change", () => {
    syncDeliveryOptionsVisibility(form);
  });

  document.querySelectorAll<HTMLButtonElement>(".js-edit").forEach((b) => {
    b.addEventListener("click", () => {
      const row = b.closest("tr") as HTMLTableRowElement;
      if (row) void enterEditMode(row);
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    for (let s = 1; s <= TOTAL_STEPS; s++) {
      const err = validateStep(s, form);
      if (err) { showStep(s); masterMsg(err, true); return; }
    }
    const cad = masterCadence(form);
    if (!cad.ok) { masterMsg(cad.error!, true); return; }

    const extra = collectExtraParams();
    const emailOn = destOn("msWantEmail");
    const cloudOn = destOn("msWantCloud");
    const odOn = cloudOn && destOn("msWantOnedrive");
    const spOn = cloudOn && destOn("msWantSharepoint");
    const odPath = odOn ? (odSelected || "") : "";
    const spPath = spOn
      ? (document.getElementById("spPathInput") as HTMLInputElement).value.trim()
      : "";
    const shared = canSeeCompany()
      && (form.querySelector<HTMLInputElement>('input[name="is_shared"]:checked')?.value === "1");
    const runAsEl = document.getElementById("msRunAs") as HTMLSelectElement | null;
    const params = { ...collectParams(form), ...extra };
    if (!emailOn) {
      params.email_to_salesmen = false;
      params.split_by_salesman = false;
      params.email_salesman_keys = [];
    }
    if (odPath && !spPath) params.folder_kind = "onedrive";
    if (spPath) params.folder_kind = "sharepoint";
    const nameEl = form.elements.namedItem("name") as HTMLInputElement;
    const body: Record<string, unknown> = {
      name: nameEl.value.trim() || selectedReportTitle(form) + " schedule",
      report_key: selectedReportKey(form),
      cadence: cad.cadence,
      recipients: emailOn
        ? (form.elements.namedItem("recipients") as HTMLInputElement).value.trim()
        : "",
      filename_template: (document.getElementById("msFilename") as HTMLInputElement | null)?.value.trim() || "",
      params,
      layout: pendingLayout,
      view_name: selectedViewName(),
    };
    const editId = (document.getElementById("editingId") as HTMLInputElement).value;
    const editingKind = (document.getElementById("editingKind") as HTMLInputElement | null)?.value || "";
    if (editingKind === "personal") {
      body.onedrive_path = odPath;
      body.sharepoint_path = odPath || spPath;
    } else if (canSeeCompany()) {
      body.is_shared = shared;
      body.sharepoint_path = spPath;
      body.onedrive_path = shared ? "" : odPath;
      if (isPrivileged()) body.run_as_user_id = runAsEl?.value || "";
    } else {
      body.onedrive_path = odPath;
      body.sharepoint_path = odPath;
    }
    masterMsg("Saving…", false);
    const submitBtn = document.getElementById("formSubmitBtn") as HTMLButtonElement;
    submitBtn.disabled = true;

    try {
      let res: Response;
      if (editId) {
        const tpl = editingKind === "personal"
          ? (wiz.getAttribute("data-personal-update-url-tpl") || "")
          : wiz.getAttribute("data-update-url-tpl")!;
        const url = tpl.replace("/0", "/" + editId);
        res = await fetch(url, { method: "PUT", headers: jsonHeaders(), body: JSON.stringify(body) });
      } else {
        const url = canSeeCompany()
          ? (wiz.getAttribute("data-create-url") || "")
          : (wiz.getAttribute("data-personal-create-url") || "");
        res = await fetch(url, {
          method: "POST", headers: jsonHeaders(), body: JSON.stringify(body),
        });
      }
      if (res.ok || res.status === 201) {
        location.reload();
        return;
      }
      const err = await res.json().catch(() => ({}));
      masterMsg((err as any).error || (err as any).description || "Could not save.", true);
    } catch {
      masterMsg("Could not save. Check your connection and try again.", true);
    } finally {
      submitBtn.disabled = false;
    }
  });

  document.querySelectorAll<HTMLButtonElement>(".js-ms-fn-token").forEach((b) => {
    b.addEventListener("click", () => {
      const input = document.getElementById("msFilename") as HTMLInputElement | null;
      if (!input) return;
      input.value = (input.value || "") + (b.dataset.token || "");
      updateMsFilenamePreview();
      input.focus();
    });
  });
  document.querySelectorAll<HTMLButtonElement>(".js-ms-sp-token").forEach((b) => {
    b.addEventListener("click", () => {
      const input = document.getElementById("spPathInput") as HTMLInputElement | null;
      if (!input) return;
      const token = b.dataset.token || "";
      const cur = (input.value || "").trim();
      if (!cur) {
        input.value = token;
      } else if (cur.endsWith("/")) {
        input.value = cur + token;
      } else if (/\{[A-Za-z]+\}/.test(cur.split("/").pop() || "")) {
        input.value = cur + " " + token;
      } else {
        input.value = cur + "/" + token;
      }
      updateMsFolderPreview();
      input.focus();
    });
  });
  document.getElementById("msFilename")?.addEventListener("input", updateMsFilenamePreview);
  document.getElementById("spPathInput")?.addEventListener("input", updateMsFolderPreview);
  updateMsFilenamePreview();
  updateMsFolderPreview();

  showStep(1);
}

async function initOdPicker(): Promise<void> {
  const root = wizardRoot();
  const section = document.getElementById("msOdSection");
  const statusUrl = root?.getAttribute("data-od-status-url") || "";
  if (!section || !statusUrl) return;
  try {
    const st = await fetch(statusUrl, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    }).then((r) => r.json());
    section.hidden = !st?.enabled;
    const status = document.getElementById("msOdStatus");
    if (status) status.textContent = st?.configured ? "" : "(mock folders in dev)";
  } catch {
    section.hidden = true;
    return;
  }
  await loadOdFolders("");
}

async function loadOdFolders(path: string): Promise<void> {
  const root = wizardRoot();
  const url = (root?.getAttribute("data-od-folders-url") || "") + "?path=" + encodeURIComponent(path);
  let folders: { name: string; path: string }[] = [];
  let error = "";
  try {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      error = data.error || (res.status === 401
        ? "Sign in expired — refresh the page."
        : "HTTP " + res.status);
    } else if (data.error) {
      error = data.error;
    } else {
      folders = data.folders || [];
    }
  } catch (e: any) {
    error = e?.message || "Could not load OneDrive folders.";
  }
  const bc = document.getElementById("msOdBreadcrumb");
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
      const sel = document.getElementById("msOdSelected");
      if (sel) sel.textContent = `Will save to: ${path || "OneDrive root"}`;
    });
    bc.appendChild(use);
  }
  const picker = document.getElementById("msOdPicker");
  if (!picker) return;
  picker.innerHTML = "";
  if (error) {
    picker.innerHTML = `<div class="sp-empty sp-picker-error">${esc(error)}</div>`;
    return;
  }
  if (!folders.length) {
    picker.innerHTML = '<div class="sp-empty">No subfolders here.</div>';
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

function updateMsFilenamePreview(): void {
  const input = document.getElementById("msFilename") as HTMLInputElement | null;
  const prev = document.getElementById("msFilenamePreview");
  if (!input || !prev) return;
  const form = masterForm();
  const report = form ? selectedReportTitle(form) : "";
  const schedule = (document.getElementById("msName") as HTMLInputElement | null)?.value.trim()
    || (report ? report + " schedule" : "");
  const period = (document.getElementById("msPeriod") as HTMLSelectElement | null)?.value || "";
  prev.textContent = previewFilename(input.value, { report, schedule, period });
}

function updateMsFolderPreview(): void {
  const input = document.getElementById("spPathInput") as HTMLInputElement | null;
  const prev = document.getElementById("msFolderPreview");
  if (!input || !prev) return;
  const form = masterForm();
  const report = form ? selectedReportTitle(form) : "";
  const schedule = (document.getElementById("msName") as HTMLInputElement | null)?.value.trim()
    || (report ? report + " schedule" : "");
  const period = (document.getElementById("msPeriod") as HTMLSelectElement | null)?.value || "";
  prev.textContent = previewFolder(input.value, { report, schedule, period });
}

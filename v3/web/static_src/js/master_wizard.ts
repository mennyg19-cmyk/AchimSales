// Master schedule wizard (admin page).

import { esc, jsonHeaders } from "./http";

const TOTAL_STEPS = 5;
let wizardStep = 1;

interface LookupRow { key: string; name: string; }
interface SalesmanEmailRow extends LookupRow { email: string; }

const selectedCustomers = new Map<string, string>(); // account -> display name
let customerOptions: LookupRow[] = [];
let salesmanEmailOptions: SalesmanEmailRow[] = [];
let customerPickerOpen = false;
let customerHandlersBound = false;
let lookupsStarted = false;
let lookupPollTimer: number | null = null;
let pendingSalesmen: string[] = [];
let pendingEmailSalesmen: string[] = [];
let pendingCustomers: string[] = [];

function wizardRoot(): HTMLElement | null {
  return document.getElementById("msWizard");
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
  const selectedSalesmen = multiValues(document.getElementById("msSalesman") as HTMLSelectElement | null);
  if (wrapper) wrapper.hidden = !hasSalesmanFilter;
  if (filtered) filtered.hidden = !hasSalesmanFilter || selectedSalesmen.length === 0;
  if (unfiltered) unfiltered.hidden = !hasSalesmanFilter || selectedSalesmen.length > 0;
  if (!hasSalesmanFilter) {
    const emailToSalesmen = document.getElementById("msEmailToSalesmen") as HTMLInputElement | null;
    const splitBySalesman = document.getElementById("msSplitBySalesman") as HTMLInputElement | null;
    if (emailToSalesmen) emailToSalesmen.checked = false;
    if (splitBySalesman) splitBySalesman.checked = false;
    setMultiSelected(document.getElementById("msEmailSalesmanKeys") as HTMLSelectElement | null, []);
  }
  void ensureLookups();
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

function multiValues(sel: HTMLSelectElement | null): string[] {
  if (!sel) return [];
  return [...sel.selectedOptions].map((o) => o.value.trim()).filter(Boolean);
}

function asStringList(raw: unknown): string[] {
  if (raw == null) return [];
  if (Array.isArray(raw)) return raw.map((x) => String(x).trim()).filter(Boolean);
  const s = String(raw).trim();
  if (!s) return [];
  if (s.includes(",")) return s.split(",").map((p) => p.trim()).filter(Boolean);
  return s.split(/\s+/).map((p) => p.trim()).filter(Boolean);
}

function setMultiSelected(sel: HTMLSelectElement | null, values: string[]): void {
  if (!sel) return;
  const want = new Set(values);
  [...sel.options].forEach((o) => { o.selected = want.has(o.value); });
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
    const vals = multiValues(document.getElementById("msStatus") as HTMLSelectElement | null);
    if (vals.length) out.status = vals;
  }
  if (needed.includes("salesman")) {
    const vals = multiValues(document.getElementById("msSalesman") as HTMLSelectElement | null);
    if (vals.length) out.salesman = vals;
    const emailToSalesmen = document.getElementById("msEmailToSalesmen") as HTMLInputElement | null;
    const splitBySalesman = document.getElementById("msSplitBySalesman") as HTMLInputElement | null;
    const emailKeys = multiValues(document.getElementById("msEmailSalesmanKeys") as HTMLSelectElement | null);
    out.email_to_salesmen = vals.length > 0 && !!emailToSalesmen?.checked;
    out.split_by_salesman = vals.length === 0 && (!!splitBySalesman?.checked || emailKeys.length > 0);
    out.email_salesman_keys = vals.length === 0 ? emailKeys : [];
  }
  if (needed.includes("customers")) {
    const vals = [...selectedCustomers.keys()];
    if (vals.length) out.customers = vals;
  }
  if (needed.includes("year")) {
    const v = (form.elements.namedItem("year") as HTMLSelectElement).value.trim();
    if (v) out.year = v;
  }
  return out;
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

  const rows: [string, string][] = [
    ["Name", (form.elements.namedItem("name") as HTMLInputElement).value.trim()],
    ["Report", selectedReportTitle(form)],
    ["When", when],
    ["Options", paramBits.length ? paramBits.join(", ") : "defaults (everything)"],
    ["Email", recipients || "—"],
    ["SharePoint", sp || "—"],
  ];
  review.innerHTML = rows.map(([k, v]) =>
    `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("");
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
  const sel = document.getElementById("msSalesman") as HTMLSelectElement | null;
  const hint = document.getElementById("msSalesmanHint");
  const url = wizardRoot()?.getAttribute("data-salesmen-url") || "";
  if (!sel || !url) return;
  const data = await getJSON<{ salesmen: LookupRow[] }>(url);
  const rows = data?.salesmen || [];
  const keep = pendingSalesmen.length ? pendingSalesmen : multiValues(sel);
  sel.innerHTML = "";
  rows.forEach((r) => {
    const o = document.createElement("option");
    o.value = r.key;
    o.textContent = r.name;
    sel.appendChild(o);
  });
  setMultiSelected(sel, keep);
  if (rows.length) pendingSalesmen = [];
  if (hint) {
    hint.textContent = rows.length
      ? "Hold Ctrl (Windows) or ⌘ (Mac) to pick several. Leave empty for all salesmen."
      : "Loading salesmen from customer master…";
  }
}

async function loadSalesmenWithEmails(): Promise<void> {
  const sel = document.getElementById("msEmailSalesmanKeys") as HTMLSelectElement | null;
  const hint = document.getElementById("msEmailSalesmanHint");
  const url = wizardRoot()?.getAttribute("data-salesmen-emails-url") || "";
  if (!sel || !url) return;
  const data = await getJSON<{ salesmen: SalesmanEmailRow[] }>(url);
  salesmanEmailOptions = data?.salesmen || [];
  const keep = pendingEmailSalesmen.length ? pendingEmailSalesmen : multiValues(sel);
  sel.innerHTML = "";
  salesmanEmailOptions.forEach((r) => {
    const o = document.createElement("option");
    o.value = r.key;
    o.textContent = `${r.name} <${r.email}>`;
    sel.appendChild(o);
  });
  setMultiSelected(sel, keep);
  if (salesmanEmailOptions.length) pendingEmailSalesmen = [];
  if (hint) {
    hint.textContent = salesmanEmailOptions.length
      ? "Pick who should receive a split workbook. Only salesmen with saved emails appear."
      : "No salesmen with emails found yet.";
  }
}

function positionCustomerOptions(): void {
  const host = document.getElementById("msCustomerPicker");
  const search = host?.querySelector<HTMLElement>(".customer-search");
  const list = host?.querySelector<HTMLElement>(".customer-options");
  if (!search || !list || list.hidden) return;
  const r = search.getBoundingClientRect();
  list.style.position = "fixed";
  list.style.top = `${Math.round(r.bottom + 2)}px`;
  list.style.left = `${Math.round(r.left)}px`;
  list.style.width = `${Math.round(r.width)}px`;
}

function ensureCustomerHandlers(): void {
  if (customerHandlersBound) return;
  customerHandlersBound = true;
  const inside = (t: Node) => {
    const p = document.getElementById("msCustomerPicker");
    const pills = document.getElementById("msCustomerPills");
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

function ensureCustomerInput(): HTMLInputElement | null {
  const host = document.getElementById("msCustomerPicker");
  if (!host) return null;
  let search = host.querySelector<HTMLInputElement>(".customer-search");
  if (search) return search;
  host.innerHTML = "";
  search = document.createElement("input");
  search.type = "text";
  search.className = "customer-search";
  search.placeholder = host.dataset.placeholder || "Search customers…";
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
  const list = document.getElementById("msCustomerPicker")?.querySelector<HTMLElement>(".customer-options");
  if (list) list.hidden = true;
}

function renderCustomerOptions(): void {
  const host = document.getElementById("msCustomerPicker");
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

function renderCustomerPills(): void {
  const host = document.getElementById("msCustomerPills");
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
    });
    host.appendChild(chip);
  });
}

function applyPendingCustomers(): void {
  if (!pendingCustomers.length) return;
  if (!customerOptions.length) return;
  pendingCustomers.forEach((key) => {
    const row = customerOptions.find((c) => c.key === key);
    selectedCustomers.set(key, row?.name || key);
  });
  pendingCustomers = [];
  renderCustomerPills();
}

async function loadCustomers(): Promise<void> {
  const hint = document.getElementById("msCustomerHint");
  const url = wizardRoot()?.getAttribute("data-customers-url") || "";
  if (!url) return;
  const data = await getJSON<{ customers: LookupRow[] }>(url);
  customerOptions = data?.customers || [];
  ensureCustomerHandlers();
  ensureCustomerInput();
  applyPendingCustomers();
  renderCustomerPills();
  if (customerPickerOpen) renderCustomerOptions();
  if (hint) {
    if (customerOptions.length) {
      hint.textContent = "Search and check customers. Leave empty for all.";
    } else {
      hint.textContent = "Loading customers from customer master…";
    }
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
      await loadSalesmenWithEmails();
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
    if (smHint && !(document.getElementById("msSalesman") as HTMLSelectElement | null)?.options.length) {
      smHint.textContent = msg;
    }
    const emHint = document.getElementById("msEmailSalesmanHint");
    if (emHint && !salesmanEmailOptions.length) emHint.textContent = msg;
    if (cuHint && !customerOptions.length) cuHint.textContent = msg;
  };
  void tick();
  stopLookupPoll();
  lookupPollTimer = window.setInterval(() => { void tick(); }, 2500);
}

async function ensureLookups(): Promise<void> {
  if (lookupsStarted) return;
  lookupsStarted = true;
  await Promise.all([loadSalesmen(), loadSalesmenWithEmails(), loadCustomers()]);
  pollLookupStatus();
}

function clearMultiFilters(): void {
  selectedCustomers.clear();
  renderCustomerPills();
  setMultiSelected(document.getElementById("msStatus") as HTMLSelectElement | null, []);
  setMultiSelected(document.getElementById("msSalesman") as HTMLSelectElement | null, []);
  setMultiSelected(document.getElementById("msEmailSalesmanKeys") as HTMLSelectElement | null, []);
  const emailToSalesmen = document.getElementById("msEmailToSalesmen") as HTMLInputElement | null;
  const splitBySalesman = document.getElementById("msSplitBySalesman") as HTMLInputElement | null;
  if (emailToSalesmen) emailToSalesmen.checked = false;
  if (splitBySalesman) splitBySalesman.checked = false;
  const search = document.getElementById("msCustomerPicker")?.querySelector<HTMLInputElement>(".customer-search");
  if (search) search.value = "";
  closeCustomerOptions();
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
  if (step === 3) syncParamsVisibility(form);
  if (step === 4) syncDeliveryOptionsVisibility(form);
  if (step === 5) fillReview(form);
}

function validateStep(step: number, form: HTMLFormElement): string | null {
  if (step === 1) {
    if (!selectedReportKey(form)) return "Pick which report this schedule should send.";
    if (!(form.elements.namedItem("name") as HTMLInputElement).value.trim()) {
      return "Give the schedule a name so you can find it later.";
    }
  }
  if (step === 2) {
    const cad = masterCadence(form);
    if (!cad.ok) return cad.error || "Check the schedule timing.";
  }
  if (step === 4) {
    const recipients = (form.elements.namedItem("recipients") as HTMLInputElement).value.trim();
    const sp = (document.getElementById("spPathInput") as HTMLInputElement)?.value.trim() || "";
    const params = collectParams(form);
    const selectedSalesmen = asStringList(params.salesman);
    const salesmanDelivery = (selectedSalesmen.length > 0 && !!params.email_to_salesmen)
      || asStringList(params.email_salesman_keys).length > 0;
    if (!recipients && !sp && !salesmanDelivery) {
      return "Add an email address, pick a SharePoint folder, or choose salesmen to email.";
    }
    if (!selectedSalesmen.length && params.split_by_salesman
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
  stopLookupPoll();
  lookupsStarted = false;
  (document.getElementById("editingId") as HTMLInputElement).value = "";
  (document.getElementById("spPathInput") as HTMLInputElement).value = "";
  document.getElementById("formTitle")!.textContent = "Set up a schedule";
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
  (form.elements.namedItem("name") as HTMLInputElement).value = row.dataset.name || "";

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

  (form.elements.namedItem("period") as HTMLSelectElement).value = params.period || "";
  setMultiSelected(
    document.getElementById("msStatus") as HTMLSelectElement | null,
    asStringList(params.status),
  );
  pendingSalesmen = asStringList(params.salesman);
  pendingEmailSalesmen = asStringList(params.email_salesman_keys);
  const emailToSalesmen = document.getElementById("msEmailToSalesmen") as HTMLInputElement | null;
  const splitBySalesman = document.getElementById("msSplitBySalesman") as HTMLInputElement | null;
  if (emailToSalesmen) emailToSalesmen.checked = !!params.email_to_salesmen;
  if (splitBySalesman) splitBySalesman.checked = !!params.split_by_salesman;
  pendingCustomers = asStringList(params.customers);
  selectedCustomers.clear();
  renderCustomerPills();
  (form.elements.namedItem("year") as HTMLSelectElement).value =
    params.year != null ? String(params.year) : "";

  (form.elements.namedItem("recipients") as HTMLInputElement).value = row.dataset.recipients || "";
  (document.getElementById("spPathInput") as HTMLInputElement).value = row.dataset.sharepointPath || "";

  document.getElementById("formTitle")!.textContent = "Edit schedule";
  document.getElementById("formSubmitBtn")!.textContent = "Save changes";
  syncCadenceVisibility(form);
  lookupsStarted = false;
  stopLookupPoll();
  openWizard();
  showStep(1);
  syncParamsVisibility(form);
  await ensureLookups();
}

export function bindMasterWizard(): void {
  const form = masterForm();
  const wiz = wizardRoot();
  if (!form || !wiz) return;

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
  });

  form.querySelectorAll<HTMLInputElement>('input[name="freq"]').forEach((r) => {
    r.addEventListener("change", () => syncCadenceVisibility(form));
  });
  form.querySelectorAll<HTMLInputElement>('input[name="report_key"]').forEach((r) => {
    r.addEventListener("change", () => {
      syncParamsVisibility(form);
      syncDeliveryOptionsVisibility(form);
      suggestName(form);
    });
  });
  document.getElementById("msSalesman")?.addEventListener("change", () => {
    syncDeliveryOptionsVisibility(form);
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

    const body = {
      name: (form.elements.namedItem("name") as HTMLInputElement).value.trim(),
      report_key: selectedReportKey(form),
      cadence: cad.cadence,
      recipients: (form.elements.namedItem("recipients") as HTMLInputElement).value.trim(),
      sharepoint_path: (document.getElementById("spPathInput") as HTMLInputElement).value.trim(),
      filename_template: (document.getElementById("msFilename") as HTMLInputElement | null)?.value.trim() || "",
      params: collectParams(form),
      layout: {},
    };

    const editId = (document.getElementById("editingId") as HTMLInputElement).value;
    masterMsg("Saving…", false);
    const submitBtn = document.getElementById("formSubmitBtn") as HTMLButtonElement;
    submitBtn.disabled = true;

    try {
      let res: Response;
      if (editId) {
        const tpl = wiz.getAttribute("data-update-url-tpl")!;
        const url = tpl.replace("/0", "/" + editId);
        res = await fetch(url, { method: "PUT", headers: jsonHeaders(), body: JSON.stringify(body) });
      } else {
        res = await fetch(wiz.getAttribute("data-create-url")!, {
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
  document.getElementById("msFilename")?.addEventListener("input", updateMsFilenamePreview);
  updateMsFilenamePreview();

  showStep(1);
}

function updateMsFilenamePreview(): void {
  const input = document.getElementById("msFilename") as HTMLInputElement | null;
  const prev = document.getElementById("msFilenamePreview");
  if (!input || !prev) return;
  const now = new Date();
  const months = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  const pad = (n: number) => String(n).padStart(2, "0");
  const map: Record<string, string> = {
    "{YYYY}": String(now.getFullYear()),
    "{YY}": String(now.getFullYear()).slice(-2),
    "{MM}": pad(now.getMonth() + 1),
    "{M}": String(now.getMonth() + 1),
    "{Month}": months[now.getMonth()],
    "{Mon}": months[now.getMonth()].slice(0, 3),
    "{DD}": pad(now.getDate()),
    "{D}": String(now.getDate()),
    "{HH}": pad(now.getHours()),
    "{mm}": pad(now.getMinutes()),
    "{ss}": pad(now.getSeconds()),
    "{Report}": "Report",
    "{Period}": String(now.getFullYear()),
  };
  let out = (input.value || "{Report}_{YYYY}{MM}{DD}").replace(/\{[A-Za-z]+\}/g, (t) => map[t] || t);
  if (!out.toLowerCase().endsWith(".xlsx")) out += ".xlsx";
  prev.textContent = out;
}

// Schedules management pages (personal + master).
// Personal create uses the same inline multi-step wizard chrome as master.

import { esc, jsonHeaders } from "./http";
import { bindMasterWizard } from "./master_wizard";
import { bindSharePointPicker } from "./sharepoint_picker";

async function act(url: string, method: string, body?: unknown): Promise<boolean> {
  try {
    const res = await fetch(url, {
      method, headers: jsonHeaders(),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return res.ok;
  } catch {
    return false;
  }
}

function bindRowActions(): void {
  document.querySelectorAll<HTMLButtonElement>(".js-toggle").forEach((b) => {
    b.addEventListener("click", async () => {
      const active = b.getAttribute("data-active") === "true";
      if (await act(b.dataset.url!, "POST", { active })) location.reload();
    });
  });
  document.querySelectorAll<HTMLButtonElement>(".js-run").forEach((b) => {
    b.addEventListener("click", async () => {
      b.disabled = true;
      b.textContent = "Running…";
      const ok = await act(b.dataset.url!, "POST", {});
      b.textContent = ok ? "Queued" : "Failed";
      setTimeout(() => { b.disabled = false; b.textContent = "Run now"; }, 2500);
    });
  });
  document.querySelectorAll<HTMLButtonElement>(".js-copy").forEach((b) => {
    b.addEventListener("click", async () => {
      b.disabled = true;
      const ok = await act(b.dataset.url!, "POST", {});
      if (ok) location.reload();
      else { b.disabled = false; window.alert("Could not copy this schedule."); }
    });
  });
  document.querySelectorAll<HTMLButtonElement>(".js-delete").forEach((b) => {
    b.addEventListener("click", async () => {
      if (!window.confirm(b.getAttribute("data-confirm") || "Delete?")) return;
      if (await act(b.dataset.url!, "DELETE")) location.reload();
    });
  });
}

// --- Personal create wizard (same chrome as master) ------------------------

const PS_STEPS = 5;

interface LookupRow { key: string; name: string; }

let psStep = 1;
const psSelectedCustomers = new Map<string, string>();
let psCustomerOptions: LookupRow[] = [];
let psCustomerPickerOpen = false;
let psCustomerHandlersBound = false;
let psLookupPoll: number | null = null;

function psRoot(): HTMLElement | null {
  return document.getElementById("psForm");
}

function psFormEl(): HTMLFormElement | null {
  return document.getElementById("psCreateForm") as HTMLFormElement | null;
}

function psMsg(text: string, isError: boolean): void {
  const el = document.getElementById("psMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
  el.className = "ms-msg" + (isError ? " ms-msg-error" : "");
  el.setAttribute("role", isError ? "alert" : "status");
}

function psReportFilters(): Record<string, string[]> {
  try {
    return JSON.parse(psRoot()?.getAttribute("data-report-filters") || "{}");
  } catch {
    return {};
  }
}

function psReportKey(form: HTMLFormElement): string {
  return form.querySelector<HTMLInputElement>('input[name="report_key"]:checked')?.value || "";
}

function psReportTitle(form: HTMLFormElement): string {
  const checked = form.querySelector<HTMLInputElement>('input[name="report_key"]:checked');
  const card = checked?.closest(".ms-report-card");
  return card?.querySelector(".ms-report-name")?.textContent?.trim() || psReportKey(form);
}

function multiValues(sel: HTMLSelectElement | null): string[] {
  if (!sel) return [];
  return [...sel.selectedOptions].map((o) => o.value).filter(Boolean);
}

function syncPsCadence(): void {
  const form = psFormEl();
  const freq = form?.querySelector<HTMLInputElement>('input[name="freq"]:checked')?.value || "daily";
  const wd = document.getElementById("psWeekdays");
  const md = document.getElementById("psMonthday");
  if (wd) wd.hidden = freq !== "weekly";
  if (md) md.hidden = freq !== "monthly";
}

function syncPsParams(): void {
  const form = psFormEl();
  if (!form) return;
  const key = psReportKey(form);
  const needed = psReportFilters()[key] || [];
  form.querySelectorAll<HTMLElement>("#psParamsFields [data-param]").forEach((el) => {
    const param = el.getAttribute("data-param") || "";
    el.hidden = !needed.includes(param);
  });
  const empty = needed.length === 0;
  const none = document.getElementById("psParamsNone");
  const fields = document.getElementById("psParamsFields");
  const intro = document.getElementById("psParamsIntro");
  if (none) none.hidden = !empty;
  if (fields) fields.hidden = empty;
  if (intro) intro.hidden = empty;
  void ensurePsLookups();
}

function setPsStep(step: number): void {
  const root = psRoot();
  if (!root) return;
  psStep = Math.max(1, Math.min(PS_STEPS, step));
  root.querySelectorAll<HTMLElement>(".ms-pane").forEach((pane) => {
    pane.hidden = Number(pane.getAttribute("data-pane")) !== psStep;
  });
  root.querySelectorAll<HTMLElement>(".ms-step").forEach((el) => {
    const n = Number(el.getAttribute("data-step"));
    el.classList.toggle("is-active", n === psStep);
    el.classList.toggle("is-done", n < psStep);
    if (n === psStep) el.setAttribute("aria-current", "step");
    else el.removeAttribute("aria-current");
  });
  const pane = root.querySelector<HTMLElement>(`.ms-pane[data-pane="${psStep}"]`);
  pane?.querySelector<HTMLElement>(".ms-pane-title")?.focus({ preventScroll: true });
  const back = document.getElementById("psBackBtn") as HTMLButtonElement | null;
  const next = document.getElementById("psNextBtn") as HTMLButtonElement | null;
  const save = document.getElementById("psSaveBtn") as HTMLButtonElement | null;
  if (back) back.hidden = psStep <= 1;
  if (next) next.hidden = psStep >= PS_STEPS;
  if (save) save.hidden = psStep < PS_STEPS;
  psMsg("", false);
  if (psStep === 2) syncPsCadence();
  if (psStep === 3) syncPsParams();
  if (psStep === 4) updatePsFilenamePreview();
  if (psStep === 5) fillPsReview();
}

function validatePsStep(step: number): string | null {
  const form = psFormEl();
  if (!form) return "Form missing.";
  if (step === 1) {
    return psReportKey(form) ? null : "Pick which report this schedule should send.";
  }
  if (step === 2) {
    const freq = form.querySelector<HTMLInputElement>('input[name="freq"]:checked')?.value || "daily";
    if (freq === "weekly") {
      if (!form.querySelectorAll('input[name="weekday"]:checked').length) {
        return "Pick at least one day of the week.";
      }
    }
    if (freq === "monthly") {
      if (!form.querySelectorAll('input[name="monthday"]:checked').length) {
        return "Pick at least one day of the month.";
      }
    }
  }
  if (step === 4) {
    const to = (document.getElementById("psRecipients") as HTMLInputElement).value.trim();
    const folder = (document.getElementById("psOdSelected")?.textContent || "").trim();
    // folder path tracked by od picker; validate on save with od.path()
    if (!to && !folder) {
      // still allow next if they might pick OD — checked again on save with od.path()
    }
  }
  return null;
}

function makeOdPicker(): { init: () => Promise<void>; path: () => string | null; clear: () => void } {
  let cur = "";
  let selected: string | null = null;
  const root = psRoot();

  async function load(path: string): Promise<void> {
    cur = path;
    const url = (root?.getAttribute("data-od-folders-url") || "") + "?path=" + encodeURIComponent(path);
    let folders: { name: string; path: string }[] = [];
    try {
      const res = await fetch(url, { headers: { Accept: "application/json" } });
      const data = await res.json();
      folders = data.folders || [];
    } catch { /* empty */ }
    const bc = document.getElementById("psOdBreadcrumb");
    if (bc) {
      bc.innerHTML = "";
      const crumb = (label: string, target: string) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "sp-crumb";
        b.textContent = label;
        b.addEventListener("click", () => load(target));
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
        selected = cur;
        const sel = document.getElementById("psOdSelected");
        if (sel) sel.textContent = `Will save to: ${cur || "OneDrive root"}`;
      });
      bc.appendChild(use);
    }
    const picker = document.getElementById("psOdPicker");
    if (!picker) return;
    picker.innerHTML = "";
    if (!folders.length) {
      picker.innerHTML = '<div class="sp-empty">No subfolders here.</div>';
      return;
    }
    folders.forEach((f) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "sp-folder";
      b.textContent = f.name;
      b.addEventListener("click", () => load(f.path));
      picker.appendChild(b);
    });
  }

  return {
    async init() {
      selected = null;
      cur = "";
      const section = document.getElementById("psOdSection");
      const sel = document.getElementById("psOdSelected");
      if (sel) sel.textContent = "";
      const statusUrl = root?.getAttribute("data-od-status-url") || "";
      try {
        const st = await fetch(statusUrl, { headers: { Accept: "application/json" } }).then((r) => r.json());
        if (section) section.hidden = !st?.enabled;
        const status = document.getElementById("psOdStatus");
        if (status) status.textContent = st?.configured ? "" : "(mock folders in dev)";
      } catch {
        if (section) section.hidden = true;
        return;
      }
      await load("");
    },
    path: () => selected,
    clear() { selected = null; },
  };
}

function lookupUrl(attr: string, reportKey: string): string {
  return (psRoot()?.getAttribute(attr) || "").replace("__KEY__", encodeURIComponent(reportKey));
}

async function getJSON<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) return null;
    return await res.json() as T;
  } catch {
    return null;
  }
}

function fillSalesmanSelect(rows: LookupRow[]): void {
  const sel = document.getElementById("psSalesman") as HTMLSelectElement | null;
  if (!sel) return;
  const keep = new Set(multiValues(sel));
  sel.innerHTML = "";
  rows.forEach((r) => {
    const o = document.createElement("option");
    o.value = r.key;
    o.textContent = r.name || r.key;
    o.selected = keep.has(r.key);
    sel.appendChild(o);
  });
  const hint = document.getElementById("psSalesmanHint");
  if (hint) {
    hint.textContent = rows.length
      ? "Leave empty for your scoped book. Hold Ctrl/⌘ to pick several."
      : "Loading salesmen…";
  }
}

function ensurePsCustomerHandlers(): void {
  if (psCustomerHandlersBound) return;
  psCustomerHandlersBound = true;
  const inside = (t: Node) => {
    const p = document.getElementById("psCustomerPicker");
    const pills = document.getElementById("psCustomerPills");
    return !!((p && p.contains(t)) || (pills && pills.contains(t)));
  };
  document.addEventListener("click", (e) => {
    if (psCustomerPickerOpen && !inside(e.target as Node)) closePsCustomerOptions();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && psCustomerPickerOpen) closePsCustomerOptions();
  });
}

function ensurePsCustomerInput(): HTMLInputElement | null {
  const host = document.getElementById("psCustomerPicker");
  if (!host) return null;
  let search = host.querySelector<HTMLInputElement>(".customer-search");
  if (search) return search;
  host.innerHTML = "";
  search = document.createElement("input");
  search.type = "text";
  search.className = "customer-search";
  search.placeholder = host.dataset.placeholder || "Search customers…";
  search.setAttribute("role", "combobox");
  search.addEventListener("focus", () => { psCustomerPickerOpen = true; renderPsCustomerOptions(); });
  search.addEventListener("input", () => { psCustomerPickerOpen = true; renderPsCustomerOptions(); });
  host.appendChild(search);
  const list = document.createElement("div");
  list.className = "customer-options";
  list.hidden = true;
  host.appendChild(list);
  return search;
}

function closePsCustomerOptions(): void {
  psCustomerPickerOpen = false;
  const list = document.getElementById("psCustomerPicker")?.querySelector<HTMLElement>(".customer-options");
  if (list) list.hidden = true;
}

function renderPsCustomerOptions(): void {
  const host = document.getElementById("psCustomerPicker");
  const search = ensurePsCustomerInput();
  const list = host?.querySelector<HTMLElement>(".customer-options");
  if (!host || !search || !list) return;
  if (!psCustomerPickerOpen) { list.hidden = true; return; }
  const q = search.value.trim().toLowerCase();
  const matches = q
    ? psCustomerOptions.filter(
        (c) => c.name.toLowerCase().includes(q) || c.key.toLowerCase().includes(q),
      )
    : psCustomerOptions;
  list.innerHTML = "";
  matches.slice(0, 200).forEach((c) => {
    const row = document.createElement("label");
    row.className = "customer-option";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = psSelectedCustomers.has(c.key);
    cb.addEventListener("change", () => {
      if (cb.checked) psSelectedCustomers.set(c.key, c.name);
      else psSelectedCustomers.delete(c.key);
      renderPsCustomerPills();
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
    empty.textContent = psCustomerOptions.length ? "No matches" : "Loading…";
    list.appendChild(empty);
  }
  list.hidden = false;
}

function renderPsCustomerPills(): void {
  const host = document.getElementById("psCustomerPills");
  if (!host) return;
  host.innerHTML = "";
  psSelectedCustomers.forEach((name, key) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "customer-chip";
    chip.textContent = `${name} ✕`;
    chip.title = `Remove ${key}`;
    chip.addEventListener("click", () => {
      psSelectedCustomers.delete(key);
      renderPsCustomerPills();
      if (psCustomerPickerOpen) renderPsCustomerOptions();
    });
    host.appendChild(chip);
  });
}

async function loadPsCustomers(): Promise<void> {
  const form = psFormEl();
  const reportKey = form ? psReportKey(form) : "";
  if (!reportKey) return;
  const salesmen = multiValues(document.getElementById("psSalesman") as HTMLSelectElement | null);
  let url = lookupUrl("data-customers-url-tpl", reportKey);
  if (salesmen.length === 1) url += `?salesman=${encodeURIComponent(salesmen[0])}`;
  const data = await getJSON<{ customers: Array<LookupRow & { salesman?: string }> }>(url);
  let rows = data?.customers || [];
  if (salesmen.length > 1) {
    const want = new Set(salesmen);
    rows = rows.filter((c) => want.has(c.salesman || ""));
  }
  psCustomerOptions = rows;
  [...psSelectedCustomers.keys()].forEach((k) => {
    if (!psCustomerOptions.some((c) => c.key === k)) psSelectedCustomers.delete(k);
  });
  renderPsCustomerPills();
  const hint = document.getElementById("psCustomerHint");
  if (hint) {
    hint.textContent = psCustomerOptions.length
      ? "Search and check customers. Leave empty for all."
      : "Loading customers…";
  }
  if (psCustomerPickerOpen) renderPsCustomerOptions();
}

async function loadPsSalesmen(): Promise<void> {
  const form = psFormEl();
  const reportKey = form ? psReportKey(form) : "";
  if (!reportKey) return;
  const data = await getJSON<{ salesmen: LookupRow[] }>(lookupUrl("data-salesmen-url-tpl", reportKey));
  fillSalesmanSelect(data?.salesmen || []);
}

async function ensurePsLookups(): Promise<void> {
  const form = psFormEl();
  if (!form) return;
  const key = psReportKey(form);
  const needed = psReportFilters()[key] || [];
  if (!needed.includes("salesman") && !needed.includes("customers")) return;
  ensurePsCustomerHandlers();
  ensurePsCustomerInput();
  if (needed.includes("salesman")) await loadPsSalesmen();
  if (needed.includes("customers")) await loadPsCustomers();

  const statusUrl = psRoot()?.getAttribute("data-lookup-status-url") || "";
  if (!statusUrl) return;
  if (psLookupPoll != null) window.clearInterval(psLookupPoll);
  psLookupPoll = window.setInterval(async () => {
    const st = await getJSON<{ status?: string }>(statusUrl);
    if (st?.status === "ready") {
      if (psLookupPoll != null) { window.clearInterval(psLookupPoll); psLookupPoll = null; }
      if (needed.includes("salesman")) await loadPsSalesmen();
      if (needed.includes("customers")) await loadPsCustomers();
    }
  }, 2000);
}

function updatePsFilenamePreview(): void {
  const form = psFormEl();
  const input = document.getElementById("psFilename") as HTMLInputElement | null;
  const prev = document.getElementById("psFilenamePreview");
  if (!input || !prev || !form) return;
  const now = new Date();
  const months = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  const mons = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const weekdays = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"];
  const pad = (n: number) => String(n).padStart(2, "0");
  const report = psReportKey(form).replace(/[^A-Za-z0-9_-]+/g, "_") || "Report";
  const map: Record<string, string> = {
    "{YYYY}": String(now.getFullYear()),
    "{YY}": String(now.getFullYear()).slice(-2),
    "{MM}": pad(now.getMonth() + 1),
    "{M}": String(now.getMonth() + 1),
    "{Month}": months[now.getMonth()],
    "{Mon}": mons[now.getMonth()],
    "{DD}": pad(now.getDate()),
    "{D}": String(now.getDate()),
    "{HH}": pad(now.getHours()),
    "{mm}": pad(now.getMinutes()),
    "{ss}": pad(now.getSeconds()),
    "{Report}": report,
    "{Period}": (document.getElementById("psPeriod") as HTMLSelectElement | null)?.value || String(now.getFullYear()),
    "{Weekday}": weekdays[(now.getDay() + 6) % 7],
  };
  let out = (input.value || "{Report}_{YYYY}{MM}{DD}").replace(/\{[A-Za-z]+\}/g, (t) => map[t] || t);
  if (!out.toLowerCase().endsWith(".xlsx")) out += ".xlsx";
  prev.textContent = out;
}

function collectPsParams(): Record<string, unknown> {
  const form = psFormEl()!;
  const key = psReportKey(form);
  const needed = psReportFilters()[key] || [];
  const params: Record<string, unknown> = {
    email_cc: (document.getElementById("psCc") as HTMLInputElement).value.trim(),
    email_bcc: (document.getElementById("psBcc") as HTMLInputElement).value.trim(),
    email_on_no_data: !!(document.getElementById("psNoDataAll") as HTMLInputElement).checked,
    email_on_no_data_me_only: !!(document.getElementById("psNoDataMe") as HTMLInputElement).checked,
  };
  if (needed.includes("period")) {
    const v = (document.getElementById("psPeriod") as HTMLSelectElement).value;
    if (v) params.period = v;
  }
  if (needed.includes("year")) {
    const v = (document.getElementById("psYear") as HTMLSelectElement).value;
    if (v) params.year = v;
  }
  if (needed.includes("status")) {
    const vals = multiValues(document.getElementById("psStatus") as HTMLSelectElement | null);
    if (vals.length) params.status = vals;
  }
  if (needed.includes("salesman")) {
    const vals = multiValues(document.getElementById("psSalesman") as HTMLSelectElement | null);
    if (vals.length) params.salesman = vals;
  }
  if (needed.includes("customers")) {
    const vals = [...psSelectedCustomers.keys()];
    if (vals.length) params.customers = vals;
  }
  return params;
}

function collectPsCadence(form: HTMLFormElement): { ok: boolean; cadence?: Record<string, unknown>; error?: string } {
  const freq = form.querySelector<HTMLInputElement>('input[name="freq"]:checked')?.value || "daily";
  const time = (form.querySelector<HTMLInputElement>('input[name="time"]')?.value) || "08:00";
  const cadence: Record<string, unknown> = { freq, time };
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

function fillPsReview(): void {
  const form = psFormEl();
  const review = document.getElementById("psReview");
  if (!form || !review) return;
  const cad = collectPsCadence(form);
  const freq = String(cad.cadence?.freq || "daily");
  let when = "Every day";
  if (freq === "weekly") {
    const names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const days = (cad.cadence?.weekdays as number[] | undefined) || [];
    when = "Weekly on " + days.map((d) => names[d] || String(d)).join(", ");
  } else if (freq === "monthly") {
    const days = (cad.cadence?.monthdays as number[] | undefined) || [];
    when = "Monthly on " + days.map((d) => (d === -1 ? "last day" : `day ${d}`)).join(", ");
  }
  when += ` at ${cad.cadence?.time || "08:00"} Eastern`;

  const params = collectPsParams();
  const paramBits: string[] = [];
  if (params.period) paramBits.push(String(params.period).replace(/_/g, " "));
  if (params.year) paramBits.push(`year ${params.year}`);
  if (params.status) paramBits.push("status " + (params.status as string[]).join(", "));
  if (params.salesman) paramBits.push("salesman " + (params.salesman as string[]).join(", "));
  if (params.customers) paramBits.push("customers " + (params.customers as string[]).join(", "));

  const to = (document.getElementById("psRecipients") as HTMLInputElement).value.trim() || "—";
  const cc = (document.getElementById("psCc") as HTMLInputElement).value.trim();
  const bcc = (document.getElementById("psBcc") as HTMLInputElement).value.trim();
  const od = document.getElementById("psOdSelected")?.textContent?.replace(/^Will save to:\s*/, "") || "—";
  const fn = (document.getElementById("psFilename") as HTMLInputElement).value.trim()
    || "{Report}_{YYYY}{MM}{DD}";

  const rows: [string, string][] = [
    ["Report", psReportTitle(form)],
    ["When", when],
    ["Options", paramBits.join(", ") || "defaults"],
    ["Email To", to],
  ];
  if (cc) rows.push(["CC", cc]);
  if (bcc) rows.push(["BCC", bcc]);
  rows.push(["OneDrive", od]);
  rows.push(["Filename", fn]);
  if (params.email_on_no_data) rows.push(["No data", "email recipients"]);
  if (params.email_on_no_data_me_only) rows.push(["No data", "email only me"]);

  review.innerHTML = rows.map(([k, v]) =>
    `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
}

function bindPersonalCreate(): void {
  const form = psFormEl();
  const panel = psRoot();
  if (!form || !panel) return;
  const od = makeOdPicker();

  const open = () => {
    form.reset();
    psSelectedCustomers.clear();
    renderPsCustomerPills();
    fillSalesmanSelect([]);
    od.clear();
    form.querySelectorAll<HTMLInputElement>('input[name="freq"]').forEach((r, i) => { r.checked = i === 0; });
    form.querySelectorAll<HTMLInputElement>('input[name="weekday"]').forEach((c) => { c.checked = false; });
    form.querySelectorAll<HTMLInputElement>('input[name="monthday"]').forEach((c) => { c.checked = false; });
    (document.getElementById("psFilename") as HTMLInputElement).value = "{Report}_{YYYY}{MM}{DD}";
    syncPsCadence();
    setPsStep(1);
    panel.hidden = false;
    document.getElementById("psEmpty")?.setAttribute("hidden", "");
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
    void od.init();
  };
  const close = () => {
    panel.hidden = true;
    if (psLookupPoll != null) { window.clearInterval(psLookupPoll); psLookupPoll = null; }
    if (!document.getElementById("schedulesRoot")) {
      document.getElementById("psEmpty")?.removeAttribute("hidden");
    }
  };

  document.getElementById("psStartBtn")?.addEventListener("click", open);
  document.getElementById("psCancelBtn")?.addEventListener("click", close);
  form.querySelectorAll<HTMLInputElement>('input[name="freq"]').forEach((r) => {
    r.addEventListener("change", syncPsCadence);
  });
  form.querySelectorAll<HTMLInputElement>('input[name="report_key"]').forEach((r) => {
    r.addEventListener("change", () => {
      psSelectedCustomers.clear();
      renderPsCustomerPills();
      syncPsParams();
      updatePsFilenamePreview();
    });
  });
  document.getElementById("psSalesman")?.addEventListener("change", () => { void loadPsCustomers(); });
  document.getElementById("psPeriod")?.addEventListener("change", updatePsFilenamePreview);
  document.getElementById("psFilename")?.addEventListener("input", updatePsFilenamePreview);
  document.querySelectorAll<HTMLButtonElement>(".js-ps-fn-token").forEach((b) => {
    b.addEventListener("click", () => {
      const input = document.getElementById("psFilename") as HTMLInputElement | null;
      if (!input) return;
      input.value = (input.value || "") + (b.dataset.token || "");
      updatePsFilenamePreview();
      input.focus();
    });
  });

  document.getElementById("psBackBtn")?.addEventListener("click", () => setPsStep(psStep - 1));
  document.getElementById("psNextBtn")?.addEventListener("click", () => {
    const err = validatePsStep(psStep);
    if (err) { psMsg(err, true); return; }
    if (psStep === 4) {
      const to = (document.getElementById("psRecipients") as HTMLInputElement).value.trim();
      if (!to && !od.path()) {
        psMsg("Add an email address or pick a OneDrive folder.", true);
        return;
      }
    }
    setPsStep(psStep + 1);
  });

  document.getElementById("psSaveBtn")?.addEventListener("click", async () => {
    const reportKey = psReportKey(form);
    if (!reportKey) { psMsg("Pick a report.", true); setPsStep(1); return; }
    const cad = collectPsCadence(form);
    if (!cad.ok || !cad.cadence) { psMsg(cad.error || "Check the schedule timing.", true); setPsStep(2); return; }
    const to = (document.getElementById("psRecipients") as HTMLInputElement).value.trim();
    const folder = od.path() || "";
    if (!to && !folder) { psMsg("Add an email address or pick a OneDrive folder.", true); setPsStep(4); return; }

    const btn = document.getElementById("psSaveBtn") as HTMLButtonElement | null;
    if (btn) btn.disabled = true;
    psMsg("Saving…", false);
    try {
      const res = await fetch(panel.getAttribute("data-create-url") || "", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          report_key: reportKey,
          recipients: to,
          sharepoint_path: folder,
          cadence: cad.cadence,
          filename_template: (document.getElementById("psFilename") as HTMLInputElement).value.trim(),
          params: collectPsParams(),
          layout: {},
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        psMsg(err.error || err.description || "Could not save.", true);
        if (btn) btn.disabled = false;
        return;
      }
      location.reload();
    } catch {
      psMsg("Could not save.", true);
      if (btn) btn.disabled = false;
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  bindRowActions();
  bindPersonalCreate();
  bindMasterWizard();
  bindSharePointPicker();
});

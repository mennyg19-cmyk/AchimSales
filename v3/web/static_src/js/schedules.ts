// Schedules management pages (personal + master).
// Master create/edit is a 5-step wizard aimed at non-technical admins.

import { jsonHeaders } from "./http";
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

// --- Personal create wizard (compact overlay) ------------------------------

const PS_STEPS = 4;

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

function psForm(): HTMLFormElement | null {
  return document.getElementById("psCreateForm") as HTMLFormElement | null;
}

function psMsg(text: string, isError: boolean): void {
  const el = document.getElementById("psMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
  el.className = "modal-msg" + (isError ? " modal-msg-error" : "");
}

function psReportFilters(): Record<string, string[]> {
  try {
    return JSON.parse(psRoot()?.getAttribute("data-report-filters") || "{}");
  } catch {
    return {};
  }
}

function multiValues(sel: HTMLSelectElement | null): string[] {
  if (!sel) return [];
  return [...sel.selectedOptions].map((o) => o.value).filter(Boolean);
}

function syncPsCadence(): void {
  const freq = (document.querySelector<HTMLInputElement>('#psCreateForm input[name="freq"]:checked')?.value) || "daily";
  const wd = document.getElementById("psWeekdays");
  const md = document.getElementById("psMonthday");
  if (wd) wd.hidden = freq !== "weekly";
  if (md) md.hidden = freq !== "monthly";
}

function syncPsParams(): void {
  const key = (document.getElementById("psReport") as HTMLSelectElement | null)?.value || "";
  const needed = psReportFilters()[key] || [];
  document.querySelectorAll<HTMLElement>("#psParamsFields [data-param]").forEach((el) => {
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
  psStep = Math.max(1, Math.min(PS_STEPS, step));
  document.querySelectorAll<HTMLElement>("#psCreateForm .ms-pane").forEach((pane) => {
    pane.hidden = Number(pane.getAttribute("data-pane")) !== psStep;
  });
  document.querySelectorAll<HTMLElement>(".ps-steps .ms-step").forEach((el) => {
    const n = Number(el.getAttribute("data-step"));
    el.classList.toggle("is-active", n === psStep);
    el.classList.toggle("is-done", n < psStep);
  });
  const back = document.getElementById("psBackBtn") as HTMLButtonElement | null;
  const next = document.getElementById("psNextBtn") as HTMLButtonElement | null;
  const save = document.getElementById("psSaveBtn") as HTMLButtonElement | null;
  if (back) back.hidden = psStep === 1;
  if (next) next.hidden = psStep === PS_STEPS;
  if (save) save.hidden = psStep !== PS_STEPS;
  if (psStep === 2) syncPsCadence();
  if (psStep === 3) syncPsParams();
  if (psStep === 4) updatePsFilenamePreview();
  psMsg("", false);
}

function validatePsStep(step: number): string | null {
  if (step === 1) {
    const key = (document.getElementById("psReport") as HTMLSelectElement).value;
    return key ? null : "Pick a report.";
  }
  if (step === 2) {
    const freq = document.querySelector<HTMLInputElement>('#psCreateForm input[name="freq"]:checked')?.value || "daily";
    if (freq === "weekly") {
      const days = document.querySelectorAll('#psCreateForm input[name="weekday"]:checked');
      if (!days.length) return "Pick at least one weekday.";
    }
  }
  return null;
}

function makeOdPicker(): { init: () => Promise<void>; path: () => string | null } {
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
  const reportKey = (document.getElementById("psReport") as HTMLSelectElement | null)?.value || "";
  if (!reportKey) return;
  const salesmen = multiValues(document.getElementById("psSalesman") as HTMLSelectElement | null);
  let url = lookupUrl("data-customers-url-tpl", reportKey);
  // API takes one salesman; for several, load all then filter client-side.
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
  const reportKey = (document.getElementById("psReport") as HTMLSelectElement | null)?.value || "";
  if (!reportKey) return;
  const data = await getJSON<{ salesmen: LookupRow[] }>(lookupUrl("data-salesmen-url-tpl", reportKey));
  fillSalesmanSelect(data?.salesmen || []);
}

async function ensurePsLookups(): Promise<void> {
  const key = (document.getElementById("psReport") as HTMLSelectElement | null)?.value || "";
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
  const input = document.getElementById("psFilename") as HTMLInputElement | null;
  const prev = document.getElementById("psFilenamePreview");
  if (!input || !prev) return;
  const now = new Date();
  const months = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  const mons = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const weekdays = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"];
  const pad = (n: number) => String(n).padStart(2, "0");
  const report = ((document.getElementById("psReport") as HTMLSelectElement | null)?.value || "Report")
    .replace(/[^A-Za-z0-9_-]+/g, "_");
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
  const key = (document.getElementById("psReport") as HTMLSelectElement).value;
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

function bindPersonalCreate(): void {
  const form = psForm();
  const panel = psRoot();
  if (!form || !panel) return;
  const od = makeOdPicker();

  const open = () => {
    psSelectedCustomers.clear();
    renderPsCustomerPills();
    (document.getElementById("psReport") as HTMLSelectElement).value = "";
    form.querySelectorAll<HTMLInputElement>('input[name="freq"]').forEach((r, i) => { r.checked = i === 0; });
    form.querySelectorAll<HTMLInputElement>('input[name="weekday"]').forEach((c) => { c.checked = false; });
    (document.getElementById("psRecipients") as HTMLInputElement).value = "";
    (document.getElementById("psCc") as HTMLInputElement).value = "";
    (document.getElementById("psBcc") as HTMLInputElement).value = "";
    (document.getElementById("psFilename") as HTMLInputElement).value = "{Report}_{YYYY}{MM}{DD}";
    (document.getElementById("psNoDataAll") as HTMLInputElement).checked = false;
    (document.getElementById("psNoDataMe") as HTMLInputElement).checked = false;
    const status = document.getElementById("psStatus") as HTMLSelectElement | null;
    if (status) [...status.options].forEach((o) => { o.selected = false; });
    fillSalesmanSelect([]);
    psMsg("", false);
    setPsStep(1);
    panel.hidden = false;
    void od.init();
  };
  const close = () => {
    panel.hidden = true;
    if (psLookupPoll != null) { window.clearInterval(psLookupPoll); psLookupPoll = null; }
  };

  document.getElementById("psStartBtn")?.addEventListener("click", open);
  document.getElementById("psCancelBtn")?.addEventListener("click", close);
  document.getElementById("psCloseBtn")?.addEventListener("click", close);
  panel.addEventListener("click", (e) => { if (e.target === panel) close(); });
  form.querySelectorAll<HTMLInputElement>('input[name="freq"]').forEach((r) => {
    r.addEventListener("change", syncPsCadence);
  });
  document.getElementById("psReport")?.addEventListener("change", () => {
    psSelectedCustomers.clear();
    renderPsCustomerPills();
    syncPsParams();
    updatePsFilenamePreview();
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
    setPsStep(psStep + 1);
  });

  document.getElementById("psSaveBtn")?.addEventListener("click", async () => {
    const reportKey = (document.getElementById("psReport") as HTMLSelectElement).value;
    if (!reportKey) { psMsg("Pick a report.", true); setPsStep(1); return; }
    const freq = form.querySelector<HTMLInputElement>('input[name="freq"]:checked')?.value || "daily";
    const time = (form.querySelector<HTMLInputElement>('input[name="time"]')?.value) || "08:00";
    const cadence: Record<string, unknown> = { freq, time };
    if (freq === "weekly") {
      const days = [...form.querySelectorAll<HTMLInputElement>('input[name="weekday"]:checked')]
        .map((c) => Number(c.value));
      if (!days.length) { psMsg("Pick at least one weekday.", true); setPsStep(2); return; }
      cadence.weekdays = days;
    } else if (freq === "monthly") {
      cadence.monthday = Number((form.querySelector<HTMLSelectElement>('select[name="monthday"]')?.value) || "1");
    }
    const to = (document.getElementById("psRecipients") as HTMLInputElement).value.trim();
    const folder = od.path() || "";
    if (!to && !folder) { psMsg("Enter recipients or pick a OneDrive folder.", true); return; }

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
          cadence,
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

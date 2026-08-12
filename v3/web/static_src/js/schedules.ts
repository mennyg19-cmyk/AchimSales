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

// --- Personal create form -------------------------------------------------

function psRoot(): HTMLElement | null {
  return document.getElementById("psForm");
}

function psMsg(text: string, isError: boolean): void {
  const el = document.getElementById("psMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
  el.className = "ms-msg" + (isError ? " ms-msg-error" : "");
}

function psReportFilters(): Record<string, string[]> {
  try {
    return JSON.parse(psRoot()?.getAttribute("data-report-filters") || "{}");
  } catch {
    return {};
  }
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

function bindPersonalCreate(): void {
  const form = document.getElementById("psCreateForm") as HTMLFormElement | null;
  const panel = psRoot();
  if (!form || !panel) return;
  const od = makeOdPicker();

  const open = () => {
    panel.hidden = false;
    psMsg("", false);
    syncPsCadence();
    syncPsParams();
    void od.init();
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const close = () => { panel.hidden = true; };

  document.getElementById("psStartBtn")?.addEventListener("click", open);
  document.getElementById("psCancelBtn")?.addEventListener("click", close);
  form.querySelectorAll<HTMLInputElement>('input[name="freq"]').forEach((r) => {
    r.addEventListener("change", syncPsCadence);
  });
  document.getElementById("psReport")?.addEventListener("change", syncPsParams);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const reportKey = (document.getElementById("psReport") as HTMLSelectElement).value;
    if (!reportKey) { psMsg("Pick a report.", true); return; }
    const freq = form.querySelector<HTMLInputElement>('input[name="freq"]:checked')?.value || "daily";
    const time = (form.querySelector<HTMLInputElement>('input[name="time"]')?.value) || "08:00";
    const cadence: Record<string, unknown> = { freq, time };
    if (freq === "weekly") {
      const days = [...form.querySelectorAll<HTMLInputElement>('input[name="weekday"]:checked')]
        .map((c) => Number(c.value));
      if (!days.length) { psMsg("Pick at least one weekday.", true); return; }
      cadence.weekdays = days;
    } else if (freq === "monthly") {
      cadence.monthday = Number((form.querySelector<HTMLSelectElement>('select[name="monthday"]')?.value) || "1");
    }
    const to = (document.getElementById("psRecipients") as HTMLInputElement).value.trim();
    const cc = (document.getElementById("psCc") as HTMLInputElement).value.trim();
    const bcc = (document.getElementById("psBcc") as HTMLInputElement).value.trim();
    const folder = od.path() || "";
    if (!to && !folder) { psMsg("Enter recipients or pick a OneDrive folder.", true); return; }

    const needed = psReportFilters()[reportKey] || [];
    const params: Record<string, unknown> = {
      email_cc: cc,
      email_bcc: bcc,
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
      const v = (document.getElementById("psStatus") as HTMLInputElement).value.trim();
      if (v) params.status = v;
    }
    if (needed.includes("customers")) {
      const v = (document.getElementById("psCustomers") as HTMLInputElement).value.trim();
      if (v) params.customers = v.split(",").map((s) => s.trim()).filter(Boolean);
    }
    if (needed.includes("salesman")) {
      const v = (document.getElementById("psSalesman") as HTMLInputElement).value.trim();
      if (v) params.salesman = v;
    }

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
          params,
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

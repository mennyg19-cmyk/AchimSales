/**
 * Report viewer: gathers filters, enqueues a run, polls the durable job, then
 * renders the returned tabs in an interactive Tabulator table. The server owns
 * all math + scope; this file is pure presentation + polling.
 */

declare const Tabulator: any;

interface Column { field: string; header: string; type?: string; }
interface Tab { key: string; name: string; columns: Column[]; rows: Record<string, unknown>[]; }
interface Payload { report_key: string; tabs: Tab[]; row_count?: number; }

const root = document.getElementById("reportRoot");

function attr(name: string): string {
  return root?.getAttribute(name) || "";
}

function setStatus(msg: string, kind: "info" | "error" = "info"): void {
  const el = document.getElementById("reportStatus");
  if (!el) return;
  el.textContent = msg;
  el.className = "report-status report-status-" + kind;
  el.hidden = false;
}

function clearStatus(): void {
  const el = document.getElementById("reportStatus");
  if (el) el.hidden = true;
}

function collectParams(): Record<string, string> {
  const form = document.getElementById("filterForm") as HTMLFormElement | null;
  const out: Record<string, string> = {};
  if (!form) return out;
  new FormData(form).forEach((value, key) => {
    const v = String(value).trim();
    if (v) out[key] = v;
  });
  return out;
}

function formatterFor(col: Column): any {
  switch (col.type) {
    case "money":
      return { formatter: "money", formatterParams: { symbol: "$", precision: 2, thousand: "," } };
    case "percent":
      return {
        formatter: (cell: any) => {
          const n = Number(cell.getValue());
          return isFinite(n) ? (n * 100).toFixed(1) + "%" : "";
        },
      };
    case "int":
      return { formatter: "money", formatterParams: { precision: 0, thousand: "," } };
    default:
      return {};
  }
}

function buildColumns(cols: Column[]): any[] {
  return cols.map((c) => ({
    title: c.header,
    field: c.field,
    headerFilter: "input",
    ...formatterFor(c),
  }));
}

let table: any = null;

function renderTab(tab: Tab): void {
  const meta = document.getElementById("reportMeta");
  if (meta) {
    meta.textContent = `${tab.rows.length.toLocaleString()} rows`;
    meta.hidden = false;
  }
  if (table) table.destroy();
  table = new Tabulator("#reportTable", {
    data: tab.rows,
    columns: buildColumns(tab.columns),
    layout: "fitDataStretch",
    height: "60vh",
    nestedFieldSeparator: false, // our fields contain "." (e.g. "Cust. #")
    placeholder: "No data for these filters.",
  });
}

function renderTabs(payload: Payload): void {
  const tabsEl = document.getElementById("reportTabs");
  if (!tabsEl) return;
  tabsEl.innerHTML = "";
  payload.tabs.forEach((tab, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "report-tab" + (i === 0 ? " active" : "");
    btn.textContent = tab.name;
    btn.addEventListener("click", () => {
      tabsEl.querySelectorAll(".report-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      renderTab(tab);
    });
    tabsEl.appendChild(btn);
  });
  tabsEl.hidden = payload.tabs.length === 0;
  if (payload.tabs.length) renderTab(payload.tabs[0]);
}

async function poll(jobId: string): Promise<void> {
  const jobUrl = attr("data-job-url").replace("__ID__", jobId);
  const resultUrl = attr("data-result-url").replace("__ID__", jobId);

  for (let i = 0; i < 600; i++) { // up to ~10 min at 1s
    const res = await fetch(jobUrl, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error("Lost track of the job");
    const job = await res.json();
    if (job.status === "success") {
      const r = await fetch(resultUrl, { headers: { Accept: "application/json" } });
      if (!r.ok) throw new Error("Could not load the result");
      const payload: Payload = await r.json();
      clearStatus();
      renderTabs(payload);
      enableExport(jobId);
      return;
    }
    if (job.status === "failure") throw new Error(job.error || "The report failed");
    if (job.status === "cancelled") throw new Error("The run was cancelled");
    setStatus(`Building report… ${job.progress || 0}%`);
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("Timed out waiting for the report");
}

function enableExport(jobId: string): void {
  const btn = document.getElementById("exportBtn") as HTMLButtonElement | null;
  if (!btn) return;
  btn.disabled = false;
  btn.onclick = () => {
    window.location.href = attr("data-export-url").replace("__ID__", jobId);
  };
}

async function run(): Promise<void> {
  const runBtn = document.getElementById("runBtn") as HTMLButtonElement | null;
  const exportBtn = document.getElementById("exportBtn") as HTMLButtonElement | null;
  if (runBtn) runBtn.disabled = true;
  if (exportBtn) exportBtn.disabled = true;
  setStatus("Starting…");
  try {
    const res = await fetch(attr("data-run-url"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": attr("data-csrf") },
      body: JSON.stringify(collectParams()),
    });
    if (!res.ok) throw new Error(`Could not start the report (${res.status})`);
    const { job_id } = await res.json();
    await poll(job_id);
  } catch (err) {
    setStatus(err instanceof Error ? err.message : "Something went wrong", "error");
  } finally {
    if (runBtn) runBtn.disabled = false;
  }
}

function initCustomRangeToggle(): void {
  const sel = document.getElementById("periodSelect") as HTMLSelectElement | null;
  if (!sel) return;
  const customs = Array.from(document.querySelectorAll<HTMLElement>("[data-custom]"));
  const sync = () => customs.forEach((c) => (c.hidden = sel.value !== "custom"));
  sel.addEventListener("change", sync);
  sync();
}

document.addEventListener("DOMContentLoaded", () => {
  if (!root) return;
  initCustomRangeToggle();
  document.getElementById("runBtn")?.addEventListener("click", run);
});

export {};

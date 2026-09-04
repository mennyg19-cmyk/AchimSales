// Schedules management pages (personal + company). Create uses the shared wizard.

import { esc, jsonHeaders } from "./http";
import { pollJobLog, renderJobLog, type JobLogEntry } from "./job_log";
import { bindMasterWizard } from "./master_wizard";
import { bindPersonalWizard } from "./personal_wizard";
import { bindSharePointPicker } from "./sharepoint_picker";

type RunLogRow = {
  id: number;
  kind: string;
  title: string;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  rows?: number | null;
  message?: string;
  log_url?: string;
  job_log?: JobLogEntry[];
};

async function act(url: string, method: string, body?: unknown): Promise<boolean> {
  const data = await actJson(url, method, body);
  return data !== null;
}

async function actJson(url: string, method: string, body?: unknown): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(url, {
      method, headers: jsonHeaders(), credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) return null;
    return await res.json().catch(() => ({}));
  } catch {
    return null;
  }
}

function badgeClass(status: string): string {
  if (status === "success") return "badge badge-success";
  if (status === "failure") return "badge badge-error";
  return "badge badge-salesman";
}

type ActiveJob = {
  id: string;
  status: string;
  step?: string;
  label: string;
};

function cancelUrl(jobId: string): string {
  const tpl = document.getElementById("runLogPanel")?.getAttribute("data-cancel-url") || "";
  return tpl.replace("__ID__", jobId);
}

async function cancelJob(jobId: string): Promise<boolean> {
  const data = await actJson(cancelUrl(jobId), "POST", {});
  return Boolean(data && (data.cancelled === true || data.status === "cancelled"));
}

function renderActiveJobs(jobs: ActiveJob[]): void {
  const el = document.getElementById("activeJobs");
  const panel = document.getElementById("runLogPanel");
  if (!el) return;
  el.hidden = jobs.length === 0;
  if (jobs.length) panel?.setAttribute("open", "");
  el.innerHTML = jobs.map((j) => {
    const step = j.step ? ` <span class="active-job-step">${esc(j.step)}</span>` : "";
    return `<div class="active-job">
      <button type="button" class="active-job-label js-watch-job" data-job-id="${esc(j.id)}">${esc(j.label)} — ${esc(j.status)}${step}</button>
      <button type="button" class="btn btn-sm btn-outline js-cancel-job" data-job-id="${esc(j.id)}">Cancel</button>
    </div>`;
  }).join("");
}

function canSeeJobLog(): boolean {
  return document.getElementById("runLogPanel")?.getAttribute("data-job-log") === "1";
}

function renderRunLog(runs: RunLogRow[]): void {
  const panel = document.getElementById("runLogPanel");
  const body = document.getElementById("runLogBody");
  const count = document.getElementById("runLogCount");
  if (!panel || !body) return;
  if (count) {
    count.textContent = String(runs.length);
    count.hidden = runs.length === 0;
  }
  if (!runs.length) {
    body.innerHTML = `<p class="run-log-empty">No schedule runs yet. Use Run now or wait for the next cadence.</p>`;
    return;
  }
  const withLog = canSeeJobLog();
  const stepLogs: JobLogEntry[][] = [];
  const rows = runs.map((r) => {
    const when = r.finished_at || r.started_at || "—";
    const status = (r.status || "queued").replace(/^./, (c) => c.toUpperCase());
    const rowCount = r.rows == null ? "—" : String(r.rows);
    const log = r.job_log || [];
    let logCell = "";
    if (withLog) {
      const link = r.log_url ? `<a class="btn btn-sm btn-outline" href="${esc(r.log_url)}">Log</a>` : "";
      let steps = "";
      if (log.length) {
        stepLogs.push(log);
        steps = `<details class="run-log-steps"><summary>Steps</summary><ol class="live-job-log js-run-steps"></ol></details>`;
      }
      logCell = `<td>${link}${steps}</td>`;
    }
    return `<tr>
      <td class="run-log-when">${esc(when)}</td>
      <td><span class="mini-flag">${esc(r.kind)}</span> ${esc(r.title)}</td>
      <td><span class="${badgeClass(r.status)}">${esc(status)}</span></td>
      <td>${esc(rowCount)}</td>
      <td class="run-log-msg">${esc(r.message || "—")}</td>
      ${logCell}
    </tr>`;
  }).join("");
  body.innerHTML = `<div class="table-wrap run-log-table-wrap">
    <table class="data-table run-log-table">
      <thead><tr>
        <th>When</th><th>Schedule</th><th>Status</th><th>Rows</th><th>What happened</th>${withLog ? "<th></th>" : ""}
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
  body.querySelectorAll<HTMLOListElement>("ol.js-run-steps").forEach((ol, i) => {
    renderJobLog(ol, stepLogs[i]);
  });
}

async function refreshRunLog(): Promise<RunLogRow[]> {
  const panel = document.getElementById("runLogPanel");
  const url = panel?.getAttribute("data-recent-url") || "";
  if (!url) return [];
  try {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const data = await res.json().catch(() => ({}));
    const runs = (data.runs || []) as RunLogRow[];
    renderActiveJobs((data.active_jobs || []) as ActiveJob[]);
    renderRunLog(runs);
    return runs;
  } catch {
    return [];
  }
}

let watchGen = 0;

async function pollJob(jobId: string, onStep: (label: string) => void): Promise<void> {
  const panel = document.getElementById("runLogPanel");
  const tpl = panel?.getAttribute("data-job-url") || "";
  if (!tpl || !jobId) return;
  const url = tpl.replace("__ID__", jobId);
  const live = document.getElementById("liveJobLog");
  const gen = ++watchGen;
  await pollJobLog(url, live, onStep, () => gen !== watchGen);
}

async function watchActiveJob(jobId: string): Promise<void> {
  document.getElementById("runLogPanel")?.setAttribute("open", "");
  await pollJob(jobId, (step) => {
    document.querySelectorAll<HTMLElement>(".js-watch-job").forEach((el) => {
      if (el.dataset.jobId === jobId) el.title = step;
    });
  });
  await refreshRunLog();
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
      document.getElementById("runLogPanel")?.setAttribute("open", "");
      renderJobLog(document.getElementById("liveJobLog"), []);
      await refreshRunLog();
      const data = await actJson(b.dataset.url!, "POST", {});
      const jobId = typeof data?.job_id === "string" ? data.job_id : "";
      if (!jobId) {
        b.textContent = "Failed";
        setTimeout(() => { b.disabled = false; b.textContent = "Run now"; }, 2500);
        return;
      }
      const cancelBtn = document.createElement("button");
      cancelBtn.type = "button";
      cancelBtn.className = "btn btn-sm btn-outline";
      cancelBtn.textContent = "Cancel";
      b.insertAdjacentElement("afterend", cancelBtn);
      cancelBtn.addEventListener("click", async () => {
        cancelBtn.disabled = true;
        await cancelJob(jobId);
      });
      b.textContent = "Queued";
      await pollJob(jobId, (step) => {
        b.textContent = "Running…";
        b.title = step;
      });
      cancelBtn.remove();
      await refreshRunLog();
      b.disabled = false;
      b.textContent = "Run now";
      b.removeAttribute("title");
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

function bindSortableTables(): void {
  document.querySelectorAll<HTMLTableElement>("table.js-sortable").forEach((table) => {
    const head = table.tHead?.rows[0];
    const body = table.tBodies[0];
    if (!head || !body) return;
    let sortCol = 0;
    let sortAsc = true;

    const key = (row: HTMLTableRowElement, col: number): string => {
      if (col === 0) {
        return (row.getAttribute("data-name") || row.cells[0]?.textContent || "")
          .trim().toLowerCase();
      }
      return (row.cells[col]?.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
    };

    const apply = () => {
      const rows = Array.from(body.rows);
      rows.sort((a, b) => {
        const cmp = key(a, sortCol).localeCompare(key(b, sortCol), undefined, {
          numeric: true, sensitivity: "base",
        });
        return sortAsc ? cmp : -cmp;
      });
      rows.forEach((row) => body.appendChild(row));
      Array.from(head.cells).forEach((th, i) => {
        if (th.hasAttribute("data-sort-skip")) {
          th.removeAttribute("aria-sort");
          return;
        }
        th.setAttribute("aria-sort", i === sortCol
          ? (sortAsc ? "ascending" : "descending") : "none");
      });
    };

    Array.from(head.cells).forEach((th, i) => {
      if (th.hasAttribute("data-sort-skip")) return;
      th.classList.add("th-sort");
      th.tabIndex = 0;
      const go = () => {
        if (sortCol === i) sortAsc = !sortAsc;
        else { sortCol = i; sortAsc = true; }
        apply();
      };
      th.addEventListener("click", go);
      th.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); go(); }
      });
    });
    apply();
  });
}

function bindGridEdit(): void {
  const root = document.getElementById("schedulesRoot");
  const btn = document.getElementById("psGridEditBtn");
  if (!root || !btn) return;
  btn.addEventListener("click", () => {
    const on = root.classList.toggle("ps-grid-editing");
    btn.classList.toggle("btn-primary", on);
    btn.classList.toggle("btn-outline", !on);
    const label = btn.querySelector("span");
    if (label) label.textContent = on ? "Done" : "Edit table";
    root.querySelectorAll<HTMLElement>(".js-grid-text").forEach((el) => { el.hidden = on; });
    root.querySelectorAll<HTMLInputElement>(".js-grid-input").forEach((el) => { el.hidden = !on; });
    if (!on) void saveGridEdits(root);
  });
}

async function saveGridEdits(root: HTMLElement): Promise<void> {
  const tpl = root.getAttribute("data-update-url-tpl") || "";
  if (!tpl) return;
  for (const row of root.querySelectorAll<HTMLTableRowElement>("tr[data-id][data-kind='personal']")) {
    const rec = row.querySelector<HTMLInputElement>('input[data-field="recipients"]');
    const folder = row.querySelector<HTMLInputElement>('input[data-field="folder"]');
    if (!rec || !folder) continue;
    const params = JSON.parse(row.dataset.params || "{}");
    const kind = row.dataset.folderKind || "onedrive";
    const path = folder.value.trim();
    const owner = (row.dataset.ownerEmail || "").trim().toLowerCase();
    const listed = rec.value.split(",").map((s) => s.trim()).filter(Boolean);
    const extras = listed.filter((e) => e.toLowerCase() !== owner);
    const origRec = (row.dataset.recipients || "").trim();
    const origFolder = (row.dataset.sharepointPath || "").trim();
    if (rec.value.trim() === origRec && path === origFolder) continue;
    const body: Record<string, unknown> = {
      cadence: JSON.parse(row.dataset.cadence || "{}"),
      recipients: extras.join(", "),
      email_to_owner: listed.some((e) => e.toLowerCase() === owner),
      filename_template: row.dataset.filenameTemplate || "",
      email_on_no_data: !!params.email_on_no_data,
      email_on_no_data_me_only: !!params.email_on_no_data_me_only,
      email_cc: params.email_cc || "",
      email_bcc: params.email_bcc || "",
      folder_kind: kind,
      onedrive_path: kind === "sharepoint" ? "" : path,
      sharepoint_path: kind === "sharepoint" ? path : "",
    };
    if (row.dataset.savedReportId) body.saved_report_id = row.dataset.savedReportId;
    const url = tpl.replace(/\/0$/, `/${row.dataset.id}`);
    const ok = await act(url, "PUT", body);
    if (!ok) {
      window.alert("Could not save a row. Check recipients and folder, then try again.");
      return;
    }
  }
  location.reload();
}

document.addEventListener("DOMContentLoaded", () => {
  bindRowActions();
  bindSortableTables();
  bindPersonalWizard();
  bindGridEdit();
  bindMasterWizard();
  bindSharePointPicker();
  document.getElementById("activeJobs")?.addEventListener("click", async (ev) => {
    const target = ev.target as HTMLElement;
    const cancel = target.closest("button.js-cancel-job") as HTMLButtonElement | null;
    if (cancel?.dataset.jobId) {
      cancel.disabled = true;
      await cancelJob(cancel.dataset.jobId);
      await refreshRunLog();
      return;
    }
    const watch = target.closest("button.js-watch-job") as HTMLButtonElement | null;
    if (watch?.dataset.jobId) void watchActiveJob(watch.dataset.jobId);
  });
  const runLog = document.getElementById("runJobLog");
  const jobUrl = runLog?.getAttribute("data-job-url") || "";
  if (runLog && jobUrl) void pollJobLog(jobUrl, runLog);
  void (async () => {
    await refreshRunLog();
    const first = document.querySelector<HTMLElement>(".js-watch-job")?.dataset.jobId;
    if (first) void watchActiveJob(first);
  })();
});

// Schedules management pages (personal + company). Create uses the shared wizard.

import { esc, jsonHeaders } from "./http";
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
  history_url: string;
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
  const rows = runs.map((r) => {
    const when = r.finished_at || r.started_at || "—";
    const status = (r.status || "queued").replace(/^./, (c) => c.toUpperCase());
    const rowCount = r.rows == null ? "—" : String(r.rows);
    return `<tr>
      <td class="run-log-when">${esc(when)}</td>
      <td><span class="mini-flag">${esc(r.kind)}</span> ${esc(r.title)}</td>
      <td><span class="${badgeClass(r.status)}">${esc(status)}</span></td>
      <td>${esc(rowCount)}</td>
      <td class="run-log-msg">${esc(r.message || "—")}</td>
      <td><a class="btn btn-sm btn-outline" href="${esc(r.history_url)}">History</a></td>
    </tr>`;
  }).join("");
  body.innerHTML = `<div class="table-wrap run-log-table-wrap">
    <table class="data-table run-log-table">
      <thead><tr>
        <th>When</th><th>Schedule</th><th>Status</th><th>Rows</th><th>What happened</th><th></th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
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
    renderRunLog(runs);
    return runs;
  } catch {
    return [];
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function pollJob(jobId: string, onStep: (label: string) => void): Promise<void> {
  const panel = document.getElementById("runLogPanel");
  const tpl = panel?.getAttribute("data-job-url") || "";
  if (!tpl || !jobId) return;
  const url = tpl.replace("__ID__", jobId);
  const deadline = Date.now() + 15 * 60 * 1000;
  while (Date.now() < deadline) {
    await sleep(1000);
    try {
      const res = await fetch(url, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!res.ok) continue;
      const job = await res.json() as { status?: string; step?: string };
      if (job.step) onStep(job.step);
      if (job.status === "success" || job.status === "failure" || job.status === "cancelled") {
        return;
      }
    } catch {
      // keep polling
    }
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
      document.getElementById("runLogPanel")?.setAttribute("open", "");
      await refreshRunLog();
      const data = await actJson(b.dataset.url!, "POST", {});
      const jobId = typeof data?.job_id === "string" ? data.job_id : "";
      if (!jobId) {
        b.textContent = "Failed";
        setTimeout(() => { b.disabled = false; b.textContent = "Run now"; }, 2500);
        return;
      }
      b.textContent = "Queued";
      await pollJob(jobId, (step) => {
        b.textContent = step.length > 48 ? step.slice(0, 45) + "…" : step;
      });
      await refreshRunLog();
      b.disabled = false;
      b.textContent = "Run now";
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

document.addEventListener("DOMContentLoaded", () => {
  bindRowActions();
  bindSortableTables();
  bindPersonalWizard();
  bindMasterWizard();
  bindSharePointPicker();
});

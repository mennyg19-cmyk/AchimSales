// Schedules management pages (personal + company). Create uses the shared wizard.

import { esc, jsonHeaders } from "./http";
import { bindMasterWizard } from "./master_wizard";
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
  try {
    const res = await fetch(url, {
      method, headers: jsonHeaders(), credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return res.ok;
  } catch {
    return false;
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
  panel.setAttribute("open", "");
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

async function pollRunLog(beforeIds: Set<number>): Promise<void> {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    await sleep(1500);
    const runs = await refreshRunLog();
    const newest = runs[0];
    if (!newest) continue;
    const isNew = !beforeIds.has(newest.id);
    const done = newest.status === "success" || newest.status === "failure";
    if (isNew && done) return;
    if (isNew && newest.status === "running") continue;
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
      const before = await refreshRunLog();
      const beforeIds = new Set(before.map((r) => r.id));
      const ok = await act(b.dataset.url!, "POST", {});
      b.textContent = ok ? "Queued" : "Failed";
      if (ok) {
        await refreshRunLog();
        void pollRunLog(beforeIds).finally(() => {
          b.disabled = false;
          b.textContent = "Run now";
        });
      } else {
        setTimeout(() => { b.disabled = false; b.textContent = "Run now"; }, 2500);
      }
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

document.addEventListener("DOMContentLoaded", () => {
  bindRowActions();
  bindMasterWizard();
  bindSharePointPicker();
});

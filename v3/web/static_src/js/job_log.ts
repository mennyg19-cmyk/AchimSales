/** Live job log shared by the report viewer and schedule Run now. */

import { esc } from "./http";
import { isHidden, sleepUntilVisible } from "./visibility";

export type JobLogEntry = {
  t?: string;
  step?: string;
  detail?: string;
  ms?: number;
  elapsed_ms?: number;
};

function msCell(e: JobLogEntry): string {
  const parts: string[] = [];
  if (e.ms != null) parts.push(`${e.ms} ms`);
  if (e.elapsed_ms != null) parts.push(`+${e.elapsed_ms}ms`);
  return parts.join(" ");
}

export function renderJobLog(el: HTMLElement | null, log: JobLogEntry[] | undefined): void {
  if (!el) return;
  const items = Array.isArray(log) ? log : [];
  el.hidden = items.length === 0;
  const panel = el.id === "jobLiveLog"
    ? document.getElementById("jobLiveLogPanel")
    : null;
  if (panel) {
    panel.hidden = items.length === 0;
    if (!items.length) {
      panel.removeAttribute("open");
      panel.removeAttribute("data-opened");
    } else if (!panel.hasAttribute("data-opened")) {
      panel.setAttribute("open", "");
      panel.setAttribute("data-opened", "1");
    }
  }
  const head = `<li class="live-job-head" aria-hidden="true">`
    + `<span>Time</span><span>Step</span><span>Detail</span><span>ms</span></li>`;
  el.innerHTML = head + items.map((e) => (
    `<li class="live-job-entry">`
    + `<span class="live-job-t">${esc(e.t || "")}</span>`
    + `<span class="live-job-step">${esc(e.step || "")}</span>`
    + `<span class="live-job-detail">${esc(e.detail || "")}</span>`
    + `<span class="live-job-ms">${esc(msCell(e))}</span>`
    + `</li>`
  )).join("");
  el.scrollTop = el.scrollHeight;
}

export async function pollJobLog(
  url: string,
  el: HTMLElement | null,
  onStep?: (label: string) => void,
  isStale?: () => boolean,
): Promise<string | undefined> {
  if (!url || !el) return;
  const deadline = Date.now() + 15 * 60 * 1000;
  let waited = false;
  while (Date.now() < deadline) {
    if (isStale?.()) return;
    if (waited) await sleepUntilVisible(1000);
    waited = true;
    if (isStale?.()) return;
    if (isHidden()) {
      await sleepUntilVisible(deadline - Date.now());
      continue;
    }
    try {
      const res = await fetch(url, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!res.ok) continue;
      const job = await res.json() as {
        status?: string; step?: string; log?: JobLogEntry[];
      };
      renderJobLog(el, job.log);
      document.getElementById("runJobEmpty")?.setAttribute("hidden", "");
      if (job.step) onStep?.(job.step);
      if (job.status === "success" || job.status === "failure" || job.status === "cancelled") {
        return job.status;
      }
    } catch {
      // keep polling
    }
  }
}

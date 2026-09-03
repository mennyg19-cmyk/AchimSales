/** Live job log shared by the report viewer and schedule Run now. */

import { esc } from "./http";

export type JobLogEntry = {
  t?: string;
  step?: string;
  detail?: string;
  ms?: number;
  elapsed_ms?: number;
};

export function renderJobLog(el: HTMLElement | null, log: JobLogEntry[] | undefined): void {
  if (!el) return;
  const items = Array.isArray(log) ? log : [];
  el.hidden = items.length === 0;
  el.innerHTML = items.map((e) => {
    const ms = e.ms != null ? ` (${e.ms} ms)` : "";
    const elapsed = e.elapsed_ms != null ? ` +${e.elapsed_ms}ms` : "";
    const detail = e.detail ? `: ${e.detail}` : "";
    return `<li><span class="live-job-t">${esc(e.t || "")}</span> `
      + `<strong>${esc(e.step || "")}</strong>${esc(detail)}${esc(ms)}${esc(elapsed)}</li>`;
  }).join("");
  el.scrollTop = el.scrollHeight;
}

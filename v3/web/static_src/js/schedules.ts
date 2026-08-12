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

document.addEventListener("DOMContentLoaded", () => {
  bindRowActions();
  bindMasterWizard();
  bindSharePointPicker();
});

// Schedules management pages (personal + master).
// Master create/edit is a 5-step wizard aimed at non-technical admins.

function csrf(): string {
  const el = document.querySelector<HTMLElement>("[data-csrf]");
  return el?.getAttribute("data-csrf") || "";
}

function headers(): Record<string, string> {
  return { "Content-Type": "application/json", "X-CSRF-Token": csrf() };
}

async function act(url: string, method: string, body?: unknown): Promise<boolean> {
  try {
    const res = await fetch(url, {
      method, headers: headers(),
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
  document.querySelectorAll<HTMLButtonElement>(".js-delete").forEach((b) => {
    b.addEventListener("click", async () => {
      if (!window.confirm(b.getAttribute("data-confirm") || "Delete?")) return;
      if (await act(b.dataset.url!, "DELETE")) location.reload();
    });
  });
}

import { bindMasterWizard } from "./master_wizard";
import { bindSharePointPicker } from "./sharepoint_picker";

document.addEventListener("DOMContentLoaded", () => {
  bindRowActions();
  bindMasterWizard();
  bindSharePointPicker();
});

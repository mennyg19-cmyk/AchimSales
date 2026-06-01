/**
 * Settings page admin interactions. Currently: feature-flag toggles that POST to
 * the admin endpoint and revert the checkbox if the request fails (optimistic UI
 * with a safe rollback). Only present for privileged users (the section is
 * server-rendered behind a role check).
 */

function initFlagToggles(): void {
  const root = document.getElementById("adminSettings");
  if (!root) return;
  const url = root.getAttribute("data-flag-url") || "";
  const csrf = root.getAttribute("data-csrf") || "";

  root.querySelectorAll<HTMLInputElement>(".flag-toggle").forEach((box) => {
    box.addEventListener("change", async () => {
      const key = box.getAttribute("data-key") || "";
      const enabled = box.checked;
      box.disabled = true;
      try {
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify({ key, enabled }),
        });
        if (!resp.ok) throw new Error(String(resp.status));
      } catch {
        box.checked = !enabled; // rollback on failure
      } finally {
        box.disabled = false;
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", initFlagToggles);

export {};

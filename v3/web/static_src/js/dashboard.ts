/**
 * Customer dashboard interactions: trigger + poll a mirror refresh, filter the
 * table by tile, and toggle a customer's "include in dashboard" exclusion. Used
 * by both the dashboard list and the customer-detail page (exclusion toggle).
 */

import { watchHiddenPoll, type PollStop } from "./dialog";

declare global {
  interface Window {
    triggerDashRefresh?: () => void;
  }
}

function headers(csrf: string): Record<string, string> {
  return { "Content-Type": "application/json", "X-CSRF-Token": csrf };
}

function announceDash(text: string): void {
  const live = document.getElementById("dashLive");
  if (!live) return;
  live.hidden = !text;
  live.textContent = text;
  if (text) live.setAttribute("role", "alert");
}

// --- dashboard list ---------------------------------------------------------
function initDashboard(): void {
  const root = document.getElementById("dashRoot");
  if (!root) return;
  const csrf = root.getAttribute("data-csrf") || "";
  const refreshUrl = root.getAttribute("data-refresh-url") || "";
  const statusUrl = root.getAttribute("data-status-url") || "";

  // Tile filtering.
  document.querySelectorAll<HTMLButtonElement>(".dash-tile").forEach((tile) => {
    tile.addEventListener("click", () => {
      const status = tile.getAttribute("data-status") || "";
      document.querySelectorAll<HTMLElement>(".dash-tile").forEach((t) => t.classList.remove("tile-active"));
      tile.classList.add("tile-active");
      document.querySelectorAll<HTMLTableRowElement>("#dashTable tbody tr").forEach((tr) => {
        tr.style.display = !status || tr.dataset.status === status ? "" : "none";
      });
    });
  });

  // Refresh: enqueue, then poll the status until the row count changes.
  const btn = document.getElementById("dashRefreshBtn") as HTMLButtonElement | null;
  async function doRefresh(): Promise<void> {
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = "Refreshing\u2026";
    const before = (await fetch(statusUrl).then((r) => r.json()).catch(() => ({}))).last_refreshed;
    const posted = await fetch(refreshUrl, { method: "POST", headers: headers(csrf) }).catch(() => null);
    if (!posted || !posted.ok) {
      announceDash("Could not refresh dashboard data.");
      btn.disabled = false;
      btn.textContent = "Refresh data";
      return;
    }
    let tries = 0;
    let stopPoll: PollStop | null = null;
    const poll = async (): Promise<void> => {
      tries += 1;
      const s = await fetch(statusUrl).then((r) => r.json()).catch(() => ({}));
      if (s.last_refreshed && s.last_refreshed !== before) {
        stopPoll?.();
        window.location.reload();
        return;
      }
      if (tries >= 40) {
        stopPoll?.();
        announceDash("Dashboard refresh timed out. Try again.");
        if (btn) { btn.disabled = false; btn.textContent = "Refresh data"; }
      }
    };
    stopPoll = watchHiddenPoll(() => { void poll(); }, 3000);
  }
  if (btn) btn.addEventListener("click", doRefresh);
  window.triggerDashRefresh = doRefresh; // hook for pull-to-refresh
}

// --- exclusion toggle (list rows have none; detail page has the switch) -----
function initExclusionToggle(): void {
  const cust = document.getElementById("custRoot");
  const box = document.getElementById("custInclude") as HTMLInputElement | null;
  if (!cust || !box) return;
  const csrf = cust.getAttribute("data-csrf") || "";
  const url = cust.getAttribute("data-exclusion-url") || "";
  const account = cust.getAttribute("data-account") || "";
  box.addEventListener("change", async () => {
    box.disabled = true;
    const resp = await fetch(url, {
      method: "POST", headers: headers(csrf),
      body: JSON.stringify({ customer_account: account, excluded: !box.checked }),
    }).catch(() => null);
    if (!resp || !resp.ok) {
      box.checked = !box.checked;
      announceDash("Could not save that dashboard setting.");
    }
    box.disabled = false;
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initDashboard();
  initExclusionToggle();
});

export {};

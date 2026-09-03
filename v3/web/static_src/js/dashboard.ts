/**
 * Customer dashboard interactions: trigger + poll a mirror refresh, filter the
 * table by tile, and toggle a customer's "include in dashboard" exclusion. Used
 * by both the dashboard list and the customer-detail page (exclusion toggle).
 */

import { isHidden, sleepUntilVisible } from "./visibility";

declare global {
  interface Window {
    triggerDashRefresh?: () => void;
  }
}

function headers(csrf: string): Record<string, string> {
  return { "Content-Type": "application/json", "X-CSRF-Token": csrf };
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
  const refreshStatus = document.getElementById("dashRefreshStatus");
  const announceRefresh = (text: string, isError = false) => {
    if (!refreshStatus) return;
    refreshStatus.textContent = text;
    refreshStatus.setAttribute("aria-live", isError ? "assertive" : "polite");
    refreshStatus.setAttribute("role", isError ? "alert" : "status");
  };
  async function doRefresh(): Promise<void> {
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = "Refreshing\u2026";
    announceRefresh("Refreshing dashboard data.");
    const before = (await fetch(statusUrl).then((r) => r.json()).catch(() => ({}))).last_refreshed;
    const queued = await fetch(refreshUrl, { method: "POST", headers: headers(csrf) }).catch(() => null);
    if (!queued?.ok) {
      btn.disabled = false;
      btn.textContent = "Refresh data";
      announceRefresh("Could not start the dashboard refresh.", true);
      return;
    }
    const deadline = Date.now() + 2 * 60 * 1000;
    const poll = async (): Promise<void> => {
      if (isHidden()) {
        await sleepUntilVisible(deadline - Date.now());
        if (Date.now() < deadline) void poll();
        return;
      }
      const s = await fetch(statusUrl).then((r) => r.json()).catch(() => ({}));
      if (s.last_refreshed && s.last_refreshed !== before) {
        announceRefresh("Dashboard data refreshed.");
        window.location.reload();
        return;
      }
      if (Date.now() < deadline) {
        await sleepUntilVisible(Math.min(3000, deadline - Date.now()));
        if (Date.now() < deadline) void poll();
      } else if (btn) {
        btn.disabled = false;
        btn.textContent = "Refresh data";
        announceRefresh("Dashboard refresh is taking longer than expected.", true);
      }
    };
    await sleepUntilVisible(3000);
    void poll();
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
    if (!resp || !resp.ok) box.checked = !box.checked; // rollback
    box.disabled = false;
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initDashboard();
  initExclusionToggle();
});

export {};

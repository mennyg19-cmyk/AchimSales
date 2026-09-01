/** Customer Last Order dialogs: previous-order picker and export. */

import { openDialog, type DialogClose } from "./dialog";

function esc(s: unknown): string {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function initPrevOrder(): void {
  const card = document.querySelector<HTMLElement>(".settings-card[data-recent-url]");
  if (!card) return;
  const recentUrl = card.getAttribute("data-recent-url") || "";
  const selected = (card.getAttribute("data-selected") || "").split(",").filter(Boolean);
  const btn = document.getElementById("addPrevOrderBtn");
  const modal = document.getElementById("prevOrderModal");
  const listEl = document.getElementById("prevOrderList");
  const loadingEl = document.getElementById("prevOrderLoading");
  if (!btn || !modal || !listEl || !loadingEl) return;

  let loaded = false;
  let closeDlg: DialogClose | null = null;

  const close = () => {
    closeDlg?.();
    closeDlg = null;
  };

  function loadOrders(): void {
    fetch(recentUrl).then((r) => r.json()).then((data) => {
      const orders = (data && data.orders) || [];
      if (!orders.length) {
        loadingEl.textContent = "No recent orders found for this customer.";
        return;
      }
      let html = "";
      orders.forEach((o: { order_number: string; customer_req?: string; order_date: string }) => {
        const checked = selected.indexOf(o.order_number) !== -1;
        const po = o.customer_req ? `<span class="muted"> &middot; PO ${esc(o.customer_req)}</span>` : "";
        html += `<label class="prev-order-row"><input type="checkbox" value="${esc(o.order_number)}"`
          + (checked ? " checked" : "") + `><span class="prev-order-num">${esc(o.order_number)}</span>`
          + `<span class="muted"> &middot; ${esc(o.order_date)}</span>${po}</label>`;
      });
      listEl.innerHTML = html;
      listEl.removeAttribute("hidden");
      loadingEl.style.display = "none";
      loaded = true;
    }).catch(() => {
      loadingEl.textContent = "Could not load recent orders. Try again.";
    });
  }

  function apply(): void {
    const checks = listEl.querySelectorAll<HTMLInputElement>('input[type="checkbox"]:checked');
    const nums = [...checks].map((c) => c.value);
    if (!nums.length) {
      loadingEl.textContent = "Pick at least one order.";
      loadingEl.removeAttribute("hidden");
      return;
    }
    window.location.href = `${window.location.pathname}?orders=${encodeURIComponent(nums.join(","))}`;
  }

  btn.addEventListener("click", () => {
    closeDlg = openDialog(modal, {
      initial: document.getElementById("prevOrderApply"),
      onClose: () => { closeDlg = null; },
    });
    if (!loaded) loadOrders();
  });
  document.getElementById("prevOrderClose")?.addEventListener("click", close);
  document.getElementById("prevOrderCancel")?.addEventListener("click", close);
  document.getElementById("prevOrderApply")?.addEventListener("click", apply);
  modal.addEventListener("click", (e) => { if (e.target === modal) close(); });
}

function initExport(): void {
  const exportBtn = document.getElementById("cloExportBtn");
  const exportModal = document.getElementById("cloExportModal");
  if (!exportBtn || !exportModal) return;
  let closeDlg: DialogClose | null = null;
  const close = () => {
    closeDlg?.();
    closeDlg = null;
  };
  exportBtn.addEventListener("click", () => {
    closeDlg = openDialog(exportModal, {
      initial: document.getElementById("cloExportXlsx"),
      onClose: () => { closeDlg = null; },
    });
  });
  document.getElementById("cloExportClose")?.addEventListener("click", close);
  document.getElementById("cloExportCancel")?.addEventListener("click", close);
  exportModal.addEventListener("click", (e) => { if (e.target === exportModal) close(); });
  ["cloExportXlsx", "cloExportPdf"].forEach((id) => {
    document.getElementById(id)?.addEventListener("click", () => { setTimeout(close, 200); });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initPrevOrder();
  initExport();
});

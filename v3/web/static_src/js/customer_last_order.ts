/** Customer Last Order: pick-page lookups plus previous-order/export dialogs. */

import { openDialog, watchHiddenPoll, type DialogClose, type PollStop } from "./dialog";

declare const feather: { replace: () => void } | undefined;

function esc(s: unknown): string {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function initPick(): void {
  const card = document.querySelector<HTMLElement>(".settings-card[data-customers-url]");
  if (!card) return;
  const customersUrl = card.getAttribute("data-customers-url") || "";
  const viewTpl = card.getAttribute("data-view-url") || "";
  const listEl = document.getElementById("cloList");
  const searchEl = document.getElementById("cloSearch") as HTMLInputElement | null;
  const salesmanEl = document.getElementById("cloSalesman") as HTMLSelectElement | null;
  if (!listEl || !searchEl) return;
  const list = listEl;
  const search = searchEl;

  type CustomerRow = { key: string; name?: string };
  let all: CustomerRow[] = [];
  let attempts = 0;
  let stop: PollStop | null = null;

  function viewUrl(acct: string): string {
    return viewTpl.replace("__ACCT__", encodeURIComponent(acct));
  }

  function render(term: string): void {
    const needle = (term || "").trim().toLowerCase();
    let rows = all;
    if (needle) {
      rows = rows.filter((c) =>
        (c.key || "").toLowerCase().includes(needle)
        || (c.name || "").toLowerCase().includes(needle));
    }
    if (!rows.length) {
      list.innerHTML = '<div class="empty-state" style="padding:16px;">'
        + '<i data-feather="search" width="22" height="22"></i>'
        + '<p style="margin-top:8px;">No customers match.</p></div>';
      feather?.replace();
      return;
    }
    const max = Math.min(rows.length, 200);
    let html = "";
    for (let i = 0; i < max; i++) {
      const c = rows[i];
      html += '<a href="' + viewUrl(c.key) + '" class="customer-pick-row">'
        + '<span class="customer-pick-acct">' + esc(c.key) + "</span>"
        + '<span class="customer-pick-name">' + esc(c.name || "") + "</span></a>";
    }
    if (rows.length > max) {
      html += '<div class="customer-pick-more">Showing ' + max + " of " + rows.length
        + ". Refine your search to narrow down.</div>";
    }
    list.innerHTML = html;
  }

  function load(): void {
    let url = customersUrl;
    if (salesmanEl && salesmanEl.value) {
      url += "?salesman=" + encodeURIComponent(salesmanEl.value);
    }
    fetch(url).then((r) => r.json()).then((data) => {
      all = (data && data.customers) || [];
      if (!all.length && attempts < 15) {
        attempts += 1;
        if (!stop) stop = watchHiddenPoll(load, 1500);
        return;
      }
      stop?.();
      stop = null;
      render(search.value);
    }).catch(() => {
      list.innerHTML = '<div class="empty-state" style="padding:16px;">'
        + "<p>Could not load customers. Please try again.</p></div>";
    });
  }

  let smAttempts = 0;
  let smStop: PollStop | null = null;
  const salesmenUrl = card.getAttribute("data-salesmen-url") || "";
  function loadSalesmen(): void {
    if (!salesmanEl || !salesmenUrl) return;
    fetch(salesmenUrl)
      .then((r) => r.json())
      .then((data) => {
        const rows = data.salesmen || [];
        if (!rows.length && smAttempts < 15) {
          smAttempts += 1;
          if (!smStop) smStop = watchHiddenPoll(loadSalesmen, 1500);
          return;
        }
        smStop?.();
        smStop = null;
        rows.forEach((s: { key: string; name: string }) => {
          const opt = document.createElement("option");
          opt.value = s.key;
          opt.textContent = s.name;
          salesmanEl.appendChild(opt);
        });
      })
      .catch(() => {
        if (smAttempts < 15) {
          smAttempts += 1;
          if (!smStop) smStop = watchHiddenPoll(loadSalesmen, 1500);
        }
      });
  }

  if (salesmanEl) {
    loadSalesmen();
    salesmanEl.addEventListener("change", () => { attempts = 0; load(); });
  }
  search.addEventListener("input", () => { render(search.value); });
  load();
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
  const list = listEl;
  const loading = loadingEl;

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
        loading.textContent = "No recent orders found for this customer.";
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
      list.innerHTML = html;
      list.removeAttribute("hidden");
      loading.style.display = "none";
      loaded = true;
    }).catch(() => {
      loading.textContent = "Could not load recent orders. Try again.";
    });
  }

  function apply(): void {
    const checks = list.querySelectorAll<HTMLInputElement>('input[type="checkbox"]:checked');
    const nums = [...checks].map((c) => c.value);
    if (!nums.length) {
      loading.textContent = "Pick at least one order.";
      loading.removeAttribute("hidden");
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
  initPick();
  initPrevOrder();
  initExport();
});

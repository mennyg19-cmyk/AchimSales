/**
 * Admin "Users & access" page. Server renders the current state; this wires the
 * mutations (add/edit/delete user, per-salesman + per-report access, salesman
 * active toggle + edit) as JSON calls against the admin API. All endpoints are
 * privilege-guarded server-side; this is purely UX.
 */

import { openDialog, type DialogClose } from "./dialog";

const root = document.getElementById("adminUsers");
const usersUrl = root?.getAttribute("data-users-url") || "";
const csrf = root?.getAttribute("data-csrf") || "";
const salesmenBase = usersUrl.replace(/\/users$/, "/salesmen");

let closeUserDlg: DialogClose | null = null;
let closeSmDlg: DialogClose | null = null;

function headers(): Record<string, string> {
  return { "Content-Type": "application/json", "X-CSRF-Token": csrf };
}

async function api(url: string, method: string, body?: unknown): Promise<Response> {
  return fetch(url, { method, headers: headers(), body: body ? JSON.stringify(body) : undefined });
}

function $(id: string): HTMLElement | null {
  return document.getElementById(id);
}

function checked(id: string): boolean {
  return ($(id) as HTMLInputElement | null)?.checked ?? false;
}

// --- user search ------------------------------------------------------------
function initSearch(): void {
  const box = $("userSearch") as HTMLInputElement | null;
  if (!box) return;
  box.addEventListener("input", () => {
    const q = box.value.trim().toLowerCase();
    document.querySelectorAll<HTMLTableRowElement>("#userTable tbody tr").forEach((tr) => {
      const hay = `${tr.dataset.email} ${tr.dataset.name}`.toLowerCase();
      tr.style.display = hay.includes(q) ? "" : "none";
    });
  });
}

// --- add user ---------------------------------------------------------------
function initAddUser(): void {
  const form = $("addUserForm") as HTMLFormElement | null;
  const msg = $("addUserMsg");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const resp = await api(usersUrl, "POST", {
      email: fd.get("email"), role: fd.get("role"),
      display_name: fd.get("display_name"), is_external: fd.get("is_external") === "on",
    });
    if (resp.ok) {
      window.location.reload();
    } else if (msg) {
      msg.textContent = (await resp.json().catch(() => ({}))).error || "Failed to add user";
    }
  });
}

// --- edit user modal --------------------------------------------------------
let editingUserId = "";

function openUserModal(tr: HTMLTableRowElement): void {
  editingUserId = tr.dataset.userId || "";
  const title = $("editUserTitle");
  if (title) title.textContent = `Edit ${tr.dataset.email}`;
  (($("euRole") as HTMLSelectElement)).value = tr.dataset.role || "salesman";
  (($("euActive") as HTMLInputElement)).checked = tr.dataset.active === "1";
  (($("euDashboard") as HTMLInputElement)).checked = tr.dataset.dashboard === "1";
  (($("euSharepoint") as HTMLInputElement)).checked = tr.dataset.sharepoint === "1";
  (($("euExternal") as HTMLInputElement)).checked = tr.dataset.external === "1";

  // Load current per-salesman + per-report access so the modal reflects the
  // user's live state (rather than blank defaults).
  Promise.all([
    api(`${usersUrl}/${editingUserId}/salesman-access`, "GET").then((r) => r.json()),
    api(`${usersUrl}/${editingUserId}/report-access`, "GET").then((r) => r.json()),
  ]).then(([scope, reports]) => {
    const keys: string[] = scope.keys || [];
    document.querySelectorAll<HTMLInputElement>("#euSalesmen input").forEach((c) => {
      c.checked = keys.includes(c.value);
    });
    const access: Record<string, string> = reports.access || {};
    document.querySelectorAll<HTMLSelectElement>("#euReports .report-access-select").forEach((sel) => {
      sel.value = access[sel.getAttribute("data-report") || ""] || "inherit";
    });
  });

  setMsg("euMsg", "");
  const modal = $("editUserModal");
  if (!modal) return;
  closeUserDlg?.();
  closeUserDlg = openDialog(modal, {
    initial: $("euRole"),
    onClose: () => { closeUserDlg = null; },
  });
}

async function saveUser(): Promise<void> {
  if (!editingUserId) return;
  const resp = await api(`${usersUrl}/${editingUserId}`, "PUT", {
    role: (($("euRole") as HTMLSelectElement)).value,
    is_active: checked("euActive"), dashboard_enabled: checked("euDashboard"),
    sharepoint_access: checked("euSharepoint"),
    is_external: checked("euExternal"),
  });
  if (!resp.ok) {
    setMsg("euMsg", (await resp.json().catch(() => ({}))).error || "Save failed");
    return;
  }
  const keys = Array.from(
    document.querySelectorAll<HTMLInputElement>("#euSalesmen input:checked")
  ).map((c) => c.value);
  const scopeResp = await api(`${usersUrl}/${editingUserId}/salesman-access`, "POST", { keys });
  if (!scopeResp.ok) {
    setMsg("euMsg", "User saved, but salesman access did not save. Try again.");
    return;
  }

  const reportPosts = Array.from(
    document.querySelectorAll<HTMLSelectElement>("#euReports .report-access-select")
  ).map((sel) => api(`${usersUrl}/${editingUserId}/report-access`, "POST",
    { report_key: sel.getAttribute("data-report"), access: sel.value }));
  const reportResps = await Promise.all(reportPosts);
  if (reportResps.some((r) => !r.ok)) {
    setMsg("euMsg", "User saved, but a report-access change did not save. Try again.");
    return;
  }
  window.location.reload();
}

async function deleteUser(): Promise<void> {
  if (!editingUserId) return;
  if (!window.confirm("Delete this user and all their saved data?")) return;
  const resp = await api(`${usersUrl}/${editingUserId}`, "DELETE");
  if (resp.ok) window.location.reload();
  else setMsg("euMsg", (await resp.json().catch(() => ({}))).error || "Delete failed");
}

// --- salesman edit + active toggle -----------------------------------------
let editingSmKey = "";

function initSalesmen(): void {
  document.querySelectorAll<HTMLInputElement>(".sm-active-toggle").forEach((box) => {
    box.addEventListener("change", async () => {
      const key = box.getAttribute("data-key") || "";
      box.disabled = true;
      const resp = await api(`${salesmenBase}/${encodeURIComponent(key)}`, "PUT",
        { is_active: box.checked });
      if (!resp.ok) box.checked = !box.checked;
      if (!resp.ok) window.alert("Could not update salesman.");
      box.disabled = false;
    });
  });
}

function openSmModal(tr: HTMLTableRowElement): void {
  editingSmKey = tr.dataset.key || "";
  (($("esNumber") as HTMLInputElement)).value = tr.dataset.number || "";
  (($("esFull") as HTMLInputElement)).value = tr.dataset.full || "";
  (($("esDisplay") as HTMLInputElement)).value = tr.dataset.display || "";
  (($("esEmail") as HTMLInputElement)).value = tr.dataset.email || "";
  setMsg("esMsg", "");
  const modal = $("editSmModal");
  if (!modal) return;
  closeSmDlg?.();
  closeSmDlg = openDialog(modal, {
    initial: $("esNumber"),
    onClose: () => { closeSmDlg = null; },
  });
}

async function saveSm(): Promise<void> {
  if (!editingSmKey) return;
  const resp = await api(`${salesmenBase}/${encodeURIComponent(editingSmKey)}`, "PUT", {
    number: (($("esNumber") as HTMLInputElement)).value,
    full_name: (($("esFull") as HTMLInputElement)).value,
    display_name: (($("esDisplay") as HTMLInputElement)).value,
    email: (($("esEmail") as HTMLInputElement)).value,
  });
  if (resp.ok) window.location.reload();
  else setMsg("esMsg", (await resp.json().catch(() => ({}))).error || "Save failed");
}

function setMsg(id: string, text: string): void {
  const el = $(id);
  if (!el) return;
  el.textContent = text;
  el.setAttribute("role", text ? "alert" : "status");
}

function closeUserModal(): void {
  closeUserDlg?.();
  closeUserDlg = null;
}

function closeSmModal(): void {
  closeSmDlg?.();
  closeSmDlg = null;
}

function initEvents(): void {
  document.addEventListener("click", (e) => {
    const t = e.target as HTMLElement;
    if (t.closest(".btn-edit-user")) {
      openUserModal(t.closest("tr") as HTMLTableRowElement);
    } else if (t.closest(".btn-edit-sm")) {
      openSmModal(t.closest("tr") as HTMLTableRowElement);
    } else if (t.closest("[data-close-user]") || t.id === "editUserModal") {
      closeUserModal();
    } else if (t.closest("[data-close-sm]") || t.id === "editSmModal") {
      closeSmModal();
    }
  });
  $("euSave")?.addEventListener("click", saveUser);
  $("euDelete")?.addEventListener("click", deleteUser);
  $("esSave")?.addEventListener("click", saveSm);
}

if (root) {
  document.addEventListener("DOMContentLoaded", () => {
    initSearch();
    initAddUser();
    initSalesmen();
    initEvents();
  });
}

export {};

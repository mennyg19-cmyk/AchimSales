/**
 * Admin "Users & access" page. Server renders the current state; this wires the
 * mutations (add/edit/delete user, per-salesman + per-report access, salesman
 * active toggle + edit) as JSON calls against the admin API. All endpoints are
 * privilege-guarded server-side; this is purely UX.
 */

const root = document.getElementById("adminUsers");
const usersUrl = root?.getAttribute("data-users-url") || "";
const csrf = root?.getAttribute("data-csrf") || "";
const salesGroupsUrl = root?.getAttribute("data-sales-groups-url") || "";
const lookupStatusUrl = root?.getAttribute("data-lookup-status-url") || "";
const salesmenBase = usersUrl.replace(/\/users$/, "/salesmen");

type SalesGroupRow = { key: string; name: string };
let salesGroups: SalesGroupRow[] = [];
let lookupPollTimer: number | null = null;

function salesmanKey(sg: string): string {
  return sg.trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
}

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
function setHidden(id: string, hidden: boolean): void {
  const el = $(id);
  if (el) el.hidden = hidden;
}

function syncAddRole(role: string): void {
  setHidden("addSalesGroupWrap", role !== "salesman");
}

function syncEditRole(role: string): void {
  setHidden("euSalesGroupWrap", role !== "salesman");
  setHidden("euSalesmenWrap", role !== "manager");
}

function fillSalesGroupSelect(sel: HTMLSelectElement | null, keep: string): void {
  if (!sel) return;
  const want = keep || sel.value;
  sel.innerHTML = '<option value="">— none —</option>';
  salesGroups.forEach((r) => {
    const o = document.createElement("option");
    o.value = r.key;
    o.textContent = r.name;
    sel.appendChild(o);
  });
  if (want && ![...sel.options].some((o) => o.value === want)) {
    const o = document.createElement("option");
    o.value = want;
    o.textContent = want;
    sel.appendChild(o);
  }
  if (!want) {
    sel.value = "";
    return;
  }
  if ([...sel.options].some((o) => o.value === want)) {
    sel.value = want;
    return;
  }
  const nk = salesmanKey(want);
  const byNorm = [...sel.options].find((o) => o.value && salesmanKey(o.value) === nk);
  if (byNorm) sel.value = byNorm.value;
}

function setSalesGroupStatus(text: string): void {
  ["addSalesGroupStatus", "euSalesGroupStatus"].forEach((id) => {
    const el = $(id);
    if (el) el.textContent = text;
  });
}

async function loadSalesGroups(): Promise<number> {
  if (!salesGroupsUrl) return 0;
  try {
    const resp = await fetch(salesGroupsUrl);
    if (!resp.ok) return 0;
    const data = await resp.json().catch(() => ({}));
    const items = Array.isArray(data.items) ? data.items : [];
    salesGroups = items.filter((r: SalesGroupRow) => r && r.key);
  } catch {
    return 0;
  }
  const keepEdit = ($("euSalesGroup") as HTMLSelectElement | null)?.value || "";
  fillSalesGroupSelect($("addSalesGroup") as HTMLSelectElement, "");
  fillSalesGroupSelect($("euSalesGroup") as HTMLSelectElement, keepEdit);
  return salesGroups.length;
}

function pollSalesGroups(): void {
  if (!lookupStatusUrl) return;
  const tick = async () => {
    try {
      const resp = await fetch(lookupStatusUrl);
      if (!resp.ok) return;
      const s = await resp.json().catch(() => ({}));
      const ready = s.status === "ready"
        || (s.cached_row_count || 0) > 0
        || (s.mirror_row_count || 0) > 0;
      if (ready) {
        if (lookupPollTimer != null) {
          window.clearInterval(lookupPollTimer);
          lookupPollTimer = null;
        }
        setSalesGroupStatus("");
        await loadSalesGroups();
        return;
      }
      if (s.status === "loading") setSalesGroupStatus("Loading SalesGroups…");
      else if (s.status === "error") setSalesGroupStatus("Customer master still warming — retrying…");
      else if (s.configured === false) setSalesGroupStatus("");
    } catch {
      /* retry on the next tick */
    }
  };
  tick();
  lookupPollTimer = window.setInterval(tick, 2500);
}

function initSalesGroups(): void {
  loadSalesGroups().then((count) => {
    if (count > 0) return;
    pollSalesGroups();
  }).catch(() => {
    setSalesGroupStatus("Could not load SalesGroups.");
  });
}

function initAddUser(): void {
  const form = $("addUserForm") as HTMLFormElement | null;
  const msg = $("addUserMsg");
  if (!form) return;
  const roleSel = $("addRole") as HTMLSelectElement | null;
  roleSel?.addEventListener("change", () => syncAddRole(roleSel.value));
  if (roleSel) syncAddRole(roleSel.value);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const role = String(fd.get("role") || "");
    const resp = await api(usersUrl, "POST", {
      email: fd.get("email"), role,
      display_name: fd.get("display_name"), is_external: fd.get("is_external") === "on",
      sales_group: role === "salesman" ? fd.get("sales_group") : "",
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
  (($("euDisplay") as HTMLInputElement)).value = tr.dataset.name || "";
  const role = tr.dataset.role || "salesman";
  (($("euRole") as HTMLSelectElement)).value = role;
  (($("euActive") as HTMLInputElement)).checked = tr.dataset.active === "1";
  (($("euDashboard") as HTMLInputElement)).checked = tr.dataset.dashboard === "1";
  (($("euSharepoint") as HTMLInputElement)).checked = tr.dataset.sharepoint === "1";
  (($("euTest") as HTMLInputElement)).checked = tr.dataset.test === "1";
  (($("euCompanyViews") as HTMLInputElement)).checked = tr.dataset.companyViews === "1";
  (($("euExternal") as HTMLInputElement)).checked = tr.dataset.external === "1";
  syncEditRole(role);
  let keepGroup = tr.dataset.salesGroup || "";
  fillSalesGroupSelect($("euSalesGroup") as HTMLSelectElement, keepGroup);

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
    if (!keepGroup && keys.length === 1) keepGroup = keys[0];
    fillSalesGroupSelect($("euSalesGroup") as HTMLSelectElement, keepGroup);
    const access: Record<string, string> = reports.access || {};
    document.querySelectorAll<HTMLSelectElement>("#euReports .report-access-select").forEach((sel) => {
      sel.value = access[sel.getAttribute("data-report") || ""] || "inherit";
    });
  });

  setMsg("euMsg", "");
  show("editUserModal");
}

async function saveUser(): Promise<void> {
  if (!editingUserId) return;
  const role = (($("euRole") as HTMLSelectElement)).value;
  const salesGroup = (($("euSalesGroup") as HTMLSelectElement | null))?.value || "";
  const resp = await api(`${usersUrl}/${editingUserId}`, "PUT", {
    display_name: (($("euDisplay") as HTMLInputElement)).value.trim(),
    role,
    is_active: checked("euActive"), dashboard_enabled: checked("euDashboard"),
    sharepoint_access: checked("euSharepoint"), test_access: checked("euTest"),
    can_see_company_views: checked("euCompanyViews"),
    is_external: checked("euExternal"),
    sales_group: role === "salesman" ? salesGroup : "",
  });
  if (!resp.ok) {
    setMsg("euMsg", (await resp.json().catch(() => ({}))).error || "Save failed");
    return;
  }
  if (role === "manager") {
    const keys = Array.from(
      document.querySelectorAll<HTMLInputElement>("#euSalesmen input:checked")
    ).map((c) => c.value);
    await api(`${usersUrl}/${editingUserId}/salesman-access`, "POST", { keys });
  }

  const reportPosts = Array.from(
    document.querySelectorAll<HTMLSelectElement>("#euReports .report-access-select")
  ).map((sel) => api(`${usersUrl}/${editingUserId}/report-access`, "POST",
    { report_key: sel.getAttribute("data-report"), access: sel.value }));
  await Promise.all(reportPosts);
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
  show("editSmModal");
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

// --- helpers ----------------------------------------------------------------
function show(id: string): void {
  const el = $(id);
  if (el) el.style.display = "flex";
}
function hide(id: string): void {
  const el = $(id);
  if (el) el.style.display = "none";
}
function setMsg(id: string, text: string): void {
  const el = $(id);
  if (el) el.textContent = text;
}

function initEvents(): void {
  document.addEventListener("click", (e) => {
    const t = e.target as HTMLElement;
    if (t.closest(".btn-edit-user")) {
      openUserModal(t.closest("tr") as HTMLTableRowElement);
    } else if (t.closest(".btn-edit-sm")) {
      openSmModal(t.closest("tr") as HTMLTableRowElement);
    } else if (t.closest("[data-close-user]") || t.id === "editUserModal") {
      hide("editUserModal");
    } else if (t.closest("[data-close-sm]") || t.id === "editSmModal") {
      hide("editSmModal");
    }
  });
  $("euSave")?.addEventListener("click", saveUser);
  $("euDelete")?.addEventListener("click", deleteUser);
  $("esSave")?.addEventListener("click", saveSm);
  $("euRole")?.addEventListener("change", () => {
    const role = ($("euRole") as HTMLSelectElement | null)?.value || "";
    syncEditRole(role);
    const box = $("euCompanyViews") as HTMLInputElement | null;
    if (role === "developer" && box) box.checked = true;
  });
}

if (root) {
  document.addEventListener("DOMContentLoaded", () => {
    initSearch();
    initAddUser();
    initSalesGroups();
    initSalesmen();
    initEvents();
  });
}

export {};

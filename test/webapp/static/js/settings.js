/* Settings page behavior. Uses /api/settings/* endpoints. */

(function () {
  "use strict";

  const PREFIX = window.V2_URL_PREFIX || "";

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  function showToast(msg, variant) {
    const el = $("#settingsToast");
    if (!el) return;
    el.textContent = msg;
    el.className = "settings-toast" + (variant === "error" ? " toast-error" : "");
    el.style.display = "block";
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.style.display = "none"; }, 2200);
  }

  async function apiPost(path, body) {
    const r = await fetch(PREFIX + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const json = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(json.error || ("HTTP " + r.status));
    return json;
  }

  async function apiGet(path) {
    const r = await fetch(PREFIX + path, { headers: { "Accept": "application/json" } });
    const json = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(json.error || ("HTTP " + r.status));
    return json;
  }

  // ---------------------------------------------------------------------
  // Collapsibles
  // ---------------------------------------------------------------------
  $all(".collapsible").forEach((h) => {
    h.addEventListener("click", () => {
      const targetId = h.getAttribute("data-toggle");
      const body = document.getElementById(targetId);
      if (!body) return;
      h.classList.toggle("collapsed");
      body.classList.toggle("collapsed");
    });
  });

  // ---------------------------------------------------------------------
  // Appearance / preferences
  // ---------------------------------------------------------------------
  async function savePrefs(patch) {
    try {
      await apiPost("/api/settings/preferences", patch);
      showToast("Saved.");
    } catch (e) {
      showToast("Save failed: " + e.message, "error");
    }
  }

  const themeToggle = $("#prefThemeToggle");
  if (themeToggle) {
    themeToggle.addEventListener("change", (ev) => {
      const isDark = ev.target.checked;
      document.body.classList.toggle("dark-theme", isDark);
      try { localStorage.setItem("v2_theme", isDark ? "dark" : "light"); } catch (_) {}
      const headerBtn = document.getElementById("themeToggleBtn");
      if (headerBtn) {
        const icon = headerBtn.querySelector("i");
        if (icon) {
          icon.setAttribute("data-feather", isDark ? "sun" : "moon");
          if (typeof feather !== "undefined") feather.replace();
        }
      }
      savePrefs({ theme: isDark ? "dark" : "light" });
    });
  }

  const landingSel = $("#prefLandingPage");
  if (landingSel) {
    landingSel.addEventListener("change", (e) => savePrefs({ landing_page: e.target.value }));
  }

  const tabSel = $("#prefDefaultTab");
  if (tabSel) {
    tabSel.addEventListener("change", (e) => savePrefs({ default_tab: e.target.value }));
  }

  // ---------------------------------------------------------------------
  // Customer exclusions
  // ---------------------------------------------------------------------
  const exSaveBar = $("#exclusionsSaveBar");
  const exSaveBtn = $("#exclusionsSaveBtn");
  const exSearch = $("#exclusionsSearch");

  function excludeDirtyCheck() {
    const anyChanged = $all("#customerList .settings-customer-item").some((item) => {
      const toggle = $(".exclusion-toggle", item);
      const was = item.classList.contains("excluded");
      return toggle.checked !== was;
    });
    if (exSaveBar) exSaveBar.style.display = anyChanged ? "flex" : "none";
  }

  $all("#customerList .exclusion-toggle").forEach((t) => {
    t.addEventListener("change", excludeDirtyCheck);
  });

  if (exSaveBtn) {
    exSaveBtn.addEventListener("click", async () => {
      const accounts = $all("#customerList .settings-customer-item")
        .filter((i) => $(".exclusion-toggle", i).checked)
        .map((i) => i.getAttribute("data-account"));
      try {
        await apiPost("/api/settings/exclusions", { accounts });
        $all("#customerList .settings-customer-item").forEach((i) => {
          i.classList.toggle("excluded", $(".exclusion-toggle", i).checked);
        });
        exSaveBar.style.display = "none";
        showToast("Exclusions saved.");
      } catch (e) {
        showToast("Save failed: " + e.message, "error");
      }
    });
  }

  if (exSearch) {
    exSearch.addEventListener("input", () => {
      const q = exSearch.value.trim().toLowerCase();
      $all("#customerList .settings-customer-item").forEach((item) => {
        const acct = (item.getAttribute("data-account") || "").toLowerCase();
        const name = ($(".settings-cust-name", item) || {}).textContent || "";
        item.style.display =
          !q || acct.includes(q) || name.toLowerCase().includes(q) ? "" : "none";
      });
    });
  }

  // ---------------------------------------------------------------------
  // Admin: feature flags
  // ---------------------------------------------------------------------
  $all(".feature-flag-toggle").forEach((t) => {
    t.addEventListener("change", async () => {
      const key = t.getAttribute("data-key");
      try {
        await apiPost("/api/settings/admin/feature-flag",
                      { key, enabled: t.checked });
        showToast("Flag saved.");
      } catch (e) {
        t.checked = !t.checked;
        showToast("Save failed: " + e.message, "error");
      }
    });
  });

  // ---------------------------------------------------------------------
  // Admin: users + permissions (mirrors live admin/settings)
  // ---------------------------------------------------------------------

  function escape(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // Hide / show the salesman dropdown based on selected role.
  function syncRoleVisibility(prefix) {
    const roleSel = $("#" + prefix + "UserRole");
    const smWrap  = $("#" + (prefix === "new" ? "newUserSalesmanWrap" : "editSalesmanWrap"));
    const assignedWrap = prefix === "edit" ? $("#editAssignedWrap") : null;
    const externalRow = prefix === "edit" ? $("#editUserExternalRow") : null;
    if (!roleSel) return;
    const role = roleSel.value;
    if (smWrap) smWrap.style.display = (role === "salesman") ? "" : "none";
    if (assignedWrap) assignedWrap.style.display = (role === "manager") ? "" : "none";
    if (externalRow) externalRow.style.display = (role === "salesman") ? "" : "none";
  }

  const newRoleSel = $("#newUserRole");
  if (newRoleSel) {
    newRoleSel.addEventListener("change", () => syncRoleVisibility("new"));
    syncRoleVisibility("new");
  }

  // ---- Add new user ----
  const newUserAddBtn = $("#newUserAddBtn");
  if (newUserAddBtn) {
    newUserAddBtn.addEventListener("click", async () => {
      const email = ($("#newUserEmail").value || "").trim().toLowerCase();
      const role  = $("#newUserRole").value;
      const sk    = ($("#newUserSalesmanKey") || {}).value || "";
      const dn    = ($("#newUserDisplayName") || {}).value || "";
      const ext   = !!($("#newUserIsExternal") || {}).checked;
      const msg   = $("#newUserMsg");
      if (!email) {
        if (msg) { msg.style.display = "block"; msg.style.color = "var(--error)"; msg.textContent = "Email required"; }
        return;
      }
      try {
        const r = await apiPost("/api/settings/admin/users/add", {
          email, role, salesman_key: sk || null,
          display_name: dn || null, is_external: ext,
        });
        rebuildUserList(r.perm_grid || []);
        $("#newUserEmail").value = "";
        $("#newUserDisplayName").value = "";
        if (msg) { msg.style.display = "block"; msg.style.color = "var(--success, #2c7a3a)"; msg.textContent = "Added " + email; }
        showToast("User added.");
      } catch (e) {
        if (msg) { msg.style.display = "block"; msg.style.color = "var(--error)"; msg.textContent = e.message; }
      }
    });
  }

  // ---- Render the user list from a permGrid array ----
  function rebuildUserList(perm_grid) {
    const list = $("#permUserList");
    if (!list) return;
    list.innerHTML = "";
    perm_grid.forEach((u) => {
      const row = document.createElement("div");
      row.className = "perm-user-row";
      row.setAttribute("data-email", u.email);
      row.setAttribute("data-user", JSON.stringify(u));
      const badges = [];
      if (u.is_external) badges.push('<span class="badge badge-external">External</span>');
      if (!u.active)     badges.push('<span class="badge badge-inactive">Inactive</span>');
      const roleClass = (u.role === "admin" || u.role === "developer") ? "badge-admin"
                      : (u.role === "manager") ? "badge-manager" : "badge-salesman";
      badges.push(`<span class="badge ${roleClass}">${escape(u.role)}</span>`);
      row.innerHTML = `
        <div class="perm-user-info">
          <span class="perm-user-name">${escape(u.display_name || u.sm_name || u.email)}</span>
          <span class="perm-user-email">${escape(u.email)}</span>
          ${u.salesman_key ? `<span class="perm-user-key">${escape(u.salesman_key)}${u.sm_number ? " #" + escape(u.sm_number) : ""}</span>` : ""}
        </div>
        <div class="perm-user-meta">
          ${badges.join("")}
          <i data-feather="chevron-right" style="width:14px;height:14px;color:var(--text-muted);"></i>
        </div>`;
      row.addEventListener("click", () => openEditUser(u));
      list.appendChild(row);
    });
    if (typeof feather !== "undefined") feather.replace();
  }

  // ---- Search filter for the user list ----
  const permGridSearch = $("#permGridSearch");
  if (permGridSearch) {
    permGridSearch.addEventListener("input", () => {
      const q = permGridSearch.value.trim().toLowerCase();
      $all("#permUserList .perm-user-row").forEach((row) => {
        const text = row.textContent.toLowerCase();
        row.style.display = !q || text.includes(q) ? "" : "none";
      });
    });
  }

  // Wire up existing rows on first render.
  $all("#permUserList .perm-user-row").forEach((row) => {
    let u;
    try { u = JSON.parse(row.getAttribute("data-user") || "{}"); }
    catch (_) { u = { email: row.getAttribute("data-email") }; }
    row.addEventListener("click", () => openEditUser(u));
  });

  // ---- Edit-user modal ----
  const editModal = $("#editUserModal");
  let _editingUser = null;

  function openEditUser(u) {
    _editingUser = u;
    $("#editUserEmail").value = u.email;
    $("#editUserEmailDisplay").value = u.email;
    $("#editUserRole").value = u.role || "salesman";
    $("#editUserSalesmanKey").value = u.salesman_key || "";
    $("#editUserDisplayName").value = u.display_name || "";
    $("#editUserActive").checked    = !!u.active;
    $("#editUserIsExternal").checked = !!u.is_external;
    $("#editUserDashboard").checked = !!u.dashboard_enabled;
    $("#editUserSharepoint").checked = !!u.sharepoint_access_enabled;
    syncRoleVisibility("edit");

    // Per-report overrides: u.reports is the *effective* permission. Compare
    // against the role default to figure out if it's an explicit override.
    const isPriv = (u.role === "admin" || u.role === "developer" || u.role === "manager");
    $all("#editUserReportsList .report-access-select").forEach((sel) => {
      const rk = sel.getAttribute("data-report-key");
      const eff = u.reports ? u.reports[rk] : undefined;
      const def = isPriv ? true : true;
      if (eff === undefined || eff === def) sel.value = "";
      else sel.value = eff ? "1" : "0";
    });

    // Assigned salesmen: only used for managers.
    const assigned = new Set(u.allowed_salesmen || []);
    $all("#editAssignedList .assigned-sm-toggle").forEach((cb) => {
      cb.checked = assigned.has(cb.getAttribute("data-sm-key"));
    });

    editModal.hidden = false;
    if (typeof feather !== "undefined") feather.replace();
  }

  function closeEditUser() {
    editModal.hidden = true;
    _editingUser = null;
  }

  if ($("#editUserClose")) $("#editUserClose").addEventListener("click", closeEditUser);
  if ($("#editUserRole")) $("#editUserRole").addEventListener("change", () => syncRoleVisibility("edit"));

  if ($("#editUserSave")) $("#editUserSave").addEventListener("click", async () => {
    if (!_editingUser) return;
    const email = _editingUser.email;
    const newEmail = ($("#editUserEmailDisplay").value || "").trim().toLowerCase();
    const role     = $("#editUserRole").value;
    const sk       = ($("#editUserSalesmanKey").value || "").trim() || null;
    const dn       = ($("#editUserDisplayName").value || "").trim() || null;
    const patch = {
      email,
      role,
      salesman_key: sk,
      display_name: dn,
      active:                    $("#editUserActive").checked,
      is_external:               $("#editUserIsExternal").checked,
      dashboard_enabled:         $("#editUserDashboard").checked,
      sharepoint_access_enabled: $("#editUserSharepoint").checked,
    };
    if (newEmail && newEmail !== email) patch.new_email = newEmail;
    try {
      const r = await apiPost("/api/settings/admin/users", patch);
      const targetEmail = (newEmail && newEmail !== email) ? newEmail : email;
      // Push per-report overrides (only those where the admin chose Allow/Deny).
      const overrides = $all("#editUserReportsList .report-access-select").map((sel) => ({
        report_key: sel.getAttribute("data-report-key"),
        value:      sel.value,
      }));
      for (const o of overrides) {
        if (o.value === "") {
          await apiPost("/api/settings/admin/users/report-access",
                        { email: targetEmail, report_key: o.report_key });
        } else {
          await apiPost("/api/settings/admin/users/report-access",
                        { email: targetEmail, report_key: o.report_key, allowed: o.value === "1" });
        }
      }
      // Push assigned salesmen list (managers only; harmless for others).
      if (role === "manager") {
        const keys = $all("#editAssignedList .assigned-sm-toggle")
          .filter((cb) => cb.checked)
          .map((cb) => cb.getAttribute("data-sm-key"));
        await apiPost("/api/settings/admin/users/salesman-access",
                      { email: targetEmail, keys });
      }
      const finalGrid = await apiGet("/api/settings/admin/users");
      rebuildUserList(finalGrid.perm_grid || r.perm_grid || []);
      closeEditUser();
      showToast("User saved.");
    } catch (e) {
      showToast("Save failed: " + e.message, "error");
    }
  });

  if ($("#editUserDelete")) $("#editUserDelete").addEventListener("click", async () => {
    if (!_editingUser) return;
    const email = _editingUser.email;
    if (!confirm("Delete " + email + "?\nAll their saved presets and schedules will remain in the DB.")) return;
    try {
      const r = await apiPost("/api/settings/admin/users/delete", { email });
      rebuildUserList(r.perm_grid || []);
      closeEditUser();
      showToast("User deleted.");
    } catch (e) {
      showToast("Delete failed: " + e.message, "error");
    }
  });

  // ---------------------------------------------------------------------
  // Admin: salesman map
  // ---------------------------------------------------------------------

  function rebuildSalesmenList(salesmen) {
    const list = $("#salesmenList");
    if (!list) return;
    list.innerHTML = "";
    salesmen.forEach((sm) => {
      const row = document.createElement("div");
      row.className = "perm-user-row";
      row.setAttribute("data-sm-key", sm.key);
      row.setAttribute("data-sm", JSON.stringify(sm));
      const badges = [];
      if (!sm.active) badges.push('<span class="badge badge-inactive">Inactive</span>');
      if (sm.commission_pct) badges.push(`<span class="badge badge-salesman" title="Commission %">${(+sm.commission_pct).toFixed(2)}%</span>`);
      row.innerHTML = `
        <div class="perm-user-info">
          <span class="perm-user-name">${escape(sm.full_name || sm.key)}</span>
          <span class="perm-user-email">${escape(sm.email || "— no email —")}</span>
          <span class="perm-user-key">${escape(sm.key)}${sm.number ? " #" + escape(sm.number) : ""}</span>
        </div>
        <div class="perm-user-meta">
          ${badges.join("")}
          <i data-feather="chevron-right" style="width:14px;height:14px;color:var(--text-muted);"></i>
        </div>`;
      row.addEventListener("click", () => openEditSm(sm));
      list.appendChild(row);
    });
    if (typeof feather !== "undefined") feather.replace();
  }

  $all("#salesmenList .perm-user-row").forEach((row) => {
    let sm;
    try { sm = JSON.parse(row.getAttribute("data-sm") || "{}"); }
    catch (_) { sm = { key: row.getAttribute("data-sm-key") }; }
    row.addEventListener("click", () => openEditSm(sm));
  });

  const smSearch = $("#salesmenSearch");
  if (smSearch) {
    smSearch.addEventListener("input", () => {
      const q = smSearch.value.trim().toLowerCase();
      $all("#salesmenList .perm-user-row").forEach((row) => {
        const text = row.textContent.toLowerCase();
        row.style.display = !q || text.includes(q) ? "" : "none";
      });
    });
  }

  const smModal = $("#editSmModal");
  let _editingSm = null;
  function openEditSm(sm) {
    _editingSm = sm;
    $("#editSmKey").value         = sm.key || "";
    $("#editSmNumber").value      = sm.number || "";
    $("#editSmFullName").value    = sm.full_name || "";
    $("#editSmDisplayName").value = sm.display_name || "";
    $("#editSmEmail").value       = sm.email || "";
    $("#editSmCommission").value  = (sm.commission_pct == null ? "" : sm.commission_pct);
    $("#editSmCc").value          = (sm.cc_list || []).join("; ");
    $("#editSmBcc").value         = (sm.bcc_list || []).join("; ");
    $("#editSmActive").checked    = !!sm.active;
    const subs = sm.subscriptions || {};
    $all("#editSmSubsList .sm-sub-toggle").forEach((cb) => {
      cb.checked = !!subs[cb.getAttribute("data-report-key")];
    });
    smModal.hidden = false;
  }
  function closeEditSm() { smModal.hidden = true; _editingSm = null; }
  if ($("#editSmClose")) $("#editSmClose").addEventListener("click", closeEditSm);

  if ($("#editSmSave")) $("#editSmSave").addEventListener("click", async () => {
    if (!_editingSm) return;
    const subs = {};
    $all("#editSmSubsList .sm-sub-toggle").forEach((cb) => {
      subs[cb.getAttribute("data-report-key")] = cb.checked;
    });
    const payload = {
      key:            _editingSm.key,
      number:         $("#editSmNumber").value.trim(),
      full_name:      $("#editSmFullName").value.trim(),
      display_name:   $("#editSmDisplayName").value.trim(),
      email:          $("#editSmEmail").value.trim(),
      commission_pct: parseFloat($("#editSmCommission").value || "0") || 0,
      cc:             $("#editSmCc").value.trim(),
      bcc:            $("#editSmBcc").value.trim(),
      active:         $("#editSmActive").checked,
      subscriptions:  subs,
    };
    try {
      const r = await apiPost("/api/settings/admin/salesmen", payload);
      rebuildSalesmenList(r.salesmen || []);
      closeEditSm();
      showToast("Salesman saved.");
    } catch (e) {
      showToast("Save failed: " + e.message, "error");
    }
  });

  if ($("#editSmDelete")) $("#editSmDelete").addEventListener("click", async () => {
    if (!_editingSm) return;
    if (!confirm("Delete salesman " + _editingSm.key + "?")) return;
    try {
      const r = await apiPost("/api/settings/admin/salesmen/delete", { key: _editingSm.key });
      rebuildSalesmenList(r.salesmen || []);
      closeEditSm();
      showToast("Salesman deleted.");
    } catch (e) {
      showToast("Delete failed: " + e.message, "error");
    }
  });

  if ($("#newSmAddBtn")) $("#newSmAddBtn").addEventListener("click", async () => {
    const key = ($("#newSmKey").value || "").trim();
    const msg = $("#newSmMsg");
    if (!key) {
      if (msg) { msg.style.display = "block"; msg.style.color = "var(--error)"; msg.textContent = "Key required"; }
      return;
    }
    const payload = {
      key,
      number:         $("#newSmNumber").value.trim(),
      full_name:      $("#newSmFullName").value.trim(),
      display_name:   $("#newSmDisplayName").value.trim(),
      email:          $("#newSmEmail").value.trim(),
      commission_pct: parseFloat($("#newSmCommission").value || "0") || 0,
      active:         true,
    };
    try {
      const r = await apiPost("/api/settings/admin/salesmen", payload);
      rebuildSalesmenList(r.salesmen || []);
      ["newSmKey","newSmNumber","newSmFullName","newSmDisplayName","newSmEmail","newSmCommission"]
        .forEach((id) => { const el = $("#" + id); if (el) el.value = ""; });
      if (msg) { msg.style.display = "block"; msg.style.color = "var(--success, #2c7a3a)"; msg.textContent = "Added"; }
      showToast("Salesman added.");
    } catch (e) {
      if (msg) { msg.style.display = "block"; msg.style.color = "var(--error)"; msg.textContent = e.message; }
    }
  });

  // ---------------------------------------------------------------------
  // Customer exclusions: add-by-account-number
  // ---------------------------------------------------------------------
  const exclusionsAddBtn = $("#exclusionsAddBtn");
  const exclusionsAddInput = $("#exclusionsAddInput");
  if (exclusionsAddBtn && exclusionsAddInput) {
    function addExclusionRow() {
      const acct = (exclusionsAddInput.value || "").trim();
      if (!acct) return;
      const list = $("#customerList");
      if (!list) return;
      const existing = list.querySelector(`[data-account="${acct.replace(/"/g, '\\"')}"]`);
      if (existing) {
        existing.scrollIntoView({ behavior: "smooth", block: "center" });
        const t = existing.querySelector(".exclusion-toggle");
        if (t) { t.checked = true; excludeDirtyCheck(); }
        exclusionsAddInput.value = "";
        return;
      }
      const row = document.createElement("div");
      row.className = "settings-customer-item";
      row.setAttribute("data-account", acct);
      row.innerHTML = `
        <div class="settings-cust-info">
          <span class="settings-cust-account">${escape(acct)}</span>
          <span class="settings-cust-name" style="font-style:italic;color:var(--text-muted);">Manually added</span>
        </div>
        <label class="toggle-switch">
          <input type="checkbox" class="exclusion-toggle" checked>
          <span class="toggle-slider"></span>
        </label>`;
      list.prepend(row);
      const tog = row.querySelector(".exclusion-toggle");
      if (tog) tog.addEventListener("change", excludeDirtyCheck);
      excludeDirtyCheck();
      exclusionsAddInput.value = "";
    }
    exclusionsAddBtn.addEventListener("click", addExclusionRow);
    exclusionsAddInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); addExclusionRow(); }
    });
  }

  // ---------------------------------------------------------------------
  // Admin: report run log
  // ---------------------------------------------------------------------
  const runLogRefresh = $("#runLogRefresh");
  const runLogUser = $("#runLogUser");

  async function loadRunLog() {
    const tbody = $("#runLogTable tbody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);">Loading...</td></tr>`;
    try {
      const q = runLogUser && runLogUser.value.trim()
        ? "?user=" + encodeURIComponent(runLogUser.value.trim())
        : "";
      const json = await apiGet("/api/settings/admin/report-log" + q);
      const rows = json.rows || [];
      if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);">No runs yet.</td></tr>`;
        return;
      }
      tbody.innerHTML = "";
      rows.forEach((r) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${escape((r.started_utc || "").replace("T", " ").slice(0, 19))}</td>
          <td>${escape(r.user_email || "")}</td>
          <td>${escape(r.report_name || r.report_key || "")}</td>
          <td>${r.rows_returned == null ? "" : r.rows_returned}</td>
          <td>${r.duration_ms == null ? "" : (r.duration_ms + " ms")}</td>
          <td><span class="run-status run-${escape(r.status)}">${escape(r.status)}</span></td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="6" style="color:var(--error);">${escape(e.message)}</td></tr>`;
    }
  }

  if (runLogRefresh) runLogRefresh.addEventListener("click", loadRunLog);

  // Auto-load the log the first time the section is expanded so admins
  // don't have to remember to hit "Refresh" before any rows appear.
  const runLogHeader = document.querySelector('[data-toggle="runLogBody"]');
  if (runLogHeader) {
    runLogHeader.addEventListener("click", function onFirstOpen() {
      // The header's click handler toggles the `collapsed` class. After
      // toggling, if the body is now expanded, fire the initial load.
      setTimeout(() => {
        const body = document.getElementById("runLogBody");
        if (body && !body.classList.contains("collapsed")) {
          loadRunLog();
          runLogHeader.removeEventListener("click", onFirstOpen);
        }
      }, 0);
    });
    // Also auto-load if the section starts expanded (e.g. saved in URL state).
    const body = document.getElementById("runLogBody");
    if (body && !body.classList.contains("collapsed")) {
      loadRunLog();
    }
  }

  // Re-load when the user filter changes (debounced).
  if (runLogUser) {
    let _t = null;
    runLogUser.addEventListener("input", () => {
      clearTimeout(_t);
      _t = setTimeout(loadRunLog, 350);
    });
  }

  // (note: `escape` is declared earlier in this IIFE, near the user list helpers.)
})();

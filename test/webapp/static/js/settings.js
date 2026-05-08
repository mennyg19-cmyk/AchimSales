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
  // Admin: master schedules (inline on Settings)
  // ---------------------------------------------------------------------
  const msList = $("#masterSchedulesList");
  if (msList) {
    msList.addEventListener("click", function (ev) {
      const item = ev.target.closest(".history-item");
      if (!item) return;
      const id = item.getAttribute("data-id");

      if (ev.target.closest(".ms-run-btn")) {
        if (!confirm("Run this master schedule now?")) return;
        const btn = ev.target.closest(".ms-run-btn");
        btn.disabled = true;
        apiPost("/master-schedules/api/" + id + "/run", {})
          .then((j) => {
            showToast("Run complete. Rows: " + (j.rows_returned || 0));
          })
          .catch((e) => showToast("Run failed: " + e.message, "error"))
          .finally(() => { btn.disabled = false; });
      }

      if (ev.target.closest(".ms-delete-btn")) {
        if (!confirm("Delete this master schedule?")) return;
        fetch(PREFIX + "/master-schedules/api/" + id, { method: "DELETE" })
          .then((r) => r.json().then((j) => ({ r, j })).catch(() => ({ r, j: {} })))
          .then((p) => {
            if (p.r.ok && p.j.ok) {
              item.remove();
              showToast("Master schedule deleted.");
            } else {
              showToast("Delete failed: " + (p.j.error || ("HTTP " + p.r.status)), "error");
            }
          })
          .catch((e) => showToast("Delete failed: " + e.message, "error"));
      }

      if (ev.target.closest(".ms-edit-btn")) {
        try {
          const sched = JSON.parse(item.getAttribute("data-schedule") || "{}");
          openMasterScheduleModal(sched);
        } catch (e) {
          showToast("Could not read schedule row: " + e.message, "error");
        }
      }
    });
  }

  const msOverlay = $("#msModalOverlay");
  const msForm = $("#msForm");
  let msEditingId = null;

  function msField(name) {
    return msForm ? msForm.querySelector(`[name="${name}"]`) : null;
  }

  function updateMasterScheduleCadenceUI() {
    if (!msForm) return;
    const cadence = (msField("cadence") || {}).value || "daily";
    const weekdays = $("#msWeekdays");
    const monthdays = $("#msMonthdays");
    if (weekdays) weekdays.style.display = (cadence === "weekly") ? "" : "none";
    if (monthdays) monthdays.style.display = (cadence === "monthly") ? "" : "none";
  }

  function todayIso() {
    const d = new Date();
    d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    return d.toISOString().slice(0, 10);
  }

  function openMasterScheduleModal(sched) {
    if (!msOverlay || !msForm) return;
    msEditingId = sched ? sched.id : null;
    msForm.reset();
    const errBox = $("#msFormError");
    if (errBox) errBox.style.display = "none";
    const title = $("#msModalTitle");
    if (title) title.textContent = sched ? ("Edit: " + sched.name) : "New master schedule";

    if (sched) {
      msField("name").value = sched.name || "";
      msField("report_key").value = sched.report_key || "";
      msField("cadence").value = sched.cadence || "daily";
      msField("time_hhmm").value = sched.time_hhmm || "07:00";
      msField("start_date").value = sched.start_date || "";
      msField("end_date").value = sched.end_date || "";
      msField("recipients").value = sched.recipients || "";
      msField("sharepoint_path").value = sched.sharepoint_path || "";
      (sched.weekdays || "").split(",").filter(Boolean).forEach((w) => {
        const cb = msForm.querySelector(`[name="weekday"][value="${w}"]`);
        if (cb) cb.checked = true;
      });
      (sched.monthdays || "").split(",").filter(Boolean).forEach((d) => {
        const cb = msForm.querySelector(`[name="monthday"][value="${d}"]`);
        if (cb) cb.checked = true;
      });
    } else {
      msField("time_hhmm").value = "07:00";
      msField("start_date").value = todayIso();
    }

    updateMasterScheduleCadenceUI();
    msOverlay.style.display = "flex";
  }

  function closeMasterScheduleModal() {
    if (msOverlay) msOverlay.style.display = "none";
    msEditingId = null;
  }

  $("#msCreateBtn")?.addEventListener("click", () => openMasterScheduleModal(null));
  $("#msCancelBtn")?.addEventListener("click", closeMasterScheduleModal);
  $("#msModalClose")?.addEventListener("click", closeMasterScheduleModal);
  msField("cadence")?.addEventListener("change", updateMasterScheduleCadenceUI);

  $("#msPickSpBtn")?.addEventListener("click", async () => {
    if (!window.openSharePointPicker) {
      showToast("SharePoint picker not loaded.", "error");
      return;
    }
    const p = await window.openSharePointPicker({
      initialPath: (msField("sharepoint_path") || {}).value || "",
    });
    if (p !== null && msField("sharepoint_path")) {
      msField("sharepoint_path").value = p;
    }
  });

  $("#msClearSpBtn")?.addEventListener("click", () => {
    if (msField("sharepoint_path")) msField("sharepoint_path").value = "";
  });

  if (msForm) {
    msForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const errBox = $("#msFormError");
      if (errBox) errBox.style.display = "none";

      const weekdays = $all('[name="weekday"]:checked', msForm)
        .map((c) => c.value).join(",");
      const monthdays = $all('[name="monthday"]:checked', msForm)
        .map((c) => c.value).join(",");
      const body = {
        name:            msField("name").value.trim(),
        report_key:      msField("report_key").value,
        cadence:         msField("cadence").value,
        weekdays:        weekdays,
        monthdays:       monthdays,
        time_hhmm:       msField("time_hhmm").value,
        start_date:      msField("start_date").value,
        end_date:        msField("end_date").value || null,
        recipients:      msField("recipients").value.trim(),
        sharepoint_path: msField("sharepoint_path").value.trim(),
        params:          {},
        layouts:         {},
      };
      const path = msEditingId
        ? "/master-schedules/api/" + msEditingId
        : "/master-schedules/api";
      try {
        await apiPost(path, body);
        closeMasterScheduleModal();
        showToast("Master schedule saved.");
        window.location.reload();
      } catch (e) {
        if (errBox) {
          errBox.textContent = e.message;
          errBox.style.display = "block";
        } else {
          showToast("Save failed: " + e.message, "error");
        }
      }
    });
  }

  // ---------------------------------------------------------------------
  // Admin: users + permissions (unified -- salesmen are users too)
  // ---------------------------------------------------------------------

  function escape(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // Show / hide form sections based on the selected role.
  // ``prefix`` is "new" (the add-user form) or "edit" (the modal).
  function syncRoleVisibility(prefix) {
    const roleSel = $("#" + prefix + "UserRole");
    if (!roleSel) return;
    const role = roleSel.value;

    if (prefix === "new") {
      // The add form has two mutually-exclusive field sets:
      //   - newSalesmanFields  (salesman: id #, name, email, etc.)
      //   - newUserFields      (admin/dev/manager: just email + name)
      const smFields = $("#newSalesmanFields");
      const baseFields = $("#newUserFields");
      if (smFields) smFields.style.display = (role === "salesman") ? "" : "none";
      if (baseFields) baseFields.style.display = (role === "salesman") ? "none" : "";
    } else {
      // Edit modal: salesman dropdown + identity fields are visible only
      // for salesman users, assigned-salesmen list only for managers,
      // external-login only for salesmen.
      const smWrap   = $("#editSalesmanWrap");
      const smIdent  = $("#editSalesmanFields");
      const assigned = $("#editAssignedWrap");
      const extRow   = $("#editUserExternalRow");
      if (smWrap)   smWrap.style.display   = (role === "salesman") ? "" : "none";
      if (smIdent)  smIdent.style.display  = (role === "salesman") ? "" : "none";
      if (assigned) assigned.style.display = (role === "manager")  ? "" : "none";
      if (extRow)   extRow.style.display   = (role === "salesman") ? "" : "none";
    }
  }

  const newRoleSel = $("#newUserRole");
  if (newRoleSel) {
    newRoleSel.addEventListener("change", () => syncRoleVisibility("new"));
    syncRoleVisibility("new");
  }

  // ---- Add new user / salesman ----
  // Admins see one combined form. Picking "Salesman" shows the salesman
  // identity fields (id #, full name, etc.) -- saving those creates
  // BOTH the app_salesmen row and the linked app_users row in one shot.
  // Picking another role shows only email + display name.
  const newUserAddBtn = $("#newUserAddBtn");
  if (newUserAddBtn) {
    newUserAddBtn.addEventListener("click", async () => {
      const role = $("#newUserRole").value;
      const msg  = $("#newUserMsg");
      function clearMsg() {
        if (msg) { msg.style.color = ""; msg.textContent = ""; }
      }
      function setError(text) {
        if (msg) { msg.style.color = "var(--error)"; msg.textContent = text; }
      }
      function setSuccess(text) {
        if (msg) { msg.style.color = "var(--success, #2c7a3a)"; msg.textContent = text; }
      }
      clearMsg();

      try {
        if (role === "salesman") {
          // Salesman flow -- creates the salesman + the linked user.
          const email     = ($("#newSmEmail").value || "").trim().toLowerCase();
          const fullName  = ($("#newSmFullName").value || "").trim();
          if (!email)    { setError("Email is required"); return; }
          if (!fullName) { setError("Full name is required"); return; }
          let key = ($("#newSmKey").value || "").trim().toLowerCase()
                       .replace(/[^a-z0-9]+/g, "");
          if (!key) {
            // Auto-derive from full name -- mirror the live ``_norm_key``.
            key = fullName.toLowerCase().replace(/[^a-z0-9]+/g, "");
          }
          const payload = {
            key,
            number:         ($("#newSmNumber").value || "").trim(),
            full_name:      fullName,
            display_name:   ($("#newSmDisplayName").value || "").trim() || fullName,
            email,
            commission_pct: parseFloat($("#newSmCommission").value || "0") || 0,
            active:         true,
          };
          await apiPost("/api/settings/admin/salesmen", payload);
          // The salesman save already created the user. If the admin
          // ticked the "external" box, push that on top.
          if ($("#newSmExternal") && $("#newSmExternal").checked) {
            await apiPost("/api/settings/admin/users",
                          { email, is_external: true });
          }
          // Reload the merged grid.
          const r = await apiGet("/api/settings/admin/users");
          rebuildUserList(r.perm_grid || []);
          updateSalesmanDropdowns(r.salesmen || []);
          ["newSmKey","newSmNumber","newSmFullName","newSmDisplayName",
           "newSmEmail","newSmCommission"]
            .forEach((id) => { const el = $("#" + id); if (el) el.value = ""; });
          setSuccess("Added salesman " + email);
          showToast("Salesman added.");
        } else {
          // Bare user flow (admin/developer/manager).
          const email = ($("#newUserEmail").value || "").trim().toLowerCase();
          const dn    = ($("#newUserDisplayName").value || "").trim() || null;
          if (!email) { setError("Email is required"); return; }
          const r = await apiPost("/api/settings/admin/users/add", {
            email, role, display_name: dn, is_external: false,
          });
          rebuildUserList(r.perm_grid || []);
          $("#newUserEmail").value = "";
          $("#newUserDisplayName").value = "";
          setSuccess("Added " + email);
          showToast("User added.");
        }
      } catch (e) {
        setError(e.message || "Save failed");
      }
    });
  }

  // Refresh the dropdowns sourced from app_salesmen anywhere on the page.
  function updateSalesmanDropdowns(salesmen) {
    const sels = [
      $("#editUserSalesmanKey"),
    ];
    sels.forEach((sel) => {
      if (!sel) return;
      const cur = sel.value;
      const head = '<option value="">— Select —</option>';
      const opts = salesmen.map((sm) => {
        const label = (sm.full_name || sm.key) +
                      (sm.number ? " (#" + sm.number + ")" : "");
        return `<option value="${escape(sm.key)}">${escape(label)}</option>`;
      }).join("");
      sel.innerHTML = head + opts;
      if (cur && salesmen.some((sm) => sm.key === cur)) sel.value = cur;
    });
    // Manager assigned-salesmen list lives in the modal; rebuild from scratch.
    const assigned = $("#editAssignedList");
    if (assigned) {
      assigned.innerHTML = salesmen.map((sm) => `
        <label class="settings-customer-item" style="min-height:34px;">
          <span style="font-size:13px;">${escape(sm.full_name || sm.key)}${sm.number ? " #" + escape(sm.number) : ""}</span>
          <input type="checkbox" class="assigned-sm-toggle" data-sm-key="${escape(sm.key)}">
        </label>`).join("");
    }
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

    // Salesman identity fields. The perm-grid payload includes the
    // joined salesman columns so we can render them inline.
    $("#editSmNumber").value      = u.sm_number || "";
    $("#editSmFullName").value    = u.sm_name || u.display_name || "";
    $("#editSmDisplayName").value = u.display_name || "";
    $("#editSmCommission").value  = (u.commission_pct == null ? "" : u.commission_pct);

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
    try {
      // ---- Order matters when the user is a salesman ----
      // We persist the salesman row first (it owns the canonical
      // email + display_name) so the user-update step doesn't fight
      // it. The salesman upsert auto-renames the linked user, so the
      // subsequent users PATCH only carries permission-related diffs.
      let identityEmail = email; // email *after* the salesman rename, if any
      if (role === "salesman" && sk) {
        const smPayload = {
          key:            sk,
          number:         ($("#editSmNumber").value || "").trim(),
          full_name:      ($("#editSmFullName").value || "").trim() || dn || newEmail || email,
          display_name:   ($("#editSmDisplayName").value || "").trim() ||
                          ($("#editSmFullName").value || "").trim() ||
                          dn || "",
          email:          newEmail || email,
          commission_pct: parseFloat($("#editSmCommission").value || "0") || 0,
          active:         $("#editUserActive").checked,
        };
        await apiPost("/api/settings/admin/salesmen", smPayload);
        identityEmail = smPayload.email;
      }

      const patch = {
        email: identityEmail,
        role,
        salesman_key: sk,
        display_name: dn,
        active:                    $("#editUserActive").checked,
        is_external:               $("#editUserIsExternal").checked,
        dashboard_enabled:         $("#editUserDashboard").checked,
        sharepoint_access_enabled: $("#editUserSharepoint").checked,
      };
      // If the admin renamed the email AND the user is NOT a salesman
      // (the salesman upsert above already cascaded), apply the rename
      // here.
      if (role !== "salesman" && newEmail && newEmail !== email) {
        patch.new_email = newEmail;
      }
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
      updateSalesmanDropdowns(finalGrid.salesmen || []);
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
  // (Salesman map was merged into Users & Permissions above.)
  // ---------------------------------------------------------------------

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

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
  // Admin: users
  // ---------------------------------------------------------------------
  async function updateUser(email, patch) {
    try {
      await apiPost("/api/settings/admin/users", Object.assign({ email }, patch));
      showToast("User updated.");
    } catch (e) {
      showToast("Save failed: " + e.message, "error");
      throw e;
    }
  }

  $all("#usersTable tr[data-email]").forEach((row) => {
    const email = row.getAttribute("data-email");
    const admin = $(".perm-admin", row);
    const sp    = $(".perm-sharepoint", row);
    const del   = $(".perm-delete", row);

    if (admin) admin.addEventListener("change", () => {
      updateUser(email, { is_admin: admin.checked })
        .catch(() => { admin.checked = !admin.checked; });
    });
    if (sp) sp.addEventListener("change", () => {
      updateUser(email, { sharepoint_access_enabled: sp.checked })
        .catch(() => { sp.checked = !sp.checked; });
    });
    if (del) del.addEventListener("click", async () => {
      if (!confirm("Delete " + email + "?\nThey will need to sign in again to re-create the account.")) return;
      try {
        await apiPost("/api/settings/admin/users/delete", { email });
        row.remove();
        showToast("User deleted.");
      } catch (e) {
        showToast("Delete failed: " + e.message, "error");
      }
    });
  });

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

  function escape(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
})();

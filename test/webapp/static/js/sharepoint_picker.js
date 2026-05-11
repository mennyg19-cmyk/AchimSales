/* SharePoint folder picker modal.
 *
 * Usage:
 *   const path = await window.openSharePointPicker({ initialPath: "" });
 *   // path is a string (relative to Direct Reports) or null if cancelled.
 *
 * The picker is self-contained: it injects its own DOM on first use and
 * reuses the same overlay on every call. It talks to the v2 SharePoint
 * browser endpoints (/api/sharepoint/...).
 */

(function (global) {
  "use strict";

  function urlPrefix() {
    // window.V2_URL_PREFIX is set in base.html; fall back to "" for root.
    return (global.V2_URL_PREFIX || "");
  }

  let root = null;
  let resolver = null;
  let currentPath = "";
  let rootLabel = "Direct Reports";

  function ensureRoot() {
    if (root) return root;

    root = document.createElement("div");
    root.className = "sp-picker-overlay";
    root.style.display = "none";
    root.innerHTML = `
      <div class="sp-picker-modal" role="dialog" aria-modal="true" aria-label="Choose SharePoint folder">
        <div class="sp-picker-header">
          <h3>Choose SharePoint folder</h3>
          <button type="button" class="sp-picker-close" aria-label="Close">&times;</button>
        </div>
        <div class="sp-picker-breadcrumb" id="spPickerCrumb"></div>
        <div class="sp-picker-body" id="spPickerBody"></div>
        <div class="sp-picker-footer">
          <div class="sp-picker-current">
            <span class="sp-picker-current-label">Current folder:</span>
            <span class="sp-picker-current-path" id="spPickerCurrentPath"></span>
          </div>
          <div class="sp-picker-actions">
            <button type="button" class="btn btn-outline sp-picker-cancel">Cancel</button>
            <button type="button" class="btn btn-primary sp-picker-select">Select this folder</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(root);

    root.querySelector(".sp-picker-close").addEventListener("click", cancel);
    root.querySelector(".sp-picker-cancel").addEventListener("click", cancel);
    root.querySelector(".sp-picker-select").addEventListener("click", confirm);
    root.addEventListener("click", function (ev) {
      if (ev.target === root) cancel();
    });

    return root;
  }

  function showError(msg) {
    const body = root.querySelector("#spPickerBody");
    body.innerHTML = `<div class="sp-picker-error">${escape(msg)}</div>`;
  }

  function escape(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function renderBreadcrumb() {
    const crumb = root.querySelector("#spPickerCrumb");
    crumb.innerHTML = "";

    const rootBtn = document.createElement("button");
    rootBtn.type = "button";
    rootBtn.className = "sp-crumb-link";
    rootBtn.textContent = rootLabel;
    rootBtn.addEventListener("click", () => loadPath(""));
    crumb.appendChild(rootBtn);

    if (!currentPath) return;
    const parts = currentPath.split("/");
    let accum = "";
    parts.forEach((p, i) => {
      if (!p) return;
      accum = accum ? accum + "/" + p : p;
      const sep = document.createElement("span");
      sep.className = "sp-crumb-sep";
      sep.textContent = " / ";
      crumb.appendChild(sep);

      if (i === parts.length - 1) {
        const cur = document.createElement("span");
        cur.className = "sp-crumb-current";
        cur.textContent = p;
        crumb.appendChild(cur);
      } else {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "sp-crumb-link";
        btn.textContent = p;
        const target = accum;
        btn.addEventListener("click", () => loadPath(target));
        crumb.appendChild(btn);
      }
    });
  }

  function renderCurrent() {
    const el = root.querySelector("#spPickerCurrentPath");
    el.textContent = currentPath
      ? rootLabel + " / " + currentPath.replace(/\//g, " / ")
      : rootLabel;
  }

  function renderFolders(folders) {
    const body = root.querySelector("#spPickerBody");
    if (!folders.length) {
      body.innerHTML = `<div class="sp-picker-empty">No subfolders here. You can still select this folder.</div>`;
      return;
    }
    body.innerHTML = "";
    const ul = document.createElement("ul");
    ul.className = "sp-picker-list";
    folders.forEach((f) => {
      const li = document.createElement("li");
      li.className = "sp-picker-item";
      li.innerHTML = `
        <span class="sp-picker-icon" aria-hidden="true"><i data-feather="folder"></i></span>
        <span class="sp-picker-name">${escape(f.name)}</span>
        <span class="sp-picker-chevron" aria-hidden="true"><i data-feather="chevron-right"></i></span>
      `;
      li.addEventListener("click", () => loadPath(f.path));
      ul.appendChild(li);
    });
    body.appendChild(ul);
    if (global.feather && typeof global.feather.replace === "function") {
      global.feather.replace();
    }
  }

  async function loadPath(path) {
    currentPath = (path || "").replace(/^\/+|\/+$/g, "");
    renderBreadcrumb();
    renderCurrent();
    const body = root.querySelector("#spPickerBody");
    body.innerHTML = `<div class="sp-picker-loading">Loading...</div>`;
    const slowTimer = setTimeout(() => {
      body.innerHTML = `<div class="sp-picker-loading">Still loading SharePoint folders...</div>`;
    }, 5000);
    try {
      const r = await fetch(
        urlPrefix() + "/api/sharepoint/folders?path=" + encodeURIComponent(currentPath),
        { headers: { "Accept": "application/json" } }
      );
      const json = await r.json().catch(() => ({}));
      if (!r.ok) {
        showError(json.error || ("HTTP " + r.status));
        return;
      }
      renderFolders(json.folders || []);
    } catch (e) {
      showError("Could not load SharePoint folders: " + e.message);
    } finally {
      clearTimeout(slowTimer);
    }
  }

  function cancel() {
    close(null);
  }

  function confirm() {
    close(currentPath);
  }

  function close(value) {
    root.style.display = "none";
    if (resolver) {
      const r = resolver; resolver = null;
      r(value);
    }
  }

  async function open(options) {
    options = options || {};
    ensureRoot();

    // Refresh root label in case the server-configured name differs.
    try {
      const r = await fetch(urlPrefix() + "/api/sharepoint/configured");
      const j = await r.json().catch(() => ({}));
      if (j && j.root_path) {
        // Show the last path segment as the breadcrumb root label.
        const parts = String(j.root_path).split("/").filter(Boolean);
        rootLabel = parts.length ? parts[parts.length - 1] : "Direct Reports";
      }
    } catch { /* fall through */ }

    root.style.display = "flex";
    return new Promise((resolve) => {
      resolver = resolve;
      const initial = (options.initialPath || "").replace(/^\/+|\/+$/g, "");
      loadPath(initial);
    });
  }

  global.openSharePointPicker = open;
})(window);

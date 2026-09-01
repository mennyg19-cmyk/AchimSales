// SharePoint folder picker for the master-schedules page.

import { openDialog, type DialogClose } from "./dialog";
import { esc } from "./http";
import { stripReportsHome } from "./filename_preview";

// --------------------------------------------------------------------------
// SharePoint folder picker
// --------------------------------------------------------------------------

let spResolver: ((path: string | null) => void) | null = null;
let spCurrentPath = "";
let spRootLabel = "Direct Reports";
let closeSpDlg: DialogClose | null = null;

function spOverlay(): HTMLElement | null {
  return document.getElementById("spPickerOverlay");
}

function spRenderBreadcrumb(): void {
  const crumb = document.getElementById("spPickerCrumb");
  if (!crumb) return;
  crumb.innerHTML = "";

  const rootBtn = document.createElement("button");
  rootBtn.type = "button";
  rootBtn.className = "sp-crumb-link";
  rootBtn.textContent = spRootLabel;
  rootBtn.addEventListener("click", () => spLoadPath(""));
  crumb.appendChild(rootBtn);

  if (!spCurrentPath) return;
  const parts = spCurrentPath.split("/");
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
      btn.addEventListener("click", () => spLoadPath(target));
      crumb.appendChild(btn);
    }
  });
}

function spRenderCurrent(): void {
  const el = document.getElementById("spPickerCurrentPath");
  if (!el) return;
  el.textContent = spCurrentPath
    ? spRootLabel + " / " + spCurrentPath.replace(/\//g, " / ")
    : spRootLabel;
}

function spRenderFolders(folders: { name: string; path: string }[]): void {
  const body = document.getElementById("spPickerBody");
  if (!body) return;
  if (!folders.length) {
    body.innerHTML = `<div class="sp-picker-empty">No subfolders. You can still select this folder.</div>`;
    return;
  }
  body.innerHTML = "";
  const ul = document.createElement("ul");
  ul.className = "sp-picker-list";
  folders.forEach((f) => {
    const li = document.createElement("li");
    li.className = "sp-picker-item";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "sp-picker-item-btn";
    btn.innerHTML = `<span class="sp-picker-icon"><i data-feather="folder"></i></span>`
      + `<span class="sp-picker-name">${esc(f.name)}</span>`
      + `<span class="sp-picker-chevron"><i data-feather="chevron-right"></i></span>`;
    btn.addEventListener("click", () => spLoadPath(f.path));
    li.appendChild(btn);
    ul.appendChild(li);
  });
  body.appendChild(ul);
  if ((window as any).feather?.replace) (window as any).feather.replace();
}

async function spLoadPath(path: string): Promise<void> {
  spCurrentPath = (path || "").replace(/^\/+|\/+$/g, "");
  spRenderBreadcrumb();
  spRenderCurrent();
  const body = document.getElementById("spPickerBody");
  if (!body) return;
  body.innerHTML = `<div class="sp-picker-loading">Loading…</div>`;
  const wiz = document.getElementById("msWizard");
  const url = wiz?.getAttribute("data-sp-folders-url") || "/api/sharepoint/folders";
  try {
    const r = await fetch(url + "?path=" + encodeURIComponent(spCurrentPath), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const json = await r.json().catch(() => ({}));
    if (!r.ok) {
      const msg = json.error || (r.status === 401
        ? "Sign in expired — refresh the page."
        : "HTTP " + r.status);
      body.innerHTML = `<div class="sp-picker-error">${esc(msg)}</div>`;
      return;
    }
    if (json.error) {
      body.innerHTML = `<div class="sp-picker-error">${esc(json.error)}</div>`;
      return;
    }
    spRenderFolders(json.folders || []);
  } catch (e: any) {
    body.innerHTML = `<div class="sp-picker-error">Could not load folders: ${esc(e.message)}</div>`;
  }
}

function spClose(value: string | null): void {
  const r = spResolver;
  spResolver = null;
  closeSpDlg?.();
  closeSpDlg = null;
  r?.(value);
}

async function openSharePointPicker(initialPath: string): Promise<string | null> {
  const ov = spOverlay();
  if (!ov) return null;

  const wiz = document.getElementById("msWizard");
  const statusUrl = wiz?.getAttribute("data-sp-status-url") || "/api/sharepoint/status";
  try {
    const r = await fetch(statusUrl, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const j = await r.json().catch(() => ({}));
    const root = j?.root_path || j?.root;
    if (root) {
      const parts = String(root).split("/").filter(Boolean);
      spRootLabel = parts.length ? parts[parts.length - 1] : "Direct Reports";
    }
  } catch { /* use default */ }

  return new Promise((resolve) => {
    spResolver = resolve;
    closeSpDlg?.();
    closeSpDlg = openDialog(ov, {
      onClose: () => {
        closeSpDlg = null;
        if (spResolver) {
          const r = spResolver;
          spResolver = null;
          r(null);
        }
      },
    });
    spLoadPath(initialPath);
  });
}

export function bindSharePointPicker(): void {
  const browseBtn = document.getElementById("spBrowseBtn");
  const clearBtn = document.getElementById("spClearBtn");
  const input = document.getElementById("spPathInput") as HTMLInputElement | null;
  if (!browseBtn || !input) return;

  browseBtn.addEventListener("click", async () => {
    const raw = input.value.trim();
    const brace = raw.indexOf("{");
    const suffix = brace >= 0 ? raw.slice(brace).replace(/^\/+/, "") : "";
    const start = stripReportsHome((brace >= 0 ? raw.slice(0, brace) : raw).replace(/\/+$/, ""));
    const result = await openSharePointPicker(start);
    if (result !== null) {
      const folder = stripReportsHome(result);
      input.value = suffix ? (folder ? folder + "/" + suffix : suffix) : folder;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });

  clearBtn?.addEventListener("click", () => {
    input.value = "";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });

  const ov = spOverlay();
  if (!ov) return;
  ov.querySelector(".sp-picker-close")?.addEventListener("click", () => spClose(null));
  ov.querySelector(".sp-picker-cancel")?.addEventListener("click", () => spClose(null));
  ov.querySelector(".sp-picker-select")?.addEventListener("click", () => spClose(spCurrentPath));
  ov.addEventListener("click", (e) => { if (e.target === ov) spClose(null); });
}

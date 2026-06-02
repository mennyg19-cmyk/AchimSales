// Schedules management pages (personal + master). Generic, data-driven actions
// plus edit mode and a SharePoint folder picker for master schedules.

function csrf(): string {
  const el = document.querySelector<HTMLElement>("[data-csrf]");
  return el?.getAttribute("data-csrf") || "";
}

function headers(): Record<string, string> {
  return { "Content-Type": "application/json", "X-CSRF-Token": csrf() };
}

async function act(url: string, method: string, body?: unknown): Promise<boolean> {
  try {
    const res = await fetch(url, {
      method, headers: headers(),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return res.ok;
  } catch {
    return false;
  }
}

// --------------------------------------------------------------------------
// Row actions (toggle, run, delete)
// --------------------------------------------------------------------------

function bindRowActions(): void {
  document.querySelectorAll<HTMLButtonElement>(".js-toggle").forEach((b) => {
    b.addEventListener("click", async () => {
      const active = b.getAttribute("data-active") === "true";
      if (await act(b.dataset.url!, "POST", { active })) location.reload();
    });
  });
  document.querySelectorAll<HTMLButtonElement>(".js-run").forEach((b) => {
    b.addEventListener("click", async () => {
      b.disabled = true;
      b.textContent = "Running…";
      const ok = await act(b.dataset.url!, "POST", {});
      b.textContent = ok ? "Queued" : "Failed";
      setTimeout(() => { b.disabled = false; b.textContent = "Run now"; }, 2500);
    });
  });
  document.querySelectorAll<HTMLButtonElement>(".js-delete").forEach((b) => {
    b.addEventListener("click", async () => {
      if (!window.confirm(b.getAttribute("data-confirm") || "Delete?")) return;
      if (await act(b.dataset.url!, "DELETE")) location.reload();
    });
  });
}

// --------------------------------------------------------------------------
// Master form (create + edit)
// --------------------------------------------------------------------------

function masterMsg(text: string, isError: boolean): void {
  const el = document.getElementById("masterMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
  el.className = "ms-msg" + (isError ? " ms-msg-error" : "");
}

function syncMasterCadence(): void {
  const freq = (document.getElementById("mFreq") as HTMLSelectElement | null)?.value || "daily";
  const wd = document.getElementById("mWeekdays");
  const md = document.getElementById("mMonthday");
  if (wd) wd.hidden = freq !== "weekly";
  if (md) md.hidden = freq !== "monthly";
}

function masterCadence(form: HTMLFormElement): { ok: boolean; cadence?: any; error?: string } {
  const freq = (form.elements.namedItem("freq") as HTMLSelectElement).value;
  const time = (form.elements.namedItem("time") as HTMLInputElement).value || "08:00";
  const cadence: any = { freq, time };
  if (freq === "weekly") {
    const days = [...form.querySelectorAll<HTMLInputElement>('input[name="weekday"]:checked')]
      .map((c) => Number(c.value));
    if (!days.length) return { ok: false, error: "Pick at least one day." };
    cadence.weekdays = days;
  } else if (freq === "monthly") {
    cadence.monthday = Number((form.elements.namedItem("monthday") as HTMLSelectElement).value) || 1;
  }
  return { ok: true, cadence };
}

function enterEditMode(row: HTMLTableRowElement): void {
  const form = document.getElementById("masterCreateForm") as HTMLFormElement | null;
  if (!form) return;

  const id = row.dataset.id!;
  const cad = JSON.parse(row.dataset.cadence || "{}");

  (document.getElementById("editingId") as HTMLInputElement).value = id;
  (form.elements.namedItem("name") as HTMLInputElement).value = row.dataset.name || "";
  (form.elements.namedItem("report_key") as HTMLSelectElement).value = row.dataset.reportKey || "";
  (form.elements.namedItem("freq") as HTMLSelectElement).value = cad.freq || "daily";
  (form.elements.namedItem("time") as HTMLInputElement).value = cad.time || "08:00";
  (form.elements.namedItem("recipients") as HTMLInputElement).value = row.dataset.recipients || "";
  (document.getElementById("spPathInput") as HTMLInputElement).value = row.dataset.sharepointPath || "";

  if (cad.freq === "weekly" && cad.weekdays) {
    form.querySelectorAll<HTMLInputElement>('input[name="weekday"]').forEach((c) => {
      c.checked = cad.weekdays.includes(Number(c.value));
    });
  } else {
    form.querySelectorAll<HTMLInputElement>('input[name="weekday"]').forEach((c) => { c.checked = false; });
  }
  if (cad.freq === "monthly") {
    (form.elements.namedItem("monthday") as HTMLSelectElement).value = String(cad.monthday ?? 1);
  }

  syncMasterCadence();
  document.getElementById("formTitle")!.textContent = "Edit schedule";
  document.getElementById("formSubmitBtn")!.textContent = "Save";
  document.getElementById("formCancelBtn")!.hidden = false;
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

function exitEditMode(): void {
  const form = document.getElementById("masterCreateForm") as HTMLFormElement | null;
  if (!form) return;
  form.reset();
  (document.getElementById("editingId") as HTMLInputElement).value = "";
  (document.getElementById("spPathInput") as HTMLInputElement).value = "";
  document.getElementById("formTitle")!.textContent = "New master schedule";
  document.getElementById("formSubmitBtn")!.textContent = "Create";
  document.getElementById("formCancelBtn")!.hidden = true;
  syncMasterCadence();
  masterMsg("", false);
}

function bindMasterForm(): void {
  const form = document.getElementById("masterCreateForm") as HTMLFormElement | null;
  if (!form) return;
  document.getElementById("mFreq")?.addEventListener("change", syncMasterCadence);
  syncMasterCadence();

  document.getElementById("formCancelBtn")?.addEventListener("click", exitEditMode);

  document.querySelectorAll<HTMLButtonElement>(".js-edit").forEach((b) => {
    b.addEventListener("click", () => {
      const row = b.closest("tr") as HTMLTableRowElement;
      if (row) enterEditMode(row);
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = (form.elements.namedItem("name") as HTMLInputElement).value.trim();
    if (!name) { masterMsg("Name is required.", true); return; }
    const cad = masterCadence(form);
    if (!cad.ok) { masterMsg(cad.error!, true); return; }
    const body = {
      name, report_key: (form.elements.namedItem("report_key") as HTMLSelectElement).value,
      cadence: cad.cadence,
      recipients: (form.elements.namedItem("recipients") as HTMLInputElement).value.trim(),
      sharepoint_path: (document.getElementById("spPathInput") as HTMLInputElement).value.trim(),
      params: {}, layout: {},
    };

    const editId = (document.getElementById("editingId") as HTMLInputElement).value;
    masterMsg("Saving…", false);

    if (editId) {
      const tpl = form.getAttribute("data-update-url-tpl")!;
      const url = tpl.replace("/0", "/" + editId);
      const res = await fetch(url, { method: "PUT", headers: headers(), body: JSON.stringify(body) });
      if (res.ok) location.reload();
      else {
        const err = await res.json().catch(() => ({}));
        masterMsg((err as any).error || "Could not save.", true);
      }
    } else {
      const res = await fetch(form.getAttribute("data-create-url")!, {
        method: "POST", headers: headers(), body: JSON.stringify(body),
      });
      if (res.status === 201) location.reload();
      else {
        const err = await res.json().catch(() => ({}));
        masterMsg((err as any).error || "Could not create.", true);
      }
    }
  });
}

// --------------------------------------------------------------------------
// SharePoint folder picker
// --------------------------------------------------------------------------

let spResolver: ((path: string | null) => void) | null = null;
let spCurrentPath = "";
let spRootLabel = "Direct Reports";

function esc(s: string): string {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

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
    li.innerHTML = `<span class="sp-picker-icon"><i data-feather="folder"></i></span>`
      + `<span class="sp-picker-name">${esc(f.name)}</span>`
      + `<span class="sp-picker-chevron"><i data-feather="chevron-right"></i></span>`;
    li.addEventListener("click", () => spLoadPath(f.path));
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
  const form = document.getElementById("masterCreateForm");
  const url = form?.getAttribute("data-sp-folders-url") || "/api/sharepoint/folders";
  try {
    const r = await fetch(url + "?path=" + encodeURIComponent(spCurrentPath),
      { headers: { Accept: "application/json" } });
    const json = await r.json().catch(() => ({}));
    if (!r.ok) {
      body.innerHTML = `<div class="sp-picker-error">${esc(json.error || "HTTP " + r.status)}</div>`;
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
  const ov = spOverlay();
  if (ov) ov.style.display = "none";
  if (spResolver) { const r = spResolver; spResolver = null; r(value); }
}

async function openSharePointPicker(initialPath: string): Promise<string | null> {
  const ov = spOverlay();
  if (!ov) return null;

  const form = document.getElementById("masterCreateForm");
  const statusUrl = form?.getAttribute("data-sp-status-url") || "/api/sharepoint/status";
  try {
    const r = await fetch(statusUrl);
    const j = await r.json().catch(() => ({}));
    if (j?.root_path) {
      const parts = String(j.root_path).split("/").filter(Boolean);
      spRootLabel = parts.length ? parts[parts.length - 1] : "Direct Reports";
    }
  } catch { /* use default */ }

  ov.style.display = "flex";
  return new Promise((resolve) => {
    spResolver = resolve;
    spLoadPath(initialPath);
  });
}

function bindSharePointPicker(): void {
  const browseBtn = document.getElementById("spBrowseBtn");
  const clearBtn = document.getElementById("spClearBtn");
  const input = document.getElementById("spPathInput") as HTMLInputElement | null;
  if (!browseBtn || !input) return;

  browseBtn.addEventListener("click", async () => {
    const result = await openSharePointPicker(input.value);
    if (result !== null) input.value = result;
  });

  clearBtn?.addEventListener("click", () => { input.value = ""; });

  const ov = spOverlay();
  if (!ov) return;
  ov.querySelector(".sp-picker-close")?.addEventListener("click", () => spClose(null));
  ov.querySelector(".sp-picker-cancel")?.addEventListener("click", () => spClose(null));
  ov.querySelector(".sp-picker-select")?.addEventListener("click", () => spClose(spCurrentPath));
  ov.addEventListener("click", (e) => { if (e.target === ov) spClose(null); });
}

// --------------------------------------------------------------------------
// Init
// --------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  bindRowActions();
  bindMasterForm();
  bindSharePointPicker();
});

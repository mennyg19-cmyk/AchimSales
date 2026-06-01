// Schedules management pages (personal + master). Generic, data-driven actions:
// each action button carries its own endpoint URL, so this module works for both
// page types without knowing which is which.

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

function masterMsg(text: string, isError: boolean): void {
  const el = document.getElementById("masterMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
  el.className = "modal-msg" + (isError ? " modal-msg-error" : "");
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
    cadence.monthday = Number((form.elements.namedItem("monthday") as HTMLInputElement).value) || 1;
  }
  return { ok: true, cadence };
}

function bindMasterForm(): void {
  const form = document.getElementById("masterCreateForm") as HTMLFormElement | null;
  if (!form) return;
  document.getElementById("mFreq")?.addEventListener("change", syncMasterCadence);
  syncMasterCadence();
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
      sharepoint_path: (form.elements.namedItem("sharepoint_path") as HTMLInputElement).value.trim(),
      params: {}, layout: {},
    };
    masterMsg("Saving…", false);
    const res = await fetch(form.getAttribute("data-create-url")!, {
      method: "POST", headers: headers(), body: JSON.stringify(body),
    });
    if (res.status === 201) location.reload();
    else {
      const err = await res.json().catch(() => ({}));
      masterMsg((err as any).error || "Could not create.", true);
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  bindRowActions();
  bindMasterForm();
});

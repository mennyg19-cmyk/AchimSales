// Master schedule wizard + SharePoint folder picker (admin page).

// --------------------------------------------------------------------------
// Master schedule wizard
// --------------------------------------------------------------------------

const TOTAL_STEPS = 5;
let wizardStep = 1;

function wizardRoot(): HTMLElement | null {
  return document.getElementById("msWizard");
}

function masterForm(): HTMLFormElement | null {
  return document.getElementById("masterCreateForm") as HTMLFormElement | null;
}

function masterMsg(text: string, isError: boolean): void {
  const el = document.getElementById("masterMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
  el.className = "ms-msg" + (isError ? " ms-msg-error" : "");
}

function reportFilters(): Record<string, string[]> {
  try {
    return JSON.parse(wizardRoot()?.getAttribute("data-report-filters") || "{}");
  } catch {
    return {};
  }
}

function selectedReportKey(form: HTMLFormElement): string {
  const checked = form.querySelector<HTMLInputElement>('input[name="report_key"]:checked');
  return checked?.value || "";
}

function selectedReportTitle(form: HTMLFormElement): string {
  const checked = form.querySelector<HTMLInputElement>('input[name="report_key"]:checked');
  const card = checked?.closest(".ms-report-card");
  return card?.querySelector(".ms-report-name")?.textContent?.trim() || selectedReportKey(form);
}

function syncCadenceVisibility(form: HTMLFormElement): void {
  const freq = (form.querySelector<HTMLInputElement>('input[name="freq"]:checked')?.value) || "daily";
  const wd = document.getElementById("mWeekdays");
  const md = document.getElementById("mMonthday");
  if (wd) wd.hidden = freq !== "weekly";
  if (md) md.hidden = freq !== "monthly";
}

function syncParamsVisibility(form: HTMLFormElement): void {
  const key = selectedReportKey(form);
  const needed = reportFilters()[key] || [];
  const none = document.getElementById("msParamsNone");
  const fields = document.getElementById("msParamsFields");
  const intro = document.getElementById("msParamsIntro");
  form.querySelectorAll<HTMLElement>("[data-param]").forEach((el) => {
    const param = el.getAttribute("data-param") || "";
    el.hidden = !needed.includes(param);
  });
  const empty = needed.length === 0;
  if (none) none.hidden = !empty;
  if (fields) fields.hidden = empty;
  if (intro) intro.hidden = empty;
}

function suggestName(form: HTMLFormElement): void {
  const nameEl = form.elements.namedItem("name") as HTMLInputElement | null;
  if (!nameEl || nameEl.value.trim()) return;
  const title = selectedReportTitle(form);
  if (title) nameEl.value = title + " schedule";
}

function masterCadence(form: HTMLFormElement): { ok: boolean; cadence?: any; error?: string } {
  const freq = form.querySelector<HTMLInputElement>('input[name="freq"]:checked')?.value || "daily";
  const time = (form.elements.namedItem("time") as HTMLInputElement).value || "08:00";
  const cadence: any = { freq, time };
  if (freq === "weekly") {
    const days = [...form.querySelectorAll<HTMLInputElement>('input[name="weekday"]:checked')]
      .map((c) => Number(c.value));
    if (!days.length) return { ok: false, error: "Pick at least one day of the week." };
    cadence.weekdays = days;
  } else if (freq === "monthly") {
    cadence.monthday = Number((form.elements.namedItem("monthday") as HTMLSelectElement).value) || 1;
  }
  return { ok: true, cadence };
}

function collectParams(form: HTMLFormElement): Record<string, unknown> {
  const key = selectedReportKey(form);
  const needed = reportFilters()[key] || [];
  const out: Record<string, unknown> = {};
  if (needed.includes("period")) {
    const v = (form.elements.namedItem("period") as HTMLSelectElement).value.trim();
    if (v) out.period = v;
  }
  if (needed.includes("status")) {
    const v = (form.elements.namedItem("status") as HTMLSelectElement).value.trim();
    if (v) out.status = v;
  }
  if (needed.includes("salesman")) {
    const v = (form.elements.namedItem("salesman") as HTMLInputElement).value.trim();
    if (v) out.salesman = v;
  }
  if (needed.includes("customers")) {
    const v = (form.elements.namedItem("customers") as HTMLInputElement).value.trim();
    if (v) out.customers = v;
  }
  if (needed.includes("year")) {
    const v = (form.elements.namedItem("year") as HTMLSelectElement).value.trim();
    if (v) out.year = v;
  }
  return out;
}

function weekdayLabels(days: number[]): string {
  const names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  return days.map((d) => names[d] || String(d)).join(", ");
}

function fillReview(form: HTMLFormElement): void {
  const review = document.getElementById("msReview");
  if (!review) return;
  const cad = masterCadence(form);
  const freq = cad.cadence?.freq || "daily";
  let when = "Every day";
  if (freq === "weekly") when = "Weekly on " + weekdayLabels(cad.cadence.weekdays || []);
  if (freq === "monthly") {
    const md = cad.cadence.monthday;
    when = md === -1 ? "Monthly on the last day" : `Monthly on day ${md}`;
  }
  when += ` at ${cad.cadence?.time || "08:00"} Eastern`;

  const params = collectParams(form);
  const paramBits: string[] = [];
  if (params.period) paramBits.push(String(params.period).replace(/_/g, " "));
  if (params.status) paramBits.push("status " + params.status);
  if (params.salesman) paramBits.push("salesman " + params.salesman);
  if (params.customers) paramBits.push("customers " + params.customers);
  if (params.year) paramBits.push("year " + params.year);

  const recipients = (form.elements.namedItem("recipients") as HTMLInputElement).value.trim();
  const sp = (document.getElementById("spPathInput") as HTMLInputElement)?.value.trim() || "";

  const rows: [string, string][] = [
    ["Name", (form.elements.namedItem("name") as HTMLInputElement).value.trim()],
    ["Report", selectedReportTitle(form)],
    ["When", when],
    ["Options", paramBits.length ? paramBits.join(", ") : "defaults (everything)"],
    ["Email", recipients || "—"],
    ["SharePoint", sp || "—"],
  ];
  review.innerHTML = rows.map(([k, v]) =>
    `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("");
}

function showStep(step: number): void {
  wizardStep = step;
  document.querySelectorAll<HTMLElement>(".ms-pane").forEach((pane) => {
    const n = Number(pane.getAttribute("data-pane"));
    pane.hidden = n !== step;
  });
  document.querySelectorAll<HTMLElement>(".ms-step").forEach((el) => {
    const n = Number(el.getAttribute("data-step"));
    el.classList.toggle("is-active", n === step);
    el.classList.toggle("is-done", n < step);
  });
  const back = document.getElementById("msBackBtn");
  const next = document.getElementById("msNextBtn");
  const save = document.getElementById("formSubmitBtn");
  if (back) back.hidden = step <= 1;
  if (next) next.hidden = step >= TOTAL_STEPS;
  if (save) save.hidden = step < TOTAL_STEPS;
  masterMsg("", false);

  const form = masterForm();
  if (!form) return;
  if (step === 2) syncCadenceVisibility(form);
  if (step === 3) syncParamsVisibility(form);
  if (step === 5) fillReview(form);
}

function validateStep(step: number, form: HTMLFormElement): string | null {
  if (step === 1) {
    if (!selectedReportKey(form)) return "Pick which report this schedule should send.";
    if (!(form.elements.namedItem("name") as HTMLInputElement).value.trim()) {
      return "Give the schedule a name so you can find it later.";
    }
  }
  if (step === 2) {
    const cad = masterCadence(form);
    if (!cad.ok) return cad.error || "Check the schedule timing.";
  }
  if (step === 4) {
    const recipients = (form.elements.namedItem("recipients") as HTMLInputElement).value.trim();
    const sp = (document.getElementById("spPathInput") as HTMLInputElement)?.value.trim() || "";
    if (!recipients && !sp) {
      return "Add at least one email address or pick a SharePoint folder.";
    }
  }
  return null;
}

function openWizard(): void {
  const wiz = wizardRoot();
  if (!wiz) return;
  wiz.hidden = false;
  document.getElementById("msEmpty")?.setAttribute("hidden", "");
  wiz.scrollIntoView({ behavior: "smooth", block: "start" });
}

function closeWizard(): void {
  const wiz = wizardRoot();
  const form = masterForm();
  if (!wiz || !form) return;
  form.reset();
  (document.getElementById("editingId") as HTMLInputElement).value = "";
  (document.getElementById("spPathInput") as HTMLInputElement).value = "";
  document.getElementById("formTitle")!.textContent = "Set up a schedule";
  document.getElementById("formSubmitBtn")!.textContent = "Save schedule";
  wiz.hidden = true;
  showStep(1);
  masterMsg("", false);
  if (!document.querySelector(".ms-table-wrap")) {
    document.getElementById("msEmpty")?.removeAttribute("hidden");
  }
}

function enterEditMode(row: HTMLTableRowElement): void {
  const form = masterForm();
  if (!form) return;
  const id = row.dataset.id!;
  const cad = JSON.parse(row.dataset.cadence || "{}");
  const params = JSON.parse(row.dataset.params || "{}");

  (document.getElementById("editingId") as HTMLInputElement).value = id;
  (form.elements.namedItem("name") as HTMLInputElement).value = row.dataset.name || "";

  const reportKey = row.dataset.reportKey || "";
  form.querySelectorAll<HTMLInputElement>('input[name="report_key"]').forEach((r) => {
    r.checked = r.value === reportKey;
  });

  const freq = cad.freq || "daily";
  form.querySelectorAll<HTMLInputElement>('input[name="freq"]').forEach((r) => {
    r.checked = r.value === freq;
  });
  (form.elements.namedItem("time") as HTMLInputElement).value = cad.time || "08:00";
  form.querySelectorAll<HTMLInputElement>('input[name="weekday"]').forEach((c) => {
    c.checked = Array.isArray(cad.weekdays) && cad.weekdays.includes(Number(c.value));
  });
  if (cad.monthday != null) {
    (form.elements.namedItem("monthday") as HTMLSelectElement).value = String(cad.monthday);
  }

  (form.elements.namedItem("period") as HTMLSelectElement).value = params.period || "";
  (form.elements.namedItem("status") as HTMLSelectElement).value = params.status || "";
  (form.elements.namedItem("salesman") as HTMLInputElement).value = params.salesman || "";
  const custs = Array.isArray(params.customers)
    ? params.customers.join(" ")
    : (params.customers || "");
  (form.elements.namedItem("customers") as HTMLInputElement).value = custs;
  (form.elements.namedItem("year") as HTMLSelectElement).value =
    params.year != null ? String(params.year) : "";

  (form.elements.namedItem("recipients") as HTMLInputElement).value = row.dataset.recipients || "";
  (document.getElementById("spPathInput") as HTMLInputElement).value = row.dataset.sharepointPath || "";

  document.getElementById("formTitle")!.textContent = "Edit schedule";
  document.getElementById("formSubmitBtn")!.textContent = "Save changes";
  syncCadenceVisibility(form);
  syncParamsVisibility(form);
  openWizard();
  showStep(1);
}

export function bindMasterWizard(): void {
  const form = masterForm();
  const wiz = wizardRoot();
  if (!form || !wiz) return;

  document.getElementById("msStartBtn")?.addEventListener("click", () => {
    closeWizard();
    openWizard();
    showStep(1);
  });
  document.getElementById("msCancelBtn")?.addEventListener("click", closeWizard);
  document.getElementById("msBackBtn")?.addEventListener("click", () => {
    if (wizardStep > 1) showStep(wizardStep - 1);
  });
  document.getElementById("msNextBtn")?.addEventListener("click", () => {
    const err = validateStep(wizardStep, form);
    if (err) { masterMsg(err, true); return; }
    if (wizardStep === 1) suggestName(form);
    if (wizardStep < TOTAL_STEPS) showStep(wizardStep + 1);
  });

  form.querySelectorAll<HTMLInputElement>('input[name="freq"]').forEach((r) => {
    r.addEventListener("change", () => syncCadenceVisibility(form));
  });
  form.querySelectorAll<HTMLInputElement>('input[name="report_key"]').forEach((r) => {
    r.addEventListener("change", () => {
      syncParamsVisibility(form);
      suggestName(form);
    });
  });

  document.querySelectorAll<HTMLButtonElement>(".js-edit").forEach((b) => {
    b.addEventListener("click", () => {
      const row = b.closest("tr") as HTMLTableRowElement;
      if (row) enterEditMode(row);
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    for (let s = 1; s <= TOTAL_STEPS; s++) {
      const err = validateStep(s, form);
      if (err) { showStep(s); masterMsg(err, true); return; }
    }
    const cad = masterCadence(form);
    if (!cad.ok) { masterMsg(cad.error!, true); return; }

    const body = {
      name: (form.elements.namedItem("name") as HTMLInputElement).value.trim(),
      report_key: selectedReportKey(form),
      cadence: cad.cadence,
      recipients: (form.elements.namedItem("recipients") as HTMLInputElement).value.trim(),
      sharepoint_path: (document.getElementById("spPathInput") as HTMLInputElement).value.trim(),
      params: collectParams(form),
      layout: {},
    };

    const editId = (document.getElementById("editingId") as HTMLInputElement).value;
    masterMsg("Saving…", false);
    const submitBtn = document.getElementById("formSubmitBtn") as HTMLButtonElement;
    submitBtn.disabled = true;

    try {
      let res: Response;
      if (editId) {
        const tpl = wiz.getAttribute("data-update-url-tpl")!;
        const url = tpl.replace("/0", "/" + editId);
        res = await fetch(url, { method: "PUT", headers: headers(), body: JSON.stringify(body) });
      } else {
        res = await fetch(wiz.getAttribute("data-create-url")!, {
          method: "POST", headers: headers(), body: JSON.stringify(body),
        });
      }
      if (res.ok || res.status === 201) {
        location.reload();
        return;
      }
      const err = await res.json().catch(() => ({}));
      masterMsg((err as any).error || (err as any).description || "Could not save.", true);
    } catch {
      masterMsg("Could not save. Check your connection and try again.", true);
    } finally {
      submitBtn.disabled = false;
    }
  });

  showStep(1);
}

function esc(s: string): string {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

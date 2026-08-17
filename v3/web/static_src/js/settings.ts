/**
 * Settings hub: flags, schedule test mode, exclusions, report visibility,
 * beta sources. Optimistic UI with rollback if the request fails.
 */

function hub(): HTMLElement | null {
  return document.getElementById("settingsHub");
}

function csrf(): string {
  return hub()?.getAttribute("data-csrf") || "";
}

async function postJson(url: string, body: unknown): Promise<Response> {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
    body: JSON.stringify(body),
  });
}

function initAccordion(): void {
  if (!window.matchMedia("(min-width: 768px)").matches) return;
  document.querySelectorAll<HTMLDetailsElement>("details.settings-cat").forEach((d) => {
    d.open = true;
  });
}

function initFlagToggles(): void {
  const root = hub();
  const url = root?.getAttribute("data-flag-url") || "";
  if (!root || !url) return;
  root.querySelectorAll<HTMLInputElement>(".flag-toggle").forEach((box) => {
    box.addEventListener("change", async () => {
      const key = box.getAttribute("data-key") || "";
      const enabled = box.checked;
      box.disabled = true;
      try {
        const resp = await postJson(url, { key, enabled });
        if (!resp.ok) throw new Error(String(resp.status));
      } catch {
        box.checked = !enabled;
      } finally {
        box.disabled = false;
      }
    });
  });
}

function initVisibilityToggles(): void {
  const root = hub();
  const url = root?.getAttribute("data-vis-url") || "";
  if (!root || !url) return;
  root.querySelectorAll<HTMLInputElement>(".vis-toggle").forEach((box) => {
    box.addEventListener("change", async () => {
      const report_key = box.getAttribute("data-key") || "";
      const enabled = box.checked;
      box.disabled = true;
      try {
        const resp = await postJson(url, { report_key, enabled });
        if (!resp.ok) throw new Error(String(resp.status));
      } catch {
        box.checked = !enabled;
      } finally {
        box.disabled = false;
      }
    });
  });
}

function initExclusions(): void {
  const root = hub();
  const url = root?.getAttribute("data-excl-url") || "";
  const list = document.getElementById("exclList");
  const search = document.getElementById("exclSearch") as HTMLInputElement | null;
  if (!root || !url || !list) return;
  search?.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase();
    list.querySelectorAll<HTMLElement>(".excl-row").forEach((row) => {
      const name = row.getAttribute("data-name") || "";
      row.hidden = Boolean(q) && !name.includes(q);
    });
  });
  list.querySelectorAll<HTMLInputElement>(".excl-toggle").forEach((box) => {
    box.addEventListener("change", async () => {
      const account = box.getAttribute("data-account") || "";
      const included = box.checked;
      box.disabled = true;
      try {
        const resp = await postJson(url, { customer_account: account, excluded: !included });
        if (!resp.ok) throw new Error(String(resp.status));
      } catch {
        box.checked = !included;
      } finally {
        box.disabled = false;
      }
    });
  });
}

function initBetaSources(): void {
  const root = hub();
  const url = root?.getAttribute("data-beta-url") || "";
  const msg = document.getElementById("betaSourcesMsg");
  if (!root || !url) return;
  root.querySelectorAll<HTMLSelectElement>(".beta-source-select").forEach((sel) => {
    sel.addEventListener("change", async () => {
      const report_key = sel.getAttribute("data-key") || "";
      const source = sel.value;
      sel.disabled = true;
      try {
        const resp = await postJson(url, { report_key, source });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error((data as { error?: string }).error || String(resp.status));
        if (msg) { msg.hidden = false; msg.textContent = `${report_key} → ${source}`; }
      } catch (err) {
        if (msg) { msg.hidden = false; msg.textContent = err instanceof Error ? err.message : "Could not save."; }
      } finally {
        sel.disabled = false;
      }
    });
  });
}

function emailsFromDom(host: HTMLElement): string[] {
  return Array.from(host.querySelectorAll<HTMLElement>(".js-test-email-remove"))
    .map((el) => el.getAttribute("data-email") || "")
    .filter(Boolean);
}

function renderChips(host: HTMLElement, emails: string[]): void {
  host.replaceChildren();
  for (const email of emails) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "customer-chip js-test-email-remove";
    btn.dataset.email = email;
    btn.setAttribute("aria-label", `Remove ${email}`);
    btn.textContent = `${email} ✕`;
    host.appendChild(btn);
  }
}

function initScheduleTest(): void {
  const root = document.getElementById("adminSettings") || hub();
  if (!root) return;
  const url = hub()?.getAttribute("data-test-url") || "";
  const toggle = document.getElementById("scheduleTestToggle") as HTMLInputElement | null;
  const chips = document.getElementById("testEmailChips");
  const form = document.getElementById("testEmailAdd") as HTMLFormElement | null;
  const input = document.getElementById("testEmailInput") as HTMLInputElement | null;
  const msg = document.getElementById("testModeMsg");
  if (!toggle || !chips || !form || !input || !url) return;

  const show = (text: string) => {
    if (!msg) return;
    msg.textContent = text;
    msg.hidden = !text;
  };

  const save = async (payload: { enabled?: boolean; emails?: string[] }) => {
    const resp = await postJson(url, payload);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error((data as { error?: string }).error || String(resp.status));
    return data as { enabled: boolean; emails: string[] };
  };

  const apply = (data: { enabled: boolean; emails: string[] }) => {
    toggle.checked = data.enabled;
    renderChips(chips, data.emails);
  };

  chips.addEventListener("click", async (ev) => {
    const btn = (ev.target as HTMLElement).closest(".js-test-email-remove");
    if (!(btn instanceof HTMLElement)) return;
    const remove = btn.getAttribute("data-email") || "";
    const next = emailsFromDom(chips).filter((e) => e !== remove);
    try {
      apply(await save({ emails: next }));
      show("");
    } catch (err) {
      show(err instanceof Error ? err.message : "Could not update test emails.");
    }
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const addr = input.value.trim();
    if (!addr) return;
    const next = emailsFromDom(chips);
    if (next.some((e) => e.toLowerCase() === addr.toLowerCase())) {
      input.value = "";
      return;
    }
    next.push(addr);
    try {
      apply(await save({ emails: next }));
      input.value = "";
      show("");
    } catch (err) {
      show(err instanceof Error ? err.message : "Could not add that address.");
    }
  });

  toggle.addEventListener("change", async () => {
    const enabled = toggle.checked;
    if (enabled && emailsFromDom(chips).length === 0) {
      toggle.checked = false;
      show("Add at least one test email before turning test mode on.");
      return;
    }
    toggle.disabled = true;
    try {
      apply(await save({ enabled }));
      show(enabled ? "Test mode on. Company schedule mail goes only to the list below." : "");
    } catch (err) {
      toggle.checked = !enabled;
      show(err instanceof Error ? err.message : "Could not update test mode.");
    } finally {
      toggle.disabled = false;
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initAccordion();
  initFlagToggles();
  initVisibilityToggles();
  initExclusions();
  initBetaSources();
  initScheduleTest();
});

export {};

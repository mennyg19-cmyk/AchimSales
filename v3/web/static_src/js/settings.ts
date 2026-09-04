/**
 * Settings hub: flags, schedule test mode, exclusions, and report visibility.
 * Optimistic UI with rollback if the request fails.
 */

import { SearchablePicker, type PickerItem } from "./searchable_picker";
import { isHidden, onVisible } from "./visibility";

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
  const cats = Array.from(
    document.querySelectorAll<HTMLDetailsElement>("details.settings-cat"),
  );
  cats.forEach((section) => {
    section.addEventListener("toggle", () => {
      if (!section.open) return;
      cats.forEach((other) => {
        if (other !== section) other.open = false;
      });
    });
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

function parseExcluded(root: HTMLElement): string[] {
  try {
    const parsed = JSON.parse(root.getAttribute("data-excluded") || "[]");
    return Array.isArray(parsed) ? parsed.map(String).filter(Boolean) : [];
  } catch {
    return [];
  }
}

function setExclHint(text: string, isError = false): void {
  const hint = document.getElementById("exclHint");
  if (!hint) return;
  hint.textContent = text;
  hint.setAttribute("aria-live", isError ? "assertive" : "polite");
  hint.setAttribute("role", isError ? "alert" : "status");
}

function initExclusions(): void {
  const root = hub();
  const saveUrl = root?.getAttribute("data-excl-url") || "";
  const customersUrl = root?.getAttribute("data-customers-url") || "";
  const statusUrl = root?.getAttribute("data-lookup-status-url") || "";
  const host = document.getElementById("exclPicker");
  const pills = document.getElementById("exclPills");
  if (!root || !saveUrl || !customersUrl || !host || !pills) return;

  const excluded = parseExcluded(root);
  let hydrating = true;
  let known = new Set<string>();
  let pollTimer: number | null = null;

  const picker = new SearchablePicker({
    host,
    pills,
    placeholder: "Search customers…",
    formatOption: (i: PickerItem) => `${i.key} — ${i.name}`,
    formatPill: (i: PickerItem) => i.name,
    onChange: () => {
      if (hydrating) return;
      const next = new Set(picker.selectedKeys());
      const added = [...next].filter((k) => !known.has(k));
      const removed = [...known].filter((k) => !next.has(k));
      known = next;
      const persist = (account: string, excluded: boolean, revert: string[]) => {
        postJson(saveUrl, { customer_account: account, excluded }).then((resp) => {
          if (resp.ok) return;
          hydrating = true;
          picker.setSelected(revert);
          known = new Set(picker.selectedKeys());
          hydrating = false;
          setExclHint("Could not save customer exclusions.", true);
        }).catch(() => {
          hydrating = true;
          picker.setSelected(revert);
          known = new Set(picker.selectedKeys());
          hydrating = false;
          setExclHint("Could not save customer exclusions.", true);
        });
      };
      for (const account of added) persist(account, true, [...known].filter((k) => k !== account));
      for (const account of removed) persist(account, false, [...picker.selectedKeys(), account]);
    },
  });

  const applyExcluded = () => {
    hydrating = true;
    picker.setSelected(excluded);
    known = new Set(picker.selectedKeys());
    hydrating = false;
  };

  const loadCustomers = async (): Promise<number> => {
    const resp = await fetch(customersUrl);
    if (!resp.ok) return 0;
    const data = await resp.json().catch(() => ({}));
    const rows = Array.isArray((data as { customers?: PickerItem[] }).customers)
      ? (data as { customers: PickerItem[] }).customers
      : [];
    picker.setOptions(rows.map((c) => ({ key: c.key, name: c.name })));
    applyExcluded();
    if (rows.length) {
      setExclHint("Search and check customers to hide them.");
    }
    return rows.length;
  };

  const stopPoll = () => {
    if (pollTimer != null) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  };

  const pollStatus = () => {
    if (!statusUrl) return;
    const tick = async () => {
      if (isHidden()) return;
      const resp = await fetch(statusUrl);
      if (!resp.ok) return;
      const s = await resp.json().catch(() => ({})) as {
        status?: string;
        cached_row_count?: number;
        mirror_row_count?: number;
        configured?: boolean;
      };
      const ready = s.status === "ready"
        || (s.cached_row_count || 0) > 0
        || (s.mirror_row_count || 0) > 0;
      if (ready) {
        stopPoll();
        await loadCustomers();
        return;
      }
      if (s.status === "loading") setExclHint("Loading customers…");
      else if (s.status === "error") setExclHint("Customer master still warming — retrying…", true);
      else if (s.configured === false) setExclHint("Customer master is not configured.");
    };
    tick();
    pollTimer = window.setInterval(tick, 2500);
    onVisible(() => { if (pollTimer != null) void tick(); });
  };

  loadCustomers().then((count) => {
    if (count > 0) return;
    pollStatus();
  }).catch(() => {
    setExclHint("Could not load customers.", true);
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

  const show = (text: string, isError = false) => {
    if (!msg) return;
    msg.textContent = text;
    msg.hidden = !text;
    msg.setAttribute("aria-live", isError ? "assertive" : "polite");
    msg.setAttribute("role", isError ? "alert" : "status");
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
      show(err instanceof Error ? err.message : "Could not update test emails.", true);
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
      show(err instanceof Error ? err.message : "Could not add that address.", true);
    }
  });

  toggle.addEventListener("change", async () => {
    const enabled = toggle.checked;
    if (enabled && emailsFromDom(chips).length === 0) {
      toggle.checked = false;
      show("Add at least one test email before turning test mode on.", true);
      return;
    }
    toggle.disabled = true;
    try {
      apply(await save({ enabled }));
      show(enabled ? "Test mode on. Company schedule mail goes only to the list below." : "");
    } catch (err) {
      toggle.checked = !enabled;
      show(err instanceof Error ? err.message : "Could not update test mode.", true);
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
  initScheduleTest();
});

export {};

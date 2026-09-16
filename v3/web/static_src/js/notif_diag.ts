function root(): HTMLElement | null {
  return document.getElementById("ndRoot");
}

function show(text: string): void {
  const el = document.getElementById("ndMsg");
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
}

async function load(email: string, run = false): Promise<void> {
  const r = root();
  const out = document.getElementById("ndOut");
  if (!r || !out || !email) return;
  const tpl = r.getAttribute(run ? "data-run-url" : "data-url") || "";
  const url = tpl.replace("__EMAIL__", encodeURIComponent(email));
  const resp = await fetch(url, {
    method: run ? "POST" : "GET",
    headers: run
      ? { "X-CSRF-Token": r.getAttribute("data-csrf") || "", Accept: "application/json" }
      : { Accept: "application/json" },
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    show((data as { error?: string }).error || "Could not load diagnostic.");
    return;
  }
  show(run ? `Generated ${data.generated ?? 0} overdue alerts (all users).` : "");
  const u = data.user || {};
  const created = (data.would_create || []) as { customer_account: string; customer_name: string }[];
  const skipped = (data.would_skip || []) as { customer_account: string; reason: string }[];
  out.innerHTML = `
    <section class="settings-card">
      <p><strong>${u.email || ""}</strong> · ${u.role || ""} · active ${u.is_active ? "yes" : "no"} · dashboard ${u.dashboard_enabled ? "on" : "off"}</p>
      <p class="flag-desc">Mirror refreshed ${data.last_refreshed || "never"} · ${data.matched_customers || 0} customers in scope · ${data.overdue_in_scope || 0} overdue</p>
      <h3 class="settings-subhead">Would create (${created.length})</h3>
      <ul>${created.map((c) => `<li>${c.customer_account} — ${c.customer_name}</li>`).join("") || "<li>None</li>"}</ul>
      <h3 class="settings-subhead">Would skip (${skipped.length})</h3>
      <ul>${skipped.map((c) => `<li>${c.customer_account} — ${c.reason}</li>`).join("") || "<li>None</li>"}</ul>
      <h3 class="settings-subhead">Excluded</h3>
      <p>${(data.excluded || []).join(", ") || "None"}</p>
      <h3 class="settings-subhead">Active alerts</h3>
      <p>${(data.active_notifications || []).length}</p>
    </section>`;
}

document.addEventListener("DOMContentLoaded", () => {
  const sel = document.getElementById("ndUser") as HTMLSelectElement | null;
  sel?.addEventListener("change", () => { if (sel.value) void load(sel.value); });
  document.getElementById("ndRun")?.addEventListener("click", () => {
    if (sel?.value) void load(sel.value, true);
  });
});

export {};

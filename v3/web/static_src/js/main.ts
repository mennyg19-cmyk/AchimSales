/**
 * App shell behaviors (ported from the live base.html inline scripts into a
 * typed module): Feather icons, help popup, double-click + double-nav guards,
 * page-loading overlay, and custom pull-to-refresh. Behavior matches live.
 */

declare const feather: { replace: () => void } | undefined;

declare global {
  interface Window {
    triggerDashRefresh?: () => void;
    openHelp: (key: string) => void;
    closeHelp: (e?: Event) => void;
  }
}

interface HelpEntry {
  title: string;
  body: string;
}
declare const HELP: Record<string, HelpEntry> | undefined;

let navPending = false;

function openHelp(key: string): void {
  const entry = typeof HELP !== "undefined" && HELP[key];
  if (!entry) return;
  const title = document.getElementById("helpTitle");
  const body = document.getElementById("helpBody");
  const overlay = document.getElementById("helpOverlay");
  if (!title || !body || !overlay) return;
  title.textContent = entry.title;
  body.innerHTML = entry.body;
  overlay.style.display = "flex";
}

function closeHelp(e?: Event): void {
  const overlay = document.getElementById("helpOverlay");
  if (!overlay) return;
  if (e && e.target && e.target !== overlay) return;
  overlay.style.display = "none";
}

window.openHelp = openHelp;
window.closeHelp = closeHelp;

function onClick(e: MouseEvent): void {
  const target = e.target as HTMLElement;

  const helpBtn = target.closest<HTMLElement>("[data-help]");
  if (helpBtn) {
    e.preventDefault();
    e.stopPropagation();
    openHelp(helpBtn.getAttribute("data-help") || "");
    return;
  }

  // Global double-click guard for non-submit buttons.
  const btn = target.closest<HTMLButtonElement>('button:not([type="submit"])');
  if (btn && !btn.dataset.noGuard) {
    if (btn.dataset.guardBusy) {
      e.preventDefault();
      e.stopPropagation();
      return;
    }
    btn.dataset.guardBusy = "1";
    setTimeout(() => delete btn.dataset.guardBusy, 600);
  }

  // Navigation overlay + double-nav guard.
  const link = target.closest<HTMLAnchorElement>("a[href]");
  if (!link) return;
  const href = link.getAttribute("href");
  if (
    !href || href.startsWith("#") || href.startsWith("javascript") ||
    link.getAttribute("target") === "_blank" || link.hasAttribute("download") ||
    href.indexOf("/download") !== -1 || e.ctrlKey || e.metaKey || e.shiftKey
  ) {
    return;
  }
  if (link.closest(".modal-overlay") || link.closest(".help-popup-overlay")) return;

  if (navPending) {
    e.preventDefault();
    return;
  }
  navPending = true;
  setTimeout(() => (navPending = false), 4000);

  const navItem = link.closest(".bottom-nav-item");
  if (navItem) {
    document.querySelectorAll(".bottom-nav-item").forEach((n) => n.classList.remove("active"));
    navItem.classList.add("active");
  }

  const overlay = document.createElement("div");
  overlay.className = "page-loading-overlay";
  overlay.innerHTML = '<div class="page-loading-spinner"></div>';
  document.body.appendChild(overlay);
}

function initPullToRefresh(): void {
  if (!("ontouchstart" in window)) return;

  const THRESHOLD = 70;
  const MAX_PULL = 110;

  const indicator = document.createElement("div");
  indicator.className = "ptr-indicator";
  indicator.innerHTML = '<span class="ptr-spinner"></span><span class="ptr-label">Pull to refresh</span>';
  document.body.appendChild(indicator);

  let startY = 0;
  let pulling = false;
  let pulled = 0;
  let refreshing = false;

  const label = () => indicator.querySelector(".ptr-label");

  function setPullDistance(d: number): void {
    const y = Math.min(d, MAX_PULL);
    indicator.style.transform = "translateY(" + (y - 60) + "px)";
    indicator.style.opacity = String(Math.min(1, d / THRESHOLD));
    const l = label();
    if (l) l.textContent = d > THRESHOLD ? "Release to refresh" : "Pull to refresh";
    indicator.classList.toggle("ptr-armed", d > THRESHOLD);
  }

  function reset(): void {
    indicator.classList.add("ptr-snapping");
    indicator.style.transform = "";
    indicator.style.opacity = "";
    indicator.classList.remove("ptr-armed");
    setTimeout(() => indicator.classList.remove("ptr-snapping"), 250);
  }

  function doRefresh(): void {
    refreshing = true;
    indicator.classList.add("ptr-refreshing");
    indicator.style.transform = "translateY(10px)";
    indicator.style.opacity = "1";
    const l = label();
    if (l) l.textContent = "Refreshing\u2026";
    if (typeof window.triggerDashRefresh === "function") {
      try { window.triggerDashRefresh(); } catch { /* fall back to reload */ }
      setTimeout(reset, 600);
      return;
    }
    setTimeout(() => window.location.reload(), 150);
  }

  window.addEventListener("touchstart", (e) => {
    if (refreshing || window.scrollY > 0) return;
    startY = e.touches[0].clientY;
    pulling = true;
    pulled = 0;
  }, { passive: true });

  window.addEventListener("touchmove", (e) => {
    if (!pulling || refreshing) return;
    if (window.scrollY > 0) { pulling = false; reset(); return; }
    pulled = e.touches[0].clientY - startY;
    if (pulled <= 0) { pulled = 0; return; }
    setPullDistance(pulled);
  }, { passive: true });

  window.addEventListener("touchend", () => {
    if (!pulling || refreshing) { pulling = false; return; }
    pulling = false;
    if (pulled > THRESHOLD) doRefresh();
    else reset();
    pulled = 0;
  });

  window.addEventListener("touchcancel", () => {
    pulling = false;
    if (!refreshing) reset();
  });
}

const THEME_ORDER = ["light", "dark", "monochrome", "monochrome_dark"] as const;
type Theme = (typeof THEME_ORDER)[number];
const THEME_ICONS: Record<Theme, string> = {
  light: "sun", dark: "moon", monochrome: "aperture", monochrome_dark: "disc",
};

function currentTheme(): Theme {
  if (document.body.classList.contains("dark-theme")) return "dark";
  if (document.body.classList.contains("monochrome-theme")) return "monochrome";
  if (document.body.classList.contains("monochrome-dark-theme")) return "monochrome_dark";
  return "light";
}

function applyTheme(btn: HTMLElement, theme: Theme): void {
  document.body.classList.toggle("dark-theme", theme === "dark");
  document.body.classList.toggle("monochrome-theme", theme === "monochrome");
  document.body.classList.toggle("monochrome-dark-theme", theme === "monochrome_dark");
  const icon = btn.querySelector("i");
  if (icon) {
    icon.setAttribute("data-feather", THEME_ICONS[theme]);
    if (typeof feather !== "undefined") feather.replace();
  }
}

function initThemeToggle(): void {
  const btn = document.getElementById("themeToggleBtn");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    const next = THEME_ORDER[(THEME_ORDER.indexOf(currentTheme()) + 1) % THEME_ORDER.length];
    applyTheme(btn, next);
    try {
      await fetch(btn.getAttribute("data-url") || "", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": btn.getAttribute("data-csrf") || "" },
        body: JSON.stringify({ theme: next }),
      });
    } catch {
      /* visual toggle already applied; persistence is best-effort */
    }
  });
}

function setBadge(id: string, count: number): void {
  const el = document.getElementById(id);
  if (!el) return;
  if (count > 0) {
    el.textContent = count > 99 ? "99+" : String(count);
    el.style.display = "";
  } else {
    el.style.display = "none";
  }
}

function initNotificationBadges(): void {
  const nav = document.querySelector<HTMLElement>(".bottom-nav[data-notifications-url]");
  if (!nav) return;
  const url = nav.getAttribute("data-notifications-url") || "";

  async function poll(): Promise<void> {
    try {
      const data = await fetch(url).then((r) => r.json());
      setBadge("badgeDashboard", data.overdue_count || 0);
      setBadge("badgeReports", data.report_ready_count || 0);
    } catch {
      /* transient; try again next tick */
    }
  }
  poll();
  setInterval(poll, 30000);
}

interface ActiveReportJob {
  job_id: string;
  report_key: string | null;
  title: string;
  status: string;
  progress: number;
}

/**
 * Always-on bar (every page) showing the user's report runs and how far along
 * they are. Click a chip to jump to that report -- if it's still running the
 * report page reconnects to it; if it just finished it loads the result.
 */
function initReportJobsBar(): void {
  const bar = document.getElementById("reportJobsBar");
  if (!bar) return;
  const activeUrl = bar.getAttribute("data-active-url") || "";
  const reportUrlTpl = bar.getAttribute("data-report-url") || "";
  if (!activeUrl) return;

  let lastSignature = "";

  function statusWord(job: ActiveReportJob): string {
    if (job.status === "running") return `building ${job.progress || 0}%`;
    if (job.status === "queued") return "waiting to start";
    if (job.status === "success") return "ready";
    if (job.status === "failure") return "failed";
    return job.status;
  }

  function render(jobs: ActiveReportJob[]): void {
    const signature = JSON.stringify(jobs.map((j) => [j.job_id, j.status, j.progress]));
    if (signature === lastSignature) return; // nothing changed; don't churn the DOM
    lastSignature = signature;

    if (!jobs.length) {
      bar.hidden = true;
      bar.innerHTML = "";
      return;
    }
    const inner = document.createElement("div");
    inner.className = "report-jobs-inner";
    const running = jobs.filter((j) => j.status === "running" || j.status === "queued").length;
    const lead = document.createElement("span");
    lead.className = "report-jobs-lead";
    lead.textContent = running ? `${running} report${running > 1 ? "s" : ""} running` : "Your reports";
    inner.appendChild(lead);

    jobs.forEach((job) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "report-job-chip report-job-" + job.status;
      chip.dataset.noGuard = "1";
      chip.title = "Open this report";
      const dot = document.createElement("span");
      dot.className = "report-job-dot";
      const label = document.createElement("span");
      label.className = "report-job-label";
      label.textContent = `${job.title} — ${statusWord(job)}`;
      chip.appendChild(dot);
      chip.appendChild(label);
      chip.addEventListener("click", () => {
        if (!job.report_key) return;
        window.location.href = reportUrlTpl.replace("__KEY__", encodeURIComponent(job.report_key));
      });
      inner.appendChild(chip);
    });

    bar.innerHTML = "";
    bar.appendChild(inner);
    bar.hidden = false;
  }

  async function poll(): Promise<void> {
    try {
      const data = await fetch(activeUrl, { headers: { Accept: "application/json" } }).then((r) => r.json());
      render((data && data.jobs) || []);
    } catch {
      /* transient; keep showing the last state and retry next tick */
    }
  }
  poll();
  setInterval(poll, 5000);
}

document.addEventListener("DOMContentLoaded", () => {
  if (typeof feather !== "undefined") feather.replace();
  document.addEventListener("click", onClick);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeHelp();
  });
  initThemeToggle();
  initNotificationBadges();
  initReportJobsBar();
  initPullToRefresh();
});

window.addEventListener("pageshow", () => {
  const overlay = document.querySelector(".page-loading-overlay");
  if (overlay) overlay.remove();
  navPending = false;
});

export {};

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
  created_at?: string | null;
  finished_at?: string | null;
  kept?: boolean;
  keep_name?: string;
  owner_name?: string;
  log?: { t?: string; step?: string; detail?: string }[];
}

const JOBS_MIN_KEY = "achim.reportJobs.minimized";

function formatJobWhen(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("en-US", {
    timeZone: "America/New_York",
    month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit",
  });
}

/**
 * Always-on floating button (bottom-right, every page) showing the user's
 * report runs. Tap it to open a small panel listing each run and how far along
 * it is; tap a row to jump to that report -- if it's still running the report
 * page reconnects to it, if it just finished it loads the result.
 * Header "Recent Reports" opens the same list. The pill shrinks to an icon.
 */
function initReportJobsBar(): void {
  const bar = document.getElementById("reportJobsBar");
  if (!bar) return;
  const activeUrl = bar.getAttribute("data-active-url") || "";
  const reportUrlTpl = bar.getAttribute("data-report-url") || "";
  const keepUrlTpl = bar.getAttribute("data-keep-url") || "";
  const csrf = bar.getAttribute("data-csrf") || "";
  if (!activeUrl) return;

  let lastSignature = "";
  let panelOpen = false;
  let minimized = localStorage.getItem(JOBS_MIN_KEY) === "1";
  let lastJobs: ActiveReportJob[] = [];

  function statusWord(job: ActiveReportJob): string {
    if (job.status === "running") return `building ${job.progress || 0}%`;
    if (job.status === "queued") return "waiting to start";
    if (job.status === "success") return job.kept ? "kept" : "ready";
    if (job.status === "failure") return "failed";
    return job.status;
  }

  function jobHref(job: ActiveReportJob): string {
    if (!job.report_key) return "";
    return reportUrlTpl.replace("__KEY__", encodeURIComponent(job.report_key))
      + "?job=" + encodeURIComponent(job.job_id);
  }

  async function renameKept(job: ActiveReportJob): Promise<void> {
    if (!keepUrlTpl) return;
    const current = (job.keep_name || job.title || "").trim();
    const name = window.prompt("Name this kept run:", current);
    if (name === null) return;
    const url = keepUrlTpl.replace(/__ID__/g, job.job_id);
    try {
      const res = await fetch(url, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, Accept: "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (!res.ok) throw new Error();
      lastSignature = "";
      await poll();
    } catch {
      window.alert("Could not rename this run.");
    }
  }

  function render(jobs: ActiveReportJob[]): void {
    lastJobs = jobs;
    const signature = JSON.stringify(jobs.map((j) =>
      [j.job_id, j.status, j.progress, j.keep_name, j.finished_at, j.kept]))
      + String(minimized) + String(panelOpen);
    if (signature === lastSignature) return;
    lastSignature = signature;

    const running = jobs.filter((j) => j.status === "running" || j.status === "queued").length;
    const anyFailed = jobs.some((j) => j.status === "failure");
    bar.classList.toggle("report-jobs-busy", running > 0);
    bar.classList.toggle("report-jobs-failed", running === 0 && anyFailed);
    bar.classList.toggle("report-jobs-done", jobs.length > 0 && running === 0 && !anyFailed);
    bar.classList.toggle("report-jobs-min", minimized);
    bar.hidden = false;

    const panel = document.createElement("div");
    panel.className = "report-jobs-panel";
    panel.hidden = !panelOpen;

    const head = document.createElement("div");
    head.className = "report-jobs-panel-head";
    const headTitle = document.createElement("span");
    headTitle.textContent = "Recent Reports";
    head.appendChild(headTitle);
    const minBtn = document.createElement("button");
    minBtn.type = "button";
    minBtn.className = "report-jobs-min-btn";
    minBtn.dataset.noGuard = "1";
    minBtn.textContent = "Minimize";
    minBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      minimized = true;
      panelOpen = false;
      localStorage.setItem(JOBS_MIN_KEY, "1");
      lastSignature = "";
      render(lastJobs);
    });
    head.appendChild(minBtn);
    panel.appendChild(head);

    if (!jobs.length) {
      const empty = document.createElement("div");
      empty.className = "report-jobs-empty";
      empty.textContent = "No recent or kept runs. Open a report, run it, then Keep this run.";
      panel.appendChild(empty);
    }

    jobs.forEach((job) => {
      const row = document.createElement("div");
      row.className = "report-job-row";
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "report-job-chip report-job-" + job.status;
      chip.dataset.noGuard = "1";
      chip.title = "Open this report";
      const dot = document.createElement("span");
      dot.className = "report-job-dot";
      const text = document.createElement("span");
      text.className = "report-job-text";
      const label = document.createElement("span");
      label.className = "report-job-label";
      label.textContent = (job.keep_name || job.title || "Report").trim();
      const meta = document.createElement("span");
      meta.className = "report-job-meta";
      const when = formatJobWhen(job.finished_at || job.created_at);
      meta.textContent = [job.owner_name, when, statusWord(job)].filter(Boolean).join(" · ");
      text.appendChild(label);
      text.appendChild(meta);
      chip.appendChild(dot);
      chip.appendChild(text);
      chip.addEventListener("click", () => {
        const href = jobHref(job);
        if (href) window.location.href = href;
      });
      row.appendChild(chip);
      if (job.kept) {
        const rename = document.createElement("button");
        rename.type = "button";
        rename.className = "report-job-rename";
        rename.dataset.noGuard = "1";
        rename.textContent = "Name";
        rename.addEventListener("click", (e) => {
          e.stopPropagation();
          void renameKept(job);
        });
        row.appendChild(rename);
      }
      if (job.log && job.log.length) {
        const steps = document.createElement("details");
        steps.className = "report-job-steps";
        const sum = document.createElement("summary");
        sum.textContent = "Steps";
        sum.dataset.noGuard = "1";
        steps.appendChild(sum);
        const ol = document.createElement("ol");
        ol.className = "live-job-log";
        job.log.forEach((e) => {
          const li = document.createElement("li");
          li.className = "live-job-entry";
          li.textContent = [e.t, e.step, e.detail].filter(Boolean).join(" — ");
          ol.appendChild(li);
        });
        steps.appendChild(ol);
        row.appendChild(steps);
      }
      panel.appendChild(row);
    });

    const fab = document.createElement("button");
    fab.type = "button";
    fab.className = "report-jobs-fab";
    fab.dataset.noGuard = "1";
    fab.title = minimized ? "Recent Reports" : "Hide or show Recent Reports";
    if (running > 0) {
      const spin = document.createElement("span");
      spin.className = "report-jobs-spinner";
      fab.appendChild(spin);
    }
    if (!minimized) {
      const fabLabel = document.createElement("span");
      fabLabel.textContent = running > 0
        ? `${running} running`
        : !jobs.length ? "Recent Reports"
          : anyFailed ? "Report failed" : "Reports ready";
      fab.appendChild(fabLabel);
    } else {
      const fabMark = document.createElement("span");
      fabMark.textContent = jobs.length ? String(Math.min(jobs.length, 9)) : "•";
      fab.appendChild(fabMark);
    }
    fab.addEventListener("click", (e) => {
      e.stopPropagation();
      if (minimized) {
        minimized = false;
        localStorage.setItem(JOBS_MIN_KEY, "0");
        panelOpen = true;
      } else {
        panelOpen = !panelOpen;
      }
      lastSignature = "";
      render(lastJobs);
    });

    bar.innerHTML = "";
    bar.appendChild(panel);
    bar.appendChild(fab);
  }

  document.getElementById("prevRunsBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    minimized = false;
    panelOpen = true;
    localStorage.setItem(JOBS_MIN_KEY, "0");
    lastSignature = "";
    render(lastJobs);
  });

  document.addEventListener("click", (e) => {
    if (panelOpen && !bar.contains(e.target as Node)
        && (e.target as HTMLElement).id !== "prevRunsBtn") {
      panelOpen = false;
      const panel = bar.querySelector<HTMLElement>(".report-jobs-panel");
      if (panel) panel.hidden = true;
    }
  });

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

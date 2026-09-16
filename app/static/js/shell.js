const THEME_ORDER = (document.body.getAttribute("data-themes") || "light,dark,monochrome,monochrome_dark")
  .split(",")
  .map((name) => name.trim())
  .filter(Boolean);
const THEME_ICONS = {
  light: "sun",
  dark: "moon",
  monochrome: "aperture",
  monochrome_dark: "disc",
};

function currentTheme() {
  if (document.body.classList.contains("dark-theme")) return "dark";
  if (document.body.classList.contains("monochrome-theme")) return "monochrome";
  if (document.body.classList.contains("monochrome-dark-theme")) return "monochrome_dark";
  return "light";
}

function applyTheme(btn, theme) {
  document.body.classList.toggle("dark-theme", theme === "dark");
  document.body.classList.toggle("monochrome-theme", theme === "monochrome");
  document.body.classList.toggle("monochrome-dark-theme", theme === "monochrome_dark");
  const icon = btn && btn.querySelector("i");
  if (icon) {
    icon.setAttribute("data-feather", THEME_ICONS[theme]);
    if (typeof feather !== "undefined") feather.replace();
  }
}

function initThemeToggle() {
  const btn = document.getElementById("themeToggleBtn");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    const previous = currentTheme();
    const next = THEME_ORDER[(THEME_ORDER.indexOf(previous) + 1) % THEME_ORDER.length];
    applyTheme(btn, next);
    const res =       await fetch(btn.getAttribute("data-url") || "/api/settings/theme", {
        method: "POST",
        headers: csrfHeaders(),
        body: JSON.stringify({ theme: next }),
      }).catch(() => null);
    if (!res || !res.ok) applyTheme(btn, previous);
  });
}

function initSettingsTheme() {
  const save = document.getElementById("settingsThemeSave");
  const select = document.getElementById("settingsTheme");
  if (!save || !select) return;
  save.addEventListener("click", async () => {
    const theme = select.value;
    applyTheme(document.getElementById("themeToggleBtn"), theme);
    const res = await fetch("/api/settings/theme", {
      method: "POST",
      headers: csrfHeaders(),
      body: JSON.stringify({ theme }),
    }).catch(() => null);
    if (!res || !res.ok) {
      alert("Theme save failed" + (res ? " (HTTP " + res.status + ")" : " (network)"));
    }
  });
}

function initRecentReports() {
  const btn = document.getElementById("prevRunsBtn");
  const panel = document.getElementById("recentPanel");
  const body = document.getElementById("recentBody");
  const close = document.getElementById("recentClose");
  if (!btn || !panel) return;
  async function load() {
    panel.hidden = false;
    const res = await fetch("/api/jobs");
    if (!res.ok) {
      body.textContent = "Could not load recent runs (HTTP " + res.status + "). Expected a signed-in session.";
      return;
    }
    const data = await res.json();
    const jobs = data.jobs || [];
    if (!jobs.length) {
      body.textContent = "No runs yet. Open a report and click Run.";
      return;
    }
    body.innerHTML = jobs.map((job) => {
      const kept = job.kept ? " · kept " + (job.keep_name || "") : "";
      return '<div class="recent-row"><a href="/reports/' + job.report_key + '">' + job.title + "</a>"
        + '<div class="muted">' + job.created_at + kept + "</div></div>";
    }).join("");
  }
  btn.addEventListener("click", () => {
    if (panel.hidden) load();
    else panel.hidden = true;
  });
  if (close) close.addEventListener("click", () => { panel.hidden = true; });
}

document.addEventListener("DOMContentLoaded", () => {
  if (typeof feather !== "undefined") feather.replace();
  initThemeToggle();
  initSettingsTheme();
  initRecentReports();
});

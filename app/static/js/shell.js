const THEME_ORDER = ["light", "dark", "monochrome", "monochrome_dark"];
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
    const next = THEME_ORDER[(THEME_ORDER.indexOf(currentTheme()) + 1) % THEME_ORDER.length];
    applyTheme(btn, next);
    try {
      await fetch(btn.getAttribute("data-url") || "/api/settings/theme", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theme: next }),
      });
    } catch (_err) {
      /* visual toggle already applied */
    }
  });
}

function initSettingsTheme() {
  const save = document.getElementById("settingsThemeSave");
  const select = document.getElementById("settingsTheme");
  if (!save || !select) return;
  save.addEventListener("click", async () => {
    const theme = select.value;
    applyTheme(document.getElementById("themeToggleBtn"), theme);
    await fetch("/api/settings/theme", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme }),
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  if (typeof feather !== "undefined") feather.replace();
  initThemeToggle();
  initSettingsTheme();
});

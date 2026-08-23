/** Client-side filename token preview. Matches web.delivery.filename_template. */

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export function slugFilenamePart(value: string, fallback = "Report"): string {
  return (value || "").trim().replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[._]+|[._]+$/g, "")
    || fallback;
}

export function stripReportsHome(path: string): string {
  const home = "direct reports";
  let p = (path || "").replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  while (p) {
    const low = p.toLowerCase();
    if (low === home) return "";
    if (low.startsWith(home + "/")) {
      p = p.slice(p.indexOf("/") + 1);
      continue;
    }
    return p;
  }
  return "";
}

/** Keep in sync with web.delivery.filename_template.DEFAULT_FILENAME_TEMPLATE. */
export const DEFAULT_FILENAME_TEMPLATE = "{Schedule}_{YYYY}-{MM}-{DD}_{HH}{mm}";

export function previewFilename(
  template: string,
  tokens: { report?: string; schedule?: string; period?: string },
  when: Date = new Date(),
): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const report = slugFilenamePart(tokens.report || "", "Report");
  const schedule = slugFilenamePart(tokens.schedule || "", report);
  const period = slugFilenamePart(tokens.period || "", String(when.getFullYear()));
  const map: Record<string, string> = {
    "{YYYY}": String(when.getFullYear()),
    "{YY}": String(when.getFullYear()).slice(-2),
    "{MM}": pad(when.getMonth() + 1),
    "{M}": String(when.getMonth() + 1),
    "{Month}": MONTHS[when.getMonth()],
    "{Mon}": MONTHS[when.getMonth()].slice(0, 3),
    "{DD}": pad(when.getDate()),
    "{D}": String(when.getDate()),
    "{HH}": pad(when.getHours()),
    "{mm}": pad(when.getMinutes()),
    "{ss}": pad(when.getSeconds()),
    "{Report}": report,
    "{Schedule}": schedule,
    "{Period}": period,
    "{Weekday}": WEEKDAYS[(when.getDay() + 6) % 7],
  };
  let out = (template || DEFAULT_FILENAME_TEMPLATE).replace(/\{[A-Za-z]+\}/g, (t) => map[t] || t);
  out = out.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[._]+|[._]+$/g, "") || report;
  if (!out.toLowerCase().endsWith(".xlsx")) out += ".xlsx";
  return out.slice(0, 180);
}

export function previewFolder(
  template: string,
  tokens: { report?: string; schedule?: string; period?: string },
  when: Date = new Date(),
): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const report = slugFilenamePart(tokens.report || "", "Report");
  const schedule = slugFilenamePart(tokens.schedule || "", report);
  const period = slugFilenamePart(tokens.period || "", String(when.getFullYear()));
  const map: Record<string, string> = {
    "{YYYY}": String(when.getFullYear()),
    "{YY}": String(when.getFullYear()).slice(-2),
    "{MM}": pad(when.getMonth() + 1),
    "{M}": String(when.getMonth() + 1),
    "{Month}": MONTHS[when.getMonth()],
    "{Mon}": MONTHS[when.getMonth()].slice(0, 3),
    "{DD}": pad(when.getDate()),
    "{D}": String(when.getDate()),
    "{HH}": pad(when.getHours()),
    "{mm}": pad(when.getMinutes()),
    "{ss}": pad(when.getSeconds()),
    "{Report}": report,
    "{Schedule}": schedule,
    "{Period}": period,
    "{Weekday}": WEEKDAYS[(when.getDay() + 6) % 7],
  };
  const raw = stripReportsHome((template || "").replace(/\\/g, "/"));
  if (!raw) return "Direct Reports";
  const expanded = raw.replace(/\{[A-Za-z]+\}/g, (t) => map[t] || t);
  const parts = expanded.split("/").map((s) => s.replace(/[\\:*?"<>|#%]/g, "").trim()).filter(Boolean);
  return ["Direct Reports", ...parts].join(" / ");
}

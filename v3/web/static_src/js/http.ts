/** Shared fetch helpers for schedule management pages. */

export function csrf(): string {
  const el = document.querySelector<HTMLElement>("[data-csrf]");
  return el?.getAttribute("data-csrf") || "";
}

export function jsonHeaders(): Record<string, string> {
  return { "Content-Type": "application/json", "X-CSRF-Token": csrf() };
}

export function esc(s: string): string {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

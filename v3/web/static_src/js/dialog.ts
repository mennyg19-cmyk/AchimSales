/** Dialog focus trap, Escape, and restore. Used by help, email, schedule, admin. */

export type DialogClose = () => void;

const FOCUSABLE = [
  "a[href]", "button:not([disabled])", "input:not([disabled])",
  "select:not([disabled])", "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function focusables(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => {
    if (el.closest("[hidden]")) return false;
    const style = window.getComputedStyle(el);
    return style.display !== "none" && style.visibility !== "hidden";
  });
}

export function openDialog(overlay: HTMLElement, opts?: {
  initial?: HTMLElement | null;
  onClose?: () => void;
}): DialogClose {
  const previously = document.activeElement instanceof HTMLElement
    ? document.activeElement : null;
  overlay.hidden = false;
  if (overlay.style.display === "none") overlay.style.display = "flex";
  overlay.setAttribute("aria-hidden", "false");
  const panel = overlay.querySelector<HTMLElement>(
    "[role='dialog'], .modal, .help-popup-content",
  ) || overlay;

  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
      return;
    }
    if (e.key !== "Tab") return;
    const list = focusables(panel);
    if (!list.length) return;
    const first = list[0];
    const last = list[list.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  function close(): void {
    overlay.hidden = true;
    overlay.style.display = "none";
    overlay.setAttribute("aria-hidden", "true");
    document.removeEventListener("keydown", onKey, true);
    opts?.onClose?.();
    previously?.focus?.();
  }

  document.addEventListener("keydown", onKey, true);
  (opts?.initial || focusables(panel)[0])?.focus();
  return close;
}

export function bindMenu(btn: HTMLElement, menu: HTMLElement): void {
  const items = () => [...menu.querySelectorAll<HTMLElement>("[role='menuitem']")]
    .filter((el) => !el.hasAttribute("disabled") && !(el as HTMLButtonElement).disabled);

  const onKey = (e: KeyboardEvent) => {
    if (menu.hidden) return;
    const list = items();
    if (!list.length) return;
    const i = list.indexOf(document.activeElement as HTMLElement);
    if (e.key === "Escape") {
      e.preventDefault();
      menu.hidden = true;
      btn.setAttribute("aria-expanded", "false");
      btn.focus();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      list[(i + 1) % list.length].focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      list[(i - 1 + list.length) % list.length].focus();
    } else if (e.key === "Home") {
      e.preventDefault();
      list[0].focus();
    } else if (e.key === "End") {
      e.preventDefault();
      list[list.length - 1].focus();
    }
  };
  menu.addEventListener("keydown", onKey);
}

export function hiddenPollMs(visibleMs: number): number {
  return document.hidden ? visibleMs * 4 : visibleMs;
}

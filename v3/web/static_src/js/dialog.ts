type DialogOverlay = HTMLElement;

interface DialogState {
  opener: HTMLElement | null;
  onKeydown: (event: KeyboardEvent) => void;
}

const dialogStates = new WeakMap<DialogOverlay, DialogState>();
let activeOverlay: DialogOverlay | null = null;
let isolatedElements: HTMLElement[] = [];

function dialogContent(overlay: DialogOverlay): HTMLElement {
  return overlay.querySelector<HTMLElement>('[role="dialog"], .modal, .sp-picker-modal') || overlay;
}

function focusableElements(dialog: HTMLElement): HTMLElement[] {
  return Array.from(dialog.querySelectorAll<HTMLElement>(
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )).filter((element) => !element.hidden && element.getClientRects().length > 0);
}

function isolateBackground(overlay: DialogOverlay): void {
  isolatedElements = [];
  let node: HTMLElement | null = overlay;
  while (node && node !== document.body) {
    const parent = node.parentElement;
    if (!parent) break;
    Array.from(parent.children).forEach((sibling) => {
      if (
        sibling instanceof HTMLElement
        && sibling !== node
        && sibling.tagName !== "SCRIPT"
      ) {
        sibling.inert = true;
        isolatedElements.push(sibling);
      }
    });
    node = parent;
  }
}

function restoreBackground(): void {
  isolatedElements.forEach((element) => { element.inert = false; });
  isolatedElements = [];
}

function focusInitial(dialog: HTMLElement): void {
  const target = dialog.querySelector<HTMLElement>("[data-dialog-initial-focus], [autofocus]")
    || focusableElements(dialog)[0];
  if (target) target.focus();
  else {
    dialog.tabIndex = -1;
    dialog.focus();
  }
}

export function openDialog(overlay: DialogOverlay, opener: HTMLElement | null = document.activeElement as HTMLElement | null): void {
  if (activeOverlay && activeOverlay !== overlay) closeDialog(activeOverlay, false);
  const dialog = dialogContent(overlay);
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  overlay.hidden = false;
  overlay.style.display = "flex";
  isolateBackground(overlay);
  const onKeydown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeDialog(overlay);
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = focusableElements(dialog);
    if (!focusable.length) {
      event.preventDefault();
      dialog.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };
  dialogStates.set(overlay, { opener, onKeydown });
  activeOverlay = overlay;
  document.addEventListener("keydown", onKeydown);
  requestAnimationFrame(() => focusInitial(dialog));
}

export function closeDialog(overlay: DialogOverlay, restoreFocus = true): void {
  const state = dialogStates.get(overlay);
  if (state) document.removeEventListener("keydown", state.onKeydown);
  overlay.hidden = true;
  overlay.style.display = "none";
  if (activeOverlay === overlay) {
    activeOverlay = null;
    restoreBackground();
  }
  dialogStates.delete(overlay);
  if (restoreFocus && state?.opener?.isConnected) state.opener.focus();
}

declare global {
  interface Window {
    dialogs: { open: typeof openDialog; close: typeof closeDialog };
  }
}

window.dialogs = { open: openDialog, close: closeDialog };

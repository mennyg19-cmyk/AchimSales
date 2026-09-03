export function isHidden(): boolean {
  return document.visibilityState === "hidden";
}

export function onVisible(fn: () => void): void {
  document.addEventListener("visibilitychange", () => {
    if (!isHidden()) fn();
  });
}

export function sleepUntilVisible(ms: number): Promise<void> {
  return new Promise((resolve) => {
    const timer = window.setTimeout(done, ms);
    function done(): void {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", wake);
      resolve();
    }
    function wake(): void {
      if (!isHidden()) done();
    }
    document.addEventListener("visibilitychange", wake);
  });
}

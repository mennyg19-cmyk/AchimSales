"""HTTP clients for live (/) and /test report run + Excel download."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

log = logging.getLogger("parity")

_CSRF_RE = re.compile(
    r'(?:name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)|'
    r'data-csrf=["\']([^"\']+)|'
    r'"csrf_token"\s*:\s*"([^"]+))',
    re.I,
)


class ParityError(RuntimeError):
    pass


class HttpClient:
    def __init__(self, base_url: str, timeout: float = 60.0):
        self.base = base_url.rstrip("/") + "/"
        self.host = urlparse(self.base).hostname or ""
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "AchimSales-parity/1.0"})

    def url(self, path: str) -> str:
        return urljoin(self.base, path.lstrip("/"))

    def get(self, path: str, **kw) -> requests.Response:
        return self.session.get(self.url(path), timeout=self.timeout, **kw)

    def post(self, path: str, **kw) -> requests.Response:
        return self.session.post(self.url(path), timeout=self.timeout, **kw)

    def set_cookie(self, name: str, value: str, *, path: str = "/") -> None:
        raw = (value or "").strip()
        # Accept "session=..." or bare value.
        if raw.lower().startswith(name.lower() + "="):
            raw = raw.split("=", 1)[1]
        # Strip wrapping quotes browsers sometimes add on copy.
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
            raw = raw[1:-1]
        # Prefer an explicit Cookie header — requests' jar often drops host-only
        # Secure cookies depending on domain attributes.
        existing = self.session.headers.get("Cookie", "")
        parts = [p for p in existing.split("; ") if p and not p.startswith(name + "=")]
        parts.append(f"{name}={raw}")
        self.session.headers["Cookie"] = "; ".join(parts)
        log.debug("Cookie header set %s (len=%d)", name, len(raw))

    def _assert_not_login_redirect(self, r: requests.Response, side: str) -> None:
        if r.status_code in (401, 403):
            raise ParityError(f"{side} auth failed (HTTP {r.status_code})")
        if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location", "")
            if "login" in loc.lower() or "microsoftonline" in loc.lower():
                raise ParityError(
                    f"{side} cookie was rejected (redirected to login). "
                    "Copy a fresh cookie value from Application → Cookies while "
                    "signed in, then retry."
                )


# Live multi-file runs (salesman, customer_activity) write a master workbook
# plus individuals. Prefer the master for parity even when History still
# points primary at newest-mtime (often one salesman).
_LIVE_CANONICAL_NEEDLE = {
    "salesman": "Monthly Salesmen Report",
    "customer_activity": "Customer_Activity_All_",
}


def _live_download_target(
    report_key: str,
    candidates: list[tuple[str, int | None, str]],
) -> tuple[str, int | None, str]:
    """Pick which History file to download: ('primary', None, name) or ('extra', idx, name)."""
    if not candidates:
        return "primary", None, ""
    needle = _LIVE_CANONICAL_NEEDLE.get(report_key)
    if needle:
        for mode, idx, name in candidates:
            if needle in name:
                return mode, idx, name
    return candidates[0]


def _candidates_from_result(result: dict[str, Any] | None) -> list[tuple[str, int | None, str]]:
    result = result or {}
    primary_name = str(result.get("filename") or "")
    candidates: list[tuple[str, int | None, str]] = [("primary", None, primary_name)]
    for i, ef in enumerate(result.get("extra_files") or []):
        if isinstance(ef, dict):
            candidates.append(("extra", i, str(ef.get("filename") or "")))
    return candidates


def _candidates_from_history_html(html: str, run_id: str) -> list[tuple[str, int | None, str]]:
    """Parse /history/view HTML for primary + extra download filenames."""
    candidates: list[tuple[str, int | None, str]] = []
    m = re.search(
        rf'/history/download/{re.escape(run_id)}"[^>]*title="([^"]+)"',
        html,
        re.I,
    )
    if m:
        candidates.append(("primary", None, m.group(1)))
    for m in re.finditer(
        rf'/history/download-extra/{re.escape(run_id)}/(\d+)"[^>]*title="([^"]+)"',
        html,
        re.I,
    ):
        candidates.append(("extra", int(m.group(1)), m.group(2)))
    return candidates


class LiveClient(HttpClient):
    """Live webapp at / — OData reports."""

    def login_dev(self) -> None:
        r = self.post("/dev-login", data={"role": "admin"}, allow_redirects=True)
        if r.status_code >= 400:
            raise ParityError(f"live dev-login failed: HTTP {r.status_code}")
        if "session" not in self.session.cookies:
            # Cookie may be HttpOnly and still set; verify with a protected page.
            check = self.get("/reports")
            if check.status_code in (401, 403) or "/login" in check.url:
                raise ParityError("live dev-login did not establish a session")

    def login_cookie(self, cookie: str) -> None:
        self.set_cookie("session", cookie, path="/")

    def run_and_download(self, report_key: str, params: dict, dest: Path,
                         poll_seconds: float = 5.0, timeout_seconds: float = 1800.0) -> Path:
        r = self.post(f"/report/{report_key}/run", json=params, allow_redirects=False)
        self._assert_not_login_redirect(r, "live")
        if r.status_code >= 400:
            raise ParityError(f"live run {report_key}: HTTP {r.status_code} {r.text[:300]}")
        try:
            body = r.json()
        except Exception as exc:
            raise ParityError(
                f"live run {report_key}: expected JSON, got HTTP {r.status_code} "
                f"(cookie may be wrong). Body starts: {(r.text or '')[:120]!r}"
            ) from exc
        run_id = body.get("run_id")
        if not run_id:
            raise ParityError(f"live run {report_key}: no run_id in {body!r}")

        deadline = time.monotonic() + timeout_seconds
        result: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            p = self.get(f"/report/progress/{run_id}")
            p.raise_for_status()
            state = p.json()
            step = state.get("step")
            log.info("live %s progress: %s %s%% %s", report_key, step, state.get("pct"), state.get("msg"))
            if step == "done":
                result = state.get("result") or {"success": True}
                break
            if step == "error":
                err = (state.get("result") or {}).get("error") or state.get("msg")
                raise ParityError(f"live {report_key} failed: {err}")
            time.sleep(poll_seconds)
        else:
            raise ParityError(f"live {report_key} timed out after {timeout_seconds}s")

        if result and result.get("success") is False:
            raise ParityError(f"live {report_key} failed: {result.get('error')}")

        candidates = _candidates_from_result(result)
        needle = _LIVE_CANONICAL_NEEDLE.get(report_key)
        # Azure multi-worker: progress often comes from DB without extras.
        if needle and not any(needle in name for _, _, name in candidates):
            hv = self.get(f"/history/view/{run_id}")
            if hv.status_code == 200 and "text/html" in hv.headers.get("Content-Type", ""):
                scraped = _candidates_from_history_html(hv.text or "", run_id)
                if scraped:
                    log.info(
                        "live %s: progress had no master filename; history view lists %d file(s)",
                        report_key, len(scraped),
                    )
                    candidates = scraped

        mode, extra_idx, picked_name = _live_download_target(report_key, candidates)
        if mode == "extra" and extra_idx is not None:
            log.info(
                "live %s: downloading master/extra file %r (idx %d), not primary %r",
                report_key, picked_name, extra_idx, result.get("filename") if result else None,
            )
            dl = self.get(f"/history/download-extra/{run_id}/{extra_idx}")
        else:
            if picked_name:
                log.info("live %s: downloading primary %r", report_key, picked_name)
            dl = self.get(f"/history/download/{run_id}")
        if dl.status_code >= 400:
            # Fallback: latest download by report key
            dl = self.get(f"/report/{report_key}/download")
        if dl.status_code >= 400 or "text/html" in dl.headers.get("Content-Type", ""):
            raise ParityError(
                f"live {report_key}: could not download Excel "
                f"(HTTP {dl.status_code}). Check history for run {run_id}."
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(dl.content)
        log.info("live %s saved %s (%d bytes) name=%r", report_key, dest, dest.stat().st_size, picked_name)
        return dest


class TestClient(HttpClient):
    """v3 app mounted at /test — Reporting API path."""

    def __init__(self, base_url: str, mount: str = "/test", timeout: float = 60.0):
        super().__init__(base_url, timeout=timeout)
        self.mount = mount.rstrip("/") or "/test"
        self._csrf: str | None = None

    def _m(self, path: str) -> str:
        return f"{self.mount}{path}"

    def login_dev(self, email: str = "parity-admin@localhost", role: str = "developer") -> None:
        # Establish session + CSRF first
        self.get(self._m("/login"))
        self._refresh_csrf()
        r = self.post(
            self._m("/login/dev"),
            data={"email": email, "role": role, "csrf_token": self._csrf or ""},
            headers=self._csrf_headers(),
            allow_redirects=True,
        )
        if r.status_code >= 400:
            raise ParityError(f"/test dev-login failed: HTTP {r.status_code} {r.text[:200]}")
        self._refresh_csrf()

    def login_cookie(self, cookie: str) -> None:
        self.set_cookie("v3_session", cookie)
        # Don't hit /test yet — verify cookie on first API call after CSRF fetch.

    def _csrf_headers(self) -> dict[str, str]:
        if not self._csrf:
            return {}
        return {"X-CSRF-Token": self._csrf}

    def _refresh_csrf(self) -> None:
        r = self.get(self._m("/"), allow_redirects=False)
        self._assert_not_login_redirect(r, "/test")
        if r.status_code in (301, 302, 303, 307, 308):
            # Follow only same-host redirects (not Microsoft login).
            loc = r.headers.get("Location", "")
            if loc.startswith("/") or self.host in loc:
                r = self.session.get(self.url(loc) if loc.startswith("/") else loc,
                                     timeout=self.timeout, allow_redirects=False)
                self._assert_not_login_redirect(r, "/test")
        m = _CSRF_RE.search(r.text or "")
        if m:
            self._csrf = next(g for g in m.groups() if g)
            return
        r = self.get(self._m("/login"), allow_redirects=False)
        self._assert_not_login_redirect(r, "/test")
        m = _CSRF_RE.search(r.text or "")
        if m:
            self._csrf = next(g for g in m.groups() if g)

    def run_and_download(self, report_key: str, params: dict, dest: Path,
                         poll_seconds: float = 5.0, timeout_seconds: float = 1800.0) -> Path:
        self._refresh_csrf()
        r = self.post(
            self._m(f"/api/reports/{report_key}/run"),
            json=params,
            headers={**self._csrf_headers(), "Content-Type": "application/json"},
            allow_redirects=False,
        )
        self._assert_not_login_redirect(r, "/test")
        if r.status_code == 400 and "csrf" in (r.text or "").lower():
            self._refresh_csrf()
            r = self.post(
                self._m(f"/api/reports/{report_key}/run"),
                json=params,
                headers={**self._csrf_headers(), "Content-Type": "application/json"},
                allow_redirects=False,
            )
            self._assert_not_login_redirect(r, "/test")
        if r.status_code >= 400:
            raise ParityError(f"/test run {report_key}: HTTP {r.status_code} {r.text[:300]}")
        try:
            job_id = r.json().get("job_id")
        except Exception as exc:
            raise ParityError(
                f"/test run {report_key}: expected JSON, got HTTP {r.status_code}"
            ) from exc
        if not job_id:
            raise ParityError(f"/test run {report_key}: no job_id")

        self._wait_job(job_id, label=f"/test {report_key} run",
                       poll_seconds=poll_seconds, timeout_seconds=timeout_seconds)

        self._refresh_csrf()
        er = self.post(
            self._m(f"/api/reports/{report_key}/export/{job_id}"),
            json={},
            headers={**self._csrf_headers(), "Content-Type": "application/json"},
        )
        if er.status_code >= 400:
            raise ParityError(f"/test export {report_key}: HTTP {er.status_code} {er.text[:300]}")
        export_id = er.json().get("export_id")
        if not export_id:
            raise ParityError(f"/test export {report_key}: no export_id")

        self._wait_job(export_id, label=f"/test {report_key} export",
                       poll_seconds=poll_seconds, timeout_seconds=timeout_seconds)

        dl = self.get(self._m(f"/api/reports/exports/{export_id}/download"))
        if dl.status_code >= 400:
            raise ParityError(f"/test download {report_key}: HTTP {dl.status_code}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(dl.content)
        log.info("/test %s saved %s (%d bytes)", report_key, dest, dest.stat().st_size)
        return dest

    def _wait_job(self, job_id: str, *, label: str,
                  poll_seconds: float, timeout_seconds: float) -> None:
        deadline = time.monotonic() + timeout_seconds
        transient_streak = 0
        while time.monotonic() < deadline:
            p = self.get(self._m(f"/api/jobs/{job_id}"))
            # Azure sometimes returns 502/503 while the app is busy; keep polling.
            if p.status_code in (502, 503, 504):
                transient_streak += 1
                if transient_streak > 30:
                    p.raise_for_status()
                log.warning("%s: HTTP %s on job poll (retry %s)", label, p.status_code, transient_streak)
                time.sleep(poll_seconds)
                continue
            transient_streak = 0
            p.raise_for_status()
            state = p.json()
            status = state.get("status")
            log.info("%s: status=%s progress=%s", label, status, state.get("progress"))
            if status == "success":
                return
            if status in ("failure", "failed", "cancelled", "error"):
                raise ParityError(f"{label} ended {status}: {state.get('error')}")
            time.sleep(poll_seconds)
        raise ParityError(f"{label} timed out after {timeout_seconds}s")

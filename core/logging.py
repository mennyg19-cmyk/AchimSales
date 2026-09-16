"""
Structured logging setup. Azure-safe (no emoji), consistent format.

Call setup_logging() once at entry point. All modules use standard
logging.getLogger(__name__).
"""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with a clean, Azure-safe format."""
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(handler)
    root.setLevel(level)


_mem_log = logging.getLogger("memory")

def log_memory(label: str) -> None:
    """Log current process RSS memory usage. Works on Linux (Azure) and Windows."""
    try:
        import os
        pid = os.getpid()
        # Linux: read from /proc (Azure Automation sandbox is Linux)
        try:
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss_kb = int(line.split()[1])
                        rss_mb = rss_kb / 1024
                        level = logging.WARNING if rss_mb > 300 else logging.INFO
                        _mem_log.log(level, "[MEMORY] %s: %.0f MB RSS%s",
                                     label, rss_mb,
                                     " ** HIGH - approaching 400MB sandbox limit **" if rss_mb > 300 else "")
                        return
        except FileNotFoundError:
            pass
        # Windows fallback
        try:
            import psutil
            proc = psutil.Process(pid)
            rss_mb = proc.memory_info().rss / (1024 * 1024)
            _mem_log.info("[MEMORY] %s: %.0f MB RSS", label, rss_mb)
        except ImportError:
            pass
    except Exception:
        pass

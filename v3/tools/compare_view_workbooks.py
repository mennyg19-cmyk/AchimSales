"""Retired. Report format is stored on the views tables, not layout_json.

The old-vs-new workbook compare has nothing left to compare.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    del argv
    print(
        "Old JSON view tables are retired. Report format is read from the views tables. "
        "This compare tool no longer runs.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

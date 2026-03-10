"""
Shared Excel writing utilities.

Provides memory-safe streaming writer, autosize, header styling,
and sheet-copy helpers used by all report writers.
"""

import logging
import math
from copy import copy as shallow_copy

import pandas as pd
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.utils import get_column_letter

from core.excel_styles import (
    ALIGN_CENTER,
    BORDER_THIN,
    FILL_HEADER,
    FMT_CURRENCY,
    FMT_DATE,
    FONT_HEADER,
)

log = logging.getLogger(__name__)

STREAMING_ROW_THRESHOLD = 2000


def should_stream(row_count: int) -> bool:
    """Whether to use write_only mode for this row count."""
    return row_count > STREAMING_ROW_THRESHOLD


def autosize_columns(ws, max_width: int = 60, min_width: int = 10) -> None:
    """Auto-size columns based on content width."""
    widths: dict[int, int] = {}
    for row in ws.iter_rows(values_only=True):
        for i, v in enumerate(row, start=1):
            if v is None:
                continue
            widths[i] = max(widths.get(i, 0), min(len(str(v)), max_width))
    for col_idx, w in widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = max(min_width, w + 2)


def apply_header_style(ws, row: int = 1) -> None:
    """Apply bold centered header style to a row and freeze panes below it."""
    for cell in ws[row]:
        cell.font = FONT_HEADER
        cell.alignment = ALIGN_CENTER
    ws.freeze_panes = f"A{row + 1}"


def format_money_columns(ws, money_keywords: set[str] | None = None, header_row: int = 1) -> None:
    """Apply currency format to columns whose headers match money keywords."""
    if money_keywords is None:
        money_keywords = {
            "subtotal invoices", "tariff charges", "freight charges", "cc charges",
            "total invoice", "sales", "freight", "cc", "tariff", "commissions",
            "total invoices", "totnofrt",
        }

    headers: dict[str, int] = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(row=header_row, column=c).value
        if v is not None:
            headers[str(v).strip().lower()] = c

    for key, col in headers.items():
        if "count" in key:
            continue
        if key in money_keywords or any(kw in key for kw in ("charge", "invoice", "sales", "tot")):
            for r in range(header_row + 1, ws.max_row + 1):
                cell = ws.cell(row=r, column=col)
                if isinstance(cell.value, (int, float)) and not math.isnan(cell.value):
                    cell.number_format = FMT_CURRENCY


def make_streaming_cell(ws, value, fill=None, font=None, border=None, fmt=None) -> WriteOnlyCell:
    """Create a WriteOnlyCell with optional styling."""
    cell = WriteOnlyCell(ws, value=value)
    if fill:
        cell.fill = fill
    if font:
        cell.font = font
    if border:
        cell.border = border
    if fmt:
        cell.number_format = fmt
    return cell


def write_header_row_streaming(ws, columns: list[str]) -> None:
    """Write a styled header row in streaming mode."""
    cells = [
        make_streaming_cell(ws, col, fill=FILL_HEADER, font=FONT_HEADER, border=BORDER_THIN)
        for col in columns
    ]
    ws.append(cells)


def write_totals_row_streaming(ws, columns: list[str], data: dict[str, float], currency_cols: set[str]) -> None:
    """Write a totals row in streaming mode."""
    cells = []
    for col in columns:
        if col == columns[0]:
            val = "Total"
        elif col in data:
            val = data[col]
        else:
            val = ""
        fmt = FMT_CURRENCY if col in currency_cols else None
        cells.append(make_streaming_cell(ws, val, fill=FILL_HEADER, font=FONT_HEADER, border=BORDER_THIN, fmt=fmt))
    ws.append(cells)


def copy_worksheet(src_ws, dst_ws) -> None:
    """Copy a worksheet's content and styles into an existing destination worksheet."""
    for col_letter, dim in src_ws.column_dimensions.items():
        try:
            dst_ws.column_dimensions[col_letter].width = dim.width
        except Exception:
            log.debug("Could not copy column width for %s", col_letter, exc_info=True)

    for row_idx, row_dim in src_ws.row_dimensions.items():
        try:
            dst_ws.row_dimensions[row_idx].height = row_dim.height
        except Exception:
            log.debug("Could not copy row height for row %s", row_idx, exc_info=True)

    for mrange in list(src_ws.merged_cells.ranges):
        try:
            dst_ws.merge_cells(str(mrange))
        except Exception:
            log.debug("Could not merge cells %s", mrange, exc_info=True)

    for row in src_ws.iter_rows():
        for cell in row:
            dst = dst_ws.cell(row=cell.row, column=cell.column, value=cell.value)
            if cell.has_style:
                dst.font = shallow_copy(cell.font)
                dst.fill = shallow_copy(cell.fill)
                dst.border = shallow_copy(cell.border)
                dst.alignment = shallow_copy(cell.alignment)
                dst.number_format = cell.number_format
                dst.protection = shallow_copy(cell.protection)

    try:
        dst_ws.freeze_panes = src_ws.freeze_panes
    except Exception:
        log.debug("Could not copy freeze_panes setting", exc_info=True)


def strip_datetime_tz(df: pd.DataFrame) -> pd.DataFrame:
    """Convert tz-aware datetime columns to naive for Excel compatibility."""
    for col in df.columns:
        try:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                if hasattr(df[col].dtype, "tz") and df[col].dtype.tz is not None:
                    df[col] = df[col].dt.tz_localize(None)
        except Exception:
            log.debug("Could not strip timezone from column %s", col, exc_info=True)
    return df

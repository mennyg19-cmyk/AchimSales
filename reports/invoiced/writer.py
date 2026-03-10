"""
Invoiced Report Excel writer.

Produces multi-sheet workbooks for MTD and Daily reports:
  Summary by Customer, Commissions, Full Details, Credits, Invoices, Audit
"""

import logging
import math
import os

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from core.excel_styles import (
    BORDER_THIN,
    FILL_HEADER,
    FILL_HEADER_BLUE,
    FMT_CURRENCY,
    FONT_HEADER,
)
from core.excel_writer import autosize_columns, format_money_columns, strip_datetime_tz

log = logging.getLogger(__name__)


def write_invoiced_report(
    summary: pd.DataFrame,
    commissions: pd.DataFrame,
    details: pd.DataFrame,
    credits: pd.DataFrame,
    invoices: pd.DataFrame,
    audit: pd.DataFrame | None,
    out_path: str,
    *,
    year: int | None = None,
    full_detail: pd.DataFrame | None = None,
    ytd_credits: pd.DataFrame | None = None,
    ytd_invoices: pd.DataFrame | None = None,
    pct_map: dict[str, float] | None = None,
    current_month: int | None = None,
) -> None:
    """Write the Invoiced Report workbook."""
    log.info("Writing Invoiced Excel: %d summary, %d detail, %d invoice rows",
             len(summary), len(details), len(invoices))
    wb = Workbook()

    log.info("  Writing sheet: Summary by Customer (%d rows)", len(summary))
    _write_data_sheet(wb, "Summary by Customer", summary, is_first=True)

    if year is not None and full_detail is not None and pct_map is not None:
        log.info("  Writing sheet: Commissions (legacy monthly format)")
        comm_credits = ytd_credits if ytd_credits is not None else credits
        comm_invoices = ytd_invoices if ytd_invoices is not None else invoices
        _write_commissions_sheet(wb, year, full_detail, comm_credits, comm_invoices, pct_map,
                                 current_month=current_month)
    else:
        log.info("  Writing sheet: Commissions (fallback -- no monthly data)")
        _write_commissions_sheet_simple(wb, commissions)

    log.info("  Writing sheet: Full Details (%d rows)", len(details))
    _write_data_sheet(wb, "Full Details", details)
    log.info("  Writing sheet: Credits (%d rows)", len(credits))
    _write_data_sheet(wb, "Credits", credits)
    log.info("  Writing sheet: Invoices (%d rows)", len(invoices))
    _write_data_sheet(wb, "Invoices", invoices)

    if audit is not None and not audit.empty:
        log.info("  Writing sheet: Audit - Reversals (%d rows)", len(audit))
        _write_data_sheet(wb, "Audit - Reversals", audit)

    wb.save(out_path)
    try:
        size_kb = os.path.getsize(out_path) / 1024
        log.info("Excel saved: %.0f KB -- %s", size_kb, out_path)
    except OSError:
        log.info("Wrote: %s", out_path)


def _write_commissions_sheet_simple(wb: Workbook, comm_df: pd.DataFrame) -> None:
    """Fallback: simple commissions sheet when monthly data is not available."""
    ws = wb.create_sheet(title="Commissions")
    if comm_df.empty or "SalesmanNumber" not in comm_df.columns:
        ws.cell(row=1, column=1, value="No commission data")
        return
    commissioned = comm_df[comm_df["Percent"] > 0].copy()
    if commissioned.empty:
        ws.cell(row=1, column=1, value="No commissioned salesmen")
        return
    ws.cell(row=1, column=1, value="Commissions Summary")
    ws.cell(row=1, column=1).font = Font(bold=True, size=14)
    row = 3
    for sm_num, grp in commissioned.groupby("SalesmanNumber", sort=True):
        sm_name = grp["SalesmanName"].iloc[0] if "SalesmanName" in grp.columns else ""
        pct = grp["Percent"].iloc[0]
        ws.cell(row=row, column=1, value=f"Salesman #{sm_num} - {sm_name}")
        ws.cell(row=row, column=1).font = Font(bold=True, size=11)
        ws.cell(row=row, column=3, value=f"{pct:.0%}")
        row += 1
        sub_total = grp["SubTotal Invoices"].sum() if "SubTotal Invoices" in grp.columns else 0
        tariff_total = grp["Total Tariff Charges"].sum() if "Total Tariff Charges" in grp.columns else 0
        freight_total = grp["Total Freight Charges"].sum() if "Total Freight Charges" in grp.columns else 0
        cc_total = grp["Total CC Charges"].sum() if "Total CC Charges" in grp.columns else 0
        inv_total = grp["Total Invoices"].sum() if "Total Invoices" in grp.columns else 0
        net = sub_total + tariff_total
        commission = net * pct
        for label, val in [("SubTotal Invoices", sub_total), ("Total Tariff Charges", tariff_total),
                           ("Total Freight Charges", freight_total), ("Total CC Charges", cc_total),
                           ("Total Invoices", inv_total), ("Net Commission Amount", net), ("Commission", commission)]:
            ws.cell(row=row, column=1, value=label)
            ws.cell(row=row, column=2, value=val).number_format = FMT_CURRENCY
            row += 1
        row += 1
    autosize_columns(ws)


def _write_data_sheet(wb: Workbook, title: str, df: pd.DataFrame, is_first: bool = False) -> None:
    """Write a simple data sheet with header styling and money formatting."""
    if is_first:
        ws = wb.active
        ws.title = title
    else:
        ws = wb.create_sheet(title=title)

    if df.empty:
        ws.cell(row=1, column=1, value="No data")
        return

    df = strip_datetime_tz(df.copy())
    cols = [c for c in df.columns if not c.startswith("_")]

    for c_idx, col in enumerate(cols, 1):
        cell = ws.cell(row=1, column=c_idx, value=col)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER_BLUE
        cell.border = BORDER_THIN

    for r_idx, (_, row) in enumerate(df.iterrows(), 2):
        for c_idx, col in enumerate(cols, 1):
            v = row.get(col, "")
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                v = 0.0
            cell = ws.cell(row=r_idx, column=c_idx, value=v)
            cell.border = BORDER_THIN

    totals_row = len(df) + 2
    money_cols = {"SubTotal Invoices", "Total Tariff Charges", "Total Freight Charges",
                  "Total CC Charges", "Total Invoices", "Total Invoice",
                  "Tariff Charges", "Freight Charges", "CC Charges", "Commissions", "Commission Base"}
    for c_idx, col in enumerate(cols, 1):
        if col in money_cols and col in df.columns:
            val = pd.to_numeric(df[col], errors="coerce").fillna(0).sum()
            cell = ws.cell(row=totals_row, column=c_idx, value=val)
            cell.number_format = FMT_CURRENCY
            cell.font = FONT_HEADER
        elif c_idx == 1:
            ws.cell(row=totals_row, column=c_idx, value="Total").font = FONT_HEADER

    format_money_columns(ws, money_cols)
    autosize_columns(ws)
    ws.freeze_panes = "A2"
    if ws.max_row > 1:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{ws.max_row}"


def _write_commissions_sheet(
    wb: Workbook,
    year: int,
    detail_df: pd.DataFrame,
    credits_df: pd.DataFrame,
    invoices_df: pd.DataFrame,
    pct_map: dict[str, float],
    *,
    current_month: int | None = None,
) -> None:
    """Write the Commissions sheet with monthly columns up to current_month."""
    import re
    from datetime import datetime as dt

    from openpyxl.utils import get_column_letter

    from reports.invoiced._commissions_styles import (
        COMMISSIONS_BLOCK_STYLE_MAP,
        COMMISSIONS_COL_WIDTHS,
        COMMISSIONS_TOP_MERGES,
        COMMISSIONS_TOP_STYLE_MAP,
        apply_commissions_style,
        build_commissions_styles,
    )

    ws = wb.create_sheet(title="Commissions")

    num_months = current_month if current_month and 1 <= current_month <= 12 else 12
    ytd_col = 4 + num_months  # column index for the YTD Total column

    for col_letter, width in COMMISSIONS_COL_WIDTHS.items():
        if width is not None:
            ws.column_dimensions[col_letter].width = width

    for rng in COMMISSIONS_TOP_MERGES:
        try:
            ws.merge_cells(rng)
        except Exception:
            pass

    built_styles = build_commissions_styles()

    for (r, c, sid) in COMMISSIONS_TOP_STYLE_MAP:
        apply_commissions_style(ws, r, c, sid, built_styles)

    ws["B2"].value = f"Commissions Summary ({year})"
    ws.row_dimensions[2].height = 18.0

    def _norm_smn(v) -> str:
        s = str(v).strip()
        if re.fullmatch(r"\d+", s or ""):
            return str(int(s))
        return s

    commissioned = [(k, v) for k, v in pct_map.items() if float(v or 0) > 0]
    commissioned.sort(key=lambda x: int(x[0]) if str(x[0]).isdigit() else str(x[0]))

    if not commissioned:
        ws.cell(row=4, column=2, value="No commissioned salesmen")
        return

    smn_to_name: dict[str, str] = {}
    smn_col_name = "SalesmanNumber" if "SalesmanNumber" in detail_df.columns else None
    name_col_name = "SalesmanName" if "SalesmanName" in detail_df.columns else None
    if smn_col_name and name_col_name:
        tmp = detail_df.copy()
        tmp["_smn"] = tmp[smn_col_name].map(_norm_smn)
        for smn, grp in tmp.groupby("_smn", dropna=False):
            nm = grp[name_col_name].astype(str).str.strip()
            nm = nm[nm != ""]
            if len(nm):
                smn_to_name[str(smn)] = nm.iloc[0]

    det = detail_df.copy()
    crd = credits_df.copy()
    inv = invoices_df.copy()

    def _coerce_month(series):
        return pd.to_datetime(series, errors="coerce").dt.month

    date_col_map = {}
    for label, df in [("det", det), ("crd", crd), ("inv", inv)]:
        for c in ["InvoiceDate", "Invoice Date", "InvoiceDate1", "Date"]:
            if c in df.columns:
                date_col_map[label] = c
                break

    if "det" in date_col_map:
        det["_month"] = _coerce_month(det[date_col_map["det"]])
    else:
        det["_month"] = pd.NA
    if "crd" in date_col_map:
        crd["_month"] = _coerce_month(crd[date_col_map["crd"]])
    else:
        crd["_month"] = pd.NA
    if "inv" in date_col_map:
        inv["_month"] = _coerce_month(inv[date_col_map["inv"]])
    else:
        inv["_month"] = pd.NA

    def _sum_month(df_src, smn_key, col):
        if df_src is None or df_src.empty or col not in df_src.columns:
            return [0.0] * num_months
        smn_c = "SalesmanNumber" if "SalesmanNumber" in df_src.columns else None
        if not smn_c:
            return [0.0] * num_months
        tmp2 = df_src.copy()
        tmp2["_smn"] = tmp2[smn_c].map(_norm_smn)
        tmp2 = tmp2[tmp2["_smn"] == _norm_smn(smn_key)]
        if tmp2.empty:
            return [0.0] * num_months
        g = tmp2.groupby("_month")[col].sum()
        return [float(g.get(m, 0.0) or 0.0) for m in range(1, num_months + 1)]

    def _find_col(df_src, candidates):
        if df_src is None or df_src.empty:
            return None
        norm = {str(c).strip().lower().replace(" ", "").replace("_", ""): c for c in df_src.columns}
        for cand in candidates:
            key = cand.strip().lower().replace(" ", "").replace("_", "")
            if key in norm:
                return norm[key]
        return None

    _row_style_map: dict[int, list[tuple[int, int]]] = {}
    for rr, c, sid in COMMISSIONS_BLOCK_STYLE_MAP:
        _row_style_map.setdefault(int(rr), []).append((int(c), int(sid)))

    def _apply_style_row(dst_abs_row, template_rel_row):
        for c, sid in _row_style_map.get(int(template_rel_row), []):
            apply_commissions_style(ws, dst_abs_row, c, sid, built_styles)

    start_row = 4
    block_height = 11

    for idx, (smn_key, pct) in enumerate(commissioned):
        r0 = start_row + idx * block_height
        smn = _norm_smn(smn_key)
        name = smn_to_name.get(smn, "")

        _apply_style_row(r0 + 0, 0)
        for k in range(1, 7):
            _apply_style_row(r0 + k, 1)
        _apply_style_row(r0 + 7, 6)
        _apply_style_row(r0 + 8, 7)
        _apply_style_row(r0 + 9, 8)
        _apply_style_row(r0 + 10, 9)

        ws.row_dimensions[r0 + 8].height = 15.0
        ws.row_dimensions[r0 + 9].height = 15.0

        ws.cell(r0, 2).value = f"{smn} - {name}".strip(" -")
        ws.cell(r0, ytd_col).value = "YTD Total"

        for mi in range(1, num_months + 1):
            ws.cell(r0, 3 + mi).value = dt(year, mi, 1)

        labels = [
            "SubTotal Invoices:",
            "Total Tariff Charges:",
            "Total Freight Charges:",
            "Total CC Charges:",
            "Total Invoices: (SubTotal+Tariff+Freight+CC)",
            "Total Credits:",
            "Net Commission Amount (Less Freight and CC)",
            "Commission:",
        ]
        for i, lab in enumerate(labels, start=1):
            ws.cell(r0 + i, 2).value = lab

        sub_row = r0 + 1
        tar_row = r0 + 2
        fre_row = r0 + 3
        cc_row = r0 + 4
        totinv_row = r0 + 5
        cred_row = r0 + 6
        net_row = r0 + 7
        comm_row = r0 + 8
        pay_row = r0 + 9

        ws.cell(comm_row, 3).value = float(pct or 0)

        subtotal_col = _find_col(inv, ["SubTotal Invoices", "SubTotal", "Subtotal", "Sub Total", "SubTotalAmount"])
        tariff_col = _find_col(det, ["Tariff Charges", "Tariff", "TariffCharge"])
        freight_col = _find_col(det, ["Freight Charges", "Freight", "FreightCharge"])
        cc_col = _find_col(det, ["CC Charges", "CC", "Credit Card Charges", "CCCharge"])
        credits_col = _find_col(crd, ["Total Invoice", "Total Invoices", "Total", "Amount"])

        subtotal = _sum_month(inv, smn, subtotal_col) if subtotal_col else [0.0] * num_months
        tariff = _sum_month(det, smn, tariff_col) if tariff_col else [0.0] * num_months
        freight = _sum_month(det, smn, freight_col) if freight_col else [0.0] * num_months
        cc = _sum_month(det, smn, cc_col) if cc_col else [0.0] * num_months
        credits_vals = _sum_month(crd, smn, credits_col) if credits_col else [0.0] * num_months

        last_data_col = 3 + num_months  # last month data column
        first_data_cl = get_column_letter(4)
        last_data_cl = get_column_letter(last_data_col)
        ytd_cl = get_column_letter(ytd_col)

        base_rows = {
            sub_row: subtotal,
            tar_row: tariff,
            fre_row: freight,
            cc_row: cc,
            cred_row: credits_vals,
        }
        for rr, vals in base_rows.items():
            for mi in range(num_months):
                ws.cell(rr, 4 + mi).value = float(vals[mi] or 0.0)
            ws.cell(rr, ytd_col).value = f"=SUM({first_data_cl}{rr}:{last_data_cl}{rr})"

        for col in range(4, ytd_col):
            cl = get_column_letter(col)
            ws.cell(totinv_row, col).value = f"={cl}{sub_row}+{cl}{tar_row}+{cl}{fre_row}+{cl}{cc_row}"
        ws.cell(totinv_row, ytd_col).value = f"=SUM({first_data_cl}{totinv_row}:{last_data_cl}{totinv_row})"

        for col in range(4, ytd_col):
            cl = get_column_letter(col)
            ws.cell(net_row, col).value = f"={cl}{totinv_row}+{cl}{cred_row}-{cl}{fre_row}-{cl}{cc_row}"
        ws.cell(net_row, ytd_col).value = f"=SUM({first_data_cl}{net_row}:{last_data_cl}{net_row})"

        for col in range(4, ytd_col):
            cl = get_column_letter(col)
            ws.cell(comm_row, col).value = f"={cl}{net_row}*C{comm_row}"
        ws.cell(comm_row, ytd_col).value = f"=SUM({first_data_cl}{comm_row}:{last_data_cl}{comm_row})"

        ws.cell(pay_row, 2).value = f"Total Payable: {smn} - {name}".strip(" -")
        ws.cell(pay_row, ytd_col).value = f"={ytd_cl}{comm_row}"

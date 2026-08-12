import pandas as pd
from pathlib import Path

p = Path(".scratch/parity/20260804-193031-postfix/ordered_line_date_probe/odata_header_vs_line_dates.csv")
d = pd.read_csv(p)
print("rows", len(d))
print(d.groupby(["side", "bucket"]).size().sort_values(ascending=False).to_string())
print("--- unique SOs no_header ---")
nh = d[d.bucket == "no_header_odata"]
print("rows", len(nh), "SOs", nh.sales_order.nunique())
print(nh.groupby("sales_order").size().sort_values(ascending=False).head(25).to_string())
print("--- dates_differ breakdown ---")
print(d.groupby(["side", "dates_differ"]).size().to_string())
print("--- nontz crosstab header_in x line_in ---")
n = d[d.tz_edge == "no"]
print(n.groupby(["side", "header_in_july", "line_in_july"]).size().to_string())
print("--- sample test_only with header present ---")
t = d[(d.side == "test_only") & (d.bucket != "no_header_odata")]
print("count", len(t))
print(t.groupby("bucket").size().to_string())
print(
    t[
        [
            "sales_order",
            "line_number",
            "report_order_date",
            "header_order_creation",
            "line_sys_created",
            "dates_differ",
            "bucket",
        ]
    ]
    .head(25)
    .to_string()
)
blank_h = d[
    d.header_order_creation.isna()
    | (d.header_order_creation.astype(str).isin(["", "nan"]))
]
print("--- blank header_order_creation ---")
print("blank header rows", len(blank_h), "SOs", blank_h.sales_order.nunique())
print("blank SOs:", sorted(blank_h.sales_order.unique().tolist()))
# How many test_only have header OUT of july with nonblank header?
tout = d[
    (d.side == "test_only")
    & (d.header_in_july == "no")
    & d.header_order_creation.notna()
    & (~d.header_order_creation.astype(str).isin(["", "nan"]))
]
print("--- test_only with real header OUT of july ---")
print("rows", len(tout), "SOs", tout.sales_order.nunique())
print(tout.groupby(["line_in_july", "bucket"]).size().to_string())
print(tout[["sales_order", "line_number", "header_order_creation", "line_sys_created", "report_order_date"]].head(15).to_string())

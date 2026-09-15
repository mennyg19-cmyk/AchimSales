# Remaining click-through

Inventory chrome/pages that can be clicked **without D365** are done (batches 1–6). Nothing left on the local Flask app except flows that need live data.

## Cannot do in this VM

- Entra / Live login on https://reports.achimonline.com
- Run report rows, last-order customer view, CLO Excel/PDF
- Overnight schedule files vs expected Excel (no `REPORTING_API_*`, no Graph)
- Fan-out CC/BCC on a real mail (F10)

Workbook layout vs expected is covered by pytest (`go-live/excel-output.md`).

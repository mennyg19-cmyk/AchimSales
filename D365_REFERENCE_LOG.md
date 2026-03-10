# D365 Entity & Column Reference Log

Every OData entity name and field name used in this codebase is listed below.
Cross-reference against your D365 `$metadata` endpoint:
`https://{your-env}.operations.dynamics.com/data/$metadata`

If a field or entity name does not match your environment, update it in
`data/field_maps.py` (the single source of truth for all mappings).

---

## Entity: SalesOrderHeadersV3

| Field | Used in | Line | Usage |
|-------|---------|------|-------|
| SalesOrderNumber | data/field_maps.py (SALES_ORDER_HEADER_SELECT) | L18 | $select; join key to lines |
| SalesOrderNumber | data/field_maps.py (SALES_ORDER_HEADER_FIELD_MAP) | L28 | mapped to SalesOrderNumber |
| SalesOrderNumber | data/d365_entities.py (fetch_sales_order_lines) | L108 | $filter field for batched line fetch |
| OrderCreationDateTime | data/field_maps.py (SALES_ORDER_HEADER_SELECT) | L19 | $select; date filter field |
| OrderCreationDateTime | data/d365_entities.py (fetch_sales_order_headers) | L66 | $filter ge/le for date range |
| OrderCreationDateTime | data/field_maps.py (SALES_ORDER_HEADER_FIELD_MAP) | L30 | mapped to OrderDate |
| SalesOrderStatus | data/field_maps.py (SALES_ORDER_HEADER_SELECT) | L20 | $select |
| SalesOrderStatus | data/field_maps.py (SALES_ORDER_HEADER_FIELD_MAP) | L32 | mapped to OrderStatus |
| SalesOrderProcessingStatus | data/field_maps.py (SALES_ORDER_HEADER_SELECT) | L21 | $select |
| SalesOrderProcessingStatus | data/field_maps.py (SALES_ORDER_HEADER_FIELD_MAP) | L34 | mapped to OrderProcessingStatus |
| InvoiceCustomerAccountNumber | data/field_maps.py (SALES_ORDER_HEADER_SELECT) | L22 | $select |
| InvoiceCustomerAccountNumber | data/field_maps.py (SALES_ORDER_HEADER_FIELD_MAP) | L36 | mapped to CustomerAccount |
| SalesOrderName | data/field_maps.py (SALES_ORDER_HEADER_SELECT) | L23 | $select |
| SalesOrderName | data/field_maps.py (SALES_ORDER_HEADER_FIELD_MAP) | L40 | mapped to SalesOrderName |
| CommissionSalesRepresentativeGroupId | data/field_maps.py (SALES_ORDER_HEADER_SELECT) | L24 | $select |
| CommissionSalesRepresentativeGroupId | data/field_maps.py (SALES_ORDER_HEADER_FIELD_MAP) | L42 | mapped to Salesman |
| OrderingCustomerName | data/field_maps.py (SALES_ORDER_HEADER_SELECT) | L25 | $select |
| OrderingCustomerName | data/field_maps.py (SALES_ORDER_HEADER_FIELD_MAP) | L44 | mapped to CustomerName |

---

## Entity: SalesOrderLinesV3

| Field | Used in | Line | Usage |
|-------|---------|------|-------|
| SalesOrderNumber | data/field_maps.py (SALES_ORDER_LINE_SELECT) | L51 | $select; $filter for batched fetch; join key |
| ItemNumber | data/field_maps.py (SALES_ORDER_LINE_SELECT) | L52 | $select; mapped to Item# |
| LineNumber | data/field_maps.py (SALES_ORDER_LINE_SELECT) | L53 | $select; mapped to LineNumber |
| SalesOrderLineStatus | data/field_maps.py (SALES_ORDER_LINE_SELECT) | L54 | $select; mapped to RawLineStatus |
| OrderedSalesQuantity | data/field_maps.py (SALES_ORDER_LINE_SELECT) | L55 | $select; mapped to QtyOrdered |
| LineAmount | data/field_maps.py (SALES_ORDER_LINE_SELECT) | L56 | $select; mapped to Total |
| SalesPrice | data/field_maps.py (SALES_ORDER_LINE_SELECT) | L57 | $select; mapped to SalesPrice |
| LineDescription | data/field_maps.py (SALES_ORDER_LINE_SELECT) | L58 | $select; mapped to LineDescription |
| InventoryLotId | data/field_maps.py (SALES_ORDER_LINE_SELECT) | L59 | $select; mapped to InventoryLotId; used to join WHS + packing slip |

---

## Entity: WHSSalesLineBiEntities

| Field | Used in | Line | Usage |
|-------|---------|------|-------|
| InventTransId | data/field_maps.py (WHS_LINE_SELECT) | L85 | $select; $filter for batched fetch |
| InventTransId | data/field_maps.py (WHS_LINE_FIELD_MAP) | L88 | mapped to InventTransId |
| ReleasedQty | data/field_maps.py (WHS_LINE_SELECT) | L85 | $select; mapped to WHSReleased |

---

## Entity: CustPackingSlipTransBiEntities

| Field | Used in | Line | Usage |
|-------|---------|------|-------|
| SalesId | data/field_maps.py (PACKING_SLIP_SELECT) | L101 | $select; $filter for batched fetch |
| SalesId | data/field_maps.py (PACKING_SLIP_FIELD_MAP) | L104 | mapped to SalesId |
| LineNum | data/field_maps.py (PACKING_SLIP_SELECT) | L101 | $select; group key for aggregation |
| InventTransId | data/field_maps.py (PACKING_SLIP_SELECT) | L101 | $select; group key for aggregation |
| Qty | data/field_maps.py (PACKING_SLIP_SELECT) | L101 | $select; summed to PackSlipQty |

---

## Entity: DVReleasedProducts

| Field | Used in | Line | Usage |
|-------|---------|------|-------|
| ItemNumber | data/field_maps.py (PRODUCT_SELECT) | L115 | $select; $filter for batched fetch; join key |
| ProductName | data/field_maps.py (PRODUCT_SELECT) | L115 | $select; LineDescription fallback |

---

## Entity: SalesInvoiceHeadersV2

| Field | Used in | Line | Usage |
|-------|---------|------|-------|
| InvoiceNumber | data/field_maps.py (SALES_INVOICE_HEADER_SELECT) | L122 | $select; mapped to InvoiceNumber |
| InvoiceDate | data/field_maps.py (SALES_INVOICE_HEADER_SELECT) | L123 | $select; $filter ge/le for date range |
| InvoiceDate | data/d365_entities.py (fetch_sales_invoice_headers) | L193 | $filter field |
| InvoiceCustomerAccountNumber | data/field_maps.py (SALES_INVOICE_HEADER_SELECT) | L124 | $select; mapped to CustomerAccount |
| SalesOrderNumber | data/field_maps.py (SALES_INVOICE_HEADER_SELECT) | L125 | $select; mapped to SalesOrderNumber |
| TotalInvoiceAmount | data/field_maps.py (SALES_INVOICE_HEADER_SELECT) | L126 | $select; mapped to TotalInvoiceAmount |
| TotalChargeAmount | data/field_maps.py (SALES_INVOICE_HEADER_SELECT) | L127 | $select; mapped to TotalChargeAmount |
| LedgerVoucher | data/field_maps.py (SALES_INVOICE_HEADER_SELECT) | L128 | $select; join key to MarkupTrans.Voucher |

---

## Entity: MarkupTransBiEntities

| Field | Used in | Line | Usage |
|-------|---------|------|-------|
| Voucher | data/field_maps.py (MARKUP_TRANS_SELECT) | L148 | $select; $filter for batched fetch; join to LedgerVoucher |
| Txt | data/field_maps.py (MARKUP_TRANS_SELECT) | L148 | $select; charge type detection (Tariff/CC/Freight) |
| Posted | data/field_maps.py (MARKUP_TRANS_SELECT) | L148 | $select; charge amount; mapped to Amount |

---

## Entity: SalesInvoiceLinesV2

| Field | Used in | Line | Usage |
|-------|---------|------|-------|
| InvoiceNumber | data/field_maps.py (SALES_INVOICE_LINE_SELECT) | L158 | $select; join key |
| InvoiceDate | data/field_maps.py (SALES_INVOICE_LINE_SELECT) | L159 | $select; $filter ge/le for date range |
| InvoiceDate | data/d365_entities.py (fetch_sales_invoice_lines) | L223 | $filter field |
| ItemNumber | data/field_maps.py (SALES_INVOICE_LINE_SELECT) | L160 | $select; mapped to Item_# |
| ProductName | data/field_maps.py (SALES_INVOICE_LINE_SELECT) | L161 | $select; mapped to Item_Name |
| InvoicedQuantity | data/field_maps.py (SALES_INVOICE_LINE_SELECT) | L162 | $select; mapped to Qty |
| SalesPrice | data/field_maps.py (SALES_INVOICE_LINE_SELECT) | L163 | $select; mapped to Price |
| LineAmount | data/field_maps.py (SALES_INVOICE_LINE_SELECT) | L164 | $select; mapped to Total_$ |

---

## Entity: CustomersV3

| Field | Used in | Line | Usage |
|-------|---------|------|-------|
| CustomerAccount | data/field_maps.py (CUSTOMER_SELECT) | L217 | $select; join key |
| AddressDescription | data/field_maps.py (CUSTOMER_SELECT) | L218 | $select; mapped to CustomerName (display field) |
| CommissionSalesGroupId | data/field_maps.py (CUSTOMER_SELECT) | L219 | $select; mapped to SalesGroup (salesman lookup) |

---

## Customer Activity Report -- Entity Usage

The Customer Activity report (`reports/customer_activity/`) reuses the following
existing entities and fields. No new entities are introduced.

### SalesOrderHeadersV3 (via `fetch_sales_order_headers`)

| Field | Usage in Customer Activity |
|-------|---------------------------|
| SalesOrderNumber | Join key to lines; count distinct orders per customer |
| OrderCreationDateTime | Mapped to OrderDate; used for last order date, avg days between orders, days since last order |
| InvoiceCustomerAccountNumber | Mapped to CustomerAccount; group-by key for per-customer metrics |
| CommissionSalesRepresentativeGroupId | Mapped to Salesman; used to assign customers to sales groups |

### SalesOrderLinesV3 (via `fetch_sales_order_lines`)

| Field | Usage in Customer Activity |
|-------|---------------------------|
| SalesOrderNumber | Join key to headers |
| LineAmount | Mapped to Total; summed per order for order totals, YTD totals, avg order value |

### CustomersV3 (via `fetch_customers`)

| Field | Usage in Customer Activity |
|-------|---------------------------|
| CustomerAccount | Join key to order headers |
| AddressDescription | Mapped to CustomerName; display field in report output |
| CommissionSalesGroupId | Mapped to SalesGroup; fallback salesman assignment when header lacks Salesman |

---

## Notes

- Entity names and field names are **case-sensitive** in some D365 environments.
- The uppercase variants in FIELD_MAP dicts handle environments that return ALL-CAPS field names.
- If your environment uses different entity versions (e.g., SalesOrderHeadersV2 instead of V3), update the entity name strings in `data/d365_entities.py`.
- To discover your entities: `GET https://{env}.operations.dynamics.com/data/$metadata`

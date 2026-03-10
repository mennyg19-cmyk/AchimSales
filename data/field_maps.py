"""
OData field rename maps and $select lists for all D365 entities.

Each entity has:
- FIELD_MAP: dict mapping OData field names -> internal standard names
- SELECT: list of fields to request via $select (minimizes payload)

These are the ONLY place entity/field names are defined. If your D365
environment uses different names, update them here.
"""

# =====================================================================
# SalesOrderHeadersV3
# =====================================================================
SALES_ORDER_HEADER_SELECT = [
    "SalesOrderNumber",
    "OrderCreationDateTime",
    "SalesOrderStatus",
    "SalesOrderProcessingStatus",
    "InvoiceCustomerAccountNumber",
    "SalesOrderName",
    "CommissionSalesRepresentativeGroupId",
    "CustomerRequisitionNumber",
]

SALES_ORDER_HEADER_FIELD_MAP = {
    "SalesOrderNumber": "SalesOrderNumber",
    "SALESORDERNUMBER": "SalesOrderNumber",
    "OrderCreationDateTime": "OrderDate",
    "ORDERCREATIONDATETIME": "OrderDate",
    "SalesOrderStatus": "OrderStatus",
    "SALESORDERSTATUS": "OrderStatus",
    "SalesOrderProcessingStatus": "OrderProcessingStatus",
    "SALESORDERPROCESSINGSTATUS": "OrderProcessingStatus",
    "InvoiceCustomerAccountNumber": "CustomerAccount",
    "INVOICECUSTOMERACCOUNTNUMBER": "CustomerAccount",
    "OrderingCustomerAccountNumber": "CustomerAccount",
    "ORDERINGCUSTOMERACCOUNTNUMBER": "CustomerAccount",
    "SalesOrderName": "SalesOrderName",
    "SALESORDERNAME": "SalesOrderName",
    "CommissionSalesRepresentativeGroupId": "Salesman",
    "COMMISSIONSALESREPRESENTATIVEGROUPID": "Salesman",
    "OrderingCustomerName": "CustomerName",
    "ORDERINGCUSTOMERNAME": "CustomerName",
    "CustomerName": "CustomerName",
    "CUSTOMERNAME": "CustomerName",
    "CustomerRequisitionNumber": "CustomerRequisition",
    "CUSTOMERREQUISITIONNUMBER": "CustomerRequisition",
    "OrderingCustomerExternalDescription": "CustomerRequisition",
    "ORDERINGCUSTOMEREXTERNALDESCRIPTION": "CustomerRequisition",
}

# =====================================================================
# SalesOrderLinesV3
# =====================================================================
SALES_ORDER_LINE_SELECT = [
    "SalesOrderNumber",
    "ItemNumber",
    "LineNumber",
    "SalesOrderLineStatus",
    "OrderedSalesQuantity",
    "LineAmount",
    "SalesPrice",
    "LineDescription",
    "InventoryLotId",
]

SALES_ORDER_LINE_FIELD_MAP = {
    "SalesOrderNumber": "SalesOrderNumber",
    "SALESORDERNUMBER": "SalesOrderNumber",
    "ItemNumber": "Item#",
    "ITEMNUMBER": "Item#",
    "LineNumber": "LineNumber",
    "LINENUMBER": "LineNumber",
    "SalesOrderLineStatus": "RawLineStatus",
    "SALESORDERLINESTATUS": "RawLineStatus",
    "SalesStatus": "RawLineStatus",
    "OrderedSalesQuantity": "QtyOrdered",
    "ORDEREDSALESQUANTITY": "QtyOrdered",
    "LineAmount": "Total",
    "LINEAMOUNT": "Total",
    "UnitPrice": "UnitPrice",
    "UNITPRICE": "UnitPrice",
    "SalesPrice": "SalesPrice",
    "SALESPRICE": "SalesPrice",
    "LineDescription": "LineDescription",
    "LINEDESCRIPTION": "LineDescription",
    "InventoryLotId": "InventoryLotId",
    "INVENTORYLOTID": "InventoryLotId",
}

# =====================================================================
# WHSSalesLineBiEntities
# =====================================================================
WHS_LINE_SELECT = ["InventTransId", "ReleasedQty"]

WHS_LINE_FIELD_MAP = {
    "InventTransId": "InventTransId",
    "INVENTTRANSID": "InventTransId",
    "ReleaseQty": "WHSReleased",
    "RELEASEQTY": "WHSReleased",
    "ReleasedQuantity": "WHSReleased",
    "RELEASEDQUANTITY": "WHSReleased",
    "QtyReleased": "WHSReleased",
    "QTYRELEASED": "WHSReleased",
    "ReleasedQty": "WHSReleased",
    "RELEASEDQTY": "WHSReleased",
}

# =====================================================================
# CustPackingSlipTransBiEntities
# =====================================================================
PACKING_SLIP_SELECT = ["SalesId", "LineNum", "InventTransId", "Qty"]

PACKING_SLIP_FIELD_MAP = {
    "SalesId": "SalesId",
    "SALESID": "SalesId",
    "LineNum": "LineNum",
    "LINENUM": "LineNum",
    "InventTransId": "InventTransId",
    "INVENTTRANSID": "InventTransId",
    "Qty": "Qty",
    "QTY": "Qty",
}

# =====================================================================
# DVReleasedProducts (for LineDescription fallback)
# =====================================================================
PRODUCT_SELECT = ["ItemNumber", "ProductName"]

PRODUCT_FIELD_MAP = {
    "ItemNumber": "ItemNumber",
    "ITEMNUMBER": "ItemNumber",
    "ProductName": "ProductName",
    "PRODUCTNAME": "ProductName",
}

# =====================================================================
# ReleasedProductsV2 (Book Price lookup)
# =====================================================================
BOOK_PRICE_SELECT = ["ItemNumber", "SalesPrice"]

BOOK_PRICE_FIELD_MAP = {
    "ItemNumber": "ItemNumber",
    "ITEMNUMBER": "ItemNumber",
    "SalesPrice": "BookPrice",
    "SALESPRICE": "BookPrice",
}

# =====================================================================
# SalesInvoiceHeadersV2 (Invoiced Report)
# =====================================================================
SALES_INVOICE_HEADER_SELECT = [
    "InvoiceNumber",
    "InvoiceDate",
    "InvoiceCustomerAccountNumber",
    "SalesOrderNumber",
    "TotalInvoiceAmount",
    "TotalChargeAmount",
    "LedgerVoucher",
]

SALES_INVOICE_HEADER_FIELD_MAP = {
    "InvoiceNumber": "InvoiceNumber",
    "INVOICENUMBER": "InvoiceNumber",
    "InvoiceDate": "InvoiceDate",
    "INVOICEDATE": "InvoiceDate",
    "InvoiceCustomerAccountNumber": "CustomerAccount",
    "INVOICECUSTOMERACCOUNTNUMBER": "CustomerAccount",
    "SalesOrderNumber": "SalesOrderNumber",
    "SALESORDERNUMBER": "SalesOrderNumber",
    "TotalInvoiceAmount": "TotalInvoiceAmount",
    "TOTALINVOICEAMOUNT": "TotalInvoiceAmount",
    "TotalChargeAmount": "TotalChargeAmount",
    "TOTALCHARGEAMOUNT": "TotalChargeAmount",
    "LedgerVoucher": "LedgerVoucher",
    "LEDGERVOUCHER": "LedgerVoucher",
}

# =====================================================================
# MarkupTransBiEntities (charges: freight, tariff, CC)
# =====================================================================
MARKUP_TRANS_SELECT = ["Voucher", "Txt", "Posted", "OrigRecId"]

MARKUP_TRANS_FIELD_MAP = {
    "Voucher": "Voucher",
    "VOUCHER": "Voucher",
    "Txt": "Txt",
    "TXT": "Txt",
    "Posted": "Amount",
    "POSTED": "Amount",
}

# =====================================================================
# SalesInvoiceLinesV2 (Number 4 Report)
# =====================================================================
SALES_INVOICE_LINE_SELECT = [
    "InvoiceNumber",
    "InvoiceDate",
    "ProductNumber",
    "ProductVariantName",
    "InvoicedQuantity",
    "SalesPrice",
    "LineAmount",
]

SALES_INVOICE_LINE_FIELD_MAP = {
    "InvoiceNumber": "InvoiceNumber",
    "INVOICENUMBER": "InvoiceNumber",
    "InvoiceDate": "InvoiceDate",
    "INVOICEDATE": "InvoiceDate",
    "ProductNumber": "Item_#",
    "PRODUCTNUMBER": "Item_#",
    "ProductVariantName": "Item_Name",
    "PRODUCTVARIANTNAME": "Item_Name",
    "InvoicedQuantity": "Qty",
    "INVOICEDQUANTITY": "Qty",
    "SalesPrice": "Price",
    "SALESPRICE": "Price",
    "LineAmount": "Total_$",
    "LINEAMOUNT": "Total_$",
}

# =====================================================================
# Customer groups / Customer Report entity
# (May need to be fetched from CustomersV3 or a custom entity)
# =====================================================================
CUSTOMER_SELECT = [
    "CustomerAccount",
    "AddressDescription",
    "OrganizationName",
    "NameAlias",
    "CommissionSalesGroupId",
]

CUSTOMER_FIELD_MAP = {
    "CustomerAccount": "CustomerAccount",
    "CUSTOMERACCOUNT": "CustomerAccount",
    "AddressDescription": "AddressDescription",
    "ADDRESSDESCRIPTION": "AddressDescription",
    "OrganizationName": "OrganizationName",
    "ORGANIZATIONNAME": "OrganizationName",
    "NameAlias": "NameAlias",
    "NAMEALIAS": "NameAlias",
    "CommissionSalesGroupId": "SalesGroup",
    "COMMISSIONSALESGROUPID": "SalesGroup",
}

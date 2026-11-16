"""Column schemas and default-visible sets for warehouse dashboard tables.

Column lists match the Nov 11 2026 gateway snapshot attached to the build brief.
"""

from __future__ import annotations

AREAS = ("shipments", "loads", "work", "clusters")
PLACEHOLDER_AREAS = ("waves", "due_dates")

STATUS_COLUMNS = {
    "shipments": "ShipmentStatus",
    "loads": "LoadStatus",
    "work": "WorkStatus",
    "clusters": "WorkClusterStatus",
    "waves": "WaveStatus",
}

# Known open statuses for per-status Reporting API fetches (Baruch production probe).
# Open rules in filters.py may accept additional statuses; client always re-filters.
OPEN_STATUS_FETCH = {
    "shipments": ("Open", "Waved", "InProcess", "Loaded"),
    "loads": ("Open", "Waved", "InProcess", "Loaded"),
    "work": ("Open", "InProcess"),
    "clusters": ("Open", "Passed", "InProcess"),
}

AREA_TITLES = {
    "shipments": "Shipments",
    "loads": "Loads",
    "work": "Work",
    "clusters": "Clusters",
    "waves": "Waves",
    "due_dates": "Due dates",
}

COLUMNS = {
    "shipments": [
        "Company", "RecId", "AccountNum", "Address", "BillOfLadingId",
        "BrokerCode", "CarrierCode", "CarrierGroupCode", "CarrierServiceCode",
        "createdBy", "createdDateTime", "CustomerRef", "CustomerReq",
        "DeliveryName", "DlvTermId", "DropOffUTCDateTime", "FreightTermCode",
        "HMIMAirWaybillNum", "InventLocationId", "InventOwnerId", "InventSiteId",
        "LoadId", "ManifestedWeight", "ModeCode", "modifiedBy", "modifiedDateTime",
        "OrderNum", "ProNum", "ReceivingCompletedDocumentDate", "Reference",
        "SCAC", "ShipCarrierAccount", "ShipConfirmUTCDateTime",
        "ShipmentArrivalUTCDateTime", "ShipmentCreatedUTCDateTime", "ShipmentId",
        "ShipmentStatus", "TableId", "WaveId", "WaveLabelsPrinted",
        "WaveLabelsPrintedBy", "WaveLabelsPrintedDateTime", "WayBill",
        "WorkTransType", "ShipmentCreatedDateTime", "ShipConfirmDateTime",
        "RecordHash", "LoadBatchId", "UpdatedUtc", "IsDeleted",
    ],
    "loads": [
        "AccountNum", "ActualGrossWeight", "ActualNetWeight", "ActualTareWeight",
        "ActualVolume", "BillOfLadingId", "BookingNum", "BrokerCode", "CarNumber",
        "CarrierCode", "CarrierGroupCode", "CarrierServiceCode", "createdBy",
        "createdDateTime", "CredManInCreditControl", "CustVendRef",
        "CutOffUTCDateTime", "dataAreaId", "DestinationName", "ETA", "ETD",
        "InventLocationId", "InventSiteId", "LoadId", "LoadNetWeight",
        "LoadReferenceNum", "LoadStatus", "LoadTemplateId", "LoadUserDef1",
        "LoadUserDef2", "LoadUserDef3", "LoadWeight", "LoadWidth", "ModeCode",
        "modifiedBy", "modifiedDateTime", "OrderNum", "OriginName",
        "PackingSlipBackgroundPostingStatus", "ProNum", "RecId", "RouteCode",
        "rowNumber", "ShippingContainerId", "SystemTareWeight", "TableId",
        "TrailerNumber", "VesselName", "VoyageNum", "InsertedUtc", "UpdatedUtc",
        "LastSeenUtc",
    ],
    "work": [
        "ACHConsolidatedLicensePlateId", "ACHHeight", "ACHLength", "ACHWidth",
        "ActualTime", "CancelReplenWhenDemandCanceled", "ClusterProfileId",
        "CombinedWorkId", "ContainerId", "createdBy", "createdDateTime",
        "dataAreaId", "DispositionCode", "Frozen", "InventJournalId",
        "InventLocationId", "InventoryAdjustmentJournalId",
        "InventoryTransactionMechanism", "InventSiteId", "ITMGoodsInTransitId",
        "ITMRegisteredLicensePlateId", "LoadId", "LockedUser", "modifiedBy",
        "modifiedDateTime", "OrderNum", "RecId", "ReplenishmentDependentWorkBlockingPolicy",
        "ShipmentId", "TableId", "TargetLicensePlateId", "TransTxt", "WaveId",
        "WorkBuildId", "WorkCancelledByUser", "WorkCancelledUTCDateTime",
        "WorkClosedUTCDateTime", "WorkCountError", "WorkCreatedBy", "WorkId",
        "WorkInProcessUTCDateTime", "WorkIsMultiSKU", "WorkManuallyCompletedBy",
        "WorkPoolId", "WorkStatus", "WorkTemplateCode", "WorkTransType",
        "LastImportedUTC",
    ],
    "clusters": [
        "ClusterId", "ClusterProfileId", "ClusterType", "createdBy",
        "createdDateTime", "dataAreaId", "LockedUser", "modifiedBy",
        "modifiedDateTime", "RecId", "TableId", "WorkClusterStatus",
        "CreatedDateTimeParsed", "ModifiedDateTimeParsed", "RecordHash",
        "LoadBatchId", "SourceFileName", "SourceSheetName", "SourceRowNumber",
        "InsertedUtc", "UpdatedUtc", "LastSeenUtc", "IsDeleted",
    ],
}

# Sensible defaults for the Tabulator grid; other columns stay toggleable.
DEFAULT_VISIBLE = {
    "shipments": [
        "ShipmentId", "ShipmentStatus", "OrderNum", "AccountNum", "DeliveryName",
        "LoadId", "WaveId", "CarrierCode", "InventLocationId", "createdDateTime",
        "modifiedDateTime", "UpdatedUtc",
    ],
    "loads": [
        "LoadId", "LoadStatus", "OrderNum", "AccountNum", "CarrierCode",
        "InventLocationId", "DestinationName", "TrailerNumber", "ETA",
        "createdDateTime", "UpdatedUtc",
    ],
    "work": [
        "WorkId", "WorkStatus", "WorkTransType", "ShipmentId", "LoadId", "WaveId",
        "OrderNum", "InventLocationId", "LockedUser", "createdDateTime",
        "LastImportedUTC",
    ],
    "clusters": [
        "ClusterId", "WorkClusterStatus", "ClusterProfileId", "ClusterType",
        "LockedUser", "createdDateTime", "modifiedDateTime", "UpdatedUtc",
    ],
}

# Gateway / expected Reporting API report ids (not present in this repo's catalog).
REPORT_IDS = {
    "shipments": "whs_shipment_table",
    "loads": "whs_load_table",
    "work": "whs_work_table",
    "clusters": "whs_work_cluster_table",
    "waves": "whs_wave_table",
}

# Procedure names reported by Achim AI Gateway (operator reference).
PROCEDURE_REFS = {
    "shipments": "rpt.usp_whsshipmenttable",
    "loads": "rpt.usp_WHSLoadTable",
    "work": "rpt.usp_WHSWorkTable",
    "clusters": "rpt.usp_whsworkclustertable",
    "waves": "rpt.usp_whswavetable",
}

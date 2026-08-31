# OData vs salesline_release — Data Mismatch Diagnosis

**Date**: June 2, 2026
**Compared files**:
- `Monthly_Ordered_Report_May_2026.xlsx` — live app (OData connection)
- `Ordered (1).xlsx` — test app (v3, `salesline_release` stored procedure)

Both reports cover May 2026 and were generated within minutes of each other.

---

## Grand Totals

| Source | Lines | QtyOrdered | Ordered $ |
|---|---|---|---|
| Live (OData) | 39,123 | 296,591 | $2,746,053.52 |
| Test (SP) | 39,056 | 297,856 | $2,746,423.40 |
| **Delta** | **-67** | **+1,265** | **+$369.88** |

---

## Category 1 — 203 orders only in OData (SP doesn't return them)

All from **2026-05-01**, order numbers `ORD00823718` through `ORD00823920`.

The SP appears to start the month later than OData — likely a timezone
boundary (e.g. midnight UTC vs midnight Eastern). These 203 early-May-1
orders are captured by OData but fall outside the SP's date window.

| Salesman | Orders | Qty | $ |
|---|---|---|---|
| Integrated | 46 | 165 | $2,390.31 |
| JWeigand | 57 | 87 | $901.05 |
| REdwards | 50 | 92 | $1,315.29 |
| AGrossman | 39 | 73 | $927.23 |
| HKaufman | 11 | 16 | $195.71 |

## Category 2 — 160 orders only in SP (OData doesn't return them)

Three sub-groups:

### a) Late May 31 orders (ORD00846049+)
~150 orders from 2026-05-31. The SP includes these; OData cuts off earlier.
Same timezone boundary issue as Category 1, but at the end of the month.

### b) Earlier-month orders appearing in May
| Order | Date | Customer | Salesman | Qty | $ | Notes |
|---|---|---|---|---|---|---|
| ORD00809181 | 2026-05-07 | 3196984 (Ocean Hardware) | MGrego | 36 | $281.22 | Pre-May order? SP sees it |
| ORD00815939 | 2026-05-11 | 8276 (Gorham's Home Centre) | LCWalker | 90 | $1,092.24 | Pre-May order? SP sees it |
| ORD00820761 | 2026-05-07 | 2267 (Variety/Rose's) | HKaufman | 960 | $4,656.00 | Pre-May order? SP sees it |

These have May dates but low order numbers, suggesting the SP may include
orders modified in May (not just created in May), while OData only uses
created date.

### c) Returns/adjustments with negative quantities
| Order | Customer | Salesman | Qty | $ |
|---|---|---|---|---|
| ORD00828850 | 0123456789 (Avi Grossman) | House | -19 | -$538.40 |
| ORD00832072 | 6513 (Ricciardi Brothers) | MKolko | -6 | -$42.60 |
| ORD00833264 | 419 (Brown's Linen Outlets) | BLevin | -2 | -$43.70 |

OData excludes these entirely; the SP includes them.

## Category 3 — 8 orders in both sources with different amounts (CHECK THESE IN D365)

These are the most important to verify. Same order number, different
qty or dollar totals. Look each one up in D365 and compare line counts.

### ORD00843058 — MKolko / Cust 8023
- **OData**: 1,840 qty / $11,715.70 (55 lines)
- **SP**: 246 qty / $1,868.76 (5 lines)
- OData has 50 extra lines (Ln 6–55) the SP doesn't return.
  These are BCPN, BCVL, ANFTM, BCCHPD, FF5P, AFB, etc. items.

### ORD00824083 — HKaufman / Cust 2267 (Variety/Rose's)
- **OData**: 2,034 qty / $10,678.50
- **SP**: 3,798 qty / $19,851.30
- SP has extra Ln 1: DRCY36AS06, 1764 qty, $9,172.80. OData doesn't have this line.

### ORD00841303 — PMazer / Cust 7186
- **OData**: 815 qty / $7,305.82
- **SP**: 815 qty / $2,568.22
- Same qty but **$4,737.60 price gap** on 3 items (Ln 47–49: items 263-2PL001,
  55-2PL0001, 163-2PL001). OData shows ~$1,612.80 each; SP shows ~$33.60 each.
  One of them has the wrong unit price.

### ORD00842418 — AGrossman / Cust 00011535
- **OData**: 90 qty / $1,113.00
- **SP**: 132 qty / $1,478.40
- Ln 2 (TRS736WH06): OData Qty=42/$693, SP Qty=42/$365.40. Different unit prices.

### ORD00828828 — HKaufman / Cust 8379
- **OData**: 156 qty / $999.12
- **SP**: 172 qty / $1,100.40
- SP has extra Ln 11 (TOVYSTWH04, 16 qty, $101.28) that OData doesn't.

### ORD00843828 — HKaufman / Cust 302 (Berkoff-Fox)
- **OData**: 86 qty / $1,002.80
- **SP**: 96 qty / $1,149.80
- Ln 2 (FTVWD20220): OData Qty=22/$143, SP Qty=10/$147. Both qty AND price differ.

### ORD00824110 — HKaufman / Cust 1977
- **OData**: 1,042 qty / $4,495.30
- **SP**: 1,060 qty / $4,582.60
- SP has extra Ln 0 (MSG229WH06, 18 qty, $87.30). Also Ln 31 differs between sources.

### ORD00842246 — HKaufman / Cust 8379
- **OData**: 144 qty / $1,000.26
- **SP**: 148 qty / $1,025.58
- SP has extra Ln 8 (TOVYSTLG04, 4 qty, $25.32).

## Category 4 — QtyReleased/Released$ systematic difference

34,580 of 38,766 shared lines have different QtyReleased values.

- OData returns QtyReleased = 0 for most invoiced lines
- The SP returns QtyReleased = the actual released/picked quantity

This is a field-definition difference between the two data sources, not a
data error. The SP's definition is arguably more useful (shows historical
release quantities even after invoicing).

## Data Quality: Duplicate keys in SP output

The SP returns 15 order+line combinations that appear multiple times
(mostly `LineNumber = 0` entries). This inflates the test app's totals
slightly and causes key-collision issues. Example duplicates:

- ORD00824119 Ln 0 — appears 4x
- ORD00826838 Ln 0 — appears 4x
- ORD00831298 Ln 0 — appears 4x
- ORD00833241 Ln 0 — appears 4x

## Conclusion

The mismatches stem from:

1. **Date boundary differences** — the SP and OData use different
   time boundaries for "May", causing ~360 orders to appear in one
   source but not the other (Categories 1 and 2).
2. **Line-level data differences** — 8 orders exist in both but with
   different line counts or unit prices (Category 3). These need
   manual verification in D365.
3. **Field semantics** — QtyReleased means different things in each
   source (Category 4).
4. **SP returning duplicates** — LineNumber 0 rows appear multiple
   times for some orders.
5. **Return orders** — the SP includes negative-qty return/adjustment
   orders that OData excludes.

**Action items**: Check the 8 Category 3 orders in D365 to determine
which source has the correct data. Discuss the date boundary and
return-order inclusion rules with the DB manager to align the SP with
the expected behavior.

# Parity: invoiced

- Params: `{'period': 'ytd'}`
- Live file: `.scratch\parity\20260724-043826\invoiced__live.xlsx`
- Test file: `.scratch\parity\20260724-043826\invoiced__test.xlsx`

## Summary

- Cells compared: **4214**
- Differences: **2603**
- Missing sheets in /test: ['Audit - Reversals']
- Extra sheets in /test: (none)
- Result: **DIFFERENCES FOUND**

## Detail

```
Comparison: .scratch\parity\20260724-043826\invoiced__live.xlsx vs .scratch\parity\20260724-043826\invoiced__test.xlsx
Cells compared: 4214
Differences: 2603
Missing sheets in new: Audit - Reversals
RESULT: DIFFERENCES FOUND

  Sheet 'Summary by Customer': 500 difference(s)
    Column count: old=10 new=11
    C1: value old=SalesmanNumber new=Salesman
    J1: value old=Total Invoices new=Total Misc Charges
    K1: value old=None new=Total Invoices
    C2: value old=?unassigned new=Unassigned
    J2: value old=108150 new=0
    K2: value old=None new=108150
    C3: value old=102 new=MGrego
    D3: value old=Meir Grego new=Grego, Meir
    J3: value old=4048.3900 new=0
    K3: value old=None new=4048.3900
    C4: value old=099 new=House
    D4: value old=ACHIM HOUSE ACCOUNT new=House, House
    J4: value old=18025 new=0
    K4: value old=None new=18025
    C5: value old=102 new=MGrego
    D5: value old=Meir Grego new=Grego, Meir
    J5: value old=-282 new=0
    K5: value old=None new=-282
    C6: value old=102 new=MGrego
    ... and 480 more

  Sheet 'Commissions': 500 difference(s)
    Row count: old=102 new=64
    Column count: old=16 new=9
    A1: value old=None new=Commissions Summary 2026
    B2: value old=Commissions Summary (2026) new=None
    A3: value old=None new=Carter-Walker, Lisa
    B3: value old=None new=Jan
    C3: value old=None new=Feb
    D3: value old=None new=Mar
    E3: value old=None new=Apr
    F3: value old=None new=May
    G3: value old=None new=Jun
    H3: value old=None new=Jul
    I3: value old=None new=YTD
    A4: value old=None new=SubTotal Invoices
    B4: value old=12 - Mendy Kolko new=16348.2000
    C4: value old=None new=1012.2000
    D4: value old=2026-01-01 00:00:00 new=446.8400
    E4: value old=2026-02-01 00:00:00 new=19094.0400
    F4: value old=2026-03-01 00:00:00 new=11958
    G4: value old=2026-04-01 00:00:00 new=6022.7400
    ... and 480 more

  Sheet 'Full Details': 500 difference(s)
    G1: value old=SalesmanNumber new=SalesmanName
    H1: value old=SalesmanName new=SubTotal Invoices
    I1: value old=SubTotal Invoices new=Tariff Charges
    J1: value old=Tariff Charges new=Freight Charges
    K1: value old=Freight Charges new=CC Charges
    L1: value old=CC Charges new=Misc Charges
    A2: value old=CRD00006873 new=FCRD-003759
    B2: value old=00011083 new=00011005
    C2: value old=Tejada hardware new=DCH BRUNSWICK TOYOTA
    D2: value old=2026-01-01 12:00:00 new=2026-05-18 00:00:00
    E2: value old=ORD00715763 new=TR-4502
    F2: value old=MGrego new=Unassigned
    G2: value old=102 new=Unassigned
    H2: value old=Meir Grego new=0
    I2: value old=-468 new=0
    M2: value old=-468 new=0
    A3: value old=CRD00006901 new=FINV-000681
    B3: value old=1724 new=00011005
    C3: value old=MILL SUPPLY CO, INC new=DCH BRUNSWICK TOYOTA
    D3: value old=2026-03-25 12:00:00 new=2026-01-02 00:00:00
    ... and 480 more

  Sheet 'Credits': 500 difference(s)
    Row count: old=544 new=517
    J1: value old=Total Invoice new=Misc Charges
    K1: value old=Salesman new=Total Invoice
    L1: value old=SalesmanNumber new=Salesman
    A2: value old=00011083 new=00011005
    B2: value old=Tejada hardware new=DCH BRUNSWICK TOYOTA
    C2: value old=2026-01-01 12:00:00 new=2026-05-18 00:00:00
    D2: value old=CRD00006873 new=FCRD-003759
    E2: value old=ORD00715763 new=TR-4502
    F2: value old=-468 new=0
    J2: value old=-468 new=0
    K2: value old=MGrego new=0
    L2: value old=102 new=Unassigned
    M2: value old=Meir Grego new=Unassigned
    A3: value old=8015 new=00011038
    B3: value old=WAYFAIR LLC (DS) new=MEGA DISCOUNT
    C3: value old=2026-01-07 12:00:00 new=2026-02-27 00:00:00
    D3: value old=FCRD-003176 new=FCRD-003398
    F3: value old=-209.1600 new=-282
    J3: value old=-209.1600 new=0
    ... and 480 more

  Sheet 'Invoices': 500 difference(s)
    Row count: old=146218 new=146203
    J1: value old=Total Invoice new=Misc Charges
    K1: value old=Salesman new=Total Invoice
    L1: value old=SalesmanNumber new=Salesman
    A2: value old=5046 new=00011005
    B2: value old=SHERWIN WILLIAMS new=DCH BRUNSWICK TOYOTA
    C2: value old=2026-01-06 12:00:00 new=2026-01-02 00:00:00
    D2: value old=IN00794218 new=FINV-000681
    E2: value old=ORD00735914 new=None
    F2: value old=44.7000 new=18025
    H2: value old=14.1500 new=0
    J2: value old=58.8500 new=0
    K2: value old=BLevin new=18025
    L2: value old=024 new=Unassigned
    M2: value old=Bruce Levin new=Unassigned
    A3: value old=5046 new=00011005
    B3: value old=SHERWIN WILLIAMS new=DCH BRUNSWICK TOYOTA
    C3: value old=2026-01-06 12:00:00 new=2026-03-02 00:00:00
    D3: value old=IN00794252 new=FINV-000744
    E3: value old=ORD00737829 new=TR-4481
    ... and 480 more

  Sheet 'Totals by Salesman': 108 difference(s)
    A1: value old=SalesmanNumber new=Salesman
    C1: value old=Salesman new=InvoiceCount
    D1: value old=InvoiceCount new=SubTotal Invoices
    E1: value old=SubTotal Invoices new=Tariff Charges
    F1: value old=Tariff Charges new=Freight Charges
    G1: value old=Freight Charges new=CC Charges
    H1: value old=CC Charges new=Misc Charges
    A2: value old=012 new=AGrossman
    B2: value old=Mendy Kolko new=Grossman, Avi
    C2: value old=MKolko new=36035
    D2: value old=612 new=1874464.7600
    E2: value old=1134331.0500 new=9390.5900
    F2: value old=88968.9200 new=1152.8000
    G2: value old=1220.9600 new=0
    H2: value old=111.4000 new=0
    I2: value old=1224632.3300 new=1885008.0200
    A3: value old=024 new=BLevin
    B3: value old=Bruce Levin new=Levin, Bruce
    C3: value old=BLevin new=844
    D3: value old=808 new=553222.6500
    ... and 88 more
```

_Live is the baseline. Review each difference: intentional product
change (accept) vs bug (fix on /test)._

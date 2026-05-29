"""Repository interfaces over the data layer.

Every other module depends on these classes, never on raw SQL, so swapping
SQLite for Postgres later is an adapter change here only (plan section 6).
"""

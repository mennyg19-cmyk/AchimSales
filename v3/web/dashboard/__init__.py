"""Customer dashboard: persistent mirror + per-customer cadence metrics.

The math here is kept in lock-step with the LIVE app (webapp/dashboard_data.py
`_compute_customer_metrics`): mean gap between orders, population stdev as the
overdue buffer, and the New/Active/Overdue/Inactive bucketing. See metrics.py.
"""

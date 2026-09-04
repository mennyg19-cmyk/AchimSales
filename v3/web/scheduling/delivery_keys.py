"""Delivery keys stored on a schedule row, not copied from a live view."""

PERSONAL_DELIVERY_PARAM_KEYS = frozenset({
    "email_on_no_data", "email_on_no_data_me_only",
    "email_cc", "email_bcc", "folder_kind", "view_source",
    "email_subject", "email_html",
})

MASTER_DELIVERY_PARAM_KEYS = PERSONAL_DELIVERY_PARAM_KEYS | {
    "split_by_salesman", "email_to_salesmen", "email_salesman_keys",
    "skip_sabbath",
}

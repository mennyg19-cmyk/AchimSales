"""Authentication + the single authorization/scope layer (rule 6).

Every data route resolves access through `authorization.Authorization`, so the
IDOR / customer-list-leak / preset / master-schedule gaps the audit found cannot
recur in one place and be missed in another.
"""

# Click-through batch 4 (local `http://127.0.0.1:5055`)

**When:** 2026-09-02 ~23:48–23:58 UTC
**Agent:** computerUse [Browser click batch 4](bc-fd2b54cd-7a09-5d46-b1da-e20ad6b5ded6)
**Model:** inherit (computerUse)
**Runner:** spawn
**Recording:** SAVE_RECORDING timed out; named screenshots `/tmp/computer-use/b4-*.webp`

## Proof-of-read (agent)

Batch 3 passed company schedules / Default modal / personal save. Remaining list wanted true salesman login plus leftover settings/help/theme/CLO/master/dashboard.

## Results (parent-verified)

| ID | Agent | Parent |
|----|-------|--------|
| 1 salesman `/login/dev` | FAIL (Viewing as banner) | **Not a product fail.** `login_dev` always sets `is_dev=True`. Chrome shows “Viewing as” when `_dev` and role is not admin/developer (`base.html`). Fresh cookie jar: `badge-impersonate` present, no Dashboard nav, `/dashboard` 403 “Dashboard access required”, `/admin/users` 403 JSON. GET `/login/dev` 405 is expected (POST only). Production Beta uses Live/Entra (`is_dev=False` for salesmen). |
| 1 settings/403 | pass | Profile / Appearance / Exclusions only; 403s as above. |
| 2 `/impersonate` | pass | Page loads; click Test Salesman 2 → Viewing as; nested `/impersonate` 400. No End control in chrome (**F12**). |
| 3 `/dev/role-picker` | PARTIAL (button hung) | **Agent missed the radio.** “View as Selected User” is `disabled` until a radio is checked. Parent POST with `target_email=golive-sm2@local.test` → 200, impersonate badge, then `__self__` returns. Not a hang. |

## Skipped (time cap)

P7 settings extras, C10 Help click, C6 theme cycle, P4.3 last-order type, P6.7 master History/Run now (history URL 200 via curl), P9 dashboard empty table.

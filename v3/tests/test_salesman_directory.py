"""SalesmanDirectory: the salesmen_master SP, cached in memory and in cache.db."""

from web.data.connection import Database
from web.data.migrate import migrate
from web.reporting.http_client import ReportResult, ReportingApiError
from web.reporting.salesman_directory import SalesmanDirectory, master_salesman


class _Client:
    def __init__(self, rows=None, *, configured=True, fail=False):
        self.rows = rows or []
        self.configured = configured
        self.fail = fail
        self.calls = 0

    def run_report(self, report_id, params):
        self.calls += 1
        if self.fail:
            raise ReportingApiError("down")
        return ReportResult(report_id=report_id, columns=[], rows=list(self.rows),
                            row_count=len(self.rows))


def _db(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    return db


_SP = [
    {"Salesman": "REdwards", "SalesmanName": "Reggie Edwards", "Email": "reggie@x.com",
     "CommissionPercentage": 6},
    {"Salesman": "HKaufman", "SalesmanName": "Heshy Kaufman", "Email": "",
     "CommissionPercentage": 0.04},
    {"Salesman": "XOld", "SalesmanName": "Retired", "Email": "x@x.com", "IsActive": 0},
    {"Salesman": "", "SalesmanName": "blank"},
]


def test_master_salesman_reads_the_real_sp_columns():
    m = master_salesman(_SP[0])
    assert (m.key, m.name, m.email, m.commission_pct) == (
        "REdwards", "Reggie Edwards", "reggie@x.com", 0.06)
    assert master_salesman(_SP[2]) is None    # IsActive 0
    assert master_salesman(_SP[3]) is None    # blank key


def test_rows_facts_and_emails_come_from_the_sp():
    d = SalesmanDirectory(_Client(_SP))
    rows = d.rows()
    assert [r.key for r in rows] == ["HKaufman", "REdwards"]  # sorted by name
    assert d.get_email("redwards") == "reggie@x.com"
    assert d.emails_by_keys(["REdwards", "HKaufman", "Nobody"]) == {
        "REdwards": "reggie@x.com", "HKaufman": "", "Nobody": ""}
    assert d.keys_with_email() == ["REdwards"]
    assert d.keys_for_email("REGGIE@x.com") == ["redwards"]
    facts = d.all_as_facts()
    assert facts["redwards"].full_name == "Reggie Edwards"
    assert facts["redwards"].commission_pct == 0.06
    assert facts["hkaufman"].commission_pct == 0.04
    assert d.status()["master_source"] == "sp"
    assert d.status()["master_row_count"] == 2


def test_last_good_list_survives_a_restart_via_cache_db(tmp_path):
    db = _db(tmp_path)
    SalesmanDirectory(_Client(_SP), db).rows()          # fetch + write cache

    cold = SalesmanDirectory(_Client(_SP, fail=True), db)  # new process, SP down
    assert [r.key for r in cold.rows()] == ["HKaufman", "REdwards"]
    assert cold.get_email("REdwards") == "reggie@x.com"
    assert cold.all_as_facts()["hkaufman"].commission_pct == 0.04
    status = cold.status()
    assert status["master_source"] == "cache"
    assert status["master_error"] == "down"

    unconfigured = SalesmanDirectory(_Client(_SP, configured=False), db)
    unconfigured.refresh()
    assert unconfigured.client.calls == 0
    assert unconfigured.keys_with_email() == ["REdwards"]  # still the cached copy


def test_no_sp_and_no_cache_means_no_salesmen(tmp_path):
    d = SalesmanDirectory(_Client(_SP, fail=True), _db(tmp_path))
    assert d.rows() == []
    assert d.get_email("REdwards") == ""
    assert d.status()["master_source"] == "none"


def test_cache_and_cooldown_limit_sp_calls():
    client = _Client(_SP)
    d = SalesmanDirectory(client, ttl_seconds=3600)
    d.rows()
    d.rows()
    d.get_email("REdwards")
    assert client.calls == 1
    assert d.rows(wait=False) and client.calls == 1

    failing = _Client(_SP, fail=True)
    d2 = SalesmanDirectory(failing, retry_cooldown_seconds=60)
    d2.rows()
    d2.rows()
    assert failing.calls == 1                             # cooldown after a failure

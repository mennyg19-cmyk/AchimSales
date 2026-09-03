"""SalesmanDirectory: salesmen_master SP first, local table as fallback."""

from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.salesmen import SalesmanRepository, SalesmanSeed
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


def _repo(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    repo = SalesmanRepository(db)
    repo.upsert_many([
        SalesmanSeed(raw_key="REdwards", number="080", full_name="Reggie Edwards",
                     display_name="Reggie", email="old@x.com", commission_pct=0.05),
        SalesmanSeed(raw_key="XOld", number="99", full_name="Retired",
                     display_name="XOld", email="x@x.com"),
        SalesmanSeed(raw_key="House", number="", full_name="House",
                     display_name="House", email="house@x.com"),
    ])
    repo.update("xold", is_active=False)
    return repo


_SP = [
    {"Salesman": "REdwards", "SalesmanName": "Reggie Edwards", "Email": "reggie@x.com",
     "CommissionPercentage": 6},
    {"Salesman": "HKaufman", "SalesmanName": "Heshy Kaufman", "Email": "",
     "CommissionPercentage": 0.04},
    {"Salesman": "XOld", "SalesmanName": "Retired", "Email": "x@x.com",
     "CommissionPercentage": 1},
]


def test_master_salesman_reads_the_real_sp_columns():
    m = master_salesman(_SP[0])
    assert (m.key, m.name, m.email, m.commission_pct) == (
        "REdwards", "Reggie Edwards", "reggie@x.com", 0.06)
    assert master_salesman({"Salesman": "", "SalesmanName": "blank"}) is None
    assert master_salesman({"Salesman": "A", "IsActive": 0}) is None


def test_sp_values_win_and_local_fills_blanks(tmp_path):
    d = SalesmanDirectory(_Client(_SP), _repo(tmp_path))
    rows = {r.key: r for r in d.rows()}
    assert rows["REdwards"].email == "reggie@x.com"            # SP over local
    assert rows["REdwards"].commission_pct == 0.06             # 6 -> fraction
    assert rows["HKaufman"].email == ""                        # SP blank, no local row
    assert "XOld" not in rows                                  # local inactive hides SP row
    assert rows["House"].email == "house@x.com"                # local-only row still listed
    assert d.get_email("redwards") == "reggie@x.com"
    assert d.keys_with_email() == ["REdwards", "House"]
    assert d.keys_for_email("REGGIE@x.com") == ["redwards"]
    facts = d.all_as_facts()
    assert facts["redwards"].number == "080" and facts["redwards"].display_name == "Reggie"
    assert facts["hkaufman"].full_name == "Heshy Kaufman" and facts["hkaufman"].number == ""
    assert d.status()["master_source"] == "sp"


def test_local_table_is_the_answer_until_the_sp_answers(tmp_path):
    down = SalesmanDirectory(_Client(_SP, fail=True), _repo(tmp_path))
    assert down.sp_rows() is None
    assert down.get_email("REdwards") == "old@x.com"
    # Same as the old table lookup: raw key only when display_name is the SalesGroup.
    assert down.keys_with_email() == ["House", "redwards"]
    assert down.status()["master_error"] == "down"
    assert down.status()["master_source"] == "local"

    unconfigured = SalesmanDirectory(_Client(_SP, configured=False), _repo(tmp_path))
    unconfigured.refresh()
    assert unconfigured.client.calls == 0
    assert unconfigured.all_as_facts()["redwards"].commission_pct == 0.05


def test_cache_and_cooldown_limit_sp_calls(tmp_path):
    client = _Client(_SP)
    d = SalesmanDirectory(client, _repo(tmp_path), ttl_seconds=3600)
    d.rows()
    d.rows()
    d.get_email("REdwards")
    assert client.calls == 1
    assert d.rows(wait=False) and client.calls == 1

    failing = _Client(_SP, fail=True)
    d2 = SalesmanDirectory(failing, _repo(tmp_path), retry_cooldown_seconds=60)
    d2.rows()
    d2.rows()
    assert failing.calls == 1                                  # cooldown after a failure

"""Salesman seed: read live config xlsx -> repository -> SalesmanFact map."""

from pathlib import Path

import pytest

from report_engine.lib import salesman_key
from web.data.connection import Database
from web.data.repositories.salesmen import SalesmanRepository, SalesmanSeed
from web.data import seed_salesmen as SEED

_MIGRATION = (Path(__file__).resolve().parents[1]
              / "web" / "data" / "migrations" / "precious" / "0001_initial.sql")


@pytest.fixture()
def db(tmp_path) -> Database:
    d = Database(tmp_path / "precious.db", tmp_path / "cache.db")
    with d.precious() as conn:
        conn.executescript(_MIGRATION.read_text(encoding="utf-8"))
    return d


def test_upsert_and_facts_roundtrip(db):
    repo = SalesmanRepository(db)
    repo.upsert_many([
        SalesmanSeed(raw_key="REdwards", number="080", full_name="Reggie Edwards",
                     display_name="REdwards", email="r@x.com", commission_pct=0.05),
    ])
    facts = repo.all_as_facts()
    key = salesman_key("REdwards")
    assert key in facts
    assert facts[key].number == "080"
    assert facts[key].commission_pct == 0.05
    assert repo.list_all()[0].email == "r@x.com"
    assert repo.get_email("REdwards") == "r@x.com"


def test_upsert_is_idempotent_and_updates(db):
    repo = SalesmanRepository(db)
    repo.upsert_many([SalesmanSeed(raw_key="MKolko", number="012",
                                   full_name="Mendy Kolko", display_name="MKolko")])
    repo.upsert_many([SalesmanSeed(raw_key="MKolko", number="012",
                                   full_name="Mendy Kolko", display_name="MK",
                                   commission_pct=0.03)])
    assert repo.count() == 1
    facts = repo.all_as_facts()
    assert facts[salesman_key("MKolko")].display_name == "MK"
    assert facts[salesman_key("MKolko")].commission_pct == 0.03


def test_keys_with_email_prefers_salesgroup_display_name(db):
    repo = SalesmanRepository(db)
    repo.upsert_many([
        SalesmanSeed(raw_key="REdwards", number="080", full_name="Reggie Edwards",
                     display_name="REdwards", email="r@x.com"),
        SalesmanSeed(raw_key="NoMail", number="1", full_name="No Mail",
                     display_name="NoMail", email=""),
        SalesmanSeed(raw_key="MKolko", number="012", full_name="Mendy Kolko",
                     display_name="M Kolko", email="m@x.com"),
    ])
    assert repo.keys_with_email() == ["mkolko", "REdwards"]


def test_reads_live_config_xlsx_if_present(db):
    if not SEED.DEFAULT_XLSX.is_file():
        pytest.skip("live salesman_map.xlsx not present in this checkout")
    seeds = SEED.read_seeds_from_xlsx()
    assert seeds, "expected at least one salesman row"
    assert any(s.number for s in seeds)
    n = SEED.seed_from_xlsx(db)
    assert n == SalesmanRepository(db).count() > 0

"""Focused regression tests for the reference solution, run from the repo root:

    python -m pytest -q scripts/tests

They exercise policy rules on tiny hand-built inputs, independent of the
generated batch, so each matcher change can be checked in isolation.
"""

import importlib.util
import sys
from pathlib import Path

SOLUTION = Path(__file__).resolve().parents[2] / "tasks" / "sanctions-name-screening" / "solution"
sys.path.insert(0, str(SOLUTION))
spec = importlib.util.spec_from_file_location("screen", SOLUTION / "screen.py")
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)


def entry(uid, name, dob="", aliases=(), ids=(), kind="individual"):
    return {"uid": uid, "type": kind, "primary_name": name, "script_name": None,
            "aliases": [{"name": a, "strength": "strong"} for a in aliases], "dob": dob,
            "nationalities": ["XX"], "ids": [{"type": t, "number": n} for t, n in ids], "programs": []}


def customer(name, dob="", cid="C1", id_type="", id_number="", kind="individual"):
    return {"customer_id": cid, "full_name": name, "dob": dob, "nationality": "XX",
            "id_type": id_type, "id_number": id_number, "type": kind}


def decide(watchlist, cust):
    return screen.screen(watchlist, [cust])[0]


def test_twins_without_dob_resolve_to_lowest_uid_even_if_other_spelling_is_closer():
    # The higher-uid twin carries an alias spelled exactly like the customer;
    # the policy still says lowest uid when neither is corroborated.
    wl = [entry("SDN-50000", "Leila Ebrahimi", dob="1954-09-06", aliases=["Lailla Ebrahemmi"]),
          entry("SDN-20000", "Leila Ebrahimi", dob="1983-06-21")]
    d = decide(wl, customer("Lailla Ebrahemmi"))
    assert d["decision"] == "MATCH" and d["matched_uid"] == "SDN-20000"


def test_twins_with_dob_resolve_by_date():
    wl = [entry("SDN-20000", "Leila Ebrahimi", dob="1954-09-06"),
          entry("SDN-50000", "Leila Ebrahimi", dob="1983-06-21")]
    assert decide(wl, customer("Leila Ebrahimi", "1983-06-21"))["matched_uid"] == "SDN-50000"
    assert decide(wl, customer("Leila Ebrahimi", "1983-06"))["matched_uid"] == "SDN-50000"
    assert decide(wl, customer("Leila Ebrahimi", "1954"))["matched_uid"] == "SDN-20000"


def test_identifier_beats_name_and_date():
    wl = [entry("SDN-10000", "Omar Haddad", dob="1970-01-01"),
          entry("SDN-30000", "Someone Else", ids=[("passport", "SY12345678")])]
    d = decide(wl, customer("Omar Haddad", "1970-01-01", id_type="passport", id_number="SY12345678"))
    assert d["matched_uid"] == "SDN-30000"


def test_unlisted_identifier_does_not_block_a_name_match():
    wl = [entry("SDN-10000", "Omar Haddad", dob="1970-01-01")]
    d = decide(wl, customer("Omar Haddad", "1970-01-01", id_type="passport", id_number="SY99999999"))
    assert d["decision"] == "MATCH" and d["matched_uid"] == "SDN-10000"


def test_dob_conflict_rules_out():
    wl = [entry("SDN-10000", "Omar Haddad", dob="1970-01-01")]
    assert decide(wl, customer("Omar Haddad", "1971-01-01"))["decision"] == "NO_MATCH"
    assert decide(wl, customer("Omar Haddad", "1971"))["decision"] == "NO_MATCH"
    assert decide(wl, customer("Omar Haddad", ""))["decision"] == "MATCH"


def test_weak_alias_needs_full_dob():
    wl = [{**entry("SDN-10000", "Omar Haddad", dob="1970-01-01"),
           "aliases": [{"name": "Abu Salem", "strength": "weak"}]}]
    assert decide(wl, customer("Abu Salem"))["decision"] == "NO_MATCH"
    assert decide(wl, customer("Abu Salem", "1970"))["decision"] == "NO_MATCH"
    assert decide(wl, customer("Abu Salem", "1970-01-01"))["decision"] == "MATCH"


def test_entity_and_vessel_exact_after_normalization():
    wl = [entry("SDN-10000", "Delta Textiles JSC", kind="entity"),
          entry("SDN-10001", "Sea Breeze II", kind="vessel"),
          entry("SDN-10002", "Sea Breeze III", kind="vessel")]
    assert decide(wl, customer("The Delta Textiles, AO", kind="entity"))["matched_uid"] == "SDN-10000"
    assert decide(wl, customer("Delta Construction JSC", kind="entity"))["decision"] == "NO_MATCH"
    assert decide(wl, customer("M/V Sea Breeze III", kind="vessel"))["matched_uid"] == "SDN-10002"

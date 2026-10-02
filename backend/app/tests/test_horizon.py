"""Horizon generation: fallback, cross-week phase continuity, rejection, skip."""
import pytest
from app import seed
from app.db import connect
from app.engines.rota import build_week_slots
from app.engines.phase import plan_horizon, week_span
from app.modules import horizon as horizon_mod
from app.modules.batchgen import generate_window
from app.modules.skip_week import skip_week, unskip_week


@pytest.fixture
def db(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()
    conn = connect()
    yield conn
    conn.close()


def roster(conn):
    mids = [r["id"] for r in conn.execute(
        "SELECT id FROM members WHERE active=1 AND data_quality='clean' ORDER BY id")]
    tids = [r["id"] for r in conn.execute(
        "SELECT id FROM tasks WHERE data_quality='clean' AND weight>0 ORDER BY id")]
    return mids, tids


def slots_of(conn, week):
    return [dict(r) for r in conn.execute(
        "SELECT day,task_id,member_id FROM assignments WHERE week_id=? ORDER BY id", (week,))]


def week(conn, week_id):
    return dict(conn.execute("SELECT * FROM weeks WHERE id=?", (week_id,)).fetchone())


def test_phase_default_matches_legacy_roster():
    legacy = build_week_slots([1, 2, 3], [10, 20], days=7)
    phased = build_week_slots([1, 2, 3], [10, 20], days=7, phase=0)
    assert phased == legacy


def test_horizon_one_matches_legacy_single_week(db):
    mids, tids = roster(db)
    res = generate_window(db, 1, 1, days=7)
    assert [(w["week_id"], w["action"], w["phase_start"], w["phase_end"]) for w in res["weeks"]] == [
        (1, "fill", 0, 7 * len(tids))]
    assert slots_of(db, 1) == build_week_slots(mids, tids, days=7)


def test_plan_chains_windows_without_restart():
    weeks = [{"id": i, "status": "draft", "phase_start": None, "phase_end": None} for i in (1, 2, 3)]
    plans = plan_horizon(weeks, days=7, task_count=2)
    assert [(p["phase_start"], p["phase_end"]) for p in plans] == [(0, 14), (14, 28), (28, 42)]
    assert all(p["action"] == "fill" for p in plans)


def test_phase_offset_continues_rotation_not_head_restart():
    w1 = build_week_slots([1, 2, 3, 4], [10, 20], days=7, phase=0)
    w2 = build_week_slots([1, 2, 3, 4], [10, 20], days=7, phase=14)
    assert w2[0]["member_id"] == 3
    assert [s["member_id"] for s in w1 + w2] == [[1, 2, 3, 4][i % 4] for i in range(28)]


def test_generate_three_weeks_pins_chained_windows(db):
    horizon_mod.set_horizon(db, 3)
    res = generate_window(db, 1, horizon_mod.get_horizon(db), days=7)
    span = 21
    assert [(w["phase_start"], w["phase_end"]) for w in res["weeks"]] == [
        (0, span), (span, 2 * span), (2 * span, 3 * span)]
    for i, wid in enumerate((1, 2, 3)):
        w = week(db, wid)
        assert (w["phase_start"], w["phase_end"], w["status"]) == (i * span, (i + 1) * span, "ready")


def test_generate_end_to_end_member_continuity(db):
    db.execute("INSERT INTO members(name,active,data_quality) VALUES ('新人',1,'clean')")
    db.commit()
    mids, tids = roster(db)
    generate_window(db, 1, 2, days=7)
    joined = [s["member_id"] for s in slots_of(db, 1) + slots_of(db, 2)]
    assert joined == [mids[i % len(mids)] for i in range(14 * len(tids))]
    assert slots_of(db, 2)[0]["member_id"] != mids[0]


def test_second_window_chains_from_previous_pinned_end(db):
    generate_window(db, 1, 2, days=7)
    res = generate_window(db, 2, 2, days=7)
    span = 21
    by_id = {w["week_id"]: w for w in res["weeks"]}
    assert by_id[2]["action"] == "keep"
    assert (by_id[3]["phase_start"], by_id[3]["phase_end"]) == (2 * span, 3 * span)


@pytest.mark.parametrize("bad", [0, -1, -7, "0", "-3", "abc", "", None, 1.5])
def test_invalid_horizon_rejected(bad):
    with pytest.raises(ValueError):
        horizon_mod.validate(bad)


@pytest.mark.parametrize("bad", [0, -2, "x"])
def test_invalid_horizon_not_persisted(db, bad):
    with pytest.raises(ValueError):
        horizon_mod.set_horizon(db, bad)
    db.rollback()
    assert horizon_mod.get_horizon(db) == horizon_mod.DEFAULT


def test_valid_horizon_persisted(db):
    horizon_mod.set_horizon(db, "4")
    assert horizon_mod.get_horizon(db) == 4


def test_settings_endpoint_rejects_bad_horizon(db):
    pytest.importorskip("fastapi")
    from fastapi import HTTPException
    from app.main import put_settings
    with pytest.raises(HTTPException) as e:
        put_settings({"horizon_weeks": 0})
    assert e.value.status_code == 400
    assert horizon_mod.get_horizon(db) == horizon_mod.DEFAULT


def test_plan_skipped_week_consumes_window():
    weeks = [
        {"id": 1, "status": "ready", "phase_start": 0, "phase_end": 14},
        {"id": 2, "status": "skipped", "phase_start": None, "phase_end": None},
        {"id": 3, "status": "draft", "phase_start": None, "phase_end": None},
    ]
    plans = plan_horizon(weeks, days=7, task_count=2)
    assert [(p["action"], p["phase_start"], p["phase_end"]) for p in plans] == [
        ("keep", 0, 14), ("skip", 14, 28), ("fill", 28, 42)]


def test_skipped_middle_week_gets_no_slots_but_phase_advances(db):
    generate_window(db, 1, 3, days=7)
    skip_week(db, 2)
    res = generate_window(db, 1, 3, days=7)
    span = 21
    by_id = {w["week_id"]: w for w in res["weeks"]}
    assert by_id[2]["action"] == "skip"
    assert (by_id[2]["phase_start"], by_id[2]["phase_end"]) == (span, 2 * span)
    assert slots_of(db, 2) == []
    assert by_id[3]["phase_start"] == 2 * span
    w3_first = slots_of(db, 3)[0]["member_id"]
    mids, _ = roster(db)
    assert w3_first == mids[(2 * span) % len(mids)]


def test_unskip_week_refills_same_window(db):
    generate_window(db, 1, 2, days=7)
    skip_week(db, 2)
    unskip_week(db, 2)
    res = generate_window(db, 1, 2, days=7)
    span = 21
    assert res["weeks"][1]["action"] == "fill"
    assert (res["weeks"][1]["phase_start"], res["weeks"][1]["phase_end"]) == (span, 2 * span)
    assert len(slots_of(db, 2)) == span


def test_horizon_change_does_not_rearrange_generated_weeks(db):
    generate_window(db, 1, 3, days=7)
    before = {wid: (week(db, wid), slots_of(db, wid)) for wid in (1, 2, 3)}
    horizon_mod.set_horizon(db, 3)
    generate_window(db, 1, 1, days=7)
    horizon_mod.set_horizon(db, 5)
    generate_window(db, 1, 5, days=7)
    for wid in (1, 2, 3):
        w, s = before[wid]
        now = week(db, wid)
        assert (now["phase_start"], now["phase_end"]) == (w["phase_start"], w["phase_end"])
        assert slots_of(db, wid) == s


def test_week_span():
    assert week_span(7, 3) == 21
    assert week_span(0, 3) == 0

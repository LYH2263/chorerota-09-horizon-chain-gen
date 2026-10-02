"""多周视野端到端：设置校验、批量生成、跨周相位、skipped 兼容、钉位不重排。

每个用例用独立临时 DATA_DIR，startup 的 seed.init_db() 在其中初始化。
"""
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.main import app  # db_path() 每次 connect 现读环境变量
    with TestClient(app) as c:
        yield c


def test_invalid_horizon_rejected_and_not_persisted(client):
    for bad in (0, -1, "abc", "1.5", True, 53):
        r = client.put("/api/settings", json={"horizon_weeks": bad})
        assert r.status_code == 400, bad
    # 与合法键同批提交也整体拒写，不做部分落库
    r = client.put("/api/settings", json={"horizon_weeks": 0, "household": "不应写入"})
    assert r.status_code == 400
    s = client.get("/api/settings").json()
    assert "horizon_weeks" not in s
    assert s.get("household") != "不应写入"


def test_valid_horizon_persists(client):
    assert client.put("/api/settings", json={"horizon_weeks": "3"}).status_code == 200
    assert client.get("/api/settings").json()["horizon_weeks"] == "3"


def test_horizon1_falls_back_to_legacy_single_week(client):
    # 种子库：3 个 clean 成员 [1,2,3]，3 个 clean 任务 [1,2,3]
    r = client.post("/api/weeks/1/generate", json={})
    assert r.status_code == 200
    assert r.json()["horizon"] == 1
    board = client.get("/api/weeks/1/board").json()
    assigns = board["assignments"]
    assert len(assigns) == 21  # 7 天 * 3 任务
    # 与改造前一致：从成员列表头起算
    assert [a["member_id"] for a in assigns[:3]] == [1, 2, 3]
    assert assigns[0]["day"] == 0 and assigns[-1]["day"] == 6
    weeks = {w["id"]: w for w in client.get("/api/weeks").json()}
    assert weeks[1]["start_phase"] == 0 and weeks[1]["end_phase"] == 21 % 3
    assert len(weeks) == 1  # horizon=1 不新建周


def test_cross_week_phase_is_continuous(client):
    # 加第 4 个在岗成员 -> n=4，每周 21 格，周末相位推进 21%4=1
    client.post("/api/members", json={"name": "阿新"})
    client.put("/api/settings", json={"horizon_weeks": 3})
    r = client.post("/api/weeks/1/generate", json={})
    assert r.status_code == 200
    weeks = client.get("/api/weeks").json()
    assert len(weeks) == 3
    assert [(w["start_phase"], w["end_phase"]) for w in weeks] == [(0, 1), (1, 2), (2, 3)]
    # 后一周首格紧接前一周末格，不得从成员列表头重启
    w1 = client.get("/api/weeks/1/board").json()["assignments"]
    w2 = client.get("/api/weeks/2/board").json()["assignments"]
    w3 = client.get("/api/weeks/3/board").json()["assignments"]
    assert w1[-1]["member_id"] == 1  # idx 20 % 4 == 0
    assert w2[0]["member_id"] == 2   # idx 21 % 4 == 1，而不是回到成员 1
    assert w2[0]["day"] == 0
    assert w3[0]["member_id"] == 3   # idx 42 % 4 == 2
    for board in (w1, w2, w3):
        assert len(board) == 21


def test_changing_horizon_does_not_rearrange_generated_weeks(client):
    client.post("/api/members", json={"name": "阿新"})
    client.put("/api/settings", json={"horizon_weeks": 3})
    client.post("/api/weeks/1/generate", json={})
    before = {w["id"]: (w["start_phase"], w["end_phase"], w["assignment_count"])
              for w in client.get("/api/weeks").json()}
    boards_before = {
        wid: client.get(f"/api/weeks/{wid}/board").json()["assignments"]
        for wid in before}

    # 只改现行视野长度（3 -> 2 再 -> 1）后重新生成：已生成周格位、相位同钉
    for h in (2, 1):
        client.put("/api/settings", json={"horizon_weeks": h})
        r = client.post("/api/weeks/1/generate", json={}).json()
        assert all(w["pinned"] for w in r["weeks"])
        after = {w["id"]: (w["start_phase"], w["end_phase"], w["assignment_count"])
                 for w in client.get("/api/weeks").json()}
        assert after == before
        for wid, assigns in boards_before.items():
            now = client.get(f"/api/weeks/{wid}/board").json()["assignments"]
            assert [(a["day"], a["task_id"], a["member_id"]) for a in now] == \
                   [(a["day"], a["task_id"], a["member_id"]) for a in assigns]


def test_skipped_week_gets_no_slots_but_phase_advances(client):
    from app.db import connect
    client.post("/api/members", json={"name": "阿新"})  # n=4，相位推进可见
    # 预置第 2 周 skipped、第 3 周 draft
    c = connect()
    c.execute("INSERT INTO weeks(label,status) VALUES ('第13周','skipped')")
    c.execute("INSERT INTO weeks(label,status) VALUES ('第14周','draft')")
    c.commit(); c.close()
    client.put("/api/settings", json={"horizon_weeks": 3})
    r = client.post("/api/weeks/1/generate", json={}).json()
    flags = {(w["week_id"]): (w["skipped"], w["assignment_count"], w["start_phase"], w["end_phase"])
             for w in r["weeks"]}
    # 周1：正常落格 0->1；周2：skipped 不落格但推进到 2；周3：从相位 2 正常落格
    assert flags[1] == (False, 21, 0, 1)
    assert flags[2] == (True, 0, 1, 2)
    assert flags[3] == (False, 21, 2, 3)
    assert client.get("/api/weeks/2/board").json()["assignments"] == []
    w3 = client.get("/api/weeks/3/board").json()["assignments"]
    assert w3[0]["member_id"] == 3  # idx 42 % 4 == 2，跳过没有打断节奏


def test_regenerating_after_skip_keeps_skipped_week_pinned(client):
    from app.db import connect
    c = connect()
    c.execute("INSERT INTO weeks(label,status) VALUES ('第13周','skipped')")
    c.commit(); c.close()
    client.put("/api/settings", json={"horizon_weeks": 2})
    client.post("/api/weeks/1/generate", json={})
    # 再次生成：skipped 周已钉相位，不落格、不重排
    r = client.post("/api/weeks/1/generate", json={}).json()
    assert all(w["pinned"] for w in r["weeks"])
    assert client.get("/api/weeks/2/board").json()["assignments"] == []


def test_skip_endpoint_state_gate(client):
    from app.db import connect
    # 空周可标记 skipped，ready 周锁定
    c = connect()
    c.execute("INSERT INTO weeks(label,status) VALUES ('第13周','draft')")
    c.commit(); c.close()
    assert client.post("/api/weeks/2/skip").json()["status"] == "skipped"
    client.put("/api/settings", json={"horizon_weeks": 2})
    client.post("/api/weeks/1/generate", json={})  # 周 1 变 ready
    assert client.post("/api/weeks/1/skip").status_code == 400
    # 取消 skip 清掉钉位，可重新正常落格
    assert client.post("/api/weeks/2/unskip").json()["status"] == "draft"
    r = client.post("/api/weeks/1/generate", json={}).json()
    week2 = next(w for w in r["weeks"] if w["week_id"] == 2)
    assert week2["skipped"] is False and week2["assignment_count"] == 21
    assert client.post("/api/weeks/999/skip").status_code == 404

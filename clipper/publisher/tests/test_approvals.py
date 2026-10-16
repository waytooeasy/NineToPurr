import approvals


def state(con, cid):
    return con.execute("SELECT state, hook_text FROM clips WHERE id=?", (cid,)).fetchone()


def test_approve_sets_hook_and_state(con, add_clip):
    cid = add_clip()
    assert approvals.approve(con, cid, 2)
    s = state(con, cid)
    assert (s["state"], s["hook_text"]) == ("approved", "h two")
    a = con.execute("SELECT * FROM approvals WHERE clip_id=?", (cid,)).fetchone()
    assert (a["decision"], a["hook_index"], a["chosen_hook"]) == ("approved", 2, "h two")


def test_double_decision_is_rejected(con, add_clip):
    cid = add_clip()
    assert approvals.kill(con, cid)
    assert not approvals.approve(con, cid, 1)
    assert state(con, cid)["state"] == "killed"
    assert con.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 1


def test_only_qc_passed_can_be_decided(con, add_clip):
    cid = add_clip(state="edited")
    assert not approvals.kill(con, cid)
    assert state(con, cid)["state"] == "edited"


def test_bad_hook_index(con, add_clip):
    cid = add_clip()
    assert not approvals.approve(con, cid, 4)
    assert not approvals.approve(con, cid, 0)
    assert state(con, cid)["state"] == "qc_passed"


def test_rerender_stores_new_hook(con, add_clip):
    cid = add_clip()
    assert approvals.request_rerender(con, cid, "  better hook ")
    s = state(con, cid)
    assert (s["state"], s["hook_text"]) == ("needs_rerender", "better hook")


def test_empty_edit_rejected(con, add_clip):
    cid = add_clip()
    assert not approvals.request_rerender(con, cid, "   ")
    assert state(con, cid)["state"] == "qc_passed"


def test_pending_to_send_only_once(con, add_clip):
    cid = add_clip()
    add_clip(state="edited")
    assert [r["id"] for r in approvals.pending_to_send(con)] == [cid]
    approvals.mark_sent(con, cid)
    assert approvals.pending_to_send(con) == []


def test_status_report(con, add_clip):
    add_clip()
    cid = add_clip()
    approvals.record_error(con, cid, "boom")
    out = approvals.status_report(con)
    assert "qc_passed: 2" in out
    assert "Waiting for you: 2" in out
    assert f"clip {cid}: boom" in out


def test_status_report_empty(con):
    out = approvals.status_report(con)
    assert "no clips yet" in out and "Last error: none" in out

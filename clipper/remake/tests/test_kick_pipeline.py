"""A finished remake goes to QC, the visual check and Telegram at once (2026-10-28: it waited up to 20 min)."""
from remake import run
from remake.tests.test_remake import db


def test_a_done_remake_starts_the_pipeline_pass_now(monkeypatch, tmp_path):
    kicked = []
    monkeypatch.setattr(run, "candidates", lambda *a, **k: [{"id": "A", "streamer": "x"}, {"id": "B", "streamer": "x"}])
    outcomes = iter([run.Unsupported("layout"), 32])

    def one(con, s, out_dir, tw=None):
        o = next(outcomes)
        if isinstance(o, Exception):
            raise o
        return o
    monkeypatch.setattr(run, "remake_one", one)
    res = run.run(db(), tmp_path, max_n=1, tw=object(), market_data={}, trending={}, kick=lambda: kicked.append(1))
    assert res["done"] == [32] and kicked == [1]          # once, for the Short that was made, not the skip


def test_kick_asks_systemd_without_waiting_and_survives_failure(monkeypatch):
    calls = []

    class R:
        returncode, stderr = 1, "Access denied"
    run.kick_pipeline(runner=lambda cmd, **k: (calls.append(cmd), R())[1])
    assert calls == [["systemctl", "start", "--no-block", "clipper-pipeline.service"]]
    run.kick_pipeline(runner=lambda cmd, **k: (_ for _ in ()).throw(OSError("no systemctl")))   # never raises
    monkeypatch.setenv("REMAKE_KICK_PIPELINE", "0")
    run.kick_pipeline(runner=lambda cmd, **k: calls.append(cmd))
    assert len(calls) == 1

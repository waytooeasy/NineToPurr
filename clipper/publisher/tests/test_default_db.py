import approvals
import approve_bot
import upload


def test_one_shared_default_db():
    assert approvals.DEFAULT_DB == "/opt/clipper/db/clip.db"
    assert upload.DEFAULT_DB is approvals.DEFAULT_DB


def test_no_stale_db_path_in_sources():
    for mod in (upload, approve_bot):
        assert "clipper.db" not in open(mod.__file__).read()

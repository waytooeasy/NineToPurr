"""setup.sh unit install + .env.example coverage. Offline: fake systemctl, no sudo."""
import os
import re
import stat
import subprocess
from pathlib import Path

CLIPPER = Path(__file__).resolve().parents[2]
SETUP = "clipper/infra/setup.sh"
ENABLED = ["clipper-pipeline.timer", "clipper-upload.timer", "clipper-remake.timer", "clipper-approve-bot.service"]


def _run(tmp_path, data_has_repo=True):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    if data_has_repo:
        (data / "repo").symlink_to(CLIPPER.parent)
    fake = tmp_path / "systemctl"
    fake.write_text(f'#!/bin/sh\necho "$@" >> {tmp_path}/calls\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    units = tmp_path / "units"
    env = dict(os.environ, CLIPPER_DATA=str(data), UNIT_DIR=str(units), SUDO="",
               SYSTEMCTL=str(fake))
    r = subprocess.run(["bash", str(data / "repo" / SETUP), "--units-only"],
                       env=env, capture_output=True, text=True)
    return r, units, tmp_path / "calls"


def test_units_installed_and_enabled_idempotently(tmp_path):
    for _ in range(2):
        r, units, calls = _run(tmp_path, data_has_repo=not (tmp_path / "data").exists())
        assert r.returncode == 0, r.stderr
    src = {p.name for p in (CLIPPER / "infra/systemd").glob("clipper-*")}
    assert src and src == {p.name for p in units.iterdir()}
    lines = calls.read_text().splitlines()
    assert lines.count("daemon-reload") == 2
    assert f"enable {' '.join(ENABLED)}" in lines


def test_refuses_outside_opt_clipper_repo(tmp_path):
    (tmp_path / "data").mkdir()
    env = dict(os.environ, CLIPPER_DATA=str(tmp_path / "data"), UNIT_DIR=str(tmp_path / "u"), SUDO="")
    r = subprocess.run(["bash", str(CLIPPER / "infra/setup.sh"), "--units-only"],
                       env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "/repo" in r.stderr
    assert not (tmp_path / "u").exists()


def test_env_example_lists_every_env_var_the_code_reads():
    listed = set(re.findall(r"^([A-Z][A-Z0-9_]+)=", (CLIPPER / "infra/.env.example").read_text(), re.M))
    read = set()
    for py in CLIPPER.rglob("*.py"):
        if "tests" in py.parts:
            continue
        text = py.read_text()
        read |= set(re.findall(r'(?:environ(?:\.get)?|getenv|\be(?:\.get)?)[\[(]\s*"([A-Z][A-Z0-9_]+)"', text))
    assert read, "scan found nothing"
    assert read <= listed, sorted(read - listed)
    for name in ("UPLOAD_TZ", "YOUTUBE_API_KEY", "TELEGRAM_BOT_TOKEN"):
        assert name in listed


def test_env_example_has_no_values():
    for line in (CLIPPER / "infra/.env.example").read_text().splitlines():
        if re.match(r"^[A-Z]", line):
            # Empty, and no inline comment: systemd EnvironmentFile would keep "# ..." as the value.
            assert re.match(r"^[A-Z0-9_]+=$", line), line


def _run_cron(tmp_path, existing):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    if not (data / "repo").exists():
        (data / "repo").symlink_to(CLIPPER.parent)
    tab = tmp_path / "tab"
    if existing is not None:
        tab.write_text(existing)
    fake = tmp_path / "crontab"
    fake.write_text(
        "#!/bin/sh\n"
        f'if [ "$1" = "-l" ]; then [ -f {tab} ] || {{ echo "no crontab" >&2; exit 1; }}; cat {tab}; exit 0; fi\n'
        f"cat > {tab}\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, CLIPPER_DATA=str(data), SUDO="", CRONTAB=str(fake))
    r = subprocess.run(["bash", str(data / "repo" / SETUP), "--cron-only"],
                       env=env, capture_output=True, text=True)
    return r, tab


def test_ytdlp_cron_on_fresh_box_without_crontab(tmp_path):
    r, tab = _run_cron(tmp_path, existing=None)
    assert r.returncode == 0, r.stderr
    lines = tab.read_text().splitlines()
    assert len(lines) == 1 and "yt-dlp" in lines[0]


def test_ytdlp_cron_idempotent_and_keeps_other_jobs(tmp_path):
    r, tab = _run_cron(tmp_path, existing="")
    assert r.returncode == 0, r.stderr
    tab.write_text(tab.read_text() + "0 1 * * * echo other\n")
    for _ in range(2):
        r, tab = _run_cron(tmp_path, existing=tab.read_text())
        assert r.returncode == 0, r.stderr
    lines = tab.read_text().splitlines()
    assert sum("yt-dlp" in l for l in lines) == 1
    assert "0 1 * * * echo other" in lines


def test_units_put_the_venv_on_path():
    # Code runs "yt-dlp" by name; under systemd it is only found via the venv's bin/ (first VM pass).
    for unit in ("clipper-pipeline.service", "clipper-upload.service", "clipper-remake.service", "clipper-approve-bot.service"):
        text = (CLIPPER / "infra/systemd" / unit).read_text()
        assert "Environment=PATH=/opt/clipper/venv/bin:" in text, unit

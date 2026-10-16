"""setup.sh unit install + .env.example coverage. Offline: fake systemctl, no sudo."""
import os
import re
import stat
import subprocess
from pathlib import Path

CLIPPER = Path(__file__).resolve().parents[2]
SETUP = "clipper/infra/setup.sh"
ENABLED = ["clipper-pipeline.timer", "clipper-upload.timer", "clipper-approve-bot.service"]


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
            assert re.match(r"^[A-Z0-9_]+=\s*(#.*)?$", line), line

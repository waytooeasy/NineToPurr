"""Twitch Helix client: app token (client credentials, cached), user lookup, Get Clips."""
import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests

API = "https://api.twitch.tv/helix"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"


def _token_cache_path():
    work = Path(os.environ.get("CLIPPER_WORK", "/opt/clipper/work"))
    return work.parent / "twitch_token.json"


class Twitch:
    def __init__(self, client_id=None, client_secret=None, session=None, cache_path=None):
        self.client_id = client_id or os.environ["TWITCH_CLIENT_ID"]
        self.client_secret = client_secret or os.environ["TWITCH_CLIENT_SECRET"]
        self.http = session or requests.Session()
        self.cache_path = Path(cache_path) if cache_path else _token_cache_path()
        self._token = None

    def token(self):
        """Cached app access token; refreshed 5 min before expiry."""
        if self._token:
            return self._token
        try:
            c = json.loads(self.cache_path.read_text())
            if c["client_id"] == self.client_id and c["expires_at"] > time.time() + 300:
                self._token = c["access_token"]
                return self._token
        except (OSError, ValueError, KeyError):
            pass
        r = self.http.post(TOKEN_URL, params={
            "client_id": self.client_id, "client_secret": self.client_secret,
            "grant_type": "client_credentials"}, timeout=20)
        r.raise_for_status()
        d = r.json()
        self._token = d["access_token"]
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps({
                "client_id": self.client_id, "access_token": self._token,
                "expires_at": time.time() + d.get("expires_in", 0)}))
            self.cache_path.chmod(0o600)
        except OSError:
            pass  # cache is best-effort
        return self._token

    def _get(self, path, params):
        h = {"Client-Id": self.client_id, "Authorization": f"Bearer {self.token()}"}
        r = self.http.get(f"{API}/{path}", params=params, headers=h, timeout=20)
        if r.status_code == 401:  # token revoked/expired: refresh once
            self._token = None
            self.cache_path.unlink(missing_ok=True)
            h["Authorization"] = f"Bearer {self.token()}"
            r = self.http.get(f"{API}/{path}", params=params, headers=h, timeout=20)
        r.raise_for_status()
        return r.json()

    def broadcaster_id(self, login):
        data = self._get("users", {"login": login}).get("data", [])
        if not data:
            raise ValueError(f"unknown Twitch login: {login}")
        return data[0]["id"]

    def is_live(self, login):
        """Get Streams: True when `login` is live right now."""
        return bool(self._get("streams", {"user_login": login}).get("data"))

    def get_clips(self, broadcaster_id, started_at, ended_at, max_clips=500):
        """Clips in [started_at, ended_at] (aware datetimes), following pagination."""
        params = {"broadcaster_id": broadcaster_id, "first": 100,
                  "started_at": _rfc3339(started_at), "ended_at": _rfc3339(ended_at)}
        out = []
        while len(out) < max_clips:
            d = self._get("clips", params)
            out.extend(d.get("data", []))
            cursor = (d.get("pagination") or {}).get("cursor")
            if not cursor:
                break
            params["after"] = cursor
        return out[:max_clips]


def _rfc3339(dt: datetime):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

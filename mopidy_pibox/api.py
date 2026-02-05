from __future__ import absolute_import, unicode_literals

import json

from mopidy import config
import socket
import tornado.web

import logging

from mopidy.models import ModelJSONEncoder, Track
from . import socket
from .pibox import RateLimitExceeded
import os
import json
import re

# Default timeout for actor calls (in seconds)
API_CALL_TIMEOUT = 15


class PiboxHandler(tornado.web.RequestHandler):
    def initialize(self, core, frontend):
        self.core = core
        self.frontend = frontend
        self.logger = logging.getLogger(__name__)

    def _get_body(self):
        return tornado.escape.json_decode(self.request.body)

    def _get_user_fingerprint(self):
        return self.request.headers["X-Pibox-Fingerprint"]


class TracklistHandler(PiboxHandler):
    def initialize(self, core, frontend):
        super(TracklistHandler, self).initialize(core, frontend)

    def post(self):
        data = self._get_body()
        fingerprint = self._get_user_fingerprint()
        track_uri = data["track"]
        (_success, error) = self.frontend.add_track_to_queue(track_uri, fingerprint).get(timeout=API_CALL_TIMEOUT)
        tracklist = self.frontend.get_queued_tracks(fingerprint).get(timeout=API_CALL_TIMEOUT)
        # include any per-user vote cooldown so clients can display it
        try:
            retry_seconds = self.frontend.pibox.get_vote_cooldown_seconds(fingerprint).get(timeout=API_CALL_TIMEOUT)
        except Exception:
            retry_seconds = None
        self.set_header("Content-Type", "application/json")
        self.write(
            json.dumps({"tracklist": tracklist, "error": error, "retry_after_seconds": retry_seconds}, cls=ModelJSONEncoder)
        )

    def get(self):
        fingerprint = self._get_user_fingerprint()
        tracklist = self.frontend.get_queued_tracks(fingerprint).get(timeout=API_CALL_TIMEOUT)
        try:
            retry_seconds = self.frontend.pibox.get_vote_cooldown_seconds(fingerprint).get(timeout=API_CALL_TIMEOUT)
        except Exception:
            retry_seconds = None
        self.set_header("Content-Type", "application/json")
        self.write(
            json.dumps({"tracklist": tracklist, "retry_after_seconds": retry_seconds}, cls=ModelJSONEncoder)
        )

    def delete(self):
        data = self._get_body()
        fingerprint = self._get_user_fingerprint()
        track_uri = data.get("track")
        (_success, error) = self.frontend.remove_user_added_track(fingerprint, track_uri).get(timeout=API_CALL_TIMEOUT)
        tracklist = self.frontend.get_queued_tracks(fingerprint).get(timeout=API_CALL_TIMEOUT)
        try:
            retry_seconds = self.frontend.pibox.get_vote_cooldown_seconds(fingerprint).get(timeout=API_CALL_TIMEOUT)
        except Exception:
            retry_seconds = None
        self.set_header("Content-Type", "application/json")
        self.write(
            json.dumps({"tracklist": tracklist, "error": error, "retry_after_seconds": retry_seconds}, cls=ModelJSONEncoder)
        )


class VoteHandler(PiboxHandler):
    def initialize(self, core, frontend):
        super(VoteHandler, self).initialize(core, frontend)

    def post(self):
        data = self._get_body()
        fingerprint = self._get_user_fingerprint()
        track = Track(uri=data["uri"])

        if self.frontend.pibox.has_user_voted_on_track(fingerprint, track).get(timeout=API_CALL_TIMEOUT):
            self.set_status(400)
            response = {
                "code": "15",
                "title": "Voted Already",
                "message": "User has already used their 1 vote to skip on this track",
            }
            self.write(response)
        else:
            try:
                self.frontend.add_vote_for_user_on_queued_track(fingerprint, track)

                socket.PiboxWebSocket.send(
                    "VOTE_ADDED",
                    {},
                )

                self.set_status(200)
            except RateLimitExceeded as e:
                self.set_status(429)
                response = {
                    "code": "RATE_LIMIT",
                    "title": "Rate Limit Exceeded",
                    "message": str(e),
                    "retry_after_seconds": getattr(e, "seconds_remaining", None),
                }
                self.write(response)


class SessionHandler(PiboxHandler):
    def initialize(self, core, frontend):
        super(SessionHandler, self).initialize(core, frontend)

    def post(self):
        data = self._get_body()
        skip_threshold = data["skipThreshold"]
        playlists = data.get("playlists", [])
        auto_start = data.get("autoStart", True)
        shuffle = data.get("shuffle", True)

        self.frontend.start_session(int(skip_threshold), playlists, auto_start, shuffle)
        session = self.frontend.pibox.to_json().get(timeout=API_CALL_TIMEOUT)

        socket.PiboxWebSocket.send(
            "SESSION_STARTED",
            session,
        )
        self.set_status(200)

    def get(self):
        session = self.frontend.pibox.to_json().get(timeout=API_CALL_TIMEOUT)
        self.write(session)

    def delete(self):
        self.frontend.end_session().get(timeout=API_CALL_TIMEOUT)
        socket.PiboxWebSocket.send("SESSION_ENDED", {})
        self.set_status(200)


class SessionPlaylistsHandler(PiboxHandler):
    """Handler to update playlists during an active session."""

    def initialize(self, core, frontend):
        super(SessionPlaylistsHandler, self).initialize(core, frontend)

    def post(self):
        """Update the selected playlists for the current session."""
        if not self.frontend.pibox.started.get(timeout=API_CALL_TIMEOUT):
            self.set_status(400)
            self.write({"error": "NO_ACTIVE_SESSION", "message": "No active session to update"})
            return

        data = self._get_body()
        playlists = data.get("playlists", [])

        if not playlists:
            self.set_status(400)
            self.write({"error": "NO_PLAYLISTS", "message": "At least one playlist must be selected"})
            return

        self.frontend.update_session_playlists(playlists)
        session = self.frontend.pibox.to_json().get(timeout=API_CALL_TIMEOUT)

        socket.PiboxWebSocket.send(
            "SESSION_PLAYLISTS_UPDATED",
            session,
        )

        self.set_header("Content-Type", "application/json")
        self.write(session)


class SuggestionsHandler(PiboxHandler):
    def initialize(self, core, frontend):
        super(SuggestionsHandler, self).initialize(core, frontend)

    def get(self):
        suggestions = self.frontend.get_suggestions(3).get(timeout=API_CALL_TIMEOUT)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"suggestions": suggestions}, cls=ModelJSONEncoder))


class ConfigHandler(tornado.web.RequestHandler):
    def initialize(self, config: config.Proxy):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def get(self):
        pibox_config = self.config.get("pibox") or {}

        # Allow explicit override via the config: [pibox] server_address = http://host:port
        configured_address = pibox_config.get("server_address")
        if configured_address:
            server_address = configured_address
        else:
            # Determine server network IP to allow frontends (kiosk) to
            # generate QR codes that point to the server's IP address.
            server_ip = "127.0.0.1"
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                # doesn't actually send data
                s.connect(("8.8.8.8", 80))
                server_ip = s.getsockname()[0]
            except Exception:
                server_ip = "127.0.0.1"
            finally:
                try:
                    s.close()
                except Exception:
                    pass

            # prefer port from the incoming request host if available
            host = self.request.host or ""
            if ":" in host:
                port = host.split(":", 1)[1]
            else:
                port = "6680"

            server_address = f"http://{server_ip}:{port}"

        self.write(
            {
                "offline": pibox_config.get("offline"),
                "defaultPlaylists": list(pibox_config.get("default_playlists")),
                "defaultSkipThreshold": pibox_config.get("default_skip_threshold"),
                "serverAddress": server_address,
                "siteTitle": pibox_config.get("site_title") or "pibox",
                "rebootCommand": pibox_config.get("reboot_command", None),
                "wsPongTimeoutMs": pibox_config.get("ws_pong_timeout_ms") or 4000,
            }
        )


class RebootHandler(tornado.web.RequestHandler):
    def initialize(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def post(self):
        pibox_config = self.config.get("pibox") or {}
        reboot_cmd = pibox_config.get("reboot_command")
        if not reboot_cmd:
            self.set_status(404)
            self.write({"error": "reboot_command not configured"})
            return

        try:
            import subprocess

            # Run the configured reboot command. Use shell=True to allow complex commands
            # (e.g. with sudo). Command is administrator-provided via config.
            subprocess.Popen(reboot_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.set_status(200)
            self.write({"started": True})
        except Exception as e:
            self.logger.exception("Failed to run reboot command")
            self.set_status(500)
            self.write({"error": str(e)})


class ManifestHandler(tornado.web.RequestHandler):
    def initialize(self, config, static_path):
        self.config = config
        self.static_path = static_path

    def get(self):
        pibox_config = self.config.get("pibox") or {}
        site_title = pibox_config.get("site_title") or "pibox"

        manifest = {
            "short_name": site_title,
            "name": f"{site_title} Music Player",
            "icons": [
                {"src": "/pibox/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/pibox/icon-512.png", "sizes": "512x512", "type": "image/png"},
            ],
            "start_url": "/pibox/",
            "display": "standalone",
            "theme_color": "#212121",
            "background_color": "#ffffff",
        }

        self.set_header("Content-Type", "application/json")
        self.write(manifest)


class IndexHandler(tornado.web.RequestHandler):
    def initialize(self, config, static_path):
        self.config = config
        self.static_path = static_path

    def get(self):
        pibox_config = self.config.get("pibox")
        site_title = pibox_config.get("site_title") or "pibox"

        index_file = os.path.join(self.static_path, "index.html")
        try:
            with open(index_file, "r", encoding="utf-8") as fh:
                content = fh.read()
        except Exception:
            content = "<html><head><title>{}</title></head><body></body></html>".format(site_title)

        # Replace <title>...</title>
        content = re.sub(r"<title>.*?</title>", f"<title>{site_title}</title>", content, flags=re.IGNORECASE | re.DOTALL)

        # Ensure apple-mobile-web-app-title meta is present
        if "apple-mobile-web-app-title" in content:
            content = re.sub(r"<meta[^>]*name=\"apple-mobile-web-app-title\"[^>]*>",
                             f"<meta name=\"apple-mobile-web-app-title\" content=\"{site_title}\">",
                             content,
                             flags=re.IGNORECASE)
        else:
            # insert after <head>
            content = content.replace("<head>", f"<head>\n<meta name=\"apple-mobile-web-app-title\" content=\"{site_title}\">", 1)

        self.set_header("Content-Type", "text/html; charset=utf-8")
        self.write(content)

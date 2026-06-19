# Mopidy-Pibox
# Original work Copyright (c) Gavin Bannerman
# Modified work Copyright (c) 2026 Brett
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Modifications:
# - Added BrandingHandler for runtime-customizable branding images
# - Added persisted playlist selection fallback in ConfigHandler
# - Added site_title, reboot_command, ws_pong_timeout_ms config exposure

from __future__ import absolute_import, unicode_literals

import json
import mimetypes

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


import subprocess


class VolumeHandler(tornado.web.RequestHandler):
    """GET/POST /api/volume — read or set the ALSA hardware volume.

    Requires [pibox] volume_control = true in mopidy.conf.
    Uses `amixer` to talk to the configured ALSA card/control.
    Volume is expressed as an integer percentage 0-100.
    """

    def initialize(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def _vol_cfg(self):
        pibox_config = self.config.get("pibox") or {}
        return {
            "enabled": pibox_config.get("volume_control", False),
            "card": str(pibox_config.get("volume_mixer_card") or 0),
            "control": pibox_config.get("volume_mixer_control") or "Digital",
        }

    def get(self):
        cfg = self._vol_cfg()
        if not cfg["enabled"]:
            self.set_status(404)
            self.write({"error": "volume_control not enabled"})
            return
        try:
            result = subprocess.run(
                ["amixer", "-c", cfg["card"], "sget", cfg["control"]],
                capture_output=True, text=True, timeout=3,
            )
            m = re.search(r'Playback\s+\d+\s+\[(\d+)%\]', result.stdout)
            if m:
                self.write({"volume": int(m.group(1)), "enabled": True})
            else:
                self.set_status(500)
                self.write({"error": "Could not parse amixer output", "raw": result.stdout})
        except Exception as e:
            self.logger.exception("Failed to get volume")
            self.set_status(500)
            self.write({"error": str(e)})

    def post(self):
        cfg = self._vol_cfg()
        if not cfg["enabled"]:
            self.set_status(404)
            self.write({"error": "volume_control not enabled"})
            return
        try:
            data = tornado.escape.json_decode(self.request.body)
            pct = max(0, min(100, int(data.get("volume", 50))))
            result = subprocess.run(
                ["amixer", "-c", cfg["card"], "sset", cfg["control"], f"{pct}%"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode != 0:
                self.set_status(500)
                self.write({"error": result.stderr.strip()})
                return
            self.write({"volume": pct, "ok": True})
        except Exception as e:
            self.logger.exception("Failed to set volume")
            self.set_status(500)
            self.write({"error": str(e)})


class PlaylistSearchHandler(PiboxHandler):
    """Search for Tidal playlists (not limited to liked/followed playlists).

    GET /api/playlists/search?q=<query>

    Browses Tidal's featured and curated playlist categories and returns
    any whose names contain the query string (case-insensitive).  When
    query is empty or omitted, all discovered playlists are returned so
    the frontend can show a browseable list.

    Returns a JSON array of {name, uri} objects – the same shape as
    entries from mopidy.playlists.asList(), so they work directly with
    the existing PlaylistSelector component and session start/update
    flows without any further conversion.
    """

    # Top-level Tidal browse URIs that expose curated/non-user playlists.
    # Each is browsed one level deep; refs of type 'playlist' are collected.
    TIDAL_BROWSE_ROOTS = [
        "tidal:featured",
        "tidal:moods",
        "tidal:genres",
    ]

    def get(self):
        query = self.get_argument("q", "").strip().lower()

        results = self.frontend.search_tidal_playlists(query).get(timeout=API_CALL_TIMEOUT)

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(results))


class ConfigHandler(tornado.web.RequestHandler):
    def initialize(self, config: config.Proxy, frontend):
        self.config = config
        self.frontend = frontend
        self.logger = logging.getLogger(__name__)

    def get(self):
        pibox_config = self.config.get("pibox") or {}

        # Allow explicit override via the config: [pibox] server_address = http://host:port
        configured_address = pibox_config.get("server_address")
        if configured_address:
            server_address = configured_address.rstrip("/")
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

        # Get default playlists from config, or fall back to persisted selection
        default_playlists = list(pibox_config.get("default_playlists") or [])
        if not default_playlists:
            # No default_playlists configured - use persisted selection from last session
            try:
                persisted = self.frontend.pibox.get_persisted_playlists().get(timeout=API_CALL_TIMEOUT)
                if persisted:
                    # Convert to URI list for frontend compatibility
                    default_playlists = [p.get("uri") for p in persisted if p.get("uri")]
            except Exception as e:
                self.logger.debug(f"Failed to get persisted playlists: {e}")

        self.write(
            {
                "offline": pibox_config.get("offline"),
                "defaultPlaylists": default_playlists,
                "defaultSkipThreshold": pibox_config.get("default_skip_threshold"),
                "serverAddress": server_address,
                "siteTitle": pibox_config.get("site_title") or "pibox",
                "rebootCommand": pibox_config.get("reboot_command", None),
                "wsPongTimeoutMs": pibox_config.get("ws_pong_timeout_ms") or 4000,
                "voteLimitCount": pibox_config.get("vote_limit_count", None),
                "voteLimitMinutes": pibox_config.get("vote_limit_minutes", None),
                "queueLimitPerUser": pibox_config.get("queue_limit_per_user", None),
                "volumeControl": pibox_config.get("volume_control", False),
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


class BrandingHandler(tornado.web.RequestHandler):
    """Serve branding images with runtime customization support.
    
    Serves images from the custom branding directory if they exist,
    otherwise falls back to the bundled default images.
    
    Custom branding directory: ~/.local/share/mopidy/pibox/branding/
    
    Supported images and their expected sizes:
      - logo.png: 196x196 - Main logo displayed on session page
      - logo-black.png: 196x196 - Logo for "nothing playing" state
      - progress-indicator.png: max 512px - Progress bar indicator on /view page
      - favicon.png: 48x48 - Browser tab icon
      - apple-touch-icon.png: 180x180 - iOS home screen icon
      - icon-192.png: 192x192 - PWA manifest icon
      - icon-512.png: 512x512 - PWA manifest icon (large)
    
    Use scripts/update-branding.sh to generate custom images from a source file.
    """
    
    # Allowed branding image names
    BRANDING_IMAGES = {
        "logo.png",
        "logo-black.png",
        "progress-indicator.png",
        "favicon.png",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
    }
    
    def initialize(self, data_dir, static_path):
        self.data_dir = data_dir
        self.static_path = static_path
        self.logger = logging.getLogger(__name__)
    
    def get(self, image_name):
        if image_name not in self.BRANDING_IMAGES:
            self.set_status(404)
            self.write({"error": f"Unknown branding image: {image_name}"})
            return
        
        # Check for custom branding first (runtime override)
        custom_path = os.path.join(self.data_dir, "branding", image_name)
        if os.path.isfile(custom_path):
            self._serve_file(custom_path)
            return
        
        # Fall back to bundled default in static/branding/
        default_path = os.path.join(self.static_path, "branding", image_name)
        if os.path.isfile(default_path):
            self._serve_file(default_path)
        else:
            self.logger.warning(f"Branding image not found: {default_path}")
            self.set_status(404)
            self.write({"error": f"Image not found: {image_name}"})
    
    def _serve_file(self, path):
        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type:
            mime_type = "application/octet-stream"
        
        self.set_header("Content-Type", mime_type)
        self.set_header("Cache-Control", "public, max-age=3600")  # Cache for 1 hour
        
        with open(path, "rb") as f:
            self.write(f.read())


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

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
# - Added BrandingHandler for runtime-customizable branding
# - Added data_dir parameter for per-instance branding support
# - Added site_title, reboot, manifest, analytics routing

from __future__ import unicode_literals

import os

from mopidy import config, ext
import pkg_resources
import pykka
import time

from . import api
from . import socket
from .routing import ClientRoutingHandler, ClientRoutingWithAnalyticsHandler

__version__ = pkg_resources.get_distribution("Mopidy-Pibox").version


def get_http_handlers(core, config, frontend, static_directory_path, data_dir):
    disable_analytics = config.get("pibox").get("disable_analytics", False)

    return [
        (
            r"/api/tracklist/?",
            api.TracklistHandler,
            {"core": core, "frontend": frontend},
        ),
        (r"/api/vote/?", api.VoteHandler, {"core": core, "frontend": frontend}),
        (
            r"/api/session/?",
            api.SessionHandler,
            {"core": core, "frontend": frontend},
        ),
        (
            r"/api/session/playlists/?",
            api.SessionPlaylistsHandler,
            {"core": core, "frontend": frontend},
        ),
        (
            r"/api/suggestions/?",
            api.SuggestionsHandler,
            {"core": core, "frontend": frontend},
        ),
        (
            r"/api/playlists/search/?",
            api.PlaylistSearchHandler,
            {"core": core, "frontend": frontend},
        ),
        (
            r"/config/?",
            api.ConfigHandler,
            {"config": config, "frontend": frontend},
        ),
        (
            r"/manifest.json",
            api.ManifestHandler,
            {"config": config, "static_path": static_directory_path},
        ),
        (
            r"/index.html",
            api.IndexHandler,
            {"config": config, "static_path": static_directory_path},
        ),
        (
            r"/",
            api.IndexHandler,
            {"config": config, "static_path": static_directory_path},
        ),
        (
            r"/api/reboot/?",
            api.RebootHandler,
            {"config": config},
        ),
        (
            r"/branding/(.+\.png)",
            api.BrandingHandler,
            {"data_dir": str(data_dir), "static_path": static_directory_path},
        ),
        (
            r"/(.*)",
            ClientRoutingHandler
            if disable_analytics
            else ClientRoutingWithAnalyticsHandler,
            {
                "path": static_directory_path,
            },
        ),
    ]


def my_app_factory(config, core):
    from .frontend import PiboxFrontend

    actors = pykka.ActorRegistry.get_by_class(PiboxFrontend)
    if not actors:
        waited = 0.0
        while not actors and waited < 5.0:
            time.sleep(0.1)
            waited += 0.1
            actors = pykka.ActorRegistry.get_by_class(PiboxFrontend)
    if not actors:
        raise RuntimeError("PiboxFrontend actor not started")
    frontend = actors[0].proxy()

    static_directory_path = os.path.join(os.path.dirname(__file__), "static")
    data_dir = Extension.get_data_dir(config)

    return [
        (r"/ws/?", socket.PiboxWebSocket),
        *get_http_handlers(core, config, frontend, static_directory_path, data_dir),
        (r"/api/reboot/?", api.RebootHandler, {"config": config}),
    ]


class Extension(ext.Extension):
    dist_name = "Mopidy-Pibox"
    ext_name = "pibox"
    version = __version__

    def get_default_config(self):
        conf_file = os.path.join(os.path.dirname(__file__), "ext.conf")
        return config.read(conf_file)

    def get_config_schema(self):
        schema = super(Extension, self).get_config_schema()
        schema["default_playlists"] = config.List(
            optional=True, unique=True, subtype=config.String()
        )
        schema["default_skip_threshold"] = config.Integer(minimum=1)
        schema["offline"] = config.Boolean(optional=True)
        schema["disable_analytics"] = config.Boolean(optional=True)
        schema["server_address"] = config.String(optional=True)
        schema["site_title"] = config.String(optional=True)
        schema["vote_limit_count"] = config.Integer(optional=True, minimum=1)
        schema["vote_limit_minutes"] = config.Integer(optional=True, minimum=1)
        schema["queue_limit_per_user"] = config.Integer(optional=True, minimum=0)
        schema["reboot_command"] = config.String(optional=True)
        schema["ws_pong_timeout_ms"] = config.Integer(optional=True, minimum=1000)
        return schema

    def setup(self, registry):
        from .frontend import PiboxFrontend

        registry.add("frontend", PiboxFrontend)
        registry.add(
            "http:app",
            {
                "name": self.ext_name,
                "factory": my_app_factory,
            },
        )

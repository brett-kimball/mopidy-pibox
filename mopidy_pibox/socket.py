import logging
import json

import tornado.websocket


class PiboxWebSocket(tornado.websocket.WebSocketHandler):
    clients = set()
    logger = logging.getLogger(__name__)

    def check_origin(self, origin):
        return True

    def open(self):
        self.clients.add(self)
        self.logger.debug("WebSocket opened")

    def on_message(self, message):
        # Expect JSON messages from clients; respond to PING with PONG
        try:
            data = json.loads(message)
        except Exception:
            # Non-JSON or unexpected payload; log at debug to avoid flooding
            self.logger.debug(message)
            return

        msg_type = data.get("type")
        if msg_type == "PING":
            try:
                self.write_message({"type": "PONG", "ts": data.get("ts")})
                self.logger.debug("Responded to PING from client")
            except Exception:
                pass
            return
        # otherwise log at info (useful messages other than PING)
        self.logger.info(message)

    def on_close(self):
        self.clients.remove(self)
        self.logger.debug("WebSocket closed")

    @classmethod
    def send(cls, subject, message):
        for conn in cls.clients:
            conn.write_message({"type": subject, "payload": message})

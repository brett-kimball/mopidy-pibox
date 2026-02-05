import MopidyConnection from "mopidy";
import { getFingerprint } from "./fingerprint";
import { pibox } from "./pibox";
// Avoid importing `BACKEND_PRIORITY_ORDER` from the Search component
// to prevent a circular dependency between services/mopidy.js and
// components/search/Search.jsx. Define the backend priority order
// locally here.

let mopidy = null;
let piboxWebsocket = null;
let _piboxShouldReconnect = true;
let _piboxReconnectAttempts = 0;
let _piboxReconnectTimer = null;
let _piboxPingTimer = null;
let _piboxPongTimer = null;
let PIBOX_PING_INTERVAL = 8000; // send ping every 8s
let PIBOX_PONG_TIMEOUT = 4000; // expect pong within 4s (configurable via config API)

const PIBOX_RECONNECT_BASE_MS = 1000;
const PIBOX_RECONNECT_MAX_MS = 30000;

const BACKEND_PRIORITY_ORDER = ["spotify", "soundcloud"];

// Allow runtime update of PONG timeout from config
export const setPiboxPongTimeout = (ms) => {
  if (typeof ms === "number" && ms >= 1000) {
    PIBOX_PONG_TIMEOUT = ms;
  }
};

export class PiboxError extends Error {
  constructor(message, meta = {}) {
    super(message);
    this.name = "PiboxError";
    this.meta = meta;
  }
}

const connectToMopidy = (webSocketUrl) =>
  new Promise((resolve) => {
    mopidy = new MopidyConnection({
      webSocketUrl,
    });

    resolve(mopidy);
  });

const _dispatchPiboxEvent = (data) => {
  let event;
  switch (data.type) {
    case "SESSION_STARTED":
      event = new CustomEvent("pibox:sessionStart", { detail: data.payload });
      break;
    case "SESSION_ENDED":
      event = new CustomEvent("pibox:sessionEnd", { detail: data.payload });
      break;
    case "SESSION_PLAYLISTS_UPDATED":
      event = new CustomEvent("pibox:sessionPlaylistsUpdated", { detail: data.payload });
      break;
    case "VOTE_ADDED":
      event = new CustomEvent("pibox:voteAdded", { detail: data.payload });
      break;
    default:
      console.debug("Default pibox websocket statement hit");
      break;
  }
  if (event) document.dispatchEvent(event);
};

const _clearPiboxReconnect = () => {
  _piboxReconnectAttempts = 0;
  if (_piboxReconnectTimer) {
    clearTimeout(_piboxReconnectTimer);
    _piboxReconnectTimer = null;
  }
};

const _schedulePiboxReconnect = (url) => {
  if (!_piboxShouldReconnect) return;
  _piboxReconnectAttempts += 1;
  const backoff = Math.min(
    PIBOX_RECONNECT_BASE_MS * 2 ** (_piboxReconnectAttempts - 1),
    PIBOX_RECONNECT_MAX_MS,
  );
  if (_piboxReconnectTimer) clearTimeout(_piboxReconnectTimer);
  _piboxReconnectTimer = setTimeout(() => {
    createPiboxWebSocket(url);
  }, backoff + Math.floor(Math.random() * 250));
};

const createPiboxWebSocket = (websocketUrl) => {
  try {
    if (piboxWebsocket && (piboxWebsocket.readyState === WebSocket.OPEN || piboxWebsocket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    piboxWebsocket = new WebSocket(websocketUrl);

    piboxWebsocket.onopen = () => {
      _clearPiboxReconnect();
      _startPiboxHeartbeat();
      document.dispatchEvent(new CustomEvent("pibox:connected", { detail: true }));
    };

    piboxWebsocket.onmessage = (message) => {
      try {
        const data = JSON.parse(message.data);
        // handle PONG for heartbeat
        if (data && data.type === "PONG") {
          // clear pong timeout
          if (_piboxPongTimer) {
            clearTimeout(_piboxPongTimer);
            _piboxPongTimer = null;
          }
          return;
        }
        _dispatchPiboxEvent(data);
      } catch (e) {
        console.debug("Invalid pibox websocket message", e);
      }
    };

    piboxWebsocket.onclose = (ev) => {
      _stopPiboxHeartbeat();
      document.dispatchEvent(new CustomEvent("pibox:connected", { detail: false }));
      // If the page is hidden, defer aggressive reconnect attempts until visible.
      if (document.visibilityState === "hidden") {
        // Keep the shouldReconnect flag true but don't attempt an immediate reconnect.
        return _schedulePiboxReconnect(websocketUrl);
      }
      _schedulePiboxReconnect(websocketUrl);
    };

    piboxWebsocket.onerror = (err) => {
      // ensure heartbeat is stopped on error
      _stopPiboxHeartbeat();
      console.debug("Pibox websocket error", err);
    };
  } catch (e) {
    _schedulePiboxReconnect(websocketUrl);
  }
};

const _sendPiboxPing = () => {
  if (!piboxWebsocket || piboxWebsocket.readyState !== WebSocket.OPEN) return;
  try {
    const ts = Date.now();
    piboxWebsocket.send(JSON.stringify({ type: "PING", ts }));
    // set pong timeout
    if (_piboxPongTimer) clearTimeout(_piboxPongTimer);
    _piboxPongTimer = setTimeout(() => {
      // no PONG received in time — force reconnect
      try {
        piboxWebsocket.close();
      } catch (e) {
        // ignore
      }
    }, PIBOX_PONG_TIMEOUT);
  } catch (e) {
    // ignore send failures
  }
};

const _startPiboxHeartbeat = () => {
  _stopPiboxHeartbeat();
  _sendPiboxPing();
  _piboxPingTimer = setInterval(_sendPiboxPing, PIBOX_PING_INTERVAL);
};

const _stopPiboxHeartbeat = () => {
  if (_piboxPingTimer) {
    clearInterval(_piboxPingTimer);
    _piboxPingTimer = null;
  }
  if (_piboxPongTimer) {
    clearTimeout(_piboxPongTimer);
    _piboxPongTimer = null;
  }
};

const connectToPibox = (websocketUrl) => {
  _piboxShouldReconnect = true;
  createPiboxWebSocket(websocketUrl);

  // When the page becomes visible again (iOS bfcache/pageshow), try to reconnect immediately.
  const onVisibility = () => {
    if (document.visibilityState === "visible") {
      if (!piboxWebsocket || piboxWebsocket.readyState === WebSocket.CLOSED) {
        createPiboxWebSocket(websocketUrl);
      }
    }
  };

  const onPageShow = (ev) => {
    // pageshow persists during bfcache restores; attempt reconnect if persisted
    if (ev.persisted || document.visibilityState === "visible") {
      createPiboxWebSocket(websocketUrl);
    }
  };

  const onBeforeUnload = () => {
    // stop reconnect attempts when user intentionally leaves
    _piboxShouldReconnect = false;
    if (piboxWebsocket) {
      try {
        piboxWebsocket.close();
      } catch (e) {
        // ignore
      }
    }
  };

  document.removeEventListener("visibilitychange", onVisibility);
  document.addEventListener("visibilitychange", onVisibility);
  window.removeEventListener("pageshow", onPageShow);
  window.addEventListener("pageshow", onPageShow);
  window.removeEventListener("beforeunload", onBeforeUnload);
  window.addEventListener("beforeunload", onBeforeUnload);

  // Try reconnecting when the network comes back or window gains focus
  const onOnline = () => {
    if (!piboxWebsocket || piboxWebsocket.readyState === WebSocket.CLOSED) {
      createPiboxWebSocket(websocketUrl);
    }
  };

  const onFocus = () => {
    if (!piboxWebsocket || piboxWebsocket.readyState === WebSocket.CLOSED) {
      createPiboxWebSocket(websocketUrl);
    }
  };

  window.removeEventListener("online", onOnline);
  window.addEventListener("online", onOnline);
  window.removeEventListener("focus", onFocus);
  window.addEventListener("focus", onFocus);
};

export const initialiseMopidy = async () => {
  const hostname = location.hostname;
  const port = location.port ? `:${location.port}` : "";
  const protocol =
    typeof document !== "undefined" && document.location.protocol === "https:"
      ? "wss://"
      : "ws://";
  const baseWebsocketUrl = `${protocol}${hostname}${port}`;
  mopidy = await connectToMopidy(`${baseWebsocketUrl}/mopidy/ws/`);
  connectToPibox(`${baseWebsocketUrl}/pibox/ws`);
  return mopidy;
};

export const getTracklist = async () => {
  const result = await pibox.get("/api/tracklist/");
  return result.data;
};

export const getCurrentTrack = () => mopidy.playback.getCurrentTrack();

export const getPlaybackState = () => mopidy.playback.getState();
export const getTimePosition = () => mopidy.playback.getTimePosition();

const _preferTidalSize = (url, size = 1280) => {
  if (!url) return url;

  try {
    // ?size=NNN or &size=NNN
    if (/[?&]size=\d+/.test(url)) {
      return url.replace(/([?&]size=)\d+/, `$1${size}`);
    }

    // /640x640/ pattern
    if (/\d+x\d+/.test(url)) {
      return url.replace(/(\d+)x(\d+)/, `${size}x${size}`);
    }

    // -640.jpg suffix
    if (/-\d+\.(jpg|png|webp|jpeg)$/i.test(url)) {
      return url.replace(/-(\d+)(\.(jpg|png|webp|jpeg))$/i, `-${size}$2`);
    }
  } catch (e) {
    // fall through to return original
  }

  return url;
};

export const getArtwork = (uri, size = 640) =>
  new Promise((resolve) => {
    mopidy.library.getImages({ uris: [uri] }).then((result) => {
      const images = result[uri] || [];
      const artworkUri = images.length ? images[0].uri : "";
      const preferred = _preferTidalSize(artworkUri, size);
      resolve(preferred || artworkUri);
    }).catch(() => resolve(""));
  });

export const getConfig = async () => {
  const result = await pibox.get("/config");
  return result.data;
};

export const getCurrentSession = async () => {
  const result = await pibox.get("/api/session");
  return result.data;
};

export const getSuggestions = async () => {
  const result = await pibox.get("/api/suggestions");
  return result.data;
};

export const getPlaylists = async () => {
  try {
    const playlists = await mopidy.playlists.asList();
    return playlists || [];
  } catch (e) {
    console.error("Could not fetch playlists:", e);
    return [];
  }
};

export const getMixes = async () => {
  try {
    // Browse tidal:my_mixes to get user's favorited mixes (Mixes & Radio)
    const mixes = await mopidy.library.browse({ uri: "tidal:my_mixes" });
    // Prepend "Mix:" to differentiate from regular playlists
    return (mixes || []).map((mix) => ({
      ...mix,
      name: `Mix - ${mix.name}`,
    }));
  } catch (e) {
    console.debug("Could not fetch mixes:", e);
    return [];
  }
};

export const getPlaylistsAndMixes = async () => {
  const [playlists, mixes] = await Promise.all([
    getPlaylists(),
    getMixes(),
  ]);
  console.debug("Fetched playlists:", playlists?.length, "mixes:", mixes?.length);
  // Combine playlists and mixes, mixes come after playlists
  return [...(playlists || []), ...(mixes || [])];
};

export const queueTrack = async (selectedTrack) => {
  const result = await pibox.post("/api/tracklist", {
    track: selectedTrack.uri,
  });

  if (result?.data?.error) {
    switch (result?.data?.error) {
      case "ALREADY_PLAYED":
        throw new PiboxError("Track has already been played");
      case "ALREADY_QUEUED":
        throw new PiboxError("Track has already been queued");
      case "USER_QUEUE_LIMIT":
        throw new PiboxError("You have reached your queue limit", { code: "USER_QUEUE_LIMIT" });
      default:
        throw new PiboxError("An unknown error occurred");
    }
  }

  return result.data.tracklist;
};

export const startSession = async (
  skipThreshold,
  playlists,
  automaticallyStartPlaying,
  enableShuffle,
) => {
  const result = await pibox.post("/api/session", {
    skipThreshold,
    playlists,
    autoStart: automaticallyStartPlaying,
    shuffle: enableShuffle,
  });
  return result.data;
};

export const endSession = async () => {
  const result = await pibox.delete("/api/session");
  return result.data;
};

export const updateSessionPlaylists = async (playlists) => {
  const result = await pibox.post("/api/session/playlists", { playlists });
  
  if (result?.status === 200) {
    return result.data;
  }
  
  if (result?.data?.error === "NO_ACTIVE_SESSION") {
    throw new PiboxError("No active session to update");
  }
  
  if (result?.data?.error === "NO_PLAYLISTS") {
    throw new PiboxError("At least one playlist must be selected");
  }
  
  throw new PiboxError("An error occurred while updating playlists");
};

export const rebootSystem = async () => {
  const result = await pibox.post("/api/reboot");
  if (result?.status === 200) return result.data;
  const err = result?.data?.error || result?.data?._text || "Failed to start reboot";
  throw new Error(err);
};

export const searchLibrary = (searchTerms) =>
  new Promise((resolve) => {
    mopidy.library
      .search({
        query: { any: searchTerms },
        exact: false,
      })
      .then((result) => {
        result.sort((a, b) => {
          const [backendA] = a.uri.split(":");
          const [backendB] = b.uri.split(":");
          const resultA = BACKEND_PRIORITY_ORDER.indexOf(backendA);
          return (
            (resultA === -1 ? Number.MAX_VALUE : resultA) -
            BACKEND_PRIORITY_ORDER.indexOf(backendB)
          );
        });
        const results = result.reduce((tracks, backendResult) => {
          tracks.push(...(backendResult.tracks || []));
          return tracks;
        }, []);
        resolve(results);
      })
      .catch(() => resolve([]));
  });

export const voteToSkipTrack = async (uri) => {
  const result = await pibox.post("/api/vote", {
    uri,
  });

  const status = result?.status;
  if (status === 200) {
    return result.data;
  }
  if (status === 400) {
    throw new PiboxError("User has already voted on this track");
  }
  if (status === 429) {
    let retry = result?.data?.retry_after_seconds;
    if (!retry) {
      const header = result?.headers?.retryAfter;
      if (header) {
        const parsed = parseInt(header, 10);
        if (!Number.isNaN(parsed)) retry = parsed;
      }
    }
    throw new PiboxError("Vote rate limit exceeded", { retryAfterSeconds: retry });
  }
  throw new PiboxError("An error occurred while voting");
};

export const removeQueuedTrack = async (uri) => {
  const result = await pibox.delete("/api/tracklist", { track: uri });

  const status = result?.status;
  if (status === 200) {
    return result.data;
  }

  throw new PiboxError("An error occurred while removing the track");
};

export const playIfStopped = async () => {
  const playbackState = await getPlaybackState();
  if (playbackState === "stopped") {
    mopidy.playback.play();
  }
};

export const togglePlaybackState = async () => {
  const currentPlaybackState = await getPlaybackState();
  if (currentPlaybackState === "paused") {
    mopidy.playback.resume();
  } else {
    mopidy.playback.pause();
  }
};

export const skipCurrentTrack = async () => {
  await mopidy.playback.next();
};

export const onConnectionChanged = (callback) => {
  const fn = (event) => {
    switch (event) {
      case "state:online":
        callback(true);
        break;

      default:
        callback(false);
    }
  };
  mopidy.on("state", fn);
  return () => mopidy.off("state", fn);
};

export const onPlaybackChanged = (callback) => {
  const fn = (playback) => callback(playback.new_state);
  mopidy.on("event:playbackStateChanged", fn);
  return () => mopidy.off("event:playbackStateChanged", fn);
};

export const onTracklistChanged = (callback) => {
  const fn = () => callback();
  mopidy.on("event:tracklistChanged", fn);
  return () => mopidy.off("event:tracklistChanged", fn);
};

export const onTrackPlaybackEnded = (callback) => {
  const fn = () => callback();
  mopidy.on("event:trackPlaybackEnded", fn);
  return () => mopidy.off("event:trackPlaybackEnded", fn);
};

export const onSessionStarted = (callback) => {
  const fn = (event) => callback(event.detail);
  document.addEventListener("pibox:sessionStart", fn);
  return () => document.removeEventListener("pibox:sessionStart", fn);
};

export const onSessionEnded = (callback) => {
  const fn = () => callback();
  document.addEventListener("pibox:sessionEnd", fn);
  return () => document.removeEventListener("pibox:sessionEnd", fn);
};

export const onSessionPlaylistsUpdated = (callback) => {
  const fn = (event) => callback(event.detail);
  document.addEventListener("pibox:sessionPlaylistsUpdated", fn);
  return () => document.removeEventListener("pibox:sessionPlaylistsUpdated", fn);
};

export const onVoteAdded = (callback) => {
  const fn = (event) => callback(event.detail);
  document.addEventListener("pibox:voteAdded", fn);
  return () => document.removeEventListener("pibox:voteAdded", fn);
};

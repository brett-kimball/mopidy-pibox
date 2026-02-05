import pykka
import logging
from random import sample, shuffle

from mopidy import core

from mopidy_pibox import Extension
from mopidy_pibox.pibox import Pibox

# Default timeout for Mopidy core API calls (in seconds)
# This prevents blocking indefinitely if Mopidy or a backend stalls
MOPIDY_CALL_TIMEOUT = 15

PUSSYCAT_LIST = [
    "spotify:track:0asT0RDbe4Vrf6pxLHgpkn",
    "spotify:track:2HkHE4EeZyx9AncSN042q3",
]


class PiboxFrontend(pykka.ThreadingActor, core.CoreListener):
    def __init__(self, config, core, pussycat_list=PUSSYCAT_LIST):
        super(PiboxFrontend, self).__init__()
        self.core = core
        self.config = config.get("pibox", {})
        self.pussycat_list = pussycat_list
        self.logger = logging.getLogger(__name__)

        data_dir = Extension.get_data_dir(config)
        self.pibox = pykka.traversable(Pibox(data_dir=data_dir))

        # apply vote limit config if provided
        try:
            vote_count = self.config.get("vote_limit_count", 2)
            vote_minutes = self.config.get("vote_limit_minutes", 60)
            # set on underlying pibox instance
            self.pibox.set_vote_limits(vote_count, vote_minutes)
        except Exception:
            pass
        # apply per-user queue limit if provided
        try:
            queue_limit = self.config.get("queue_limit_per_user", 0)
            self.pibox.set_queue_limit(queue_limit)
        except Exception:
            pass

        self.core.tracklist.set_consume(value=True)

    def start_session(self, skip_threshold, playlists, auto_start, shuffle):
        self.pibox.start_session(skip_threshold, playlists, shuffle)
        if auto_start:
            self.__queue_song_from_session_playlists()
            self.__start_playing()

    def update_session_playlists(self, playlists):
        """Update the selected playlists during an active session.
        
        This recalculates the remaining playlist tracks based on the new
        playlists while preserving played_tracks and denylist state.
        """
        self.pibox.update_playlists(playlists)
        
        # Recalculate remaining playlist tracks with new playlist selection
        # This uses the same logic as __queue_song_from_session_playlists
        # but only updates the remaining_playlist_tracks list
        playlist_items = self.__get_session_playlist_items()
        
        if self.pibox.shuffle:
            shuffle(playlist_items)
        
        seen = set()
        remaining_playlist = [
            ref
            for (ref, playlist_name) in playlist_items
            if (
                self.__can_play(ref.uri)
                and ref.uri not in seen
                and not seen.add(ref.uri)
            )
        ]
        
        self.__update_remaining_playlist_tracks(remaining_playlist)
        
        self.logger.info(
            f"Updated session playlists. {len(remaining_playlist)} tracks remaining."
        )

    def track_playback_ended(self, tl_track, time_position=None):
        if not self.pibox.started:
            return

        # Detect potential playback failure: if time_position is very short
        # (< 2 seconds) and the track has a reasonable length, it likely failed
        # to play (e.g., unavailable on Tidal). However, don't treat quick manual
        # skips as failures - only auto-transitions. We detect this by checking
        # if there are still tracks in the tracklist (manual skip leaves queue intact).
        is_playback_failure = False
        track_length = getattr(tl_track.track, 'length', None) if tl_track and tl_track.track else None
        tracklist_len = self.core.tracklist.get_length().get(timeout=MOPIDY_CALL_TIMEOUT)
        
        if time_position is not None and time_position < 2000 and tracklist_len == 0:
            # Track barely played AND tracklist is empty = automatic failure, not manual skip
            if track_length is None or track_length > 10000:  # track is > 10s or unknown length
                self.logger.warning(
                    f"Track {tl_track.track.uri} ended after only {time_position}ms "
                    f"(length: {track_length}ms). Treating as playback failure."
                )
                is_playback_failure = True
                # Add to denylist so we don't try it again
                try:
                    if tl_track.track.uri not in self.pibox.denylist:
                        self.pibox.denylist.append(tl_track.track.uri)
                        self.logger.info(f"Added {tl_track.track.uri} to denylist")
                except Exception:
                    pass

        # Only mark as played if it wasn't a failure
        if not is_playback_failure:
            self.__update_played_tracks(tl_track)

        if self.__should_play_whats_new_pussycat(tl_track):
            self.core.tracklist.add(uris=[self.pussycat_list[0]], at_position=0).get(timeout=MOPIDY_CALL_TIMEOUT)
            self.logger.info("Meow")
            self.__start_playing()
        elif self.core.tracklist.get_length().get(timeout=MOPIDY_CALL_TIMEOUT) == 0:
            self.__queue_song_from_session_playlists()
            self.__start_playing()

    def track_playback_started(self, tl_track, time_position=None):
        try:
            uri = tl_track.track.uri if tl_track and tl_track.track else None
        except Exception:
            uri = None
        self.logger.info(f"Track playback started: {uri}")

    def playback_state_changed(self, old_state, new_state):
        self.logger.info(f"Playback state changed: {old_state} -> {new_state}")

    def get_queued_tracks(self, user_fingerprint):
        tracks = self.core.tracklist.get_tracks().get(timeout=MOPIDY_CALL_TIMEOUT)
        result = []
        for track in tracks:
            try:
                votes = self.pibox.get_votes_for_track(track)
            except Exception:
                votes = 0
            try:
                voted = self.pibox.has_user_voted_on_track(user_fingerprint, track)
            except Exception:
                voted = False
            # determine if this track was manually added by this user
            try:
                user_list = self.pibox.user_queued_tracks.get(user_fingerprint, [])
            except Exception:
                user_list = []
            added_by_me = track.uri in user_list
            result.append({"info": track, "votes": votes, "voted": voted, "added_by_me": added_by_me})

        return result
    
    def add_track_to_queue(self, track_uri, user_fingerprint=None):
        if track_uri in self.pibox.played_tracks:
            return (False, "ALREADY_PLAYED")

        if self.__is_queued(track_uri):
            return (False, "ALREADY_QUEUED")

        # If a per-user queue limit is set, ensure the user hasn't exceeded it
        try:
            if user_fingerprint:
                allowed = self.pibox.add_manually_queued_track_for_user(user_fingerprint, track_uri)
                if not allowed:
                    return (False, "USER_QUEUE_LIMIT")
        except Exception:
            # On error, fall back to allowing the add
            pass

        self.core.tracklist.add(uris=[track_uri]).get(timeout=MOPIDY_CALL_TIMEOUT)
        try:
            self.pibox.manually_queued_tracks.append(track_uri)
            # Track the source as user-queued with their fun nickname
            if user_fingerprint:
                nickname = self.pibox.get_user_nickname(user_fingerprint)
                self.pibox.set_track_source(track_uri, "user", nickname)
        except Exception:
            pass

        return (True, None)

    def remove_user_added_track(self, user_fingerprint, track_uri):
        """Remove a track from the queue if it was added by the given user."""
        try:
            user_list = self.pibox.user_queued_tracks.get(user_fingerprint, [])
        except Exception:
            user_list = []

        if track_uri not in user_list:
            return (False, "NOT_OWNER")

        # remove from core tracklist
        try:
            self.core.tracklist.remove({"uri": [track_uri]}).get(timeout=MOPIDY_CALL_TIMEOUT)
        except Exception:
            pass

        # remove from pibox internal structures (votes, mappings, manual lists)
        try:
            self.pibox.remove_queued_track(track_uri)
        except Exception:
            pass

        return (True, None)
    

    def add_vote_for_user_on_queued_track(self, user_fingerprint, track):
        vote_count = self.pibox.add_vote_for_user_on_track(user_fingerprint, track)
        self.logger.info(
            f"Vote added for {track.uri} by {user_fingerprint} ({vote_count}/{self.pibox.skip_threshold})"
        )
        if vote_count >= self.pibox.skip_threshold:
            self.logger.info(f"Skipping {track.uri} due to votes")
            self.core.tracklist.remove({"uri": [track.uri]}).get(timeout=MOPIDY_CALL_TIMEOUT)

            self.logger.info("Track removed from tracklist")
            self.pibox.skip_queued_track(track)

    def end_session(self):
        self.core.playback.stop()
        self.core.tracklist.clear()

        self.pibox.end_session()

        # Refresh playlists so new ones are available for the next session
        self._refresh_playlists()

    def _refresh_playlists(self):
        """Refresh playlists from all backends so newly added playlists are available."""
        try:
            self.logger.info("Refreshing playlists...")
            self.core.playlists.refresh(uri_scheme="tidal").get(timeout=MOPIDY_CALL_TIMEOUT)
            self.logger.info("Playlists refreshed")
        except Exception as e:
            self.logger.warning(f"Failed to refresh playlists: {e}")

    def get_suggestions(self, length):
        suggestions = self.pibox.get_suggestions()

        unqueued_suggestions = [
            track for track in suggestions if not self.__is_queued(track)
        ]
        size = (
            len(unqueued_suggestions) if len(unqueued_suggestions) < length else length
        )
        unplayed_tracks = [
            track
            for tracks in self.core.library.lookup(sample(unqueued_suggestions, size))
            .get()
            .values()
            for track in tracks
        ]

        return unplayed_tracks

    def __queue_song_from_session_playlists(self):
        self.logger.info("Pibox is trying to queue a song")

        # playlist_items is now list of tuples: (track_ref, playlist_name)
        playlist_items = self.__get_session_playlist_items()

        if self.pibox.shuffle:
            shuffle(playlist_items)

        seen = set()

        remaining_playlist = [
            (ref, playlist_name)
            for (ref, playlist_name) in playlist_items
            if (
                self.__can_play(ref.uri)
                and ref.uri not in seen
                and not seen.add(ref.uri)
            )
        ]
        # Update remaining tracks (just the refs for compatibility)
        self.__update_remaining_playlist_tracks([ref for (ref, _) in remaining_playlist])

        if len(remaining_playlist) == 0:
            self.logger.info("No more tracks to play")
            self.end_session()
            return

        # Add the first available track. If it fails to play (e.g., unavailable
        # on Tidal), track_playback_ended will handle it by adding it to the
        # denylist and trying again.
        next_track, source_playlist = remaining_playlist[0]

        try:
            self.core.tracklist.add(uris=[next_track.uri], at_position=0).get(timeout=MOPIDY_CALL_TIMEOUT)
            # Track the source playlist for this track
            self.pibox.set_track_source(next_track.uri, "playlist", source_playlist)
            self.logger.info(f"Pibox auto-added {next_track.name} ({next_track.uri}) from '{source_playlist}' to tracklist")
        except Exception as e:
            self.logger.warning(f"Failed to add {next_track.uri} to tracklist: {e}")
            # Add to denylist and try next track
            if next_track.uri not in self.pibox.denylist:
                self.pibox.denylist.append(next_track.uri)
            # Recursively try next track
            self.__queue_song_from_session_playlists()

    def __get_session_playlist_items(self):
        """Get all tracks from session playlists with their source playlist info.
        
        Returns list of tuples: (track_ref, playlist_name)
        """
        if self.config.get("offline", False):
            tracks = self.core.library.browse(uri="local:directory?type=track").get(timeout=MOPIDY_CALL_TIMEOUT)
            return [(track, "Local Library") for track in tracks]
        else:
            result = []
            for playlist in self.pibox.playlists:
                tracks = self.core.playlists.get_items(playlist["uri"]).get(timeout=MOPIDY_CALL_TIMEOUT)
                for track in tracks:
                    result.append((track, playlist["name"]))
            return result

    def __update_played_tracks(self, tl_track):
        self.pibox.played_tracks.append(tl_track.track.uri)
        # Remove the played track from any user's manual queue entries
        try:
            self.pibox.remove_queued_track_for_all_users(tl_track.track.uri)
        except Exception:
            pass

    def __update_remaining_playlist_tracks(self, remaining_playlist):
        self.pibox.remaining_playlist_tracks = [
            track.uri for track in remaining_playlist
        ]

    def __can_play(self, uri):
        return (uri not in self.pibox.played_tracks) and (
            uri not in self.pibox.denylist
        )

    def __is_queued(self, uri):
        return self.core.tracklist.filter({"uri": [uri]}).get(timeout=MOPIDY_CALL_TIMEOUT) != []

    def __start_playing(self):
        if self.core.playback.get_state().get(timeout=MOPIDY_CALL_TIMEOUT) == core.PlaybackState.STOPPED:
            self.core.playback.play().get(timeout=MOPIDY_CALL_TIMEOUT)
            self.logger.info("Pibox started playback")
            
            # Check if playback actually started - tracks can fail to load
            # (e.g., ManifestDecodeError from Tidal) and get removed from
            # tracklist before playback begins. In that case, try next track.
            import time
            time.sleep(0.3)  # Brief delay to let Mopidy process the play command
            
            state = self.core.playback.get_state().get(timeout=MOPIDY_CALL_TIMEOUT)
            tracklist_len = self.core.tracklist.get_length().get(timeout=MOPIDY_CALL_TIMEOUT)
            
            if state == core.PlaybackState.STOPPED and tracklist_len == 0:
                self.logger.warning("Playback failed to start (track may be unavailable). Trying next track.")
                self.__queue_song_from_session_playlists()
                self.__start_playing()

    def __should_play_whats_new_pussycat(self, tl_track):
        tracklist = self.core.tracklist.get_tracks().get(timeout=MOPIDY_CALL_TIMEOUT)
        return tl_track.track.uri in self.pussycat_list and len(tracklist) == 0

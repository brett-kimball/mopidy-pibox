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
# - Added build_collection_index() for library_restrict mode with Tidal integration
# - Added source-based metadata fetching to avoid Tidal API rate limits
# - Added background metadata lookup with rate limiting and exponential backoff
# - Added collection search/browse methods (get_collection_artists, search_collection, etc.)
# - Added update_session_playlists() for runtime playlist modification
# - Added track source attribution for playlist vs user-queued tracks

import pykka
import logging
import time
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

        # apply library restriction mode if configured
        try:
            library_restrict = self.config.get("library_restrict", False)
            self.pibox.set_library_restrict(library_restrict)
        except Exception:
            pass

        self.core.tracklist.set_consume(value=True)

    def start_session(self, skip_threshold, playlists, auto_start, shuffle):
        self.pibox.start_session(skip_threshold, playlists, shuffle)
        
        # Build collection index if library_restrict is enabled
        if self.pibox.library_restrict:
            try:
                self.build_collection_index()
            except Exception as e:
                self.logger.error(f"Failed to build collection index: {e}")
        
        if auto_start and len(playlists) > 0:
            # Only auto-queue and play if playlists were selected
            # If no playlists, session starts in "wait mode" for user selections
            self.__queue_song_from_session_playlists()
            self.__start_playing()

    def update_session_playlists(self, playlists):
        """Update the selected playlists during an active session.
        
        This recalculates the remaining playlist tracks based on the new
        playlists while preserving played_tracks and denylist state.
        
        Note: When library_restrict is enabled, the collection index search
        filtering automatically applies based on session playlists - no need
        to rebuild the index. Saved tracks and albums are always searchable,
        while playlist/mix tracks are only searchable if their source is selected.
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

        track_uri = None
        try:
            track_uri = tl_track.track.uri if tl_track and tl_track.track else None
        except Exception:
            pass

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
                    f"Track {track_uri} ended after only {time_position}ms "
                    f"(length: {track_length}ms). Treating as playback failure."
                )
                is_playback_failure = True
                # Add to denylist so we don't try it again
                try:
                    if track_uri and track_uri not in self.pibox.denylist:
                        self.pibox.denylist.append(track_uri)
                        self.logger.info(f"Added {track_uri} to denylist")
                except Exception:
                    pass
                # Mark track as invalid in SQLite cache
                if track_uri and self.pibox.library_restrict:
                    try:
                        self.pibox.mark_track_invalid(track_uri)
                    except Exception as e:
                        self.logger.warning(f"Failed to mark track invalid: {e}")

        # Only mark as played if it wasn't a failure
        if not is_playback_failure:
            self.__update_played_tracks(tl_track)
            # Increment play count in SQLite cache for successful plays
            if track_uri and self.pibox.library_restrict:
                try:
                    self.pibox.increment_track_play_count(track_uri)
                except Exception as e:
                    self.logger.warning(f"Failed to increment play count: {e}")
        else:
            # Even for playback failures, we must remove from user queue counts
            # so they can add new tracks
            try:
                self.pibox.remove_queued_track_for_all_users(tl_track.track.uri)
            except Exception:
                pass

        if self.__should_play_whats_new_pussycat(tl_track):
            self.core.tracklist.add(uris=[self.pussycat_list[0]], at_position=0).get(timeout=MOPIDY_CALL_TIMEOUT)
            self.logger.info("Meow")
            self.__start_playing()
        elif self.core.tracklist.get_length().get(timeout=MOPIDY_CALL_TIMEOUT) == 0:
            # Only try to queue from playlists if we have playlists configured
            if len(self.pibox.playlists) > 0:
                self.__queue_song_from_session_playlists()
                self.__start_playing()
            # else: no playlists mode - just wait for users to queue tracks

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

    def build_collection_index(self):
        """Build a searchable index of the user's full Tidal collection.
        
        Indexes ALL of:
        - Saved tracks (tidal:my_tracks) - always searchable
        - Saved albums (tidal:my_albums) - always searchable  
        - Playlists (tidal:my_playlists) - searchable only if selected for session
        - Mixes (tidal:my_mixes) - searchable only if selected for session
        
        Uses persistent cache to minimize API calls. The full index is stored,
        and filtering happens at search time based on session playlists.
        
        Sources that were previously in the collection but are no longer found
        are marked as removed (in_collection=0) but their tracks are preserved
        for play count history.
        
        Returns:
            dict: Index with tracks, sources, and searchability metadata
        """
        import time
        
        if not self.pibox.library_restrict:
            self.logger.info("library_restrict is disabled, skipping collection index build")
            return None
        
        self.logger.info("Building full collection index from Tidal library...")
        
        # Collect track refs with source info: (ref, source_type, source_name, source_uri)
        # source_type: "saved", "album", "playlist", "mix"
        # source_uri is used to check if a playlist/mix is selected
        all_track_refs = {}  # uri -> (ref, source_type, source_name, source_uri)
        
        # Track all source URIs we see during this refresh
        sources_seen = set()
        
        cache_hits = 0
        cache_misses = 0
        
        COLLECTION_TIMEOUT = 60
        
        # Helper to add tracks from cache or API
        def add_tracks_from_source(source_uri, source_name, source_type, use_playlist_api=False):
            nonlocal cache_hits, cache_misses
            
            sources_seen.add(source_uri)
            
            # For 'saved' type (tidal:my_tracks), always fetch fresh from API
            # because we can't detect when user adds tracks via Tidal web/app
            if source_type != "saved":
                cached = self.pibox.get_cached_playlist_tracks(source_uri)
                if cached:
                    cache_hits += 1
                    self.logger.debug(f"Cache hit: {source_name}")
                    for track_data in cached.get("tracks", []):
                        track_uri = track_data["uri"]
                        if track_uri not in all_track_refs:
                            class TrackRef:
                                def __init__(self, uri, name):
                                    self.uri = uri
                                    self.name = name
                            all_track_refs[track_uri] = (
                                TrackRef(track_uri, track_data["name"]),
                                source_type,
                                source_name,
                                source_uri
                            )
                    return True
            
            # Fetch from API
            cache_misses += 1
            self.logger.info(f"Fetching: {source_name} ({source_type})")
            
            try:
                tracks = None
                track_data = []
                
                # Helper to extract full metadata from Track objects
                def extract_track_data(track_list):
                    result = []
                    for t in track_list:
                        if hasattr(t, 'uri'):
                            artist_name = None
                            album_name = None
                            if hasattr(t, 'artists') and t.artists:
                                artist_name = ", ".join([a.name for a in t.artists if a and a.name])
                            if hasattr(t, 'album') and t.album and t.album.name:
                                album_name = t.album.name
                            result.append({
                                "uri": t.uri, 
                                "name": t.name,
                                "artist": artist_name,
                                "album": album_name
                            })
                    return result
                
                if use_playlist_api:
                    # Use playlists.lookup to get FULL track objects with artist/album metadata
                    # Works for playlists AND mixes!
                    playlist = self.core.playlists.lookup(source_uri).get(timeout=COLLECTION_TIMEOUT)
                    if playlist and hasattr(playlist, 'tracks') and playlist.tracks:
                        tracks = playlist.tracks
                        track_data = extract_track_data(tracks)
                elif source_type == "album":
                    # Use library.lookup for albums - returns full Track objects
                    result = self.core.library.lookup(uris=[source_uri]).get(timeout=COLLECTION_TIMEOUT)
                    if result and source_uri in result:
                        tracks = result[source_uri]
                        track_data = extract_track_data(tracks)
                else:
                    # Use library.browse for saved tracks (returns Refs only, no metadata)
                    refs = self.core.library.browse(uri=source_uri).get(timeout=COLLECTION_TIMEOUT)
                    if refs:
                        tracks = refs
                        track_data = [{"uri": t.uri, "name": t.name} for t in refs if hasattr(t, 'uri')]
                
                if track_data:
                    self.pibox.cache_playlist_tracks(source_uri, track_data, source_name, source_type)
                
                if tracks:
                    for ref in tracks:
                        if hasattr(ref, 'uri') and ref.uri not in all_track_refs:
                            all_track_refs[ref.uri] = (ref, source_type, source_name, source_uri)
                
                # Rate limit - be conservative to avoid 429 errors
                if cache_misses > 1:
                    time.sleep(1.0)  # Increased from 0.2s to avoid rate limits
                return True
            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "too many" in error_str or "rate" in error_str:
                    self.logger.warning(f"Rate limited fetching {source_name} - sleeping 30s")
                    time.sleep(30.0)
                else:
                    self.logger.warning(f"Failed to fetch {source_name}: {e}")
                return False
        
        # 1. Saved tracks (always searchable)
        add_tracks_from_source("tidal:my_tracks", "My Saved Tracks", "saved")
        
        # 2. Saved albums (always searchable)
        try:
            self.logger.info("Fetching saved albums list...")
            saved_albums = self.core.library.browse(uri="tidal:my_albums").get(timeout=COLLECTION_TIMEOUT)
            self.logger.info(f"Found {len(saved_albums)} saved albums")
            
            for album_ref in saved_albums:
                if album_ref.type == "album":
                    add_tracks_from_source(album_ref.uri, album_ref.name, "album")
        except Exception as e:
            self.logger.warning(f"Failed to browse saved albums: {e}")
        
        # 3. Playlists (searchable only if selected for session)
        try:
            self.logger.info("Fetching playlists list...")
            playlists = self.core.library.browse(uri="tidal:my_playlists").get(timeout=COLLECTION_TIMEOUT)
            self.logger.info(f"Found {len(playlists)} playlists")
            
            for playlist_ref in playlists:
                if playlist_ref.type == "playlist":
                    add_tracks_from_source(playlist_ref.uri, playlist_ref.name, "playlist", use_playlist_api=True)
        except Exception as e:
            self.logger.warning(f"Failed to browse playlists: {e}")
        
        # 4. Mixes (searchable only if selected for session)
        try:
            self.logger.info("Fetching mixes list...")
            mixes = self.core.library.browse(uri="tidal:my_mixes").get(timeout=COLLECTION_TIMEOUT)
            self.logger.info(f"Found {len(mixes)} mixes")
            
            for mix_ref in mixes:
                if mix_ref.type in ("playlist", "directory"):
                    # Mixes also support playlists.lookup for full metadata
                    add_tracks_from_source(mix_ref.uri, mix_ref.name, "mix", use_playlist_api=True)
        except Exception as e:
            self.logger.warning(f"Failed to browse mixes: {e}")
        
        self.logger.info(f"Collection index: {cache_hits} cache hits, {cache_misses} API calls, {len(all_track_refs)} unique tracks")
        
        # Detect sources that were in our cache but are no longer in the Tidal collection
        previously_cached_sources = set(self.pibox.get_sources_in_collection())
        removed_sources = previously_cached_sources - sources_seen
        if removed_sources:
            self.logger.info(f"Detected {len(removed_sources)} sources removed from Tidal collection")
            self.pibox.mark_sources_removed(list(removed_sources))
        
        if not all_track_refs:
            self.logger.warning("No tracks found in collection")
            return None
        
        # Build the index from the SQLite cache
        index = self.pibox.build_collection_index_from_cache()
        
        # Schedule background metadata lookup after a short delay (don't block session start)
        self._schedule_metadata_lookup()
        
        return index

    def _schedule_metadata_lookup(self):
        """Schedule metadata lookup to run after session start completes."""
        import threading
        
        def trigger_lookup():
            try:
                # Use tell() to send async message to this actor
                self.actor_ref.tell({"cmd": "lookup_metadata_batch"})
            except Exception as e:
                self.logger.warning(f"Failed to schedule metadata lookup: {e}")
        
        # Delay 2 seconds to let session start complete
        timer = threading.Timer(2.0, trigger_lookup)
        timer.daemon = True
        timer.start()
        self.logger.info("Scheduled background metadata lookup in 2s")
    
    def on_receive(self, message):
        """Handle async messages sent to this actor."""
        if isinstance(message, dict) and message.get("cmd") == "lookup_metadata_batch":
            self._lookup_metadata_batch()
            return True
        return super().on_receive(message)

    def _lookup_metadata_batch(self):
        """Look up metadata by fetching complete source data (one API call per source).
        
        Instead of looking up individual tracks (which causes rate limits),
        we re-fetch the source (playlist/album/mix) and update all its tracks
        with full metadata in one API call.
        
        This processes ONE source per call to avoid blocking the actor.
        Rate limiting is critical - Tidal enforces strict limits.
        """
        import threading
        
        # Conservative delays to avoid rate limits
        BASE_DELAY = 8.0  # seconds between sources (increased from 5)
        SAVED_TRACKS_DELAY = 10.0  # extra delay for saved tracks (per-album lookups)
        
        # Get sources that have tracks with incomplete metadata
        sources_needing_metadata = self.pibox.get_sources_needing_metadata()
        
        if not sources_needing_metadata:
            # Log completion with stats
            try:
                stats = self.pibox.get_metadata_stats()
                self.logger.info(
                    f"Metadata lookup complete: {stats['complete_metadata']}/{stats['total_unique_tracks']} "
                    f"tracks have metadata. By type: {stats['by_type']}"
                )
            except Exception:
                self.logger.info("Metadata lookup complete - all tracks have metadata")
            return
        
        # Process one source
        source = sources_needing_metadata[0]
        source_uri = source["source_uri"]
        source_name = source["source_name"]
        source_type = source["source_type"]
        incomplete_count = source["incomplete_tracks"]
        remaining_sources = len(sources_needing_metadata)
        
        self.logger.info(
            f"Fetching metadata for '{source_name}' ({source_type}): "
            f"{incomplete_count} incomplete tracks, {remaining_sources} sources remaining"
        )
        
        track_metadata_map = {}
        success = False
        delay = BASE_DELAY
        
        try:
            tracks = None
            
            if source_type in ("playlist", "mix"):
                # Use playlists.lookup - returns full Playlist with Track objects
                # This is ONE API call that returns ALL tracks with metadata
                playlist = self.core.playlists.lookup(source_uri).get(timeout=60)
                if playlist and hasattr(playlist, 'tracks'):
                    tracks = playlist.tracks
            elif source_type == "album":
                # Use library.lookup - returns list of Track objects
                # This is ONE API call that returns all album tracks with metadata
                result = self.core.library.lookup(uris=[source_uri]).get(timeout=60)
                if result and source_uri in result:
                    tracks = result[source_uri]
            elif source_type == "saved":
                # Saved tracks require individual album lookups
                # Process ONE album at a time to avoid rate limits
                # mopidy-tidal caches entire album when looking up any track from it
                from collections import defaultdict
                
                tracks_needing = self.pibox.get_tracks_needing_metadata_lookup(limit=200)
                
                if tracks_needing:
                    # Group tracks by album ID
                    # URI format: tidal:track:artist:album:track
                    tracks_by_album = defaultdict(list)
                    
                    for uri in tracks_needing:
                        parts = uri.split(":")
                        if len(parts) >= 4:
                            album_id = parts[3]
                            tracks_by_album[album_id].append(uri)
                    
                    # Pick ONE album to process this round
                    # Choose album with most tracks to maximize efficiency
                    albums_sorted = sorted(tracks_by_album.items(), key=lambda x: -len(x[1]))
                    album_id, album_tracks = albums_sorted[0]
                    
                    self.logger.info(
                        f"Saved tracks: looking up 1 album ({len(album_tracks)} tracks) "
                        f"of {len(tracks_by_album)} albums remaining"
                    )
                    
                    # Lookup just ONE track from this album - mopidy-tidal caches the rest
                    result = self.core.library.lookup(uris=[album_tracks[0]]).get(timeout=60)
                    
                    if result:
                        # Now lookup all tracks from this album (should be cached)
                        time.sleep(0.5)  # Small delay before cache lookups
                        all_result = self.core.library.lookup(uris=album_tracks).get(timeout=60)
                        
                        for uri, track_list in all_result.items():
                            if track_list and len(track_list) > 0:
                                track = track_list[0]
                                metadata = self._extract_track_metadata(track)
                                if metadata:
                                    track_metadata_map[uri] = metadata
                        success = bool(track_metadata_map)
                    
                    delay = SAVED_TRACKS_DELAY  # Longer delay for saved tracks
            
            # Extract metadata from fetched tracks
            if tracks:
                for t in tracks:
                    if hasattr(t, 'uri'):
                        metadata = self._extract_track_metadata(t)
                        if metadata:
                            track_metadata_map[t.uri] = metadata
                success = True
                        
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "too many" in error_str or "rate" in error_str:
                self.logger.warning(f"Rate limited fetching metadata for {source_name} - backing off 60s")
                delay = 60.0  # Back off significantly on rate limit
            else:
                self.logger.warning(f"Failed to fetch metadata for {source_name}: {e}")
                delay = BASE_DELAY * 2  # Double delay on other errors
        
        # Update the cache with metadata
        if track_metadata_map:
            self.pibox.update_track_metadata(track_metadata_map)
            self.logger.info(f"Updated metadata for {len(track_metadata_map)} tracks from '{source_name}'")
            
            # Rebuild the index with updated metadata
            self.pibox.build_collection_index_from_cache()
        
        # Check if more sources need lookup
        remaining = len(self.pibox.get_sources_needing_metadata())
        if remaining > 0:
            # Schedule next source after delay
            if not success:
                delay = max(delay, BASE_DELAY * 2)  # At least double delay on failure
            
            self.logger.debug(f"Scheduling next metadata lookup in {delay}s")
            
            def schedule_next():
                try:
                    self.actor_ref.tell({"cmd": "lookup_metadata_batch"})
                except Exception:
                    pass
            
            timer = threading.Timer(delay, schedule_next)
            timer.daemon = True
            timer.start()

    def _extract_track_metadata(self, track):
        """Extract artist and album metadata from a Track object."""
        metadata = {}
        if hasattr(track, 'artists') and track.artists:
            artist_names = [a.name for a in track.artists if a and a.name]
            if artist_names:
                metadata["artist"] = ", ".join(artist_names)
        if hasattr(track, 'album') and track.album and track.album.name:
            metadata["album"] = track.album.name
        return metadata if metadata else None

    def _lookup_missing_track_metadata(self):
        """Legacy method - now uses source-based approach. Kept for compatibility."""
        self._lookup_metadata_batch()

    def _maybe_refresh_collection_index(self):
        """Check if collection index needs refresh and rebuild if so.
        
        Called before collection search/browse operations to ensure
        the index stays reasonably fresh (default: 60 minutes).
        """
        if not self.pibox.library_restrict:
            return
        
        if self.pibox.needs_index_refresh(max_age_minutes=60):
            self.logger.info("Collection index is stale, refreshing...")
            try:
                self.build_collection_index()
            except Exception as e:
                self.logger.warning(f"Failed to refresh collection index: {e}")

    def get_collection_artists(self):
        """Get sorted list of artists in the collection."""
        self._maybe_refresh_collection_index()
        return self.pibox.get_collection_artists()

    def search_collection(self, query):
        """Search the collection index."""
        self._maybe_refresh_collection_index()
        return self.pibox.search_collection(query)

    def get_tracks_for_artist(self, artist_name):
        """Get all tracks for a specific artist."""
        self._maybe_refresh_collection_index()
        return self.pibox.get_tracks_for_artist(artist_name)

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
            if self.pibox.library_restrict:
                # In library_restrict mode the session never terminates —
                # users are the only ones who can add new tracks, so ending
                # the session would lock out non-admin users permanently.
                self.logger.info(
                    "No more tracks to play from playlists; idling "
                    "(library_restrict mode — session will not terminate)"
                )
                return
            elif len(self.pibox.playlists) == 0:
                # No playlists were selected in either mode.
                # Idle indefinitely so users can queue tracks manually.
                self.logger.info(
                    "No playlists selected; idling until users queue tracks manually"
                )
                return
            else:
                # Original mode: playlists were selected and are now exhausted.
                # End the session so any user can start a fresh one with new playlists.
                self.logger.info("No more tracks to play from playlists; ending session")
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
                if len(self.pibox.playlists) == 0:
                    # No playlists configured — idle, don't retry
                    self.logger.debug("No playlists configured; not retrying playback")
                    return
                self.logger.warning(
                    "Playback failed to start (track may be unavailable). Trying next track."
                )
                self.__queue_song_from_session_playlists()
                # Only recurse if a track was actually queued.
                # If __queue_song_from_session_playlists idled (library_restrict
                # exhausted, or all tracks denylisted), the tracklist will still
                # be empty and we must not loop.
                new_tracklist_len = self.core.tracklist.get_length().get(
                    timeout=MOPIDY_CALL_TIMEOUT
                )
                if new_tracklist_len > 0:
                    self.__start_playing()

    def __should_play_whats_new_pussycat(self, tl_track):
        tracklist = self.core.tracklist.get_tracks().get(timeout=MOPIDY_CALL_TIMEOUT)
        return tl_track.track.uri in self.pussycat_list and len(tracklist) == 0

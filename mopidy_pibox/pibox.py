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
# - Added SQLite-based track caching with normalized schema (tracks, sources, track_sources)
# - Added collection index for artist/track search in library_restrict mode
# - Added user nickname generation and per-user queue tracking
# - Added track source attribution (playlist name vs user nickname)
# - Added metadata stats and background metadata lookup support
# - Added play count and last_played tracking

from datetime import datetime, timezone, timedelta
import json
import logging
import random
import sqlite3


# Word lists for generating user nicknames (nautical/seafarer theme).
# Alternate themed lists (biker bar, sailing race, dark pirates, etc.)
# are archived in scripts/word-lists-archive.txt (not tracked by git).
ADJECTIVES = [
    "Salty", "Scurvy", "Barnacled", "Swashbuckling", "Landlubbing", "Seafaring",
    "Windswept", "Crusty", "Briny", "Stormy", "Drifting", "Anchored", "Rigged",
    "Capsized", "Marooned", "Plundering", "Rowdy", "Mutinous", "Jolly", "Rusty",
    "Groggy", "Bilge", "Scallywag", "Sunburnt", "Tattered", "Wayward", "Roving",
    "Shipwrecked", "Weathered", "Tipsy", "Rogue", "Surly", "Cunning", "Fearless",
    "Grizzled", "Legendary", "Mysterious", "One-Eyed", "Peg-Legged", "Ragged",
    "Sneaky", "Tattooed", "Toothless", "Treacherous", "Wily", "Wobbly", "Cursed",
]

NOUNS = [
    "Buccaneer", "Privateer", "Corsair", "Mariner", "Skipper", "Deckhand",
    "Helmsman", "Bosun", "Quartermaster", "Shipmate", "Scallywag", "Rapscallion",
    "Landlubber", "Seadog", "Swab", "Barnacle", "Kraken", "Mermaid", "Parrot",
    "Pelican", "Albatross", "Dolphin", "Whale", "Shark", "Octopus", "Jellyfish",
    "Starfish", "Seahorse", "Manatee", "Stingray", "Barracuda", "Mackerel",
    "Cutlass", "Compass", "Anchor", "Cannon", "Doubloon", "Spyglass", "Plank",
    "Rigger", "Swabbie", "Castaway", "Smuggler", "Stowaway", "Drifter", "Voyager",
]

class Pibox:
    def __init__(self, data_dir):
        super().__init__()
        self.data_dir = data_dir
        self.queued_history = []
        # vote limits: defaults (can be overridden by frontend when creating Pibox)
        self.vote_limit_count = 2
        self.vote_limit_minutes = 60
        
        # SQLite database for persistent playlist track cache
        self._db_path = data_dir.joinpath("collection-cache.db")
        self._init_database()

        self.__initialise()

        self.logger = logging.getLogger(__name__)

    def _get_db_connection(self):
        """Get a database connection. SQLite connections are thread-local."""
        conn = sqlite3.connect(str(self._db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn

    def _init_database(self):
        """Initialize the SQLite database schema."""
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Sources table: albums, playlists, mixes, saved tracks
            # source_last_updated: Tidal's last_updated timestamp for change detection
            # in_collection: False if source was removed from Tidal collection
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sources (
                    source_uri TEXT PRIMARY KEY,
                    source_name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    source_last_updated TEXT,
                    in_collection INTEGER DEFAULT 1
                )
            """)
            
            # Tracks table: unique tracks with track_uri as primary key
            # artist_name and album_name are populated via background metadata lookup
            # status: 'unknown', 'valid', 'invalid' (based on playback success/failure)
            # play_count: number of times track has been played (across all sources)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tracks (
                    track_uri TEXT PRIMARY KEY,
                    track_name TEXT NOT NULL,
                    artist_name TEXT,
                    album_name TEXT,
                    status TEXT DEFAULT 'unknown',
                    play_count INTEGER DEFAULT 0,
                    last_played_at TEXT
                )
            """)
            
            # Junction table: many-to-many relationship between tracks and sources
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS track_sources (
                    track_uri TEXT NOT NULL,
                    source_uri TEXT NOT NULL,
                    PRIMARY KEY (track_uri, source_uri),
                    FOREIGN KEY (track_uri) REFERENCES tracks(track_uri) ON DELETE CASCADE,
                    FOREIGN KEY (source_uri) REFERENCES sources(source_uri) ON DELETE CASCADE
                )
            """)
            
            # Add new columns to sources table for optimization (for legacy schema upgrades)
            try:
                cursor.execute("ALTER TABLE sources ADD COLUMN source_last_updated TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute("ALTER TABLE sources ADD COLUMN in_collection INTEGER DEFAULT 1")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            # Indexes for fast lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_track_sources_source 
                ON track_sources(source_uri)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_track_sources_track 
                ON track_sources(track_uri)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tracks_artist 
                ON tracks(artist_name)
            """)
            
            conn.commit()
        finally:
            conn.close()

    def get_cached_playlist_tracks(self, playlist_uri):
        """Get cached tracks for a playlist URI, or None if not cached.
        
        Returns dict with 'tracks' list and 'cached_at' timestamp, or None.
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Check if source exists
            cursor.execute(
                "SELECT cached_at FROM sources WHERE source_uri = ?",
                (playlist_uri,)
            )
            source_row = cursor.fetchone()
            if not source_row:
                return None
            
            # Get all tracks for this source via junction table
            cursor.execute("""
                SELECT t.track_uri, t.track_name, t.artist_name, t.album_name 
                FROM tracks t
                JOIN track_sources ts ON t.track_uri = ts.track_uri
                WHERE ts.source_uri = ?
            """, (playlist_uri,))
            tracks = [{"uri": row["track_uri"], "name": row["track_name"], 
                       "artist": row["artist_name"], "album": row["album_name"]} 
                      for row in cursor.fetchall()]
            
            return {
                "tracks": tracks,
                "cached_at": source_row["cached_at"],
            }
        finally:
            conn.close()

    def cache_playlist_tracks(self, playlist_uri, tracks, source_name=None, source_type=None, source_last_updated=None):
        """Cache tracks for a playlist URI.
        
        Args:
            playlist_uri: The playlist/mix/album URI
            tracks: List of track dicts with uri, name, and optionally artist
            source_name: Name of the source (optional, for new entries)
            source_type: Type of source: 'saved', 'album', 'playlist', 'mix'
            source_last_updated: Tidal's last_updated timestamp for the source (for change detection)
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            cached_at = datetime.now(timezone.utc).isoformat()
            
            # Infer source_type from URI if not provided
            if not source_type:
                if "my_tracks" in playlist_uri:
                    source_type = "saved"
                elif "album" in playlist_uri:
                    source_type = "album"
                elif "mix" in playlist_uri:
                    source_type = "mix"
                else:
                    source_type = "playlist"
            
            if not source_name:
                source_name = playlist_uri.split(":")[-1]
            
            # Insert or update source - always mark as in_collection when we cache it
            cursor.execute("""
                INSERT INTO sources (source_uri, source_name, source_type, cached_at, source_last_updated, in_collection)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(source_uri) DO UPDATE SET
                    source_name = excluded.source_name,
                    source_type = excluded.source_type,
                    cached_at = excluded.cached_at,
                    source_last_updated = COALESCE(excluded.source_last_updated, source_last_updated),
                    in_collection = 1
            """, (playlist_uri, source_name, source_type, cached_at, source_last_updated))
            
            # Insert or update tracks and create track-source links
            if tracks:
                for t in tracks:
                    track_uri = t.get("uri", t.get("track_uri"))
                    track_name = t.get("name", t.get("track_name"))
                    artist_name = t.get("artist", t.get("artist_name"))
                    album_name = t.get("album", t.get("album_name"))
                    
                    # Insert or update track - preserve play_count, status, last_played_at
                    # Only update metadata fields if new values provided
                    cursor.execute("""
                        INSERT INTO tracks (track_uri, track_name, artist_name, album_name)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(track_uri) DO UPDATE SET
                            track_name = excluded.track_name,
                            artist_name = COALESCE(NULLIF(excluded.artist_name, ''), tracks.artist_name),
                            album_name = COALESCE(NULLIF(excluded.album_name, ''), tracks.album_name)
                    """, (track_uri, track_name, artist_name, album_name))
                    
                    # Create link between track and source
                    cursor.execute("""
                        INSERT OR IGNORE INTO track_sources (track_uri, source_uri)
                        VALUES (?, ?)
                    """, (track_uri, playlist_uri))
            
            conn.commit()
        finally:
            conn.close()

    def get_tracks_needing_metadata_lookup(self, limit=50, priority_first=True):
        """Get track URIs that don't have artist or album info yet.
        
        Args:
            limit: Maximum number of track URIs to return
            priority_first: If True, prioritize saved/album tracks over playlist/mix tracks
        
        Returns list of unique track URIs needing metadata lookup.
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            
            if priority_first:
                # Prioritize tracks from "saved" and "album" sources first
                # Then fall back to playlist/mix tracks
                # Use MIN to get the best (lowest) priority across all sources for each track
                cursor.execute("""
                    SELECT t.track_uri, 
                           MIN(CASE WHEN s.source_type IN ('saved', 'album') THEN 0 ELSE 1 END) as priority
                    FROM tracks t
                    JOIN track_sources ts ON t.track_uri = ts.track_uri
                    JOIN sources s ON ts.source_uri = s.source_uri
                    WHERE (t.artist_name IS NULL OR t.artist_name = ''
                           OR t.album_name IS NULL OR t.album_name = '')
                      AND s.in_collection = 1
                    GROUP BY t.track_uri
                    ORDER BY priority
                    LIMIT ?
                """, (limit,))
            else:
                cursor.execute("""
                    SELECT DISTINCT t.track_uri FROM tracks t
                    JOIN track_sources ts ON t.track_uri = ts.track_uri
                    JOIN sources s ON ts.source_uri = s.source_uri
                    WHERE (t.artist_name IS NULL OR t.artist_name = ''
                           OR t.album_name IS NULL OR t.album_name = '')
                      AND s.in_collection = 1
                    LIMIT ?
                """, (limit,))
            
            return [row["track_uri"] for row in cursor.fetchall()]
        finally:
            conn.close()

    def update_track_metadata(self, track_metadata_map):
        """Update artist and album names for multiple tracks.
        
        Args:
            track_metadata_map: dict of {track_uri: {"artist": str, "album": str}}
        """
        if not track_metadata_map:
            return
        
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.executemany("""
                UPDATE tracks SET artist_name = ?, album_name = ? WHERE track_uri = ?
            """, [(meta.get("artist"), meta.get("album"), uri) 
                  for uri, meta in track_metadata_map.items()])
            conn.commit()
            self.logger.info(f"Updated metadata for {len(track_metadata_map)} tracks")
        finally:
            conn.close()

    def get_all_cached_tracks_with_metadata(self, exclude_invalid=True, only_in_collection=True):
        """Get all cached tracks with source info for index building.
        
        Args:
            exclude_invalid: If True, exclude tracks marked as invalid (failed to play)
            only_in_collection: If True, only include tracks from sources still in collection
        
        Returns list of dicts with track and source info (one row per track-source pair).
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT t.track_uri, t.track_name, t.artist_name, t.album_name,
                       ts.source_uri, s.source_name, s.source_type, t.status, t.play_count,
                       s.in_collection
                FROM tracks t
                JOIN track_sources ts ON t.track_uri = ts.track_uri
                JOIN sources s ON ts.source_uri = s.source_uri
                WHERE 1=1
            """
            if exclude_invalid:
                query += " AND (t.status != 'invalid' OR t.status IS NULL)"
            if only_in_collection:
                query += " AND s.in_collection = 1"
            
            cursor.execute(query)
            return [
                {
                    "track_uri": row["track_uri"],
                    "track_name": row["track_name"],
                    "artist_name": row["artist_name"],
                    "album_name": row["album_name"],
                    "source_uri": row["source_uri"],
                    "source_name": row["source_name"],
                    "source_type": row["source_type"],
                    "status": row["status"] or "unknown",
                    "play_count": row["play_count"] or 0,
                    "in_collection": bool(row["in_collection"]),
                }
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def increment_track_play_count(self, track_uri):
        """Increment play count for a track and mark it as valid.
        
        Called when a track finishes playing successfully.
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                UPDATE tracks 
                SET play_count = play_count + 1,
                    last_played_at = ?,
                    status = 'valid'
                WHERE track_uri = ?
            """, (now, track_uri))
            conn.commit()
            if cursor.rowcount > 0:
                self.logger.debug(f"Incremented play count for {track_uri}")
        finally:
            conn.close()

    def mark_track_invalid(self, track_uri):
        """Mark a track as invalid (failed to play).
        
        Called when a track fails to play (unavailable, region-locked, etc.)
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tracks SET status = 'invalid' WHERE track_uri = ?
            """, (track_uri,))
            conn.commit()
            if cursor.rowcount > 0:
                self.logger.info(f"Marked track as invalid: {track_uri}")
        finally:
            conn.close()

    def get_track_stats(self, track_uri):
        """Get play count and status for a track."""
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT play_count, status, last_played_at 
                FROM tracks WHERE track_uri = ? LIMIT 1
            """, (track_uri,))
            row = cursor.fetchone()
            if row:
                return {
                    "play_count": row["play_count"] or 0,
                    "status": row["status"] or "unknown",
                    "last_played_at": row["last_played_at"]
                }
            return None
        finally:
            conn.close()

    def get_metadata_lookup_count(self):
        """Get count of unique tracks still needing metadata lookup."""
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(DISTINCT t.track_uri) as count 
                FROM tracks t
                JOIN track_sources ts ON t.track_uri = ts.track_uri
                JOIN sources s ON ts.source_uri = s.source_uri
                WHERE (t.artist_name IS NULL OR t.artist_name = ''
                       OR t.album_name IS NULL OR t.album_name = '')
                  AND s.in_collection = 1
            """)
            row = cursor.fetchone()
            return row["count"] if row else 0
        finally:
            conn.close()

    def get_sources_needing_metadata(self):
        """Get sources that have tracks with incomplete metadata.
        
        Returns list of dicts with source info, prioritizing saved/album over playlist/mix.
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT s.source_uri, s.source_name, s.source_type,
                       CASE WHEN s.source_type IN ('saved', 'album') THEN 0 ELSE 1 END as priority,
                       COUNT(DISTINCT t.track_uri) as incomplete_tracks
                FROM sources s
                JOIN track_sources ts ON s.source_uri = ts.source_uri
                JOIN tracks t ON ts.track_uri = t.track_uri
                WHERE s.in_collection = 1
                  AND (t.artist_name IS NULL OR t.artist_name = ''
                       OR t.album_name IS NULL OR t.album_name = '')
                GROUP BY s.source_uri
                ORDER BY priority, incomplete_tracks DESC
            """)
            return [
                {
                    "source_uri": row["source_uri"],
                    "source_name": row["source_name"],
                    "source_type": row["source_type"],
                    "incomplete_tracks": row["incomplete_tracks"],
                }
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def get_metadata_stats(self):
        """Get detailed stats about metadata population.
        
        Returns dict with counts by source type and completion status.
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Total unique tracks (that belong to at least one in-collection source)
            cursor.execute("""
                SELECT COUNT(DISTINCT t.track_uri) as total FROM tracks t
                JOIN track_sources ts ON t.track_uri = ts.track_uri
                JOIN sources s ON ts.source_uri = s.source_uri
                WHERE s.in_collection = 1
            """)
            total = cursor.fetchone()["total"]
            
            # Tracks with complete metadata
            cursor.execute("""
                SELECT COUNT(DISTINCT t.track_uri) as complete FROM tracks t
                JOIN track_sources ts ON t.track_uri = ts.track_uri
                JOIN sources s ON ts.source_uri = s.source_uri
                WHERE s.in_collection = 1
                  AND t.artist_name IS NOT NULL AND t.artist_name != ''
                  AND t.album_name IS NOT NULL AND t.album_name != ''
            """)
            complete = cursor.fetchone()["complete"]
            
            # Breakdown by source type (note: a track may be counted in multiple types)
            cursor.execute("""
                SELECT s.source_type, 
                       COUNT(DISTINCT t.track_uri) as total,
                       COUNT(DISTINCT CASE WHEN t.artist_name IS NOT NULL 
                                            AND t.artist_name != ''
                                            AND t.album_name IS NOT NULL
                                            AND t.album_name != '' 
                                       THEN t.track_uri END) as complete
                FROM tracks t
                JOIN track_sources ts ON t.track_uri = ts.track_uri
                JOIN sources s ON ts.source_uri = s.source_uri
                WHERE s.in_collection = 1
                GROUP BY s.source_type
            """)
            by_type = {row["source_type"]: {"total": row["total"], "complete": row["complete"]} 
                      for row in cursor.fetchall()}
            
            return {
                "total_unique_tracks": total,
                "complete_metadata": complete,
                "incomplete_metadata": total - complete,
                "by_type": by_type,
            }
        finally:
            conn.close()

    def get_source_last_updated(self, source_uri):
        """Get the cached last_updated timestamp for a source.
        
        Returns None if source not in cache or no timestamp stored.
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT source_last_updated FROM sources WHERE source_uri = ?",
                (source_uri,)
            )
            row = cursor.fetchone()
            return row["source_last_updated"] if row else None
        finally:
            conn.close()

    def get_all_source_timestamps(self):
        """Get all cached source URIs with their last_updated timestamps.
        
        Returns dict of {source_uri: source_last_updated}
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT source_uri, source_last_updated FROM sources WHERE in_collection = 1")
            return {row["source_uri"]: row["source_last_updated"] for row in cursor.fetchall()}
        finally:
            conn.close()

    def mark_sources_removed(self, source_uris):
        """Mark sources as removed from Tidal collection.
        
        Sources are not deleted - they remain for play count history.
        Tracks in these sources will not be searchable unless they exist
        in another source that is still in the collection.
        
        Args:
            source_uris: List of source URIs that are no longer in collection
        """
        if not source_uris:
            return
        
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            placeholders = ",".join("?" * len(source_uris))
            cursor.execute(
                f"UPDATE sources SET in_collection = 0 WHERE source_uri IN ({placeholders})",
                source_uris
            )
            conn.commit()
            if cursor.rowcount > 0:
                self.logger.info(f"Marked {cursor.rowcount} sources as removed from collection")
        finally:
            conn.close()

    def get_sources_in_collection(self):
        """Get list of source URIs that are still in the Tidal collection."""
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT source_uri FROM sources WHERE in_collection = 1")
            return [row["source_uri"] for row in cursor.fetchall()]
        finally:
            conn.close()

    def clear_playlist_cache(self, playlist_uri=None):
        """Clear the playlist cache.
        
        WARNING: This permanently deletes track records including play counts!
        Only use for admin purposes. Track data persists even when items are
        removed from Tidal collection - play count reporting is handled by
        external utilities.
        
        Args:
            playlist_uri: If provided, clear only this playlist. 
                          If None, clear entire cache.
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            
            if playlist_uri:
                # Remove links for this source
                cursor.execute("DELETE FROM track_sources WHERE source_uri = ?", (playlist_uri,))
                # Remove orphaned tracks (tracks with no remaining source links)
                cursor.execute("""
                    DELETE FROM tracks WHERE track_uri NOT IN 
                    (SELECT DISTINCT track_uri FROM track_sources)
                """)
                cursor.execute("DELETE FROM sources WHERE source_uri = ?", (playlist_uri,))
                self.logger.info(f"Cleared cache for playlist: {playlist_uri}")
            else:
                cursor.execute("DELETE FROM track_sources")
                cursor.execute("DELETE FROM tracks")
                cursor.execute("DELETE FROM sources")
                self.logger.info("Cleared entire playlist cache")
            
            conn.commit()
        finally:
            conn.close()

    def get_playlist_cache_stats(self):
        """Get statistics about the playlist cache."""
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM sources")
            source_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM tracks")
            track_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM track_sources")
            link_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT source_uri FROM sources")
            source_uris = [row[0] for row in cursor.fetchall()]
            
            # Count by source type
            cursor.execute("""
                SELECT source_type, COUNT(*) as count 
                FROM sources GROUP BY source_type
            """)
            by_type = {row["source_type"]: row["count"] for row in cursor.fetchall()}
            
            return {
                "cached_playlists": source_count,
                "playlist_uris": source_uris,
                "total_tracks": track_count,
                "total_track_source_links": link_count,
                "by_type": by_type,
                "storage": "sqlite",
            }
        finally:
            conn.close()

    def start_session(self, skip_threshold, playlists, shuffle):
        self.started = True
        self.start_time = datetime.now(timezone.utc)

        self.skip_threshold = skip_threshold
        self.playlists = playlists
        self.shuffle = shuffle

        playlist_names = ",".join([playlist["name"] for playlist in playlists])
        self.queued_history = self.__load_queued_history()
        
        # Persist playlist selection for restoration on restart
        self.__save_selected_playlists()
        
        self.logger.info(
            f"Started Pibox session with skip threshold {skip_threshold} and {len(playlists)} playlists: {playlist_names}"
        )

    def update_playlists(self, playlists):
        """Update the selected playlists during an active session.
        
        This preserves the played_tracks, denylist, votes, and other session state
        while updating the available pool of tracks.
        """
        if not self.started:
            return False

        old_playlist_names = ",".join([p["name"] for p in self.playlists])
        new_playlist_names = ",".join([p["name"] for p in playlists])
        
        self.playlists = playlists
        
        # Persist playlist selection for restoration on restart
        self.__save_selected_playlists()
        
        self.logger.info(
            f"Updated Pibox session playlists from [{old_playlist_names}] to [{new_playlist_names}]"
        )
        return True

    def get_votes_for_track(self, track):
        return self.votes.get(track.uri, 0)

    def has_user_voted_on_track(self, user_fingerprint, track):
        return user_fingerprint in self.has_voted.get(track.uri, [])

    def add_vote_for_user_on_track(self, user_fingerprint, track):
        # Enforce per-user rate limit: max `vote_limit_count` votes within `vote_limit_minutes`
        now = datetime.now(timezone.utc)
        window = timedelta(minutes=self.vote_limit_minutes)

        timestamps = self.user_vote_times.get(user_fingerprint, [])
        # prune timestamps outside window
        timestamps = [t for t in timestamps if now - t <= window]

        if len(timestamps) >= self.vote_limit_count:
            # indicate rate limit exceeded and include seconds until next allowed vote
            # earliest timestamp will be the one that falls out of the window first
            earliest = min(timestamps)
            allow_at = earliest + window
            seconds_remaining = int((allow_at - now).total_seconds())
            if seconds_remaining < 0:
                seconds_remaining = 0
            raise RateLimitExceeded(
                f"User exceeded vote limit of {self.vote_limit_count} per {self.vote_limit_minutes} minutes",
                seconds_remaining,
            )

        # record this vote timestamp
        timestamps.append(now)
        self.user_vote_times[user_fingerprint] = timestamps

        users_who_voted = self.has_voted.get(track.uri, [])
        users_who_voted.append(user_fingerprint)
        self.has_voted[track.uri] = users_who_voted

        vote_count = self.votes.get(track.uri, 0) + 1
        self.votes[track.uri] = vote_count

        return vote_count



    def skip_queued_track(self, track):
        del self.votes[track.uri]
        del self.has_voted[track.uri]

        # Remove from any user's queued lists when skipping/removing from queue
        self.remove_queued_track_for_all_users(track.uri)

        self.denylist.append(track.uri)

    def get_suggestions(self):
        unplayed_queue_history = [
            uri for uri in self.queued_history if uri not in self.played_tracks
        ]

        return unplayed_queue_history

    def end_session(self):
        self.__save_queued_history()
        self.__initialise()

        self.logger.info("Ended Pibox session")

    def to_json(self):
        return {
            "started": self.started,
            "startTime": (self.start_time.isoformat() if self.start_time else None),
            "skipThreshold": self.skip_threshold,
            "playlists": self.playlists,
            "playedTracks": self.played_tracks,
            "remainingPlaylistTracks": self.remaining_playlist_tracks,
            "trackSources": self.track_sources,
        }

    def get_user_nickname(self, fingerprint):
        """Get or generate a fun nickname for a user based on their fingerprint."""
        if fingerprint not in self.user_nicknames:
            # Use fingerprint as seed for consistent nickname per session
            rng = random.Random(fingerprint)
            adjective = rng.choice(ADJECTIVES)
            noun = rng.choice(NOUNS)
            self.user_nicknames[fingerprint] = f"{adjective} {noun}"
        return self.user_nicknames[fingerprint]

    def set_track_source(self, track_uri, source_type, source_name):
        """Record the source of a track (playlist name or user nickname)."""
        self.track_sources[track_uri] = {
            "type": source_type,
            "name": source_name,
        }

    def __load_queued_history(self):
        try:
            with open(self.data_dir.joinpath("pibox-queue-history.json")) as f:
                history = json.load(f)
                return history
        except FileNotFoundError:
            return []

    def __load_selected_playlists(self):
        """Load persisted playlist selection from disk.
        
        Returns a list of playlist dicts with 'uri' and 'name' keys,
        or an empty list if no persisted selection exists.
        """
        try:
            with open(self.data_dir.joinpath("pibox-selected-playlists.json")) as f:
                playlists = json.load(f)
                return playlists
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            self.logger.warning("Failed to parse persisted playlists, ignoring")
            return []

    def __save_selected_playlists(self):
        """Persist current playlist selection to disk.
        
        Saves the current playlists list (uri and name for each) so it can
        be restored on restart when default_playlists is not configured.
        """
        try:
            with open(self.data_dir.joinpath("pibox-selected-playlists.json"), "w") as f:
                json.dump(self.playlists, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to persist playlist selection: {e}")

    def get_persisted_playlists(self):
        """Get persisted playlist selection (public method for config API)."""
        return self.__load_selected_playlists()

    def __save_queued_history(self):
        existing_suggestions = self.queued_history
        suggestions_to_add = [
            uri for uri in self.manually_queued_tracks if uri not in self.denylist
        ]
        new_suggestions = existing_suggestions + suggestions_to_add
        with open(self.data_dir.joinpath("pibox-queue-history.json"), "w+") as f:
            json.dump(new_suggestions, f)

    def __initialise(self):
        self.started = False
        self.start_time = None
        self.skip_threshold = 1
        self.playlists = []
        self.denylist = ["spotify:track:0afhq8XCExXpqazXczTSve"]
        self.played_tracks = []
        self.manually_queued_tracks = []
        self.remaining_playlist_tracks = []
        # Library restriction mode - when True, only collection tracks are searchable
        self.library_restrict = False
        # Collection index for library_restrict mode
        self.collection_index = None
        self.collection_index_time = None
        self.votes = {}
        self.has_voted = {}
        # mapping fingerprint -> list[datetime] of recent vote timestamps
        self.user_vote_times = {}
        # mapping fingerprint -> list[uris] of manually queued tracks for that user
        self.user_queued_tracks = {}
        # per-user queue limit (0 = unlimited)
        self.queue_limit_per_user = 0
        # mapping fingerprint -> fun nickname
        self.user_nicknames = {}
        # mapping track_uri -> source info {"type": "playlist"|"user", "name": "..."}
        self.track_sources = {}

    def set_vote_limits(self, count, minutes):
        try:
            self.vote_limit_count = int(count)
            self.vote_limit_minutes = int(minutes)
        except Exception:
            pass

    def set_queue_limit(self, limit):
        try:
            self.queue_limit_per_user = int(limit)
            import logging
            logging.getLogger(__name__).info(f"Queue limit per user set to: {self.queue_limit_per_user}")
        except Exception:
            pass

    def set_library_restrict(self, enabled):
        """Enable or disable library restriction mode."""
        self.library_restrict = bool(enabled)

    def build_collection_index(self, tracks):
        """Build a searchable index from a list of Track objects.
        
        Args:
            tracks: List of Mopidy Track objects with uri, name, artists, album
            
        The index structure:
        {
            "tracks": [{"uri", "name", "artist", "album", "searchable"}, ...],
            "artists": {"Artist Name": [track_indices], ...},
            "albums": {"Album Name": [track_indices], ...}
        }
        """
        from datetime import datetime, timezone
        
        index = {
            "tracks": [],
            "artists": {},
            "albums": {},
        }
        
        for i, track in enumerate(tracks):
            # Extract artist name(s)
            artist_names = []
            if hasattr(track, 'artists') and track.artists:
                artist_names = [a.name for a in track.artists if a and a.name]
            artist_str = ", ".join(artist_names) if artist_names else "Unknown Artist"
            
            # Extract album name
            album_name = "Unknown Album"
            if hasattr(track, 'album') and track.album and track.album.name:
                album_name = track.album.name
            
            # Build searchable string (lowercase for case-insensitive search)
            searchable = f"{track.name} {artist_str} {album_name}".lower()
            
            track_entry = {
                "uri": track.uri,
                "name": track.name,
                "artist": artist_str,
                "album": album_name,
                "searchable": searchable,
            }
            index["tracks"].append(track_entry)
            
            # Index by artist
            for artist_name in artist_names:
                if artist_name not in index["artists"]:
                    index["artists"][artist_name] = []
                index["artists"][artist_name].append(i)
            
            # Index by album
            if album_name != "Unknown Album":
                if album_name not in index["albums"]:
                    index["albums"][album_name] = []
                index["albums"][album_name].append(i)
        
        self.collection_index = index
        self.collection_index_time = datetime.now(timezone.utc)
        
        self.logger.info(
            f"Built collection index: {len(index['tracks'])} tracks, "
            f"{len(index['artists'])} artists, {len(index['albums'])} albums"
        )
        return index

    def build_collection_index_from_refs(self, track_refs):
        """Build a searchable index from track Refs (fast, no lookups needed).
        
        Args:
            track_refs: List of tuples (ref, source_type, source_name, source_uri)
                       where ref is a Mopidy Ref with uri and name
                       source_type is "saved", "album", "playlist", or "mix"
                       source_uri is the URI of the source (for session filtering)
            
        The index structure:
        {
            "tracks": [{"uri", "name", "artist", "source", "source_type", "source_uri", "searchable"}, ...],
            "artists": {"Artist Name": [track_indices], ...},
            "sources": {"Source Name": [track_indices], ...}
        }
        
        Tracks from "saved" and "album" sources are always searchable.
        Tracks from "playlist" and "mix" sources are only searchable if 
        the source is selected in the current session playlists.
        """
        # Build index from SQLite cache which has artist info
        return self.build_collection_index_from_cache()

    def build_collection_index_from_cache(self):
        """Build a searchable index from the SQLite cache.
        
        This method reads all cached tracks and builds an index structure
        that includes artist information for Artist > Tracks browsing.
        
        Tracks are deduped by URI but track ALL sources they belong to.
        This allows proper session filtering - a track is searchable if
        ANY of its sources are enabled for the session.
        """
        from datetime import datetime, timezone
        
        # Get all cached tracks with metadata (only from sources still in collection)
        cached_tracks = self.get_all_cached_tracks_with_metadata()
        
        if not cached_tracks:
            self.logger.warning("No tracks in cache to build index from")
            return None
        
        index = {
            "tracks": [],
            "artists": {},  # Index by artist name
            "sources": {},  # Index by source (album/playlist) 
        }
        
        # Track URIs we've seen (dedupe across sources)
        # We store all sources for each track to allow proper session filtering
        seen_uris = {}  # uri -> {"index": int, "sources": [{type, uri, name}, ...]}
        
        for track_data in cached_tracks:
            track_uri = track_data["track_uri"]
            source_info = {
                "type": track_data["source_type"],
                "uri": track_data["source_uri"],
                "name": track_data["source_name"],
            }
            
            # If we've already indexed this track, add this source to its list
            if track_uri in seen_uris:
                existing = seen_uris[track_uri]
                existing_idx = existing["index"]
                
                # Add source to the track's sources list (avoid duplicates)
                if source_info not in existing["sources"]:
                    existing["sources"].append(source_info)
                    # Update the track entry in the index
                    index["tracks"][existing_idx]["all_sources"] = existing["sources"]
                
                # Add to source index
                source_name = track_data["source_name"]
                if source_name not in index["sources"]:
                    index["sources"][source_name] = []
                if existing_idx not in index["sources"][source_name]:
                    index["sources"][source_name].append(existing_idx)
                continue
            
            artist_name = track_data["artist_name"] or "Unknown Artist"
            album_name = track_data["album_name"] or ""
            source_name = track_data["source_name"]
            source_type = track_data["source_type"]
            source_uri = track_data["source_uri"]
            track_name = track_data["track_name"]
            
            # Build searchable string
            searchable = f"{track_name} {artist_name} {album_name} {source_name}".lower()
            
            track_entry = {
                "uri": track_uri,
                "name": track_name,
                "artist": artist_name,
                "album": album_name,
                "source": source_name,  # Primary source (for display)
                "source_type": source_type,  # Primary source type
                "source_uri": source_uri,  # Primary source URI
                "all_sources": [source_info],  # ALL sources this track belongs to
                "searchable": searchable,
            }
            
            idx = len(index["tracks"])
            index["tracks"].append(track_entry)
            seen_uris[track_uri] = {"index": idx, "sources": [source_info]}
            
            # Index by artist
            if artist_name and artist_name != "Unknown Artist":
                if artist_name not in index["artists"]:
                    index["artists"][artist_name] = []
                index["artists"][artist_name].append(idx)
            
            # Index by source
            if source_name not in index["sources"]:
                index["sources"][source_name] = []
            index["sources"][source_name].append(idx)
        
        self.collection_index = index
        self.collection_index_time = datetime.now(timezone.utc)
        
        self.logger.info(
            f"Built collection index: {len(index['tracks'])} tracks, "
            f"{len(index['artists'])} artists, {len(index['sources'])} sources"
        )
        return index

    def _is_source_enabled_for_session(self, track):
        """Check if ANY of a track's sources are enabled for the current session.
        
        A track is searchable if ANY of the following is true:
        - It exists in a "saved" source (Liked Tracks) - ALWAYS enabled
        - It exists in an "album" source (Collection Albums) - ALWAYS enabled  
        - It exists in a "playlist" or "mix" that is selected in session playlists
        
        Args:
            track: Track entry from the index (must have "all_sources" list)
            
        Returns:
            bool: True if the track should be searchable in current session
        """
        all_sources = track.get("all_sources", [])
        
        # Fallback for old index format without all_sources
        if not all_sources:
            source_type = track.get("source_type", "")
            if source_type in ("saved", "album"):
                return True
            source_uri = track.get("source_uri")
            if source_uri and self.playlists:
                session_uris = {p.get("uri") for p in self.playlists}
                return source_uri in session_uris
            return False
        
        # Check each source the track belongs to
        session_uris = {p.get("uri") for p in self.playlists} if self.playlists else set()
        
        for source in all_sources:
            source_type = source.get("type", "")
            
            # Saved tracks and albums are always searchable
            if source_type in ("saved", "album"):
                return True
            
            # Playlists and mixes require the source to be in session playlists
            source_uri = source.get("uri")
            if source_uri and source_uri in session_uris:
                return True
        
        # No enabled source found
        return False

    def search_collection(self, query):
        """Search the collection index for tracks matching query.
        
        Only returns tracks that are enabled for the current session:
        - Saved tracks and album tracks are always returned
        - Playlist/mix tracks only returned if source is selected for session
        
        Args:
            query: Search string (case-insensitive)
            
        Returns:
            List of matching track entries with uri, name, artist, album
        """
        if not self.collection_index:
            return []
        
        query_lower = query.lower()
        results = []
        
        for track in self.collection_index["tracks"]:
            # Filter by session-enabled sources
            if not self._is_source_enabled_for_session(track):
                continue
                
            if query_lower in track["searchable"]:
                results.append({
                    "uri": track["uri"],
                    "name": track["name"],
                    "artist": track.get("artist", "Unknown Artist"),
                    "album": track.get("album") or track.get("source", ""),
                })
        
        return results

    def get_collection_sources(self):
        """Get sorted list of all sources (albums/playlists) in the collection."""
        if not self.collection_index:
            return []
        # Support both old (artists) and new (sources) index structure
        if "sources" in self.collection_index:
            return sorted(self.collection_index["sources"].keys())
        elif "artists" in self.collection_index:
            return sorted(self.collection_index["artists"].keys())
        return []

    def get_collection_sources_for_session(self):
        """Get sorted list of sources (albums/playlists) enabled for current session.
        
        Only returns sources that are:
        - Albums (always enabled)
        - Saved tracks source (always enabled)
        - Playlists/mixes that are selected in session playlists
        """
        if not self.collection_index:
            return []
        
        enabled_sources = set()
        
        for track in self.collection_index["tracks"]:
            if self._is_source_enabled_for_session(track):
                enabled_sources.add(track.get("source", ""))
        
        return sorted(enabled_sources)

    def get_collection_artists(self):
        """Get sorted list of artists with tracks enabled for current session.
        
        Only returns artists who have at least one track enabled for the session
        (i.e., from saved tracks, albums, or selected playlists/mixes).
        """
        if not self.collection_index:
            return []
        
        if "artists" not in self.collection_index or not self.collection_index["artists"]:
            # Fall back to sources for ref-based index
            return self.get_collection_sources_for_session()
        
        # Filter artists: only include those with at least one enabled track
        enabled_artists = set()
        tracks = self.collection_index["tracks"]
        
        for artist_name, track_indices in self.collection_index["artists"].items():
            for idx in track_indices:
                if self._is_source_enabled_for_session(tracks[idx]):
                    enabled_artists.add(artist_name)
                    break  # Found at least one enabled track
        
        return sorted(enabled_artists)

    def get_tracks_for_artist(self, artist_name):
        """Get all tracks for a specific artist (or source).
        
        Only returns tracks enabled for the current session.
        
        Args:
            artist_name: Exact artist/source name (case-sensitive)
            
        Returns:
            List of track entries for that artist/source
        """
        if not self.collection_index:
            return []
        
        # Support both old (artists) and new (sources) index structure
        if "artists" in self.collection_index and artist_name in self.collection_index["artists"]:
            track_indices = self.collection_index["artists"].get(artist_name, [])
        elif "sources" in self.collection_index:
            track_indices = self.collection_index["sources"].get(artist_name, [])
        else:
            track_indices = []
        
        tracks = self.collection_index["tracks"]
        
        # Filter by session-enabled sources
        return [
            {
                "uri": tracks[i]["uri"],
                "name": tracks[i]["name"],
                "artist": tracks[i].get("artist", "Unknown Artist"),
                "album": tracks[i].get("album") or tracks[i].get("source", ""),
            }
            for i in track_indices
            if self._is_source_enabled_for_session(tracks[i])
        ]

    def get_collection_stats(self):
        """Get statistics about the collection index and what's enabled for session.
        
        Returns:
            dict with total and session-enabled counts
        """
        if not self.collection_index:
            return {"indexed": False}
        
        tracks = self.collection_index["tracks"]
        
        # Count by source type
        total_by_type = {"saved": 0, "album": 0, "playlist": 0, "mix": 0}
        enabled_by_type = {"saved": 0, "album": 0, "playlist": 0, "mix": 0}
        
        for track in tracks:
            source_type = track.get("source_type", "unknown")
            if source_type in total_by_type:
                total_by_type[source_type] += 1
                if self._is_source_enabled_for_session(track):
                    enabled_by_type[source_type] += 1
        
        total_enabled = sum(enabled_by_type.values())
        total_tracks = len(tracks)
        total_artists = len(self.collection_index.get("artists", {}))
        enabled_artists = len(self.get_collection_artists())
        
        return {
            "indexed": True,
            "total_tracks": total_tracks,
            "enabled_tracks": total_enabled,
            "total_artists": total_artists,
            "enabled_artists": enabled_artists,
            "total_sources": len(self.collection_index.get("sources", {})),
            "by_type": {
                "saved": {"total": total_by_type["saved"], "enabled": enabled_by_type["saved"]},
                "album": {"total": total_by_type["album"], "enabled": enabled_by_type["album"]},
                "playlist": {"total": total_by_type["playlist"], "enabled": enabled_by_type["playlist"]},
                "mix": {"total": total_by_type["mix"], "enabled": enabled_by_type["mix"]},
            },
            "indexed_at": self.collection_index_time.isoformat() if self.collection_index_time else None,
        }

    def needs_index_refresh(self, max_age_minutes=60):
        """Check if the collection index needs to be refreshed.
        
        Args:
            max_age_minutes: Maximum age in minutes before refresh is needed
            
        Returns:
            True if index is missing or older than max_age_minutes
        """
        if not self.collection_index or not self.collection_index_time:
            return True
        
        from datetime import datetime, timezone, timedelta
        age = datetime.now(timezone.utc) - self.collection_index_time
        return age > timedelta(minutes=max_age_minutes)

    def get_user_queue_count(self, user_fingerprint):
        return len(self.user_queued_tracks.get(user_fingerprint, []))

    def add_manually_queued_track_for_user(self, user_fingerprint, track_uri):
        import logging
        logger = logging.getLogger(__name__)
        # Enforce per-user manual queue limit if configured (>0)
        current_count = self.get_user_queue_count(user_fingerprint)
        logger.info(f"add_manually_queued_track_for_user: user={user_fingerprint[:8] if user_fingerprint else 'None'}..., limit={self.queue_limit_per_user}, current_count={current_count}")
        if self.queue_limit_per_user and current_count >= self.queue_limit_per_user:
            logger.info(f"Queue limit exceeded for user {user_fingerprint[:8] if user_fingerprint else 'None'}...")
            return False
        lst = self.user_queued_tracks.get(user_fingerprint, [])
        lst.append(track_uri)
        self.user_queued_tracks[user_fingerprint] = lst
        return True

    def remove_queued_track_for_all_users(self, track_uri):
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"remove_queued_track_for_all_users: {track_uri}")
        # Remove the track from any user's manual queue lists
        for user, lst in list(self.user_queued_tracks.items()):
            if track_uri in lst:
                logger.info(f"Removing {track_uri} from user {user[:8] if user else 'None'}... queue (had {len(lst)} tracks)")
                try:
                    lst = [u for u in lst if u != track_uri]
                    if lst:
                        self.user_queued_tracks[user] = lst
                    else:
                        del self.user_queued_tracks[user]
                except Exception:
                    pass
        # Also remove from the flat manually_queued_tracks list if present
        try:
            self.manually_queued_tracks = [u for u in self.manually_queued_tracks if u != track_uri]
        except Exception:
            pass

    def remove_queued_track(self, track_uri):
        """
        Remove a queued track from all internal lists and vote records, without adding it
        to the denylist (i.e. owner-initiated removal).
        """
        try:
            if track_uri in self.votes:
                del self.votes[track_uri]
        except Exception:
            pass
        try:
            if track_uri in self.has_voted:
                del self.has_voted[track_uri]
        except Exception:
            pass

        # Remove from user-specific queued lists and the flat manually_queued_tracks list
        self.remove_queued_track_for_all_users(track_uri)

    def get_vote_cooldown_seconds(self, user_fingerprint):
        """
        Return the number of seconds remaining until `user_fingerprint` may
        cast another vote. Returns 0 if the user is allowed to vote now.
        """
        now = datetime.now(timezone.utc)
        window = timedelta(minutes=self.vote_limit_minutes)

        timestamps = self.user_vote_times.get(user_fingerprint, [])
        # prune timestamps outside window
        timestamps = [t for t in timestamps if now - t <= window]

        if len(timestamps) < self.vote_limit_count:
            return 0

        earliest = min(timestamps)
        allow_at = earliest + window
        seconds_remaining = int((allow_at - now).total_seconds())
        return max(0, seconds_remaining)

class RateLimitExceeded(Exception):
    def __init__(self, message=None, seconds_remaining=None):
        super().__init__(message or "Rate limit exceeded")
        try:
            self.seconds_remaining = int(seconds_remaining) if seconds_remaining is not None else None
        except Exception:
            self.seconds_remaining = None

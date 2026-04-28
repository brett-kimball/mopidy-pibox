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
# - Added user nickname generation and per-user queue tracking
# - Added track source attribution (playlist name vs user nickname)
# - Added persisted playlist selection (restored on restart)

from datetime import datetime, timezone, timedelta
import json
import logging
import random


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

        self.__initialise()

        self.logger = logging.getLogger(__name__)

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

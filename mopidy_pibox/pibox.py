from datetime import datetime, timezone, timedelta
import json
import logging
import random


# Word lists for generating fun nautical user nicknames
ADJECTIVES = [
    "Salty", "Scurvy", "Barnacled", "Swashbuckling", "Landlubbing", "Seafaring",
    "Windswept", "Crusty", "Briny", "Stormy", "Drifting", "Anchored", "Rigged",
    "Capsized", "Marooned", "Plundering", "Rowdy", "Mutinous", "Jolly", "Rusty",
    "Groggy", "Bilge", "Scallywag", "Sunburnt", "Tattered", "Wayward", "Roving",
    "Shipwrecked", "Weathered", "Tipsy", "Rogue", "Surly", "Cunning", "Fearless",
    "Grizzled", "Legendary", "Mysterious", "One-Eyed", "Peg-Legged", "Ragged",
    "Sneaky", "Tattooed", "Toothless", "Treacherous", "Wily", "Wobbly", "Cursed",
]

#NOUNS = [
#    "Buccaneer", "Privateer", "Corsair", "Mariner", "Skipper", "Deckhand",
#    "Helmsman", "Bosun", "Quartermaster", "Shipmate", "Scallywag", "Rapscallion",
#    "Landlubber", "Seadog", "Swab", "Barnacle", "Kraken", "Mermaid", "Parrot",
#    "Pelican", "Albatross", "Dolphin", "Whale", "Shark", "Octopus", "Jellyfish",
#    "Starfish", "Seahorse", "Manatee", "Stingray", "Barracuda", "Mackerel",
#    "Cutlass", "Compass", "Anchor", "Cannon", "Doubloon", "Spyglass", "Plank",
#    "Rigger", "Swabbie", "Castaway", "Smuggler", "Stowaway", "Drifter", "Voyager",
#]

#ADJECTIVES = [
#    "Rum-Soaked", "Grog-Blind", "Blackhearted", "Gut-Slitting", "Noose-Ready", "Hangman’s",
#    "Keel-hauled", "Davy-Jonesed", "Blood-crusted", "Spleen-ripping", "Cut-throat",
#    "Back-stabbing", "Plague-ridden", "Pox-marked", "Gangrenous", "Lice-ridden",
#    "Festering", "Bilge-slurping", "Cannon-blasted", "Powder-burnt", "Chain-shackled",
#    "Brine-pickled", "Ghost-haunted", "Hell-bound", "Demon-eyed", "Kraken-touched",
#    "Shark-bitten", "Cursed-by-Calypso", "Doubloon-greedy", "Treasonous", "Mutiny-sparking",
#    "Parrot-plucking", "Peg-leg-stomping", "Hook-handed", "Eyepatch-wearing", "Scurvy-mouthed",
#    "Rum-reeking", "Booty-obsessed", "Blunderbuss-toting", "Flensing-knife", "Cat-o-nine-tails",
#    "Gibbet-dancing", "Yardarm-swinging", "Walk-the-plank", "Buried-alive", "Soul-forsaken",
#]

#NOUNS = [
#    "Reaver", "Cutpurse", "Throat-cutter", "Gut-stabber", "Necklace-thief", "Grave-robber",
#    "Hangman’s Get", "Galley-slave", "Press-gang Brute", "Powder-monkey", "Bilge-rat",
#    "Chain-gang Scum", "Mutineer", "Turncoat", "Blackguard", "Sea-ghoul",
#    "Drowned Wretch", "Ghost-sailor", "Kraken-bait", "Shark-chum", "Leper-pirate",
#    "Pox-carrier", "Rum-fiend", "Grog-zombie", "Doubloon-hoarder", "Booty-madman",
#    "Plunder-lord", "Blood-debt Captain", "Noose-dodger", "Gibbet-crow", "Yardarm-corpse",
#    "Plank-walker", "Hook-whore", "Peg-leg Butcher", "Eyepatch Fiend", "Scurvy Dog",
#    "Mangy Parrot", "Lice-nest Beard", "Cannon-fodder", "Chain-rattler", "Shackle-dragger",
#    "Cat-o-nine Victim", "Flayed-back", "Soul-seller", "Devil’s Bargain", "Calypso’s Curse",
#]

#ADJECTIVES = [
#    "Sleep-Deprived", "Spinnaker-Shredded", "Beer-Can", "Rail-Meat", "Foul-Weather", "No-Wind",
#    "Thunder-Squall", "Mackinac-Fogged", "Port-Huron-Start", "Buoy-Rounding", "Over-Canvassed",
#    "Under-Canvassed", "Broach-Prone", "Gybe-Broked", "Protest-Flag", "Rating-Cheating",
#    "Fudge-Bribed", "Lake-Huron-Hosed", "Straits-Squalled", "Round-Island", "Puff-Chasing",
#    "Tack-Happy", "Jib-Tearin'", "Boom-Vanged", "Keel-Draggin'", "Rudder-Rattlin'",
#    "Crew-Sick", "Hangover-Helm", "Mud-Bottom", "Light-Air-Loser", "Heavy-Air-Hero",
#    "Chicken-Chute", "Pole-Dancing", "Grinder-Gnarled", "Trim-Terror", "Bow-Pulpit",
#    "Stern-Whine", "Finish-Line", "DNF-Doomed", "PHRF-Pirate", "CORK-Cursed",
#]

#NOUNS = [
#    "Rail-Slave", "Beer-Ballast", "Mackinac-Mule", "Fudge-Gobbler", "Squall-Surfer", "Spinnaker-Tangler",
#    "Protest-Paperweight", "Buoy-Bouncer", "Puff-Hunter", "Tack-Tyrant", "Gybe-Goon",
#    "Boom-Banger", "Jib-Jockey", "Grinder-Gorilla", "Pit-Pirate", "Mast-Maniac",
#    "Nav-Nerd", "Helm-Hobo", "Bow-Brat", "Stern-Screamer", "Keel-Cleaner",
#    "Rudder-Ranger", "Chute-Chucker", "Pole-Pusher", "Vang-Victim", "Winch-Wench",
#    "Sheet-Hand", "Tactician-Troll", "Trim-Terrorist", "Rail-Rat", "Mud-Mucker",
#    "Fog-Fumbler", "Thunder-Chicken", "Start-Line-Squatter", "Finish-Line-Fumbler", "DNF-Diva",
#    "PHRF-Punk", "CORK-Criminal", "Mackinac-Marathoner", "Huron-Hangover", "Port-Huron-Paddler",
#]

#ADJECTIVES = [
#    "Sleep Deprived", "Spinnaker Shredded", "Beer Can", "Rail Meat", "Foul Weather", "No Wind",
#    "Thunder Squall", "Mackinac Fogged", "Port Huron Start", "Buoy Rounding", "Over Canvassed",
#    "Under Canvassed", "Broach Prone", "Gybe Broked", "Protest Flag", "Rating Cheating",
#    "Fudge Bribed", "Lake Huron Hosed", "Straits Squalled", "Round Island", "Puff Chasing",
#    "Tack Happy", "Jib Tearin'", "Boom Vanged", "Keel Draggin'", "Rudder Rattlin'",
#    "Crew Sick", "Hangover Helm", "Mud Bottom", "Light Air Loser", "Heavy Air Hero",
#    "Chicken Chute", "Pole Dancing", "Grinder Gnarled", "Trim Terror", "Bow Pulpit",
#    "Stern Whine", "Finish Line", "DNF Doomed", "PHRF Pirate", "CORK Cursed",
#]

#NOUNS = [
#    "Rail Slave", "Beer Ballast", "Mackinac Mule", "Fudge Gobbler", "Squall Surfer", "Spinnaker Tangler",
#    "Protest Paperweight", "Buoy Bouncer", "Puff Hunter", "Tack Tyrant", "Gybe Goon",
#    "Boom Banger", "Jib Jockey", "Grinder Gorilla", "Pit Pirate", "Mast Maniac",
#    "Nav Nerd", "Helm Hobo", "Bow Brat", "Stern Screamer", "Keel Cleaner",
#    "Rudder Ranger", "Chute Chucker", "Pole Pusher", "Vang Victim", "Winch Wench",
#    "Sheet Hand", "Tactician Troll", "Trim Terrorist", "Rail Rat", "Mud Mucker",
#    "Fog Fumbler", "Thunder Chicken", "Start Line Squatter", "Finish Line Fumbler", "DNF Diva",
#    "PHRF Punk", "CORK Criminal", "Mackinac Marathoner", "Huron Hangover", "Port Huron Paddler",
#]

#ADJECTIVES = [
#    "Overslept",
#    "Shredded",
#    "Beered",
#    "Railed",
#    "Soaked",
#    "Becalmed",
#    "Squalled",
#    "Fogged",
#    "Started",
#    "Rounded",
#    "Overpowered",
#    "Underpowered",
#    "Broached",
#    "Gybed",
#    "Protested",
#    "Cheated",
#    "Fudged",
#    "Hosed",
#    "Straited",
#    "Puffed",
#    "Tacked",
#    "Jibbed",
#    "Vanged",
#    "Dragged",
#    "Rattled",
#    "Seasick",
#    "Hungover",
#    "Muddy",
#    "Lightair",
#    "Heavyair",
#    "Choked",
#    "Poled",
#    "Grinded",
#    "Trimmed",
#    "Bowed",
#    "Sterned",
#    "Finished",
#    "DNF'ed",
#    "PHRF'ed",
#    "Blistered",
#    "Chafed",
#    "Snagged",
#    "Wrapped",
#    "Kinked",
#    "Slugged",
#]
#    "CORK'ed",

NOUNS = [
    "Railmeat",
    "Beerballast",
    "Mackmule",
    "Fudgehog",
    "Squallsurfer",
    "Chutewrapper",
    "Protestflag",
    "Buoybumper",
    "Puffchaser",
    "Tackhead",
    "Gybeass",
    "Boombiter",
    "Jibmonkey",
    "Grindbeast",
    "Pitrat",
    "Mastweasel",
    "Navgeek",
    "Helmclown",
    "Bowbrat",
    "Sternbitch",
    "Keeldragger",
    "Rudderpig",
    "Chutethrower",
    "Polejockey",
    "Vangvictim",
    "Winchwench",
    "Sheethand",
    "Tactictroll",
    "Trimlord",
    "Railvermin",
    "Mudrat",
    "Fogfart",
    "Thunderchicken",
    "Startlinecreep",
    "Finishfumbler",
    "DNFqueen",
    "PHRFpunk",
    "CORKcrook",
    "Mackwalker",
    "Huronhead",
    "Blisterfoot",
    "Chafemarks",
    "Snagking",
    "Wrapmaster",
    "Kinklord",
    "Sluggo",
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
        except Exception:
            pass

    def get_user_queue_count(self, user_fingerprint):
        return len(self.user_queued_tracks.get(user_fingerprint, []))

    def add_manually_queued_track_for_user(self, user_fingerprint, track_uri):
        # Enforce per-user manual queue limit if configured (>0)
        if self.queue_limit_per_user and self.get_user_queue_count(user_fingerprint) >= self.queue_limit_per_user:
            return False
        lst = self.user_queued_tracks.get(user_fingerprint, [])
        lst.append(track_uri)
        self.user_queued_tracks[user_fingerprint] = lst
        return True

    def remove_queued_track_for_all_users(self, track_uri):
        # Remove the track from any user's manual queue lists
        for user, lst in list(self.user_queued_tracks.items()):
            if track_uri in lst:
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

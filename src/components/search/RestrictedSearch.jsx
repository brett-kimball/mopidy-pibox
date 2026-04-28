import React, { useState, useEffect, useCallback } from "react";
import SearchResultItem from "./SearchResultItem.jsx";
import { searchCollection, queueTrack, playIfStopped } from "services/mopidy.js";
import { useLocation } from "wouter";
import toast from "react-hot-toast";
import BounceLoader from "react-spinners/BounceLoader";
import CloseIcon from "@mui/icons-material/Close";
import { IconButton, TextField, InputAdornment, Tabs, Tab, Box } from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import ArtistBrowser from "./ArtistBrowser.jsx";

/**
 * RestrictedSearch - Search component for library_restrict mode.
 * Provides dynamic filtering of the user's Tidal collection with
 * instant results as the user types.
 */
const RestrictedSearch = () => {
  const [searchTerm, setSearchTerm] = useState("");
  const [results, setResults] = useState([]);
  const [fetching, setFetching] = useState(false);
  const [activeTab, setActiveTab] = useState(0); // 0 = Search, 1 = Browse Artists
  const [_, navigate] = useLocation();

  // Debounced search - triggers after user stops typing
  useEffect(() => {
    if (activeTab !== 0) return; // Only search in search tab
    
    if (!searchTerm || searchTerm.length < 2) {
      setResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      setFetching(true);
      try {
        const tracks = await searchCollection(searchTerm);
        setResults(tracks);
      } catch (error) {
        console.error("Collection search error:", error);
        setResults([]);
      } finally {
        setFetching(false);
      }
    }, 150); // 150ms debounce for responsive feel

    return () => clearTimeout(timer);
  }, [searchTerm, activeTab]);

  const queue = async (track) => {
    try {
      // track from collection API is {uri, name, artist, album}
      // need to pass uri to queueTrack
      const trackForQueue = track.uri ? { uri: track.uri, name: track.name } : track;
      await queueTrack(trackForQueue);
      
      // Track that this user added this track
      try {
        if (typeof window !== "undefined" && window.localStorage) {
          const uri = track.uri || track;
          window.localStorage.setItem(`pibox_added_${uri}`, "1");
        }
      } catch (e) {
        // ignore
      }
      
      playIfStopped();
      toast.success(`${track.name} added to queue`);
      navigate("/");
    } catch (e) {
      toast.error(e.message);
    }
  };

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
    setSearchTerm("");
    setResults([]);
  };

  const searchResults = results.map((track, index) => (
    <SearchResultItem
      key={track.uri || index}
      track={{
        uri: track.uri,
        name: track.name,
        artists: [{ name: track.artist }],
        album: { name: track.album },
      }}
      onClick={() => queue(track)}
    />
  ));

  return (
    <div className="h-full w-full">
      <div className="h-full flex flex-col">
        {/* Header with tabs */}
        <div className="max-w-4xl mx-auto w-full px-2">
          <div className="flex items-center justify-between mb-2">
            <Tabs
              value={activeTab}
              onChange={handleTabChange}
              textColor="inherit"
              indicatorColor="primary"
              sx={{
                "& .MuiTab-root": { color: "white", minWidth: 100 },
                "& .Mui-selected": { color: "#90caf9" },
              }}
            >
              <Tab label="Search" />
              <Tab label="Browse Artists" />
            </Tabs>
            <IconButton
              color="secondary"
              onClick={() => navigate("/")}
              className="ml-2 p-0 bg-transparent border-transparent"
            >
              <CloseIcon className="w-11 h-11 text-white" />
            </IconButton>
          </div>

          {/* Search input (only in search tab) */}
          {activeTab === 0 && (
            <TextField
              fullWidth
              variant="outlined"
              placeholder="Search your collection..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              autoFocus
              slotProps={{
                input: {
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon sx={{ color: "white" }} />
                    </InputAdornment>
                  ),
                  sx: {
                    color: "white",
                    backgroundColor: "rgba(255,255,255,0.1)",
                    borderRadius: 1,
                    "& .MuiOutlinedInput-notchedOutline": {
                      borderColor: "rgba(255,255,255,0.3)",
                    },
                    "&:hover .MuiOutlinedInput-notchedOutline": {
                      borderColor: "rgba(255,255,255,0.5)",
                    },
                    "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
                      borderColor: "#90caf9",
                    },
                  },
                },
              }}
            />
          )}
        </div>

        {/* Results area */}
        <div className="flex-1 overflow-auto mt-4">
          {activeTab === 0 ? (
            // Search tab content
            fetching ? (
              <div className="loading flex justify-center items-center h-32">
                <BounceLoader size={44} color="#FFFFFF" />
              </div>
            ) : results.length > 0 ? (
              <div className="w-full">{searchResults}</div>
            ) : searchTerm.length >= 2 ? (
              <div className="text-white text-center mt-8">
                No tracks found matching "{searchTerm}"
              </div>
            ) : (
              <div className="text-white text-center mt-8 opacity-70">
                Start typing to search the music collection
              </div>
            )
          ) : (
            // Browse Artists tab content
            <ArtistBrowser onTrackSelected={queue} />
          )}
        </div>
      </div>
    </div>
  );
};

export default RestrictedSearch;

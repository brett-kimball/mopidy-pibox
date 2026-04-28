import React, { useState, useEffect, useMemo } from "react";
import {
  getCollectionArtists,
  getCollectionArtistTracks,
} from "services/mopidy.js";
import BounceLoader from "react-spinners/BounceLoader";
import {
  TextField,
  InputAdornment,
  List,
  ListItemButton,
  ListItemText,
  IconButton,
  Divider,
} from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import SearchResultItem from "./SearchResultItem.jsx";

/**
 * ArtistBrowser - Browse artists in the collection and view their tracks.
 * Features:
 * - Alphabetical artist list with dynamic filter
 * - Click artist to see all their tracks
 * - Back button to return to artist list
 */
const ArtistBrowser = ({ onTrackSelected }) => {
  const [artists, setArtists] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterText, setFilterText] = useState("");
  const [selectedArtist, setSelectedArtist] = useState(null);
  const [artistTracks, setArtistTracks] = useState([]);
  const [loadingTracks, setLoadingTracks] = useState(false);

  // Load artists on mount
  useEffect(() => {
    const loadArtists = async () => {
      setLoading(true);
      try {
        const artistList = await getCollectionArtists();
        setArtists(artistList);
      } catch (error) {
        console.error("Failed to load artists:", error);
        setArtists([]);
      } finally {
        setLoading(false);
      }
    };
    loadArtists();
  }, []);

  // Filter artists based on search input
  const filteredArtists = useMemo(() => {
    if (!filterText) return artists;
    const lower = filterText.toLowerCase();
    return artists.filter((artist) => artist.toLowerCase().includes(lower));
  }, [artists, filterText]);

  // Load tracks when artist is selected
  const selectArtist = async (artistName) => {
    setSelectedArtist(artistName);
    setLoadingTracks(true);
    try {
      const tracks = await getCollectionArtistTracks(artistName);
      setArtistTracks(tracks);
    } catch (error) {
      console.error("Failed to load artist tracks:", error);
      setArtistTracks([]);
    } finally {
      setLoadingTracks(false);
    }
  };

  const goBack = () => {
    setSelectedArtist(null);
    setArtistTracks([]);
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-32">
        <BounceLoader size={44} color="#FFFFFF" />
      </div>
    );
  }

  // Artist track list view
  if (selectedArtist) {
    return (
      <div className="w-full">
        <div className="flex items-center mb-4 px-4">
          <IconButton onClick={goBack} sx={{ color: "white" }}>
            <ArrowBackIcon />
          </IconButton>
          <h2 className="text-white text-xl ml-2">{selectedArtist}</h2>
          <span className="text-gray-400 ml-2">
            ({artistTracks.length} tracks)
          </span>
        </div>

        {loadingTracks ? (
          <div className="flex justify-center items-center h-32">
            <BounceLoader size={44} color="#FFFFFF" />
          </div>
        ) : artistTracks.length > 0 ? (
          <div className="w-full">
            {artistTracks.map((track, index) => (
              <SearchResultItem
                key={track.uri || index}
                track={{
                  uri: track.uri,
                  name: track.name,
                  artists: [{ name: track.artist }],
                  album: { name: track.album },
                }}
                onClick={() => onTrackSelected(track)}
              />
            ))}
          </div>
        ) : (
          <div className="text-white text-center mt-8">
            No tracks found for {selectedArtist}
          </div>
        )}
      </div>
    );
  }

  // Artist list view
  return (
    <div className="w-full max-w-4xl mx-auto px-2">
      {/* Filter input */}
      <TextField
        fullWidth
        variant="outlined"
        placeholder="Filter artists..."
        value={filterText}
        onChange={(e) => setFilterText(e.target.value)}
        size="small"
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

      {/* Artist count */}
      <div className="text-gray-400 text-sm mt-2 mb-2">
        {filteredArtists.length} artist{filteredArtists.length !== 1 ? "s" : ""}
        {filterText && ` matching "${filterText}"`}
      </div>

      {/* Artist list */}
      <List
        sx={{
          bgcolor: "transparent",
          maxHeight: "60vh",
          overflow: "auto",
        }}
      >
        {filteredArtists.map((artist, index) => (
          <React.Fragment key={artist}>
            <ListItemButton
              onClick={() => selectArtist(artist)}
              sx={{
                color: "white",
                "&:hover": {
                  backgroundColor: "rgba(255,255,255,0.1)",
                },
              }}
            >
              <ListItemText primary={artist} />
            </ListItemButton>
            {index < filteredArtists.length - 1 && (
              <Divider sx={{ bgcolor: "rgba(255,255,255,0.1)" }} />
            )}
          </React.Fragment>
        ))}
      </List>

      {filteredArtists.length === 0 && (
        <div className="text-white text-center mt-8">
          {artists.length === 0
            ? "No artists in your collection"
            : `No artists matching "${filterText}"`}
        </div>
      )}
    </div>
  );
};

export default ArtistBrowser;

import React, { useState, useEffect } from "react";
import { useLocation } from "wouter";
import { endSession, rebootSystem, updateSessionPlaylists } from "services/mopidy";
import {
  Button, IconButton, Collapse, CircularProgress,
  TextField, Typography, List, ListItem, ListItemText, ListItemSecondaryAction,
} from "@mui/material";
import EditIcon from "@mui/icons-material/Edit";
import CloseIcon from "@mui/icons-material/Close";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";
import { useSessionDetails } from "hooks/session";
import { usePlaylists, usePlaylistSearch } from "hooks/playlists";
import { useAdmin } from "hooks/admin";
import { useConfig } from "hooks/config";
import PlaylistSelector from "components/common/PlaylistSelector";

// Logo loaded dynamically from branding endpoint
const LOGO_URL = "/pibox/branding/logo.png";

const SessionPage = () => {
  const {
    session: {
      playlists,
      playlistNames,
      skipThreshold,
      startedAt,
      playedTracks,
      remainingPlaylistTracks,
    },
    refetchSession,
  } = useSessionDetails();

  const { playlists: availablePlaylists, playlistsLoading, refetchPlaylists } = usePlaylists();
  const { clearAdmin } = useAdmin();
  const { config } = useConfig();
  const offline = config?.offline ?? false;
  const siteTitle = config?.siteTitle ?? "pibox";

  const [isEditingPlaylists, setIsEditingPlaylists] = useState(false);
  const [, setLocation] = useLocation();
  const [selectedPlaylists, setSelectedPlaylists] = useState(playlists || []);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  // Tidal playlist search state (for the editor panel)
  const [searchQuery, setSearchQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const { searchResults, searchLoading } = usePlaylistSearch(submittedQuery, searchOpen);

  const handleSearchSubmit = () => {
    const normalised = searchQuery.trim().replace(/[\s+]+/g, " ").trim();
    if (!normalised) return;
    setSubmittedQuery(normalised);
    setSearchOpen(true);
  };

  const handleAddSearchResult = (playlist) => {
    if (!selectedPlaylists.some((p) => p.uri === playlist.uri)) {
      setSelectedPlaylists([...selectedPlaylists, playlist]);
    }
  };

  // Sync selectedPlaylists when session playlists change
  useEffect(() => {
    if (playlists) {
      setSelectedPlaylists(playlists);
    }
  }, [playlists]);

  const handleSavePlaylists = async () => {
    if (selectedPlaylists.length === 0) {
      setSaveError("At least one playlist must be selected");
      return;
    }

    setIsSaving(true);
    setSaveError(null);

    try {
      await updateSessionPlaylists(selectedPlaylists);
      setIsEditingPlaylists(false);
      refetchSession();
    } catch (e) {
      setSaveError(e.message || "Failed to update playlists");
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancelEdit = () => {
    setSelectedPlaylists(playlists || []);
    setIsEditingPlaylists(false);
    setSaveError(null);
    setSearchQuery("");
    setSubmittedQuery("");
    setSearchOpen(false);
  };

  return (
    <div className="w-full h-full flex flex-col justify-between items-stretch p-2 overflow-y-auto">
      <div className="text-center">
        <h2 className="font-bold text-xl">{siteTitle}</h2>
        <img className="w-[70px] h-auto mx-auto my-2" alt="logo" src={LOGO_URL} />
      </div>
      <div>
        <div className="flex justify-between items-start w-full p-2 min-h-16 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <p className="font-bold text-gray-400">Selected Playlists:</p>
            {!offline && !isEditingPlaylists && (
              <IconButton
                size="small"
                onClick={() => {
                  setIsEditingPlaylists(true);
                  refetchPlaylists();
                }}
                title="Edit playlists"
              >
                <EditIcon fontSize="small" />
              </IconButton>
            )}
          </div>
          <div className="flex flex-col justify-end">
            {offline ? (
              <p className="text-right leading-tight">Local library</p>
            ) : (
              playlistNames.map((name) => (
                <p key={name} className="text-right leading-tight">
                  {name}
                </p>
              ))
            )}
            <span className="text-gray-400 text-right">
              ({remainingPlaylistTracks.length} tracks remaining)
            </span>
          </div>
        </div>

        {/* Playlist Editor */}
        <Collapse in={isEditingPlaylists && !offline}>
          <div className="p-3 bg-gray-50 border-b border-gray-200">
            <div className="flex justify-between items-center mb-2">
              <p className="font-semibold text-sm">Modify Playlists</p>
              <IconButton size="small" onClick={handleCancelEdit}>
                <CloseIcon fontSize="small" />
              </IconButton>
            </div>
            
            {playlistsLoading ? (
              <div className="flex justify-center py-4">
                <CircularProgress size={24} />
              </div>
            ) : (
              <>
                <PlaylistSelector
                  availablePlaylists={availablePlaylists || []}
                  selectedPlaylists={selectedPlaylists}
                  onChange={setSelectedPlaylists}
                  label="Select Playlists"
                  disabled={isSaving}
                />

                {/* Tidal playlist search */}
                {!offline && (
                  <div className="mt-3">
                    <div className="flex gap-2 items-center">
                      <TextField
                        fullWidth
                        size="small"
                        label="Search Tidal for playlists"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleSearchSubmit(); } }}
                        disabled={isSaving}
                        InputProps={{
                          endAdornment: searchLoading ? <CircularProgress size={18} /> : null,
                        }}
                      />
                      <IconButton
                        onClick={handleSearchSubmit}
                        disabled={!searchQuery.trim() || searchLoading || isSaving}
                        color="primary"
                        size="small"
                      >
                        <SearchIcon />
                      </IconButton>
                    </div>

                    <Collapse in={searchOpen && submittedQuery.length > 0}>
                      {searchResults.length === 0 && !searchLoading ? (
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 1, ml: 0.5 }}>
                          No playlists found for &ldquo;{submittedQuery}&rdquo;
                        </Typography>
                      ) : (
                        <List dense sx={{ maxHeight: 160, overflowY: "auto", mt: 0.5 }}>
                          {searchResults.map((playlist) => {
                            const alreadyAdded = selectedPlaylists.some((p) => p.uri === playlist.uri);
                            return (
                              <ListItem key={playlist.uri} disablePadding sx={{ pl: 0.5 }}>
                                <ListItemText
                                  primary={playlist.name}
                                  primaryTypographyProps={{ variant: "body2" }}
                                />
                                <ListItemSecondaryAction>
                                  <IconButton
                                    edge="end"
                                    size="small"
                                    disabled={alreadyAdded || isSaving}
                                    onClick={() => handleAddSearchResult(playlist)}
                                    color={alreadyAdded ? "default" : "primary"}
                                  >
                                    <AddIcon fontSize="small" />
                                  </IconButton>
                                </ListItemSecondaryAction>
                              </ListItem>
                            );
                          })}
                        </List>
                      )}
                    </Collapse>
                  </div>
                )}

                {saveError && (
                  <p className="text-red-500 text-sm mt-2">{saveError}</p>
                )}

                <div className="flex gap-2 mt-3 justify-end">
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={handleCancelEdit}
                    disabled={isSaving}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="contained"
                    size="small"
                    onClick={handleSavePlaylists}
                    disabled={isSaving || selectedPlaylists.length === 0}
                  >
                    {isSaving ? <CircularProgress size={16} /> : "Save"}
                  </Button>
                </div>
              </>
            )}
          </div>
        </Collapse>

        <SessionStatistic
          label="Tracks Played"
          value={<p className="text-right">{playedTracks.length}</p>}
        />
        <SessionStatistic
          label="Started"
          value={<p className="text-right">{startedAt.fromNow()}</p>}
        />
        <SessionStatistic
          label="Skip Threshold"
          value={<p className="text-right">{skipThreshold}</p>}
        />
        {config?.queueLimitPerUser > 0 && (
          <SessionStatistic
            label="Queue Limit (per user)"
            value={<p className="text-right">{config.queueLimitPerUser} track{config.queueLimitPerUser !== 1 ? "s" : ""}</p>}
          />
        )}
        {config?.voteLimitCount > 0 && config?.voteLimitMinutes > 0 && (
          <SessionStatistic
            label="Vote Rate Limit"
            value={
              <p className="text-right">
                {config.voteLimitCount} vote{config.voteLimitCount !== 1 ? "s" : ""} per {config.voteLimitMinutes} min
              </p>
            }
          />
        )}
      </div>
      <div className="flex flex-col gap-4 my-10 mx-0 self-center items-center">
        <Button
          variant="outlined"
          startIcon={<ArrowBackIcon />}
          onClick={() => {
            clearAdmin();
            setLocation("/");
          }}
        >
          Back to Player
        </Button>
        
        <div className="flex gap-4">
          {config?.rebootCommand && (
            <Button
              variant="contained"
              color="warning"
              onClick={async () => {
                if (!window.confirm("Reboot system now?")) return;
                try {
                  await rebootSystem();
                  alert("Reboot command started");
                } catch (e) {
                  alert(`Failed to start reboot: ${e.message || e}`);
                }
              }}
            >
              Reboot System
            </Button>
          )}

          <Button
            className="mx-0"
            variant="contained"
            color="error"
            onClick={endSession}
          >
            End Session
          </Button>
        </div>
      </div>
    </div>
  );
};

function SessionStatistic({ label, value }) {
  return (
    <div className="flex justify-between items-center w-full p-2 min-h-16 border-b border-gray-200">
      <p className="font-bold text-gray-400">{label}:</p>
      {value}
    </div>
  );
}

export default SessionPage;

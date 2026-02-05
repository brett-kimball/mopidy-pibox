import React, { useState, useEffect } from "react";
import { useLocation } from "wouter";
import { endSession, rebootSystem, updateSessionPlaylists } from "services/mopidy";
import { Button, IconButton, Collapse, CircularProgress } from "@mui/material";
import EditIcon from "@mui/icons-material/Edit";
import CloseIcon from "@mui/icons-material/Close";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { useSessionDetails } from "hooks/session";
import { usePlaylists } from "hooks/playlists";
import { useAdmin } from "hooks/admin";
import logo from "res/logo.png";
import { useConfig } from "hooks/config";
import PlaylistSelector from "components/common/PlaylistSelector";

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

  const { playlists: availablePlaylists, playlistsLoading } = usePlaylists();
  const { clearAdmin } = useAdmin();
  const { config } = useConfig();
  const offline = config?.offline ?? false;
  const siteTitle = config?.siteTitle ?? "pibox";

  const [isEditingPlaylists, setIsEditingPlaylists] = useState(false);
  const [, setLocation] = useLocation();
  const [selectedPlaylists, setSelectedPlaylists] = useState(playlists || []);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

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
  };

  return (
    <div className="w-full h-full flex flex-col justify-between items-stretch p-2 overflow-y-auto">
      <div className="text-center">
        <h2 className="font-bold text-xl">{siteTitle}</h2>
        <img className="w-[70px] h-auto mx-auto my-2" alt="logo" src={logo} />
      </div>
      <div>
        <div className="flex justify-between items-start w-full p-2 min-h-16 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <p className="font-bold text-gray-400">Selected Playlists:</p>
            {!offline && !isEditingPlaylists && (
              <IconButton
                size="small"
                onClick={() => setIsEditingPlaylists(true)}
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

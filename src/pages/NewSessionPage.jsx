import React, { useState } from "react";
import {
  TextField,
  Button,
  Checkbox,
  FormControlLabel,
  CircularProgress,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Typography,
  Collapse,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";
import { useConfig } from "hooks/config";
import { usePlaylists, usePlaylistSearch } from "hooks/playlists";
import { LoadingScreen } from "components/common/LoadingScreen";
import PlaylistSelector from "components/common/PlaylistSelector";

const NewSessionPage = ({ onStartSessionClick }) => {
  const {
    config: { defaultPlaylists, defaultSkipThreshold, offline, siteTitle },
  } = useConfig();
  const { playlists, playlistsLoading } = usePlaylists();

  if (offline) {
    return (
      <OfflineSessionForm
        initialSkipThreshold={defaultSkipThreshold}
        onSubmit={onStartSessionClick}
        siteTitle={siteTitle}
      />
    );
  }

  if (playlistsLoading) {
    return <LoadingScreen />;
  }

  const initialPlaylists = playlists.filter((p) =>
    defaultPlaylists.includes(p.uri),
  );

  return (
    <NewSessionForm
      initialSkipThreshold={defaultSkipThreshold}
      initialPlaylists={initialPlaylists}
      availablePlaylists={playlists}
      onSubmit={onStartSessionClick}
      siteTitle={siteTitle}
    />
  );
};

function OfflineSessionForm({ onSubmit, initialSkipThreshold, siteTitle }) {
  const [votesToSkip, setVotesToSkip] = useState(`${initialSkipThreshold}`);
  const [automaticallyStartPlaying, setAutomaticallyStartPlaying] =
    useState(true);
  const [enableShuffle, setEnableShuffle] = useState(true);

  const handleSubmit = (event) => {
    event.preventDefault();
    onSubmit({
      votesToSkip,
      automaticallyStartPlaying,
      enableShuffle,
    });
  };

  return (
    <form
      className="flex flex-col items-center justify-evenly mx-auto h-4/5 w-4/5"
      onSubmit={handleSubmit}
    >
      <h2 className="font-bold text-xl">{siteTitle ?? "pibox"}</h2>

      <TextField
        fullWidth
        label="Number of votes to skip"
        type="number"
        value={votesToSkip}
        onChange={(event) => setVotesToSkip(event.target.value)}
        placeholder="3"
      />

      <FormControlLabel
        control={
          <Checkbox
            name="enableShuffle"
            checked={enableShuffle}
            color="secondary"
            onChange={(event) => setEnableShuffle(event.target.checked)}
          />
        }
        label="Shuffle songs in the playlist"
      />

      <FormControlLabel
        control={
          <Checkbox
            name="automaticallyStartPlaying"
            checked={automaticallyStartPlaying}
            color="secondary"
            onChange={(event) =>
              setAutomaticallyStartPlaying(event.target.checked)
            }
          />
        }
        label="Automatically start playing music when session starts"
      />

      <Button
        type="submit"
        variant="contained"
        disabled={!votesToSkip}
        color="primary"
      >
        Start
      </Button>
    </form>
  );
}

function NewSessionForm({
  onSubmit,
  initialSkipThreshold,
  initialPlaylists,
  availablePlaylists,
  siteTitle,
}) {
  const [votesToSkip, setVotesToSkip] = useState(`${initialSkipThreshold}`);
  const [automaticallyStartPlaying, setAutomaticallyStartPlaying] =
    useState(true);
  const [enableShuffle, setEnableShuffle] = useState(true);
  const [selectedPlaylists, setSelectedPlaylists] = useState(initialPlaylists);

  // Tidal playlist search state
  const [searchQuery, setSearchQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const { searchResults, searchLoading } = usePlaylistSearch(submittedQuery, searchOpen);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setSubmittedQuery(searchQuery);
    setSearchOpen(true);
  };

  const handleAddSearchResult = (playlist) => {
    if (!selectedPlaylists.some((p) => p.uri === playlist.uri)) {
      setSelectedPlaylists([...selectedPlaylists, playlist]);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    onSubmit({
      selectedPlaylists,
      votesToSkip,
      automaticallyStartPlaying,
      enableShuffle,
    });
  };

  return (
    <form
      className="flex flex-col items-center justify-evenly mx-auto h-4/5 w-4/5"
      onSubmit={handleSubmit}
    >
      <h2 className="font-bold text-xl">{siteTitle ?? "pibox"}</h2>

      <TextField
        fullWidth
        label="Number of votes to skip"
        type="number"
        value={votesToSkip}
        onChange={(event) => setVotesToSkip(event.target.value)}
        placeholder="3"
      />

      <PlaylistSelector
        availablePlaylists={availablePlaylists}
        selectedPlaylists={selectedPlaylists}
        onChange={setSelectedPlaylists}
        label="Playlists"
      />

      {/* Tidal playlist search */}
      <div className="w-full">
        <div className="flex gap-2 items-center">
          <TextField
            fullWidth
            size="small"
            label="Search Tidal for playlists"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); setSubmittedQuery(searchQuery); setSearchOpen(true); } }}
            InputProps={{
              endAdornment: searchLoading ? <CircularProgress size={18} /> : null,
            }}
          />
          <IconButton
            onClick={handleSearchSubmit}
            disabled={!searchQuery.trim() || searchLoading}
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
            <List dense sx={{ maxHeight: 200, overflowY: "auto", mt: 0.5 }}>
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
                        disabled={alreadyAdded}
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

      <FormControlLabel
        control={
          <Checkbox
            name="enableShuffle"
            checked={enableShuffle}
            color="secondary"
            onChange={(event) => setEnableShuffle(event.target.checked)}
          />
        }
        label="Shuffle songs in the playlist"
      />

      <FormControlLabel
        control={
          <Checkbox
            name="automaticallyStartPlaying"
            checked={automaticallyStartPlaying}
            color="secondary"
            onChange={(event) =>
              setAutomaticallyStartPlaying(event.target.checked)
            }
          />
        }
        label="Automatically start playing music when session starts"
      />

      <Button
        type="submit"
        variant="contained"
        disabled={!votesToSkip}
        color="primary"
      >
        Start
      </Button>
    </form>
  );
}

export default NewSessionPage;

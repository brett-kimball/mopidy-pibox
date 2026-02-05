import React, { useState } from "react";
import {
  TextField,
  Button,
  Checkbox,
  FormControlLabel,
} from "@mui/material";
import { useConfig } from "hooks/config";
import { usePlaylists } from "hooks/playlists";
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
        disabled={!votesToSkip || !selectedPlaylists.length}
        color="primary"
      >
        Start
      </Button>
    </form>
  );
}

export default NewSessionPage;

import React from "react";
import ArtistSentence from "components/common/ArtistSentence";
import SkipNextIcon from "@mui/icons-material/SkipNext";
import {
  Card,
  CardContent,
  CardActions,
  Typography,
  Button,
} from "@mui/material";

const TracklistItem = ({
  track,
  skipThreshold,
  buttonEnabled,
  onVoteClick,
  cooldownSeconds = 0,
}) => {
  const buttonIcon = track.voted ? null : <SkipNextIcon className="ml-1" />;
  const formatMmSs = (s) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    const mm = String(m).padStart(2, "0");
    const ss = String(sec).padStart(2, "0");
    return `${mm}:${ss}`;
  };

  return (
    <Card className="tracklist-item m-2 flex justify-between items-center">
      <CardContent className="p-4">
        <Typography type="subheading" component="h2">
          {track.info.name}
        </Typography>
        <Typography type="body2" component="h2">
          <ArtistSentence artists={track.info.artists} />
        </Typography>
      </CardContent>
      <CardActions className="flex grow-0 shrink-0">
        <Button
          disabled={!buttonEnabled || cooldownSeconds > 0}
          onClick={onVoteClick}
          color="secondary"
        >
          {track.voted ? (
            track.votes + "/" + skipThreshold + " votes"
          ) : cooldownSeconds > 0 ? (
            `Vote in ${formatMmSs(cooldownSeconds)}`
          ) : track.added_by_me ? (
            "DELETE"
          ) : (
            "Vote to skip"
          )}
          {buttonIcon}
        </Button>
      </CardActions>
    </Card>
  );
};

export default TracklistItem;

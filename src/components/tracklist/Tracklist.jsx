import React, { useState, useEffect, useRef } from "react";
import TracklistItem from "./TracklistItem.jsx";
import NothingPlaying from "components/playback/NothingPlaying.jsx";
import { voteToSkipTrack, removeQueuedTrack, PiboxError } from "services/mopidy";
import { Card } from "@mui/material";
import { useSessionDetails } from "hooks/session.js";
import { useTracklist } from "hooks/tracklist.js";

const Tracklist = ({ display, readOnly = false }) => {
  const { session } = useSessionDetails();
  const [votePending, setVotePending] = useState(false);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  const cooldownRef = useRef(null);

  useEffect(() => {
    if (cooldownSeconds > 0 && !cooldownRef.current) {
      cooldownRef.current = setInterval(() => {
        setCooldownSeconds((s) => {
          if (s <= 1) {
            clearInterval(cooldownRef.current);
            cooldownRef.current = null;
            return 0;
          }
          return s - 1;
        });
      }, 1000);
    }
    return () => {
      if (cooldownRef.current) {
        clearInterval(cooldownRef.current);
        cooldownRef.current = null;
      }
    };
  }, [cooldownSeconds]);

  const { tracklist, refetchTracklist } = useTracklist();
  const { retryAfterSeconds } = useTracklist();

  useEffect(() => {
    if (retryAfterSeconds && retryAfterSeconds > 0) {
      setCooldownSeconds(retryAfterSeconds);
    }
  }, [retryAfterSeconds]);

  if (!tracklist) {
    return null;
  }

  const generateSkipHandler = (track) => async () => {
    const trackUri = track.info.uri;
    const setTrackAsVoted = () => {
      refetchTracklist();
    };

    setVotePending(true);
    try {
      if (track.added_by_me) {
        await removeQueuedTrack(trackUri);
        try {
          if (typeof window !== "undefined" && window.localStorage) {
            window.localStorage.removeItem(`pibox_added_${trackUri}`);
          }
        } catch (e) {
          // ignore
        }
      } else {
        await voteToSkipTrack(trackUri);
      }
      setTrackAsVoted();
    } catch (e) {
      if (e instanceof PiboxError) {
        // If rate-limited, show cooldown timer; otherwise refresh to reflect vote state
        const retry = e.meta?.retryAfterSeconds;
        if (retry && retry > 0) {
          setCooldownSeconds(retry);
        } else {
          setTrackAsVoted();
        }
      }
    }
    setVotePending(false);
  };

  const queueLength = tracklist.length - 1;
  const tracksNotShown = queueLength - display;

  const skipThreshold = session?.skipThreshold ?? 0;

  const tracklistItems = tracklist
    .slice(1, 1 + display)
    .map((track) =>
      readOnly ? (
        <TracklistItem
          key={track.info.uri}
          track={{ ...track, voted: true }}
          skipThreshold={skipThreshold}
          buttonEnabled={true}
          cooldownSeconds={cooldownSeconds}
          onVoteClick={() => {}}
        />
      ) : (
          <TracklistItem
            key={track.info.uri}
            track={{ ...track, added_by_me: track.added_by_me || (typeof window !== "undefined" && !!window.localStorage.getItem(`pibox_added_${track.info.uri}`)) }}
            skipThreshold={skipThreshold}
            buttonEnabled={!(votePending || track.voted)}
            cooldownSeconds={cooldownSeconds}
            onVoteClick={generateSkipHandler(track)}
          />
        ),
    );

  return (
    <>
      {/**
       * When used on the `/view` page we render `Tracklist` with `readOnly=true`.
       * In that context the tracklist should fill the available column instead
       * of being constrained to 400px as it is on smaller screens. Use a
       * wider container when `readOnly` is true.
       */}
      <div className={readOnly ? "w-full mx-0 mb-7 mt-0" : "max-w-[400px] mx-auto mb-7 mt-0"}>
        {readOnly && queueLength <= 0 && (
          <div className="my-0 mx-2">
            <NothingPlaying viewOnly />
          </div>
        )}
        {queueLength > 0 && (
          <div className={`my-0 mx-2 font-normal text-sm text-gray-400 border-b border-gray-200 ${readOnly ? "view-queue-count" : ""}`}>
            {queueLength} song{queueLength !== 1 ? "s" : ""} queued
          </div>
        )}
        {tracklistItems}
        {tracksNotShown > 0 && (
          <Card className="m-2 text-center py-4">+ {tracksNotShown} more</Card>
        )}
      </div>
    </>
  );
};

export default Tracklist;

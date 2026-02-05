import React from "react";
import Thumbnail from "components/common/Thumbnail";
import ArtistSentence from "components/common/ArtistSentence";
import PlaybackControls from "./PlaybackControls";
import { togglePlaybackState, skipCurrentTrack } from "services/mopidy";
import NothingPlaying from "./NothingPlaying";
import { useAdmin } from "hooks/admin";
import { useSessionDetails } from "hooks/session";
import { useNowPlaying } from "hooks/nowPlaying";
import { useConfig } from "hooks/config";
import { useTextOverflow } from "hooks/useTextOverflow";

const NowPlaying = ({ viewOnly = false }) => {
  const { session, sessionLoading } = useSessionDetails();
  const { isAdmin } = useAdmin();
  const { config } = useConfig();
  const offline = config?.offline ?? false;
  // TV display (/view) uses 1280px artwork, mobile uses 640px
  const artworkSize = viewOnly ? 1280 : 640;
  const { currentTrack, playbackState, artworkUrl } = useNowPlaying({ artworkSize });
  
  // For TV display, detect if track title overflows to enable ticker animation
  const { ref: titleRef, isOverflowing } = useTextOverflow(currentTrack?.name);


  if (!currentTrack) return <NothingPlaying viewOnly={viewOnly} showInstructions={false} showQr={false} />;

  // Get the source for the current track
  const trackSource = session?.trackSources?.[currentTrack.uri];

  return (
    <div className="px-2">
      {!sessionLoading && session && (
        <PlayingFrom 
          offline={offline} 
          playlistNames={session.playlistNames}
          trackSource={trackSource}
          viewOnly={viewOnly}
        />
      )}
      <div className="flex flex-col items-center justify-evenly">
        <div className="flex flex-col items-center justify-end relative">
          <Thumbnail url={artworkUrl} />
          {isAdmin && (
            <PlaybackControls
              playbackState={playbackState}
              onPlayPauseClick={togglePlaybackState}
              onSkipClick={skipCurrentTrack}
            />
          )}
          
        </div>
        <div className="pt-7 basis-auto text-center m-2 max-w-full">
          {viewOnly ? (
            <div 
              className="overflow-hidden"
              style={{ 
                maxWidth: '60vw', 
                margin: '0 auto',
                ...(isOverflowing && {
                  maskImage: 'linear-gradient(to right, transparent, black 8%, black 92%, transparent)',
                  WebkitMaskImage: 'linear-gradient(to right, transparent, black 8%, black 92%, transparent)',
                }),
              }}
            >
              <h2 
                ref={titleRef}
                className="text-xl font-bold py-1 whitespace-nowrap"
                style={isOverflowing ? { 
                  animation: 'ticker 15s linear infinite',
                  display: 'inline-block',
                  paddingLeft: '100%',
                  willChange: 'transform',
                  backfaceVisibility: 'hidden',
                } : {
                  textAlign: 'center',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  display: 'block',
                }}
              >
                {currentTrack.name}
              </h2>
            </div>
          ) : (
            <h2 className="text-xl font-bold py-1">{currentTrack.name}</h2>
          )}
          <h3 
            className="text-base font-medium text-gray-400 py-1"
            style={viewOnly ? {
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              maxWidth: '60vw',
              margin: '0 auto',
            } : {}}
          >
            <ArtistSentence artists={currentTrack.artists} />
          </h3>
          <h3 
            className="text-base font-medium text-gray-400 py-1"
            style={viewOnly ? {
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              maxWidth: '60vw',
              margin: '0 auto',
            } : {
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {currentTrack.album?.name ?? "Unknown Album"}
          </h3>
        </div>
      </div>
    </div>
  );
};

function PlayingFrom({ offline, playlistNames, trackSource, viewOnly }) {
  return (
    <h3 
      className="text-sm font-normal text-gray-400 text-center py-1 pb-4"
      style={viewOnly ? {
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        maxWidth: '60vw',
        margin: '0 auto',
      } : {}}
    >
      {getPlayingFromText(offline, playlistNames, trackSource)}
    </h3>
  );
}

function getPlayingFromText(offline, playlistNames, trackSource) {
  if (offline) return "Playing from local library";

  // If we have specific track source info, use it
  if (trackSource) {
    if (trackSource.type === "user") {
      return `Queued by: ${trackSource.name}`;
    } else if (trackSource.type === "playlist") {
      return `Playing from: ${trackSource.name}`;
    }
  }

  // Fallback to original behavior
  return playlistNames.length === 1
    ? `Playing from: ${playlistNames[0]}`
    : `Playing from ${playlistNames.length} playlist${playlistNames.length > 1 ? "s" : ""}`;
}

export default NowPlaying;

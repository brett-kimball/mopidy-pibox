import React from "react";
import NowPlaying from "components/playback/NowPlaying";
import Tracklist from "components/tracklist/Tracklist";
import ProgressBar from "components/playback/ProgressBar";

const ViewPage = () => {
  return (
    <div
      className="view-page root-fullscreen"
      style={{ position: "relative" }}
    >
      <div className="view-content" style={{ position: "relative", zIndex: 1 }}>
        <div className="view-nowplaying">
            <NowPlaying viewOnly />
          </div>
        <div className="view-tracklist">
          <Tracklist display={6} readOnly />
        </div>
      </div>
      <ProgressBar />
    </div>
  );
};

export default ViewPage;

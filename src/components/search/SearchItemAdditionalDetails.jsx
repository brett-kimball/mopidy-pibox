import React from "react";
import ArtistSentence from "components/common/ArtistSentence";

export function SearchItemAdditionalDetails({ track }) {
  return (
    <span>
      <strong>Artist:</strong>&nbsp;<ArtistSentence artists={track.artists} />,
      &nbsp;Album: {track.album?.name ?? "Unknown Album"}
    </span>
  );
}

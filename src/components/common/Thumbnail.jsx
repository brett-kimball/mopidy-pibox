import React from "react";
import placeholder from "res/placeholder.png";

const Thumbnail = ({ url }) => {
  // Use placeholder if url is falsy or empty string
  const src = url && url.length > 0 ? url : placeholder;
  return (
    <img
      className="w-full h-auto max-w-56 min-w-40 rounded-xl"
      src={src}
      alt="Album artwork"
    />
  );
};

export default Thumbnail;

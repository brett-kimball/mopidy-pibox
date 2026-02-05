import React from "react";
import { BounceLoader } from "react-spinners";

export const LoadingScreen = ({ siteTitle = "pibox" }) => {
  let title = siteTitle;
  try {
    if ((!siteTitle || siteTitle === "pibox") && typeof document !== "undefined" && document.title) {
      title = document.title || siteTitle;
    }
  } catch (e) {
    // ignore
  }

  return (
    <div className="loading">
      <h1>{title}</h1>
      <BounceLoader size={44} color="#00796B" />
    </div>
  );
};

import React from "react";
import { useState } from "react";
import { useConfig } from "hooks/config";
import QRCode from "react-qr-code";

// Logo loaded dynamically from branding endpoint
const LOGO_BLACK_URL = "/pibox/branding/logo-black.png";

const NothingPlaying = ({ viewOnly = false, showInstructions = true, showQr = true }) => {
  const { config } = useConfig();
  const siteTitle = config?.siteTitle || "pibox";

  // For /view page (TV display)
  if (viewOnly) {
    // Show QR code (used in tracklist area)
    if (showQr) {
      const serverAddress = config?.serverAddress
        ? config.serverAddress
        : typeof window !== "undefined"
        ? `${window.location.protocol}//${window.location.hostname}${
            window.location.port ? ":" + window.location.port : ""
          }`
        : "http://127.0.0.1:6680";
      // If serverAddress is explicitly set, use it as-is (allows custom paths like http://m/)
      // Otherwise, append /pibox for direct mopidy access
      const targetUrl = config?.serverAddress ? serverAddress : `${serverAddress}/pibox`;
      const qrSize = 256;

      return (
        <div className="flex flex-col justify-center items-center text-center">
          <h2 className="text-xl font-bold mb-4">Scan to Add Music</h2>
          <div className="view-qr rounded-xl p-2 bg-white">
            <QRCode value={targetUrl} size={qrSize} />
          </div>
        </div>
      );
    }

    // Show welcome message with large logo (used in now playing area)
    return (
      <div className="flex flex-col justify-center items-center text-center">
        <h2 className="text-3xl font-bold mb-6">Welcome</h2>
        <img className="welcome-logo w-[256px] h-auto" alt="logo" src={LOGO_BLACK_URL} />
      </div>
    );
  }

  if (!showInstructions) {
    return null;
  }

  // Regular player page - show welcome with instructions
  return (
    <div className="flex flex-wrap justify-center flex-col items-center">
      <h2>Welcome to {siteTitle}!</h2>
      <img className="w-[70px] h-auto m-1" alt="logo" src={LOGO_BLACK_URL} />
      <ol className="list-decimal" type="1">
        <li className="p-1">Tap the search icon at the top right</li>
        <li className="p-1">Search for an artist, song or album</li>
        <li className="p-1">Tap on the song you want to queue</li>
        <Step4 className="p-1" />
      </ol>
    </div>
  );
};

const Step4 = ({ className }) => {
  const options = [
    "Enjoy! 🎵",
    "Have a wee boogie! 💃",
    "Have a wee boogie! 🕺",
    "Sing your heart out! 🎤",
    "Just bust a move! 😎",
    "Dance like nobody's watching! 🙈",
    "Turn it up to 11! 🎸",
  ];

  const [option] = useState(
    () => options[(options.length * Math.random()) | 0],
  );

  return <li className={className}>{option}</li>;
};

export default NothingPlaying;

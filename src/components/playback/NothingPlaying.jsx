import React from "react";
import logo from "res/logo-black.png";
import { useState } from "react";
import { useConfig } from "hooks/config";
import QRCode from "react-qr-code";

const NothingPlaying = ({ viewOnly = false, showInstructions = true, showQr = true }) => {
  if (viewOnly) {
    if (!showQr) {
      return null;
    }
    const { config } = useConfig();
    // Prefer serverAddress returned by the backend config API. Fall back to
    // window.location if not available.
    const serverAddress = config?.serverAddress
      ? config.serverAddress
      : typeof window !== "undefined"
      ? `${window.location.protocol}//${window.location.hostname}${
          window.location.port ? ":" + window.location.port : ""
        }`
      : "http://127.0.0.1:6680";
    const targetUrl = `${serverAddress}/pibox`;
    const qrSize = 256;

    return (
      <div className="flex flex-col justify-center items-center text-center">
        {showInstructions && (
          <>
            <h2 className="text-xl font-bold mb-2">Add Music to the Playlist</h2>
            <p className="text-gray-400 mb-4">Scan the QR Code to Open the App</p>
          </>
        )}
        <div className="view-qr rounded-xl p-2 bg-white">
          <QRCode value={targetUrl} size={qrSize} />
        </div>
        {showInstructions && (
          <p className="text-sm text-gray-400 mt-2">
            Or open: <a className="underline" href={targetUrl}>{targetUrl}</a>
          </p>
        )}
      </div>
    );
  }

  if (!showInstructions) {
    return null;
  }

  return (
    <div className="flex flex-wrap justify-center flex-col items-center">
      <h2>Welcome to pibox!</h2>
      <img className="w-[70px] h-auto m-1" alt="logo" src={logo} />
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

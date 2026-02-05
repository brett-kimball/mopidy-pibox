import React, { useEffect, useRef, useState } from "react";
import { getTimePosition } from "services/mopidy";
import { useNowPlaying } from "hooks/nowPlaying";
import burgee from "res/burgee_306.png";

function msToTime(ms) {
  if (ms == null || isNaN(ms)) return "0:00";
  const s = Math.floor(ms / 1000);
  const hh = Math.floor(s / 3600);
  const mm = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  if (hh > 0) return `${hh}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
  return `${mm}:${String(ss).padStart(2, "0")}`;
}

const ProgressBar = ({ pollInterval = 500 }) => {
  const { currentTrack, playbackState } = useNowPlaying();
  const [position, setPosition] = useState(0);
  const rafRef = useRef(null);
  const lastTsRef = useRef(Date.now());
  const containerRef = useRef(null);
  const burgeeRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [burgeeWidth, setBurgeeWidth] = useState(0);

  // polling function to fetch authoritative position from Mopidy
  const pollPosition = async () => {
    try {
      const pos = await getTimePosition();
      if (typeof pos === "number") {
        setPosition(pos);
        lastTsRef.current = Date.now();
      }
    } catch (e) {
      // ignore
    }
  };

  // rAF updater for smooth animation when playing
  const startRaf = () => {
    if (rafRef.current) return;
    const tick = () => {
      if (playbackState === "playing") {
        const now = Date.now();
        const delta = now - lastTsRef.current;
        setPosition((p) => p + delta);
        lastTsRef.current = now;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  };

  const stopRaf = () => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  };

  useEffect(() => {
    let interval = null;
    // whenever the track changes, resync
    pollPosition();
    interval = setInterval(pollPosition, pollInterval);

    const measure = () => {
      if (containerRef.current) setContainerWidth(containerRef.current.clientWidth || 0);
      if (burgeeRef.current) setBurgeeWidth(burgeeRef.current.clientWidth || 0);
    };
    measure();
    window.addEventListener("resize", measure);

    return () => {
      if (interval) clearInterval(interval);
      window.removeEventListener("resize", measure);
    };
  }, [currentTrack && currentTrack.uri]);

  useEffect(() => {
    if (playbackState === "playing") {
      lastTsRef.current = Date.now();
      startRaf();
    } else {
      stopRaf();
    }
    return () => stopRaf();
  }, [playbackState]);

  const duration = currentTrack?.length || 0;
  const pct = duration > 0 ? Math.max(0, Math.min(100, (position / duration) * 100)) : 0;

  // compute left position for burgee within container
  const leftPx = (() => {
    if (!containerWidth || !burgeeWidth) return 0;
    const x = (pct / 100) * containerWidth - burgeeWidth / 2;
    return Math.max(0, Math.min(containerWidth - burgeeWidth, x));
  })();

  return (
    <div
      ref={containerRef}
      className="view-progress fixed left-0 bottom-0 w-full z-50 pointer-events-none"
      aria-hidden
    >
      <div className="mx-auto relative w-full" style={{ height: Math.max(36, burgeeWidth ? Math.round(burgeeWidth * 0.4) : 56) }}>
        <div className="absolute left-0 right-0 bottom-4 px-4">
          <div className="relative h-2 w-full bg-white/10 rounded overflow-hidden">
            <div
              className="absolute left-0 top-0 h-full bg-white/80"
              style={{ width: `${pct}%`, transition: "width 120ms linear" }}
            />
          </div>
        </div>

        <img
          ref={burgeeRef}
          src={burgee}
          alt="burgee"
          className="progress-burgee absolute bottom-6"
          style={{ left: leftPx, transition: playbackState === "playing" ? "left 120ms linear" : "left 200ms ease" }}
        />

        <div className="absolute left-6 right-6 bottom-10 flex justify-between text-sm text-white/90">
          <div>{msToTime(position)}</div>
          <div>-{msToTime(Math.max(0, duration - position))}</div>
        </div>
      </div>
    </div>
  );
};

export default ProgressBar;

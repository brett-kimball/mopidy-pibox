import React, { useState, useRef, useCallback, useEffect } from "react";
import CloseIcon from "@mui/icons-material/Close";
import { IconButton } from "@mui/material";
import { useVolume } from "hooks/volume";

// ── Knob geometry ─────────────────────────────────────────────────────────────
const SIZE = 260;
const STROKE = 18;
const R = (SIZE - STROKE) / 2; // 121
const CX = SIZE / 2;            // 130
const CY = SIZE / 2;            // 130

// The knob sweep runs clockwise from the lower-left (≈ 8 o'clock)
// to the lower-right (≈ 4 o'clock), leaving a gap at the bottom.
const START_ANGLE = -225; // degrees in SVG/math coords (0° = 3 o'clock)
const END_ANGLE = 45;
const SWEEP = END_ANGLE - START_ANGLE; // 270°

function toRad(deg) {
  return (deg * Math.PI) / 180;
}

function polarXY(angleDeg) {
  return {
    x: CX + R * Math.cos(toRad(angleDeg)),
    y: CY + R * Math.sin(toRad(angleDeg)),
  };
}

function arcPath(startDeg, endDeg) {
  const s = polarXY(startDeg);
  const e = polarXY(endDeg);
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${R} ${R} 0 ${large} 1 ${e.x.toFixed(2)} ${e.y.toFixed(2)}`;
}

// ── Component ─────────────────────────────────────────────────────────────────
export const VolumeKnob = ({ onClose }) => {
  const { volume: serverVolume, setVolume, flushVolume } = useVolume();

  // Local display volume — follows serverVolume when not dragging
  const [localVolume, setLocalVolume] = useState(serverVolume);
  const localVolumeRef = useRef(localVolume);

  const isDragging = useRef(false);
  const dragState = useRef(null); // { lastAngle, accumVol }
  const svgRef = useRef(null);

  // Sync with server when idle
  useEffect(() => {
    if (!isDragging.current) {
      setLocalVolume(serverVolume);
      localVolumeRef.current = serverVolume;
    }
  }, [serverVolume]);

  // ── Geometry helpers ────────────────────────────────────────────────────────
  const valueAngle = START_ANGLE + (localVolume / 100) * SWEEP;
  const trackPath = arcPath(START_ANGLE, END_ANGLE);
  const valuePath = localVolume > 0 ? arcPath(START_ANGLE, valueAngle) : null;

  // ── Pointer event helpers ───────────────────────────────────────────────────
  const getAngle = useCallback((e) => {
    const svg = svgRef.current;
    if (!svg) return 0;
    const rect = svg.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const clientX = e.clientX ?? e.touches?.[0]?.clientX ?? cx;
    const clientY = e.clientY ?? e.touches?.[0]?.clientY ?? cy;
    return Math.atan2(clientY - cy, clientX - cx) * (180 / Math.PI);
  }, []);

  const applyDelta = useCallback(
    (currentAngle) => {
      if (!dragState.current) return;
      let delta = currentAngle - dragState.current.lastAngle;
      // Normalise wrap-around — consecutive events are always < 180° apart
      if (delta > 180) delta -= 360;
      if (delta < -180) delta += 360;
      const deltaVol = (delta / SWEEP) * 100;
      // Accumulate as float to avoid rounding drift across many small moves
      const newAccum = Math.max(
        0,
        Math.min(100, dragState.current.accumVol + deltaVol),
      );
      const newVol = Math.round(newAccum);
      dragState.current.lastAngle = currentAngle;
      dragState.current.accumVol = newAccum;
      setLocalVolume(newVol);
      localVolumeRef.current = newVol;
      setVolume(newVol); // throttled
    },
    [setVolume],
  );

  // ── Pointer handlers ────────────────────────────────────────────────────────
  const handlePointerDown = useCallback(
    (e) => {
      e.preventDefault();
      e.currentTarget.setPointerCapture(e.pointerId);
      isDragging.current = true;
      dragState.current = {
        lastAngle: getAngle(e),
        accumVol: localVolumeRef.current,
      };
    },
    [getAngle],
  );

  const handlePointerMove = useCallback(
    (e) => {
      if (!isDragging.current) return;
      applyDelta(getAngle(e));
    },
    [applyDelta, getAngle],
  );

  const handlePointerUp = useCallback(
    (e) => {
      if (!isDragging.current) return;
      isDragging.current = false;
      dragState.current = null;
      flushVolume(localVolumeRef.current); // send final value immediately
    },
    [flushVolume],
  );

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    // Backdrop — click outside to close
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm"
      onClick={onClose}
    >
      {/* Dialog — stop propagation so clicks inside don't close */}
      <div
        className="flex flex-col items-center gap-3 rounded-2xl bg-zinc-900 p-6 shadow-2xl"
        style={{ width: 320, maxWidth: "92vw" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex w-full items-center justify-between text-white">
          <span className="text-lg font-medium">Volume</span>
          <IconButton onClick={onClose} size="small" sx={{ color: "white" }}>
            <CloseIcon />
          </IconButton>
        </div>

        {/* SVG knob */}
        <svg
          ref={svgRef}
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          style={{ touchAction: "none", userSelect: "none", cursor: "pointer" }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          {/* Background track */}
          <path
            d={trackPath}
            fill="none"
            stroke="#3f3f46"
            strokeWidth={STROKE}
            strokeLinecap="round"
          />
          {/* Value track (teal = MUI primary) */}
          {valuePath && (
            <path
              d={valuePath}
              fill="none"
              stroke="#009688"
              strokeWidth={STROKE}
              strokeLinecap="round"
            />
          )}
          {/* Knob dot at current position */}
          {(() => {
            const dot = polarXY(valueAngle);
            return (
              <circle cx={dot.x} cy={dot.y} r={STROKE / 2 + 3} fill="white" />
            );
          })()}
          {/* Volume percentage label */}
          <text
            x={CX}
            y={CY - 10}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize="52"
            fontWeight="bold"
            fill="white"
            style={{ fontFamily: "Roboto, sans-serif" }}
          >
            {localVolume}
          </text>
          <text
            x={CX}
            y={CY + 32}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize="16"
            fill="#a1a1aa"
            style={{ fontFamily: "Roboto, sans-serif" }}
          >
            %
          </text>
        </svg>

        {/* Hint */}
        <p className="text-xs text-zinc-500">Drag the knob to adjust volume</p>
      </div>
    </div>
  );
};

export default VolumeKnob;

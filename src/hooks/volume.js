import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef } from "react";
import { getVolume, setVolume } from "services/mopidy";
import { useConfig } from "./config";

/**
 * Hook for reading and setting the ALSA hardware volume.
 *
 * Returns:
 *   volume          - current volume 0-100 (optimistically updated while dragging)
 *   volumeEnabled   - true if volume_control is enabled in mopidy.conf
 *   setVolume       - throttled setter (~80ms), call continuously while dragging
 *   flushVolume     - immediate setter, call on pointer-up to send the final value
 *   isLoading       - true on the initial fetch
 */
export const useVolume = () => {
  const { config } = useConfig();
  const enabled = config?.volumeControl === true;
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["volume"],
    queryFn: getVolume,
    enabled,
    refetchInterval: 30000,
    staleTime: 10000,
  });

  const mutation = useMutation({
    mutationFn: setVolume,
    onMutate: (payload) => {
      // payload may be { volume, eq } object or a plain number
      const vol = typeof payload === "object" ? payload.volume : payload;
      // Optimistically update the cache so the knob stays in sync
      queryClient.setQueryData(["volume"], (old) => ({
        ...(old || {}),
        volume: vol,
      }));
    },
  });

  // Trailing throttle: schedule a send at most once per 80ms,
  // always using the latest requested value.
  const throttleTimer = useRef(null);
  const latestVol = useRef(null);

  const throttledSet = useCallback(
    (vol) => {
      latestVol.current = vol;
      // Optimistically update cache immediately for smooth UI
      queryClient.setQueryData(["volume"], (old) => ({
        ...(old || {}),
        volume: vol,
      }));
      if (throttleTimer.current) return;
      throttleTimer.current = setTimeout(() => {
        throttleTimer.current = null;
        mutation.mutate({ volume: latestVol.current, eq: false }); // no EQ during drag
      }, 80);
    },
    [mutation, queryClient],
  );

  const flushSet = useCallback(
    (vol) => {
      if (throttleTimer.current) {
        clearTimeout(throttleTimer.current);
        throttleTimer.current = null;
      }
      mutation.mutate({ volume: vol, eq: true }); // apply EQ on release
    },
    [mutation],
  );

  return {
    volume: data?.volume ?? 50,
    volumeEnabled: enabled,
    setVolume: throttledSet,
    flushVolume: flushSet,
    isLoading,
  };
};

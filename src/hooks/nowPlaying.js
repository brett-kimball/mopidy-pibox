import {
  useQuery,
  useQueryClient,
  keepPreviousData,
} from "@tanstack/react-query";
import { useEffect } from "react";
import {
  getArtwork,
  getCurrentTrack,
  getPlaybackState,
  onPlaybackChanged,
} from "services/mopidy";

let subscriptionInitialised = false;

export const useNowPlaying = ({ artworkSize = 640 } = {}) => {
  const { data: currentTrack, isLoading: currentTrackLoading } = useQuery({
    queryKey: ["currentTrack"],
    queryFn: getCurrentTrack,
    staleTime: 30000,
  });

  const { data: playbackState, isLoading: playbackStateLoading } = useQuery({
    queryKey: ["playbackState"],
    queryFn: getPlaybackState,
    staleTime: 30000,
  });

  const { data: artworkUrl, isLoading: artworkUrlLoading } = useQuery({
    queryKey: [currentTrack, "artworkUrl", artworkSize],
    queryFn: async () => {
      if (!currentTrack) {
        return null;
      }
      return getArtwork(currentTrack.uri, artworkSize);
    },
    enabled: !!currentTrack,
    staleTime: 30000,
    placeholderData: keepPreviousData,
  });

  const queryClient = useQueryClient();

  useEffect(() => {
    if (subscriptionInitialised) {
      return;
    }

    const cleanup = onPlaybackChanged(async () => {
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["currentTrack"] });
      }, 1500);
      queryClient.invalidateQueries({ queryKey: ["playbackState"] });
    });

    // When the app becomes visible again, refetch the current track
    // Note: We don't invalidate artworkUrl here to preserve the thumbnail while reconnecting
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        queryClient.invalidateQueries({ queryKey: ["currentTrack"] });
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cleanup();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return {
    currentTrack,
    currentTrackLoading,
    playbackState,
    playbackStateLoading,
    artworkUrl,
    artworkUrlLoading,
  };
};

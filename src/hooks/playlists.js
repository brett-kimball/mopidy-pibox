import { useQuery } from "@tanstack/react-query";
import { getPlaylistsAndMixes } from "services/mopidy";

export const usePlaylists = () => {
  const { data, isLoading, error } = useQuery({
    queryKey: ["playlists"],
    queryFn: getPlaylistsAndMixes,
    staleTime: 60_000,
  });

  return {
    playlists: data,
    playlistsLoading: isLoading,
    error,
  };
};

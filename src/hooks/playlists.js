import { useQuery } from "@tanstack/react-query";
import { getPlaylistsAndMixes, searchTidalPlaylists } from "services/mopidy";

export const usePlaylists = () => {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["playlists"],
    queryFn: getPlaylistsAndMixes,
    staleTime: 60_000,
  });

  return {
    playlists: data,
    playlistsLoading: isLoading,
    error,
    refetchPlaylists: refetch,
  };
};

/**
 * Search Tidal for playlists not in the user's liked list.
 * Results are fetched only when `query` is non-empty or `enabled` is true.
 * @param {string} query - search string
 * @param {boolean} enabled - whether to run the query at all
 */
export const usePlaylistSearch = (query, enabled = false) => {
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["playlistSearch", query],
    queryFn: () => searchTidalPlaylists(query),
    enabled: enabled && query.trim().length > 0,
    staleTime: 30_000,
    placeholderData: [],
  });

  return {
    searchResults: data || [],
    searchLoading: isLoading || isFetching,
  };
};

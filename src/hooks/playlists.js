import { useQuery } from "@tanstack/react-query";
import { getPlaylists, searchTidalPlaylists } from "services/mopidy";

export const usePlaylists = () => {
  const playlistQuery = useQuery({
    queryKey: ["playlists"],
    queryFn: getPlaylists,
    staleTime: 60_000,
    // Retry a few times in case the backend isn't ready yet, then stop.
    retry: 3,
    retryDelay: 3000,
  });

  return {
    playlists: playlistQuery.data || [],
    playlistsLoading: playlistQuery.isLoading,
    error: playlistQuery.error,
    refetchPlaylists: playlistQuery.refetch,
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

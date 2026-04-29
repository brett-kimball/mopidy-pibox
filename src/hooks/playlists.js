import { useQuery } from "@tanstack/react-query";
import { getPlaylistsAndMixes, searchTidalPlaylists } from "services/mopidy";

// How many times to retry fetching playlists before giving up.
// Tidal loads asynchronously at startup; we poll briefly to wait for it.
const PLAYLIST_MAX_RETRIES = 10; // ~30 seconds at 3s intervals

export const usePlaylists = () => {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["playlists"],
    queryFn: getPlaylistsAndMixes,
    staleTime: 60_000,
    // Poll every 3s while empty, but only up to PLAYLIST_MAX_RETRIES times.
    // This handles the case where mopidy-tidal needs a moment to load
    // playlists at startup, without hammering the API forever on accounts
    // with no liked playlists.
    refetchInterval: (query) => {
      const hasData = query.state.data && query.state.data.length > 0;
      const retriesExhausted = query.state.fetchFailureCount >= PLAYLIST_MAX_RETRIES ||
        query.state.dataUpdateCount >= PLAYLIST_MAX_RETRIES;
      return hasData || retriesExhausted ? false : 3000;
    },
  });

  return {
    playlists: data || [],
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

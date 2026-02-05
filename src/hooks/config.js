import { useQuery } from "@tanstack/react-query";
import { getConfig, setPiboxPongTimeout } from "services/mopidy";

export const useConfig = () => {
  const { data, isLoading, error } = useQuery({
    queryKey: ["config"],
    queryFn: async () => {
      const config = await getConfig();
      // Apply configurable WebSocket PONG timeout
      if (config?.wsPongTimeoutMs) {
        setPiboxPongTimeout(config.wsPongTimeoutMs);
      }
      return config;
    },
    staleTime: Infinity,
  });

  return {
    config: data,
    configLoading: isLoading,
    error,
  };
};

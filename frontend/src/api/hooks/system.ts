import { useQuery } from '@tanstack/react-query';
import { api, unwrap } from '../client.ts';

export const STATUS_REFETCH_MS = 15_000;

export const systemKeys = {
  status: ['status'] as const,
  overview: ['overview'] as const,
};

export function useStatus() {
  return useQuery({
    queryKey: systemKeys.status,
    queryFn: async () => unwrap(await api().GET('/api/status')),
    refetchInterval: STATUS_REFETCH_MS,
  });
}

export function useOverview() {
  return useQuery({
    queryKey: systemKeys.overview,
    queryFn: async () => unwrap(await api().GET('/api/overview')),
  });
}

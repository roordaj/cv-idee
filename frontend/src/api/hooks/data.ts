import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap, type RequestBody } from '../client.ts';

export interface RangeParams {
  from?: string;
  to?: string;
}

export function useQuality(range: RangeParams = {}) {
  return useQuery({
    queryKey: ['quality', range],
    queryFn: async () => unwrap(await api().GET('/api/quality', { params: { query: range } })),
  });
}

export function useTimeline(range: RangeParams = {}) {
  return useQuery({
    queryKey: ['timeline', range],
    queryFn: async () => unwrap(await api().GET('/api/timeline', { params: { query: range } })),
  });
}

export function useCycles(params: RangeParams & { limit?: number; offset?: number } = {}) {
  return useQuery({
    queryKey: ['cycles', params],
    queryFn: async () => unwrap(await api().GET('/api/cycles', { params: { query: params } })),
  });
}

export function useImports() {
  return useQuery({
    queryKey: ['imports'],
    queryFn: async () => unwrap(await api().GET('/api/import')),
  });
}

export const IMPORT_POLL_MS = 2000;
const IMPORT_ACTIVE: readonly string[] = ['pending', 'fetching', 'analysing'];

export function useImport(importId: string | null) {
  return useQuery({
    queryKey: ['imports', importId],
    enabled: importId !== null,
    refetchInterval: (query) =>
      query.state.data && IMPORT_ACTIVE.includes(query.state.data.status) ? IMPORT_POLL_MS : false,
    queryFn: async () =>
      unwrap(
        await api().GET('/api/import/{import_id}', {
          params: { path: { import_id: importId ?? '' } },
        }),
      ),
  });
}

export function useStartImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: RequestBody<'/api/import', 'post'>) =>
      unwrap(await api().POST('/api/import', { body })),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['imports'] }),
        queryClient.invalidateQueries({ queryKey: ['status'] }),
      ]);
    },
  });
}

export function useCancelImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (importId: string) =>
      unwrap(
        await api().POST('/api/import/{import_id}/cancel', {
          params: { path: { import_id: importId } },
        }),
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['imports'] }),
        queryClient.invalidateQueries({ queryKey: ['status'] }),
      ]);
    },
  });
}

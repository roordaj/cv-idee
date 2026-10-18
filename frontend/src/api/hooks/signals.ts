import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap, type RequestBody } from '../client.ts';
import { systemKeys } from './system.ts';

export const signalKeys = { all: ['signals'] as const, analyses: ['analyses'] as const };

export function useSignals() {
  return useQuery({
    queryKey: signalKeys.all,
    queryFn: async () => unwrap(await api().GET('/api/signals')),
  });
}

export function useAnalyses() {
  return useQuery({
    queryKey: signalKeys.analyses,
    queryFn: async () => unwrap(await api().GET('/api/analyses')),
  });
}

export function useHaEntities() {
  return useQuery({
    queryKey: ['ha', 'entities'],
    queryFn: async () => unwrap(await api().GET('/api/ha/entities')),
  });
}

export function useHaStatus() {
  return useQuery({
    queryKey: ['ha', 'status'],
    queryFn: async () => unwrap(await api().GET('/api/ha/status')),
  });
}

export function useHaExport() {
  return useQuery({
    queryKey: ['ha', 'export'],
    queryFn: async () => unwrap(await api().GET('/api/ha/export')),
  });
}

export function useUpdateSignal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (args: {
      signalId: string;
      body: RequestBody<'/api/signals/{signal_id}', 'put'>;
    }) =>
      unwrap(
        await api().PUT('/api/signals/{signal_id}', {
          params: { path: { signal_id: args.signalId } },
          body: args.body,
        }),
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: signalKeys.all }),
        queryClient.invalidateQueries({ queryKey: signalKeys.analyses }),
        queryClient.invalidateQueries({ queryKey: systemKeys.status }),
      ]);
    },
  });
}

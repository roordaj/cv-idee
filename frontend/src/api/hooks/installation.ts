import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap, type RequestBody } from '../client.ts';

const installationKey = ['installation'] as const;
const periodsKey = ['periods'] as const;

export function useInstallation() {
  return useQuery({
    queryKey: installationKey,
    queryFn: async () => unwrap(await api().GET('/api/installation')),
  });
}

export function useUpdateInstallation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: RequestBody<'/api/installation', 'put'>) =>
      unwrap(await api().PUT('/api/installation', { body })),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: installationKey }),
        queryClient.invalidateQueries({ queryKey: ['comfort-analysis'] }),
      ]);
    },
  });
}

export function useRoomComfortAnalysis() {
  return useQuery({
    queryKey: ['comfort-analysis'],
    queryFn: async () => unwrap(await api().GET('/api/comfort')),
  });
}

export function usePeriods() {
  return useQuery({
    queryKey: periodsKey,
    queryFn: async () => unwrap(await api().GET('/api/periods')),
  });
}

export function useCreatePeriod() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: RequestBody<'/api/periods', 'post'>) =>
      unwrap(await api().POST('/api/periods', { body })),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: periodsKey }),
        queryClient.invalidateQueries({ queryKey: ['comfort-analysis'] }),
      ]);
    },
  });
}

export function useUpdatePeriod() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (args: {
      periodId: string;
      body: RequestBody<'/api/periods/{period_id}', 'put'>;
    }) =>
      unwrap(
        await api().PUT('/api/periods/{period_id}', {
          params: { path: { period_id: args.periodId } },
          body: args.body,
        }),
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: periodsKey }),
        queryClient.invalidateQueries({ queryKey: ['comfort-analysis'] }),
      ]);
    },
  });
}

export function useDeletePeriod() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (periodId: string) => {
      const result = await api().DELETE('/api/periods/{period_id}', {
        params: { path: { period_id: periodId } },
      });
      if (result.error !== undefined) unwrap(result);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: periodsKey }),
        queryClient.invalidateQueries({ queryKey: ['comfort-analysis'] }),
      ]);
    },
  });
}

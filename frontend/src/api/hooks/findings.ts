import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap, type RequestBody } from '../client.ts';

const findingsKey = ['findings'] as const;

export function useFindings() {
  return useQuery({
    queryKey: findingsKey,
    queryFn: async () => unwrap(await api().GET('/api/findings')),
  });
}

export function useFinding(findingId: string) {
  return useQuery({
    queryKey: [...findingsKey, findingId],
    queryFn: async () =>
      unwrap(
        await api().GET('/api/findings/{finding_id}', {
          params: { path: { finding_id: findingId } },
        }),
      ),
  });
}

function useInvalidateFindings() {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: findingsKey }),
      queryClient.invalidateQueries({ queryKey: ['status'] }),
      queryClient.invalidateQueries({ queryKey: ['overview'] }),
    ]);
  };
}

export function useSetFindingStatus() {
  const invalidate = useInvalidateFindings();
  return useMutation({
    mutationFn: async (args: {
      findingId: string;
      body: RequestBody<'/api/findings/{finding_id}/status', 'post'>;
    }) =>
      unwrap(
        await api().POST('/api/findings/{finding_id}/status', {
          params: { path: { finding_id: args.findingId } },
          body: args.body,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useAddFindingNote() {
  const invalidate = useInvalidateFindings();
  return useMutation({
    mutationFn: async (args: {
      findingId: string;
      body: RequestBody<'/api/findings/{finding_id}/notes', 'post'>;
    }) =>
      unwrap(
        await api().POST('/api/findings/{finding_id}/notes', {
          params: { path: { finding_id: args.findingId } },
          body: args.body,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useHistory(params: { limit?: number; offset?: number } = {}) {
  return useQuery({
    queryKey: ['history', params],
    queryFn: async () => unwrap(await api().GET('/api/history', { params: { query: params } })),
  });
}

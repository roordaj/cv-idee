import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap, type RequestBody } from '../client.ts';

const changesKey = ['changes'] as const;

export function useChanges() {
  return useQuery({
    queryKey: changesKey,
    queryFn: async () => unwrap(await api().GET('/api/changes')),
  });
}

export function useCreateChange() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: RequestBody<'/api/changes', 'post'>) =>
      unwrap(await api().POST('/api/changes', { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: changesKey }),
  });
}

export function useChangeEvaluation(changeId: string) {
  return useQuery({
    queryKey: [...changesKey, changeId, 'evaluation'],
    queryFn: async () =>
      unwrap(
        await api().GET('/api/changes/{change_id}/evaluation', {
          params: { path: { change_id: changeId } },
        }),
      ),
  });
}

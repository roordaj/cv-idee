import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { POSTPONE_DAYS, statusText } from '../../screens/Findings/labels.ts';
import { api, unwrap, type RequestBody } from '../client.ts';
import type { components } from '../schema';

type FindingDetail = components['schemas']['FindingDetail'];
type FindingList = components['schemas']['FindingList'];

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
  const queryClient = useQueryClient();
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
    // Optimistic update (FR-27): patch list and detail caches, roll back on error.
    onMutate: async (args) => {
      await queryClient.cancelQueries({ queryKey: findingsKey });
      const snapshot = queryClient.getQueriesData({ queryKey: findingsKey });
      const status = args.body.status;
      const until = args.body.postponed_until
        ? new Date(args.body.postponed_until)
        : new Date(Date.now() + POSTPONE_DAYS * 86_400_000);
      const patch = { status, status_text: statusText(status, until) };
      queryClient.setQueryData<FindingDetail>([...findingsKey, args.findingId], (old) =>
        old ? { ...old, ...patch } : old,
      );
      queryClient.setQueryData<FindingList>(findingsKey, (old) =>
        old
          ? {
              ...old,
              items: old.items.map((f) => (f.id === args.findingId ? { ...f, ...patch } : f)),
            }
          : old,
      );
      return { snapshot };
    },
    onError: (_error, _args, context) => {
      context?.snapshot.forEach(([key, data]) => {
        queryClient.setQueryData(key, data);
      });
    },
    onSettled: invalidate,
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

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap, type RequestBody } from '../client.ts';

const settingsKey = ['settings'] as const;
const policyKey = ['notification-policy'] as const;

export function useSettings() {
  return useQuery({
    queryKey: settingsKey,
    queryFn: async () => unwrap(await api().GET('/api/settings')),
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: RequestBody<'/api/settings', 'put'>) =>
      unwrap(await api().PUT('/api/settings', { body })),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: settingsKey }),
        queryClient.invalidateQueries({ queryKey: ['status'] }),
        queryClient.invalidateQueries({ queryKey: ['zone-analysis'] }),
      ]);
    },
  });
}

export function useNotificationPolicy() {
  return useQuery({
    queryKey: policyKey,
    queryFn: async () => unwrap(await api().GET('/api/notifications/policy')),
  });
}

export function useUpdateNotificationPolicy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: RequestBody<'/api/notifications/policy', 'put'>) =>
      unwrap(await api().PUT('/api/notifications/policy', { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: policyKey }),
  });
}

export function useNotifications(params: { limit?: number; offset?: number } = {}) {
  return useQuery({
    queryKey: ['notifications', params],
    queryFn: async () =>
      unwrap(await api().GET('/api/notifications', { params: { query: params } })),
  });
}

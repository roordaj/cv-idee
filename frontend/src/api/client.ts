import createClient from 'openapi-fetch';
import { getBasePath } from '../lib/basePath.ts';
import type { paths } from './schema';

export class ApiError extends Error {
  readonly status: number;
  readonly problem: unknown;

  constructor(status: number, problem: unknown) {
    const detail =
      typeof problem === 'object' && problem !== null && 'title' in problem
        ? String(problem.title)
        : `HTTP ${String(status)}`;
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.problem = problem;
  }
}

type Client = ReturnType<typeof createClient<paths>>;

/** JSON request body type of an operation, e.g. `RequestBody<'/api/installation', 'put'>`. */
export type RequestBody<P extends keyof paths, M extends keyof paths[P]> = paths[P][M] extends {
  requestBody: { content: { 'application/json': infer B } };
}
  ? B
  : never;

/**
 * Typed API client. Created lazily so the ingress base path (set by the backend in
 * index.html) is read at first use; `fetch` is resolved per request (mockable in tests).
 */
let client: Client | undefined;
let clientBase: string | undefined;

export function api(): Client {
  const base = getBasePath();
  if (!client || clientBase !== base) {
    client = createClient<paths>({
      // Absolute so `new Request(url)` also works outside a browser document (tests).
      baseUrl: `${window.location.origin}${base}`,
      fetch: (request) => globalThis.fetch(request),
    });
    clientBase = base;
  }
  return client;
}

/** Unwrap an openapi-fetch result: return data or throw an `ApiError` (RFC 7807 body). */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || result.data === undefined) {
    throw new ApiError(result.response.status, result.error);
  }
  return result.data;
}

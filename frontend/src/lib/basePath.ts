/**
 * Base path of the app. Under Home Assistant ingress the backend injects the ingress
 * prefix (e.g. `/api/hassio_ingress/<token>`) into index.html as `window.__INGRESS_PATH__`;
 * standalone it is empty. Use it as router basename and as prefix for API calls.
 */

declare global {
  interface Window {
    __INGRESS_PATH__?: string;
  }
}

export function getBasePath(): string {
  const value = window.__INGRESS_PATH__ ?? '';
  return value.replace(/\/+$/, '');
}

/** Router basename: the base path, or `/` when the app is served at the root. */
export function getRouterBasename(): string {
  return getBasePath() || '/';
}

/** Absolute URL path for an API route, e.g. `apiPath('/api/health')`. */
export function apiPath(path: string): string {
  return `${getBasePath()}${path.startsWith('/') ? path : `/${path}`}`;
}

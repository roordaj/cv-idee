import { useSyncExternalStore } from 'react';

function getMatch(query: string): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia(query).matches;
}

/** Subscribe to a CSS media query. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
        return () => undefined;
      }
      const list = window.matchMedia(query);
      list.addEventListener('change', onChange);
      return () => {
        list.removeEventListener('change', onChange);
      };
    },
    () => getMatch(query),
    () => false,
  );
}

/** Design v3: below 960px viewport the sidebar collapses to a 72px icon rail. */
export const RAIL_QUERY = '(max-width: 959.98px)';

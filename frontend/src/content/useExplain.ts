import { useCallback, useSyncExternalStore } from 'react';

const EXPLAIN_KEY = 'cv-idee.explain';
const REQ_IDS_KEY = 'cv-idee.showRequirementIds';

type Listener = () => void;
const listeners = new Set<Listener>();
// Fallback memory so the toggle still works when localStorage is unavailable.
const memory = new Map<string, boolean>();

function read(key: string, fallback: boolean): boolean {
  try {
    const v = window.localStorage.getItem(key);
    return v === null ? fallback : v === '1';
  } catch {
    return fallback;
  }
}

function get(key: string, fallback: boolean): boolean {
  return memory.get(key) ?? read(key, fallback);
}

function notify(): void {
  listeners.forEach((l) => {
    l();
  });
}

function set(key: string, value: boolean): void {
  memory.set(key, value);
  try {
    window.localStorage.setItem(key, value ? '1' : '0');
  } catch {
    /* setting just isn't persisted */
  }
  notify();
}

function subscribe(l: Listener): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

/** Forget in-memory state so storage is read again (tests). */
export function resetExplainState(): void {
  memory.clear();
  notify();
}

export interface ExplainState {
  /** 'uitleg tonen' (default on, persisted per browser). */
  explain: boolean;
  setExplain: (value: boolean) => void;
  /** Dev-only 'requirement-ID's tonen' (default off). Always false in production builds. */
  showRequirementIds: boolean;
  setShowRequirementIds: (value: boolean) => void;
}

export function useExplain(): ExplainState {
  const explain = useSyncExternalStore(subscribe, () => get(EXPLAIN_KEY, true));
  const reqIds = useSyncExternalStore(subscribe, () => get(REQ_IDS_KEY, false));
  const setExplain = useCallback((v: boolean) => {
    set(EXPLAIN_KEY, v);
  }, []);
  const setShowRequirementIds = useCallback((v: boolean) => {
    set(REQ_IDS_KEY, v);
  }, []);
  return {
    explain,
    setExplain,
    showRequirementIds: import.meta.env.DEV && reqIds,
    setShowRequirementIds,
  };
}

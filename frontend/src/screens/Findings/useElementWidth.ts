import { useCallback, useEffect, useState } from 'react';

/** Width of an element (main-width breakpoints from design v3); `fallback` until measured. */
export function useElementWidth(fallback: number): [(el: HTMLElement | null) => void, number] {
  const [el, setEl] = useState<HTMLElement | null>(null);
  const [width, setWidth] = useState(fallback);
  const ref = useCallback((node: HTMLElement | null) => {
    setEl(node);
  }, []);
  useEffect(() => {
    if (!el) return undefined;
    const measure = () => {
      if (el.clientWidth > 0) setWidth(el.clientWidth);
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => {
      observer.disconnect();
    };
  }, [el]);
  return [ref, width];
}

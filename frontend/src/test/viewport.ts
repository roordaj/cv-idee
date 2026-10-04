/** Stub `window.matchMedia` so `(max-width: Npx)` / `(min-width: Npx)` queries match `width`. */
export function setViewportWidth(width: number): void {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width });
  window.matchMedia = (query: string): MediaQueryList => {
    const max = /max-width:\s*([\d.]+)px/.exec(query);
    const min = /min-width:\s*([\d.]+)px/.exec(query);
    const matches =
      (max?.[1] === undefined || width <= Number(max[1])) &&
      (min?.[1] === undefined || width >= Number(min[1]));
    return {
      matches,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    };
  };
}

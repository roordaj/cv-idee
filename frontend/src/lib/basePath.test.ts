import { afterEach } from 'vitest';
import { apiPath, getBasePath, getRouterBasename } from './basePath.ts';

describe('basePath', () => {
  afterEach(() => {
    delete window.__INGRESS_PATH__;
  });

  it('is empty when not running under ingress', () => {
    expect(getBasePath()).toBe('');
    expect(getRouterBasename()).toBe('/');
    expect(apiPath('/api/health')).toBe('/api/health');
  });

  it('uses the injected ingress path', () => {
    window.__INGRESS_PATH__ = '/api/hassio_ingress/abc/';
    expect(getBasePath()).toBe('/api/hassio_ingress/abc');
    expect(getRouterBasename()).toBe('/api/hassio_ingress/abc');
    expect(apiPath('api/health')).toBe('/api/hassio_ingress/abc/api/health');
  });
});

import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import type { Plugin } from 'vite';

// Fixtures live in ../n8n/fixtures; the mock API imports them straight from there.
const fixturesDir = fileURLToPath(new URL('../n8n/fixtures', import.meta.url));

/**
 * public/about/ is a static one-page site next to the app. nginx (infra/nginx.conf) serves the
 * directory index for /about/; the dev and preview servers would fall through to the SPA, so map the
 * path to the file here the same way.
 */
function aboutIndex(): Plugin {
  const rewrite = (req: { url?: string }, _res: unknown, next: () => void) => {
    if (req.url === '/about' || req.url === '/about/') req.url = '/about/index.html';
    next();
  };
  return {
    name: 'about-index',
    configureServer: (server) => void server.middlewares.use(rewrite),
    configurePreviewServer: (server) => void server.middlewares.use(rewrite),
  };
}

export default defineConfig({
  plugins: [react(), aboutIndex()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@fixtures': fixturesDir,
    },
  },
  server: {
    fs: { allow: [fileURLToPath(new URL('.', import.meta.url)), fixturesDir] },
    // `npm run dev:api` talks to nginx from infra/ (VITE_MOCK=0); plain `npm run dev` uses the mock.
    proxy: { '/api': { target: 'http://localhost', changeOrigin: true } },
    // Screenshots from the Gotenberg container reach the dev server via host.docker.internal.
    allowedHosts: ['host.docker.internal'],
  },
  test: { include: ['src/**/*.test.{ts,tsx}'] },
});

import { useEffect, useState } from 'react';

// Two routes, no library: `/` and `/jobs/{id}` (frontend/CLAUDE.md).
export type Route =
  { name: 'home' } | { name: 'job'; id: string } | { name: 'policy' } | { name: 'notFound' };

export function parseRoute(pathname: string): Route {
  if (pathname === '/' || pathname === '') return { name: 'home' };
  const m = pathname.match(/^\/jobs\/([A-Za-z0-9_-]+)\/?$/);
  if (m) return { name: 'job', id: m[1] };
  if (pathname === '/policy' || pathname === '/policy/') return { name: 'policy' };
  return { name: 'notFound' };
}

export function navigate(path: string): void {
  window.history.pushState(null, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.pathname));
  useEffect(() => {
    const onPop = () => setRoute(parseRoute(window.location.pathname));
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  return route;
}

/** Intercept in-app links so the router handles them without a reload. */
export function onLinkClick(event: React.MouseEvent<HTMLAnchorElement>): void {
  if (
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey
  )
    return;
  const href = event.currentTarget.getAttribute('href');
  if (!href || !href.startsWith('/')) return;
  event.preventDefault();
  navigate(href);
}

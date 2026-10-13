import { useRoute } from '@/lib/router';
import { HomePage } from '@/pages/HomePage';
import { JobPage } from '@/pages/JobPage';
import { NotFoundPage, PolicyPage } from '@/pages/ServicePages';
import { Toasts } from '@/components/Toasts';

export function App() {
  const route = useRoute();
  return (
    <>
      {route.name === 'home' && <HomePage />}
      {route.name === 'job' && <JobPage id={route.id} key={route.id} />}
      {route.name === 'policy' && <PolicyPage />}
      {route.name === 'notFound' && <NotFoundPage path={window.location.pathname} />}
      <Toasts />
    </>
  );
}

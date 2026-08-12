// reactapp/src/App.tsx
import { useEffect } from 'react';
import { RouterProvider } from 'react-router-dom';
import { ensureCsrf } from './api';
import { router } from './router';

export default function App() {
  // Seed the CSRF cookie once so later POSTs (submit/presign) don't 403.
  useEffect(() => {
    ensureCsrf();
  }, []);

  return <RouterProvider router={router} />;
}

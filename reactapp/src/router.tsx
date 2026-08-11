// reactapp/src/router.tsx
// Client-side routes for the workspace. AppShell is the layout; the detail pane
// (<Outlet/>) renders the active child route. Served under the Tethys app path in
// production (/apps/fimeval-gui/) and at / in dev — basename derives from Vite's
// BASE_URL so deep links resolve in both. Tethys's catch_all serves index.html
// for any sub-path, so /runs/:jobId survives a refresh.
import { createBrowserRouter, Navigate } from 'react-router-dom';
import AppShell from './AppShell';
import NewEvaluation from './NewEvaluation';
import RunDetail from './RunDetail';
import Docs from './Docs';

const basename = import.meta.env.BASE_URL.replace(/\/$/, '') || '/';

export const router = createBrowserRouter(
  [
    {
      path: '/',
      element: <AppShell />,
      children: [
        { index: true, element: <Navigate to="/new" replace /> },
        { path: 'new', element: <NewEvaluation /> },
        { path: 'runs/:jobId', element: <RunDetail /> },
        { path: 'docs', element: <Docs /> },
      ],
    },
  ],
  { basename },
);

// reactapp/src/IndexRedirect.tsx
// The app root forwards to the wizard. The FIMbench handoff (FE65) lands on the
// root with a query string, so the search is carried along for NewEvaluation.
import { Navigate, useLocation } from 'react-router-dom';

export default function IndexRedirect() {
  const { search } = useLocation();
  return <Navigate to={{ pathname: '/new', search }} replace />;
}

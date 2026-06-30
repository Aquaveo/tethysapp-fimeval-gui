// reactapp/src/ErrorBoundary.tsx
import { Component } from 'react';
import type { ReactNode } from 'react';

interface Props {
  fallback: ReactNode;
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

// Contains render errors in a subtree (e.g. the chart) so a failure degrades to
// the fallback instead of blanking the whole page.
class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    console.error('Subtree render error:', error);
  }

  render() {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}

export default ErrorBoundary;

// reactapp/src/RunDetail.tsx
// Placeholder — the status-driven run detail pane is built in FE30.
import { useParams } from 'react-router-dom';

export default function RunDetail() {
  const { jobId } = useParams();
  return (
    <div>
      <h2>Run #{jobId}</h2>
      <p style={{ color: 'var(--color-text-muted)' }}>Run details are coming next.</p>
    </div>
  );
}

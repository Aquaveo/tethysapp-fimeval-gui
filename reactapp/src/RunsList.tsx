// reactapp/src/RunsList.tsx
// Placeholder — the persistent Runs list is built in FE28 (fetches GET api/jobs,
// renders run cards, polls in-progress, highlights the selected route).
export default function RunsList() {
  return (
    <div style={{ padding: '0.9rem 1rem' }}>
      <div style={{ fontWeight: 600, fontSize: '1rem', marginBottom: '0.4rem' }}>Runs</div>
      <p style={{ margin: 0, color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
        Your runs will appear here.
      </p>
    </div>
  );
}

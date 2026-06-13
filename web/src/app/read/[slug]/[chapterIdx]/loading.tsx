export default function Loading() {
  return (
    <div className="max-w-3xl mx-auto px-4 md:px-6 py-6">
      <div className="mb-6">
        <div className="h-4 w-32 rounded bg-[var(--color-surface)] animate-pulse" />
        <div className="h-4 w-48 rounded bg-[var(--color-surface)] animate-pulse mt-2" />
        <div className="h-6 w-64 rounded bg-[var(--color-surface)] animate-pulse mt-2" />
      </div>
      <div className="space-y-3" aria-busy="true">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="h-4 rounded bg-[var(--color-surface)] animate-pulse"
            style={{ width: `${70 + ((i * 13) % 25)}%` }}
          />
        ))}
      </div>
    </div>
  );
}

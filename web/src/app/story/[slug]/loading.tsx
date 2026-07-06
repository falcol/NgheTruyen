export default function Loading() {
  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <div className="h-4 w-24 rounded bg-[var(--color-surface)] animate-shimmer mb-4" />
      <div className="h-7 w-56 rounded bg-[var(--color-surface)] animate-shimmer mb-2" />
      <div className="h-4 w-40 rounded bg-[var(--color-surface)] animate-shimmer mb-6" />
      <div className="space-y-1">
        {Array.from({ length: 12 }).map((_, i) => (
          <div
            key={i}
            className="h-12 rounded-lg bg-[var(--color-surface)] animate-shimmer"
          />
        ))}
      </div>
    </main>
  );
}

export default function Loading() {
  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <div className="h-4 w-24 rounded bg-[var(--color-surface)] animate-shimmer mb-4" />
      <div className="h-8 w-32 rounded bg-[var(--color-surface)] animate-shimmer mb-6" />
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="h-[72px] rounded-lg bg-[var(--color-surface)] animate-shimmer"
          />
        ))}
      </div>
    </main>
  );
}

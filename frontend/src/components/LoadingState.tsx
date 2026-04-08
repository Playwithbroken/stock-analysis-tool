export default function LoadingState() {
  return (
    <div className="space-y-6">
      <div className="surface-panel rounded-[2rem] p-6">
        <div className="flex items-center gap-4">
          <div className="loading-pulse h-16 w-16 rounded-[1.2rem] bg-[var(--bg-soft)]" />
          <div className="space-y-2">
            <div className="loading-pulse h-6 w-48 rounded bg-[var(--bg-soft)]" />
            <div className="loading-pulse h-4 w-32 rounded bg-[var(--bg-soft)]" />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div key={i} className="surface-panel rounded-[1.5rem] p-5">
            <div className="mb-4 h-5 w-32 rounded bg-[var(--bg-soft)] loading-pulse" />
            <div className="space-y-2">
              <div className="h-4 w-full rounded bg-[var(--bg-soft)] loading-pulse" />
              <div className="h-4 w-3/4 rounded bg-[var(--bg-soft)] loading-pulse" />
              <div className="h-4 w-1/2 rounded bg-[var(--bg-soft)] loading-pulse" />
            </div>
          </div>
        ))}
      </div>

      <div className="py-8 text-center">
        <div className="inline-flex items-center gap-3 rounded-full border border-black/8 bg-white/80 px-6 py-3">
          <svg
            className="h-5 w-5 animate-spin text-[var(--accent)]"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <span className="text-sm font-medium text-slate-600">
            Analysiere Marktdaten...
          </span>
        </div>
      </div>
    </div>
  );
}

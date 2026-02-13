export default function LoadingState() {
  return (
    <div className="space-y-6">
      {/* Header skeleton */}
      <div className="bg-[#050507] rounded-2xl p-6 border border-white/5">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 bg-[#0a0a0c] rounded-xl loading-pulse"></div>
          <div className="space-y-2">
            <div className="h-6 w-48 bg-[#0a0a0c] rounded loading-pulse"></div>
            <div className="h-4 w-32 bg-[#0a0a0c] rounded loading-pulse"></div>
          </div>
        </div>
      </div>

      {/* Cards skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div
            key={i}
            className="bg-[#050507] rounded-xl p-5 border border-white/5"
          >
            <div className="h-5 w-32 bg-[#0a0a0c] rounded mb-4 loading-pulse"></div>
            <div className="space-y-2">
              <div className="h-4 w-full bg-[#0a0a0c] rounded loading-pulse"></div>
              <div className="h-4 w-3/4 bg-[#0a0a0c] rounded loading-pulse"></div>
              <div className="h-4 w-1/2 bg-[#0a0a0c] rounded loading-pulse"></div>
            </div>
          </div>
        ))}
      </div>

      {/* Loading message */}
      <div className="text-center py-8">
        <div className="inline-flex items-center gap-3 px-6 py-3 bg-[#050507] rounded-full border border-white/5">
          <svg
            className="w-5 h-5 animate-spin text-purple-500"
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
            ></circle>
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            ></path>
          </svg>
          <span className="text-gray-500">Analyzing stock data...</span>
        </div>
      </div>
    </div>
  );
}

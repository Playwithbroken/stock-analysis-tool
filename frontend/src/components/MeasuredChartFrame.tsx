import React, { useEffect, useRef, useState } from "react";

interface MeasuredChartFrameProps {
  className: string;
  minHeight?: number;
  fallback?: React.ReactNode;
  children: React.ReactNode;
}

export default function MeasuredChartFrame({
  className,
  minHeight = 180,
  fallback,
  children,
}: MeasuredChartFrameProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const update = () => {
      const rect = node.getBoundingClientRect();
      setReady(rect.width > 32 && rect.height > 32);
    };

    update();

    const observer = new ResizeObserver(() => update());
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className={className} style={{ minHeight }}>
      {ready ? children : fallback ?? <div className="h-full w-full" />}
    </div>
  );
}

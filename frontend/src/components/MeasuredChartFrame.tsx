import React, { useEffect, useRef, useState } from "react";

interface MeasuredChartFrameProps {
  className: string;
  minHeight?: number;
  fallback?: React.ReactNode;
  children: React.ReactNode | ((size: { w: number; h: number }) => React.ReactNode);
}

/**
 * Renders chart children only after the host element has a non-zero size for
 * at least two animation frames. This guarantees recharts' ResponsiveContainer
 * sees a measurable parent on its very first mount and never emits the
 * "width(-1) height(-1)" warning.
 */
export default function MeasuredChartFrame({
  className,
  minHeight = 180,
  fallback,
  children,
}: MeasuredChartFrameProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    let raf1 = 0;
    let raf2 = 0;
    const measure = () => {
      // A newer resize (including hiding the panel) supersedes pending work.
      cancelAnimationFrame(raf1);
      cancelAnimationFrame(raf2);
      const rect = node.getBoundingClientRect();
      const w = Math.floor(rect.width);
      const h = Math.floor(Math.max(rect.height, minHeight));
      if (w < 32 || h < 32) {
        setSize(null);
        return;
      }
      // Double RAF: ensures layout has fully settled before exposing children
      raf1 = requestAnimationFrame(() => {
        raf2 = requestAnimationFrame(() => {
          // Compare with rendered state: after hiding, identical dimensions
          // still need to restore the chart from its null/fallback state.
          setSize(previous => previous?.w === w && previous.h === h ? previous : { w, h });
        });
      });
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(raf1);
      cancelAnimationFrame(raf2);
    };
  }, [minHeight]);

  return (
    <div
      ref={ref}
      className={className}
      style={{ minHeight, position: "relative" }}
    >
      {size ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            width: size.w,
            height: size.h,
          }}
        >
          {typeof children === "function" ? children(size) : children}
        </div>
      ) : (
        fallback ?? <div style={{ height: minHeight, width: "100%" }} />
      )}
    </div>
  );
}

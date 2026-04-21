import { type ReactNode, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";

interface ShimmerProps {
  /** Whether data is still loading */
  loading: boolean;
  /** Skeleton / placeholder to show while loading */
  fallback: ReactNode;
  /** Real content */
  children: ReactNode;
  /**
   * Minimum ms to show the skeleton — avoids a jarring flash
   * when the API responds instantly. Default 300ms.
   */
  minDuration?: number;
  /** Extra class on the wrapper */
  className?: string;
}

/**
 * Centralized loading-state wrapper.
 *
 * Usage:
 *   <Shimmer loading={query.isLoading} fallback={<SkeletonKpi />}>
 *     <KpiCard ... />
 *   </Shimmer>
 */
export function Shimmer({
  loading,
  fallback,
  children,
  minDuration = 300,
  className,
}: ShimmerProps) {
  const startRef = useRef(Date.now());
  const [show, setShow] = useState(!loading);

  useEffect(() => {
    if (loading) {
      startRef.current = Date.now();
      setShow(false);
      return;
    }

    const elapsed = Date.now() - startRef.current;
    const remaining = Math.max(0, minDuration - elapsed);

    if (remaining === 0) {
      setShow(true);
      return;
    }

    const id = setTimeout(() => setShow(true), remaining);
    return () => clearTimeout(id);
  }, [loading, minDuration]);

  if (!show) return <>{fallback}</>;

  return (
    <div className={cn("animate-fade-in", className)}>
      {children}
    </div>
  );
}

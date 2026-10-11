import { Skeleton } from "@/components/ui/skeleton";

/**
 * Placeholder rows for the list panels (inbox, needs-input). Renders a
 * fragment so the rows participate in the parent's `divide-y`.
 */
export function ListRowsSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          aria-hidden="true"
          className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:gap-4 sm:p-5"
        >
          <Skeleton className="h-3.5 w-28 shrink-0" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-3.5 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
          <Skeleton className="h-6 w-20 rounded-full" />
        </div>
      ))}
    </>
  );
}

/** Placeholder `<tr>` rows for the tables (mission control, inventory). */
export function TableRowsSkeleton({ rows = 5, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r} aria-hidden="true">
          {Array.from({ length: cols }).map((_, c) => (
            <td key={c} className="px-5 py-3.5">
              <Skeleton className={c === 0 ? "h-3.5 w-24" : "h-3.5 w-full max-w-[180px]"} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getCase, listCases, type AgentCase, type CaseDetail } from "@/lib/api";
import { ListRowsSkeleton } from "@/components/ui/loading";

type Row = AgentCase & { question: string | null };

export function NeedsInputList() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const page = await listCases({ execution: "waiting_input", limit: 100 });
        const withQuestions = await Promise.all(
          page.items.map(async (item): Promise<Row> => {
            try {
              const detail: CaseDetail = await getCase(item.case_id);
              return { ...item, question: detail.clarification };
            } catch {
              return { ...item, question: null };
            }
          }),
        );
        if (cancelled) return;
        setRows(withQuestions);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Worklist failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    // Initial load on mount; guarded by cancelled flag.
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      {error && (
        <div className="panel mb-4 border-warning/20 p-4">
          <p className="text-sm text-warning">{error}</p>
        </div>
      )}
      <div className="panel divide-y divide-hairline overflow-hidden">
        {loading && <ListRowsSkeleton rows={4} />}
        {!loading && rows.length === 0 && !error && (
          <p className="p-5 text-sm text-muted-foreground">
            Nothing waiting. Every case is moving without you.
          </p>
        )}
        {rows.map((t) => (
          <Link
            key={t.case_id}
            href={`/ticket/${t.case_id}`}
            className="flex flex-col gap-2 p-4 transition-colors hover:bg-accent/40 sm:flex-row sm:items-center sm:gap-4 sm:p-5"
          >
            <span className="font-mono text-xs text-muted-foreground sm:w-36 sm:shrink-0">
              {t.case_id}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">{t.message}</p>
              <p className="mt-0.5 truncate text-sm text-muted-foreground">
                {t.question ?? "Waiting on a reply — open to see details."}
              </p>
            </div>
            <span className="font-mono text-xs text-muted-foreground">{t.current_run_id}</span>
          </Link>
        ))}
      </div>
    </>
  );
}

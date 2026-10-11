"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  listCases,
  submitTicket,
  type AcceptResponse,
  type AgentCase,
  type CaseList,
} from "@/lib/api";

export type { AgentCase, AcceptResponse };

type SwapDeskContextValue = {
  cases: AgentCase[];
  summary: CaseList["summary"] | null;
  total: number;
  loading: boolean;
  error: string | null;
  executionFilter: string;
  setExecutionFilter: (value: string) => void;
  refresh: () => Promise<void>;
  loadMore: () => Promise<void>;
  hasMore: boolean;
  submit: (body: {
    message: string;
    order_id?: string | null;
    order_item_id?: string | null;
    size?: string | null;
    qty?: number;
    consent_size?: string | null;
  }) => Promise<AcceptResponse>;
};

const SwapDeskContext = createContext<SwapDeskContextValue | null>(null);

const TERMINAL = new Set(["completed", "failed"]);

export function SwapDeskProvider({ children }: { children: ReactNode }) {
  const [cases, setCases] = useState<AgentCase[]>([]);
  const [summary, setSummary] = useState<CaseList["summary"] | null>(null);
  const [total, setTotal] = useState(0);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [executionFilter, setExecutionFilter] = useState("");
  const requestId = useRef(0);

  const fetchPage = useCallback(
    async (execution: string, cursorValue: string | null, append: boolean) => {
      const mine = ++requestId.current;
      if (!append) setLoading(true);
      try {
        const page = await listCases({
          execution: execution || undefined,
          limit: 25,
          cursor: cursorValue,
        });
        if (requestId.current !== mine) return;
        setCases((prev) => (append ? [...prev, ...page.items] : page.items));
        setSummary(page.summary);
        setTotal(page.total);
        setCursor(page.next_cursor);
        setError(null);
      } catch (err) {
        if (requestId.current !== mine) return;
        setError(err instanceof Error ? err.message : "Case list failed to load");
      } finally {
        if (requestId.current === mine) setLoading(false);
      }
    },
    [],
  );

  const refresh = useCallback(
    () => fetchPage(executionFilter, null, false),
    [executionFilter, fetchPage],
  );

  const loadMore = useCallback(() => {
    if (!cursor) return Promise.resolve();
    return fetchPage(executionFilter, cursor, true);
  }, [cursor, executionFilter, fetchPage]);

  const changeFilter = useCallback(
    (value: string) => {
      setExecutionFilter(value);
      setCursor(null);
      void fetchPage(value, null, false);
    },
    [fetchPage],
  );

  const submit = useCallback(
    async (body: {
      message: string;
      order_id?: string | null;
      order_item_id?: string | null;
      size?: string | null;
      qty?: number;
      consent_size?: string | null;
    }) => {
      const accepted = await submitTicket({
        message: body.message,
        order_id: body.order_id ?? null,
        order_item_id: body.order_item_id ?? null,
        size: body.size ?? null,
        qty: body.qty ?? 1,
        consent_size: body.consent_size ?? null,
      });
      await refresh();
      return accepted;
    },
    [refresh],
  );

  useEffect(() => {
    // Initial load on mount; guarded by request id.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchPage("", null, false);
  }, [fetchPage]);

  // Status polling only: refresh the shared list while any visible case
  // is still queued or running. Never resubmits anything.
  const hasActive = cases.some((c) => !TERMINAL.has(c.execution_status));
  useEffect(() => {
    if (!hasActive) return;
    const timer = window.setInterval(() => {
      void fetchPage(executionFilter, null, false);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [hasActive, executionFilter, fetchPage]);

  const value = useMemo(
    () => ({
      cases,
      summary,
      total,
      loading,
      error,
      executionFilter,
      setExecutionFilter: changeFilter,
      refresh,
      loadMore,
      hasMore: cursor !== null,
      submit,
    }),
    [cases, summary, total, loading, error, executionFilter, changeFilter, refresh, loadMore, cursor, submit],
  );

  return <SwapDeskContext.Provider value={value}>{children}</SwapDeskContext.Provider>;
}

export function useSwapDesk() {
  const context = useContext(SwapDeskContext);
  if (!context) {
    throw new Error("useSwapDesk must be used within a SwapDeskProvider");
  }
  return context;
}

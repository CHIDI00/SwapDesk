"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  continueCase,
  getCase,
  getTimeline,
  isTerminalExecution,
  type AcceptResponse,
  type CaseDetail,
  type TimelineEvent,
} from "@/lib/api";

export type { CaseDetail, TimelineEvent, AcceptResponse };

/**
 * Saved case detail plus timeline, fetched by id so reloads and direct
 * links work without any in-memory state. Polls status while the run is
 * non-terminal. Continuation only ever fires from an explicit user
 * action through `sendContinue` — nothing here retries automatically.
 */
export function useCaseDetail(caseId: string | undefined) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    if (!caseId) {
      setLoading(false);
      setMissing(true);
      return;
    }
    const mine = ++requestId.current;
    setLoading(true);
    try {
      const [fetchedDetail, fetchedTimeline] = await Promise.all([
        getCase(caseId),
        getTimeline(caseId),
      ]);
      if (requestId.current !== mine) return;
      setDetail(fetchedDetail);
      setTimeline(fetchedTimeline);
      setMissing(false);
      setError(null);
    } catch (err) {
      if (requestId.current !== mine) return;
      if (err instanceof ApiError && err.status === 404) {
        setMissing(true);
        setDetail(null);
      } else {
        setError(err instanceof Error ? err.message : "Case failed to load");
      }
    } finally {
      if (requestId.current === mine) setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    // Initial load on mount or id change; guarded by request id.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const active =
    detail !== null && !isTerminalExecution(detail.execution_status);

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => {
      void load();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [active, load]);

  const sendContinue = useCallback(
    async (body: { message?: string | null; consent_size?: string | null }) => {
      if (!caseId) throw new Error("No case selected");
      setSending(true);
      try {
        const result = await continueCase(caseId, body);
        await load();
        return result;
      } finally {
        setSending(false);
      }
    },
    [caseId, load],
  );

  return { detail, timeline, loading, missing, error, sending, reload: load, sendContinue };
}

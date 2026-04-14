import { useEffect, useRef, useCallback } from "react";
import { submitTelemetry, TelemetryEvent } from "../lib/api";

export function useTelemetry(currentTab: string) {
  const tabStartRef = useRef<number>(Date.now());
  const sessionStartRef = useRef<number>(Date.now());
  const pendingRef = useRef<TelemetryEvent[]>([]);

  const flush = useCallback(async () => {
    if (pendingRef.current.length === 0) return;
    const batch = [...pendingRef.current];
    pendingRef.current = [];
    try {
      await submitTelemetry(batch);
    } catch {
      // silent fail — telemetry is best-effort
    }
  }, []);

  // Record time spent on previous tab when tab changes
  useEffect(() => {
    tabStartRef.current = Date.now();
    return () => {
      const secs = Math.round((Date.now() - tabStartRef.current) / 1000);
      if (secs >= 1 && currentTab !== "admin") {
        pendingRef.current.push({
          event_type: "tab_time",
          event_key: currentTab,
          count: 1,
          seconds: secs,
        });
      }
    };
  }, [currentTab]);

  // Flush every 30 seconds
  useEffect(() => {
    const id = setInterval(flush, 30_000);
    return () => clearInterval(id);
  }, [flush]);

  // Flush on tab hide; record session on unload
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "hidden") {
        const sessionSecs = Math.round((Date.now() - sessionStartRef.current) / 1000);
        if (sessionSecs >= 3) {
          pendingRef.current.push({
            event_type: "session",
            event_key: "app",
            count: 1,
            seconds: sessionSecs,
          });
        }
        flush();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [flush]);

  const trackClick = useCallback((key: string) => {
    pendingRef.current.push({ event_type: "click", event_key: key, count: 1, seconds: 0 });
  }, []);

  return { trackClick };
}

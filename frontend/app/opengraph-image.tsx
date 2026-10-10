import { ImageResponse } from "next/og";
import { SITE_NAME, SITE_TAGLINE } from "@/lib/seo";

export const alt = `${SITE_NAME} — ${SITE_TAGLINE}`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "72px",
          background: "#111113",
          backgroundImage:
            "radial-gradient(900px circle at 12% 0%, rgba(91,255,159,0.14), transparent 55%)",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: 64,
                height: 64,
                borderRadius: 16,
                background: "#5bff9f",
                color: "#0a0a0b",
                fontSize: 38,
                fontWeight: 700,
              }}
            >
              S
            </div>
            <div style={{ display: "flex", color: "#f4f4f5", fontSize: 36, fontWeight: 600 }}>
              {SITE_NAME}
            </div>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              border: "1px solid rgba(91,255,159,0.35)",
              background: "rgba(91,255,159,0.08)",
              color: "#5bff9f",
              padding: "10px 22px",
              borderRadius: 999,
              fontSize: 24,
            }}
          >
            <div style={{ display: "flex", width: 12, height: 12, borderRadius: 999, background: "#5bff9f" }} />
            Live · V2 Production
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div style={{ display: "flex", color: "#f4f4f5", fontSize: 72, fontWeight: 700, lineHeight: 1.08 }}>
            Autonomous exchange &amp; return support
          </div>
          <div style={{ display: "flex", color: "#a1a1aa", fontSize: 32, lineHeight: 1.3 }}>
            Middleware between your helpdesk and commerce stack — idempotent and policy-safe.
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ display: "flex", width: 8, height: 8, borderRadius: 999, background: "#5bff9f" }} />
          <div style={{ display: "flex", color: "#71717a", fontSize: 24, fontFamily: "monospace" }}>
            swapdesk · mission control · agent telemetry
          </div>
        </div>
      </div>
    ),
    { ...size }
  );
}

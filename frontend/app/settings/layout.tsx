import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Agent Settings",
  description: "Configure SwapDesk agent autonomy, retries, and verification guardrails.",
  path: "/settings",
});

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return children;
}

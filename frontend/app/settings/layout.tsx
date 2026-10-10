import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Agent Settings — SwapDesk",
  description: "Configure SwapDesk agent autonomy, retries and verification.",
  openGraph: {
    title: "Agent Settings — SwapDesk",
    description: "Configure agent autonomy and guardrails.",
  },
};

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return children;
}

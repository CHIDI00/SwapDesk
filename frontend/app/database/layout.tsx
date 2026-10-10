import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Database Schema — SwapDesk",
  description: "Tables the SwapDesk agent reads and writes.",
  openGraph: {
    title: "Database Schema — SwapDesk",
    description: "Tables the agent reads and writes.",
  },
};

export default function DatabaseLayout({ children }: { children: React.ReactNode }) {
  return children;
}

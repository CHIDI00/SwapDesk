import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Database Schema",
  description: "Tables the SwapDesk agent reads and writes during autonomous support.",
  path: "/database",
});

export default function DatabaseLayout({ children }: { children: React.ReactNode }) {
  return children;
}

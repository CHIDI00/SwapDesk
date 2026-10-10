import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Ticket Execution",
  description:
    "Inspect a SwapDesk ticket's autonomous execution timeline, SKU reservations, and agent actions.",
});

export default function TicketLayout({ children }: { children: React.ReactNode }) {
  return children;
}

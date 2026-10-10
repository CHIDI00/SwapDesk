import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Inventory",
  description: "Live stock levels and agent reservations across warehouses.",
  path: "/inventory",
});

export default function InventoryLayout({ children }: { children: React.ReactNode }) {
  return children;
}

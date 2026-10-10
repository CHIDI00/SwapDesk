import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Inventory — SwapDesk",
  description: "Live stock and agent reservations across warehouses.",
  openGraph: {
    title: "Inventory — SwapDesk",
    description: "Live stock and agent reservations.",
  },
};

export default function InventoryLayout({ children }: { children: React.ReactNode }) {
  return children;
}

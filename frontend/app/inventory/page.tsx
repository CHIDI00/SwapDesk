import type { Metadata } from "next";
import { AppShell, PageTitle } from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Inventory — SwapDesk",
  description: "Live stock and agent reservations across warehouses.",
  openGraph: {
    title: "Inventory — SwapDesk",
    description: "Live stock and agent reservations.",
  },
};

const items = [
  { sku: "AJ4-MIL-43", name: "Air Jordan 4 Military", size: 43, stock: 7, res: 1, wh: "WH-AMS-02" },
  { sku: "AJ4-MIL-42", name: "Air Jordan 4 Military", size: 42, stock: 3, res: 0, wh: "WH-AMS-02" },
  { sku: "SMB-OG-41", name: "Adidas Samba OG", size: 41, stock: 12, res: 2, wh: "WH-BER-01" },
  { sku: "NB550-GRY-39", name: "New Balance 550 Grey", size: 39, stock: 0, res: 0, wh: "WH-BER-01" },
  { sku: "GK30-BLK-44", name: "Asics Gel-Kayano 30", size: 44, stock: 5, res: 1, wh: "WH-AMS-02" },
];

export default function InventoryPage() {
  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Inventory" }]}>
      <PageTitle title="Inventory" sub="Reservations made by the agent are locked until the exchange ships." />
      <div className="panel overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr className="border-b border-hairline">
              {["SKU", "Product", "Size", "Available", "Reserved", "Warehouse"].map((h) => (
                <th key={h} className="px-5 py-3 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {items.map((i) => (
              <tr key={i.sku} className="hover:bg-accent/30">
                <td className="px-5 py-3 font-mono text-xs">{i.sku}</td>
                <td className="px-5 py-3">{i.name}</td>
                <td className="num px-5 py-3">{i.size}</td>
                <td className={`num px-5 py-3 ${i.stock === 0 ? "text-danger" : ""}`}>{i.stock}</td>
                <td className={`num px-5 py-3 ${i.res ? "text-success" : "text-muted-foreground"}`}>{i.res}</td>
                <td className="px-5 py-3 font-mono text-xs text-muted-foreground">{i.wh}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}

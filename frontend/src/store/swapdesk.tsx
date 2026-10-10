"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

export type TicketStatus = "resolved" | "escalated" | "processing";

export type Ticket = {
  id: string;
  message: string;
  status: TicketStatus;
  statusLabel: string;
  actions: string[];
  time: string;
  sku: string;
};

export type InventoryItem = {
  sku: string;
  name: string;
  size: number;
  stock: number;
  res: number;
  wh: string;
};

export const MOCK_TICKET = {
  message: "Jordan 4 size 43 exchange",
  status: "resolved" as TicketStatus,
  statusLabel: "Resolved Autonomously",
  actions: ["RESERVE_STOCK", "CREATE_LABEL"],
  time: "Just now",
  sku: "AJ4-MIL-43",
};

const createInitialTickets = (): Ticket[] => [
  {
    id: "TCK-9042",
    message: "Jordan 4s are too tight, need size 43.",
    status: "resolved",
    statusLabel: "Resolved Autonomously",
    actions: ["RESERVE_STOCK", "CREATE_LABEL"],
    time: "Just now",
    sku: "AJ4-MIL-43",
  },
  {
    id: "TCK-9043",
    message: "I want a refund but I bought these 90 days ago.",
    status: "escalated",
    statusLabel: "Escalated to Human",
    actions: ["POLICY_DENY"],
    time: "2 min ago",
    sku: "SMB-OG-41",
  },
  {
    id: "TCK-9044",
    message: "Need a size 10 exchange.",
    status: "resolved",
    statusLabel: "Resolved (Recovered)",
    actions: ["API_TIMEOUT_RECOVERED"],
    time: "5 min ago",
    sku: "GK30-BLK-44",
  },
];

const createInitialInventory = (): InventoryItem[] => [
  { sku: "AJ4-MIL-43", name: "Air Jordan 4 Military", size: 43, stock: 5, res: 1, wh: "WH-AMS-02" },
  { sku: "AJ4-MIL-42", name: "Air Jordan 4 Military", size: 42, stock: 3, res: 0, wh: "WH-AMS-02" },
  { sku: "SMB-OG-41", name: "Adidas Samba OG", size: 41, stock: 12, res: 2, wh: "WH-BER-01" },
  { sku: "NB550-GRY-39", name: "New Balance 550 Grey", size: 39, stock: 0, res: 0, wh: "WH-BER-01" },
  { sku: "GK30-BLK-44", name: "Asics Gel-Kayano 30", size: 44, stock: 5, res: 1, wh: "WH-AMS-02" },
];

type SwapDeskContextValue = {
  tickets: Ticket[];
  inventory: InventoryItem[];
  simulateTicket: () => Ticket;
  submitCustomerTicket: (message: string) => Ticket;
  resetMockData: () => void;
  getTicket: (id: string) => Ticket | undefined;
};

const SwapDeskContext = createContext<SwapDeskContextValue | null>(null);

export function SwapDeskProvider({ children }: { children: ReactNode }) {
  const [tickets, setTickets] = useState<Ticket[]>(createInitialTickets);
  const [inventory, setInventory] = useState<InventoryItem[]>(createInitialInventory);
  const seq = useRef(9045);

  const simulateTicket = useCallback(() => {
    const ticket: Ticket = { id: `TCK-${seq.current++}`, ...MOCK_TICKET };
    setTickets((prev) => [ticket, ...prev]);
    setInventory((prev) =>
      prev.map((item) =>
        item.sku === MOCK_TICKET.sku
          ? { ...item, stock: Math.max(0, item.stock - 1), res: item.res + 1 }
          : item,
      ),
    );
    return ticket;
  }, []);

  const submitCustomerTicket = useCallback((message: string) => {
    const text = message.trim() || "My Jordan 4s arrived but are too tight. I need to exchange for a size 43.";
    const ticket: Ticket = {
      id: `TCK-${seq.current++}`,
      message: text,
      status: "processing",
      statusLabel: "Agent Processing",
      actions: ["INTAKE", "ROUTING"],
      time: "Just now",
      sku: "AJ4-MIL-43",
    };
    setTickets((prev) => [ticket, ...prev]);
    return ticket;
  }, []);

  const resetMockData = useCallback(() => {
    setTickets([]);
    setInventory(createInitialInventory());
  }, []);

  const getTicket = useCallback((id: string) => tickets.find((ticket) => ticket.id === id), [tickets]);

  const value = useMemo(
    () => ({ tickets, inventory, simulateTicket, submitCustomerTicket, resetMockData, getTicket }),
    [tickets, inventory, simulateTicket, submitCustomerTicket, resetMockData, getTicket],
  );

  return <SwapDeskContext.Provider value={value}>{children}</SwapDeskContext.Provider>;
}

export function useSwapDesk() {
  const context = useContext(SwapDeskContext);
  if (!context) {
    throw new Error("useSwapDesk must be used within a SwapDeskProvider");
  }
  return context;
}

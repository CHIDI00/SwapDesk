import type { Metadata } from "next";
import { Bricolage_Grotesque, Geist_Mono, Plus_Jakarta_Sans } from "next/font/google";
import { Toaster } from "sonner";
import { SwapDeskProvider } from "@/store/swapdesk";
import "./globals.css";

const jakartaSans = Plus_Jakarta_Sans({
  variable: "--font-jakarta",
  subsets: ["latin"],
});

const bricolage = Bricolage_Grotesque({
  variable: "--font-bricolage",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Mission Control — SwapDesk",
  description:
    "Monitor autonomous support performance, policy safety, and live SwapDesk agent executions.",
  openGraph: {
    title: "Mission Control — SwapDesk",
    description: "Live agent performance and support execution monitoring.",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${jakartaSans.variable} ${bricolage.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <SwapDeskProvider>
          {children}
          <Toaster theme="dark" position="bottom-right" richColors />
        </SwapDeskProvider>
      </body>
    </html>
  );
}

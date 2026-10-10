# SwapDesk Frontend

The frontend dashboard for **SwapDesk** — autonomous middleware between a e-commerce helpdesk and its commerce stack that resolves exchanges, returns, and refunds safely. It is an idempotent, policy-aware agent runtime.

Built as a self-contained Next.js app with **client-side demo state** — no backend is required to run or demo it.

## Tech Stack

- **Next.js 16.4.0** (App Router, Turbopack, `cacheComponents` + `partialPrefetching` enabled)
- **React 19** with Server & Client Components
- **TypeScript** (strict), path alias `@/*` → `./src/*`
- **Tailwind CSS v4** (CSS-first theme tokens in `app/globals.css`)
- **lucide-react** icons
- **sonner** toasts
- Fonts via `next/font/google`: **Bricolage Grotesque** (display), **Plus Jakarta Sans** (body), **Geist Mono** (technical/mono)

## Getting Started

```bash
npm install      # install dependencies
npm run dev      # start the development server (http://localhost:3000)
```

Other scripts:

| Script          | Description                                    |
| --------------- | ---------------------------------------------- |
| `npm run build` | Production build (static + partial prerender)  |
| `npm run start` | Serve the production build                     |
| `npm run lint`  | ESLint (flat config)                           |

## Environment Variables

| Variable                 | Default                             | Purpose                                                                |
| ------------------------ | ----------------------------------- | ---------------------------------------------------------------------- |
| `NEXT_PUBLIC_SITE_URL`   | `https://swapdesk.vercel.app`       | Canonical origin used for `metadataBase`, canonical URLs, sitemap, robots. Override when deploying. |

## Project Structure

```
app/
├── layout.tsx              # Root layout, global <head> metadata, fonts, SwapDeskProvider, Toaster
├── page.tsx                # Server entry → renders <MissionControl />
├── mission-control.tsx     # "Mission Control" home (client) — metrics + live queue
├── inbox/page.tsx          # Full ticket inbox (static demo data)
├── inventory/              # Live stock + reservations (client; stock reacts to simulations)
│   ├── layout.tsx          #   metadata
│   └── page.tsx
├── database/layout.tsx     # Schema view (metadata)
├── integrations/           # Inbound webhook triggers (Zendesk, Shopify Inbox, Gorgias)
│   ├── layout.tsx          #   metadata
│   └── page.tsx
├── settings/layout.tsx     # Agent autonomy/guardrail settings (metadata)
├── simulate/page.tsx       # Customer Simulation — inject a ticket into the queue
├── ticket/[id]/page.tsx    # Ticket execution detail (Suspense split; see below)
├── robots.ts               # /robots.txt
├── sitemap.ts              # /sitemap.xml
├── opengraph-image.tsx     # Generated OG image (ImageResponse)
├── twitter-image.tsx       # Re-exports from opengraph-image
└── globals.css             # Theme tokens + utilities (panel, glass, pulse-dot, num, rise)

src/
├── components/
│   ├── AppShell.tsx                # Sidebar + top bar + mobile bottom nav, "Simulate Ticket" button
│   └── CustomerSimulationWidget.tsx
├── lib/
│   ├── seo.ts                      # SITE_* constants + pageMetadata() helper
│   └── utils.ts                    # cn() (clsx + tailwind-merge)
└── store/
    └── swapdesk.tsx                # Global demo state + SwapDeskProvider
```

## Demo Flow

Everything is driven by a client-side store — no network calls.

1. Click **Simulate Ticket** (top bar) or open **Customer Simulation** (`/simulate`), type a complaint, and submit.
2. The store appends a ticket with status `Agent Processing` (`INTAKE` / `ROUTING` actions).
3. It appears instantly in **Mission Control** and the **Inbox**, filterable by status.
4. Open any ticket to inspect its execution timeline, actions, and SKU reservation.
5. **Simulate Ticket** also decrements stock for `AJ4-MIL-43` (5 → 4) — visible on `/inventory`.
6. **Reset Mock Data** (inventory page) clears tickets and restores stock.

## State Management

`src/store/swapdesk.tsx` exposes a `SwapDeskProvider` (mounted in `app/layout.tsx`) plus a `useSwapDesk()` hook:

```ts
const { tickets, inventory, simulateTicket, submitCustomerTicket, resetMockData, getTicket } =
  useSwapDesk();
```

- `TicketStatus` = `"resolved" | "escalated" | "processing"`
- `simulateTicket(): Ticket` — prepends `TCK-9045+` resolved ticket, decrements `AJ4-MIL-43` stock.
- `submitCustomerTicket(message): Ticket` — prepends a `processing` ticket with your message.
- `resetMockData()` — wipes tickets, restores initial inventory.
- `getTicket(id)` — look up a single ticket.

## Routes

| Route                 | Page                    | Type            | Notes                              |
| --------------------- | ----------------------- | --------------- | ---------------------------------- |
| `/`                   | Mission Control         | server + client | metrics + live queue, filter       |
| `/inbox`              | Inbox                   | server          | static ticket list                 |
| `/inventory`          | Inventory               | server layout + client page | stock reacts to simulations |
| `/database`           | Database Schema         | server          |                                    |
| `/integrations`       | Integrations            | server layout + client page | webhook toggle + URL copy  |
| `/settings`           | Agent Settings          | server          |                                    |
| `/simulate`           | Customer Simulation     | server          | `CustomerSimulationWidget`         |
| `/ticket/[id]`        | Ticket Execution        | client          | Partial Prerender (Suspense)       |
| `/robots.txt`         | —                       | metadata route  | auto-generated                     |
| `/sitemap.xml`        | —                       | metadata route  | auto-generated                     |
| `/opengraph-image`    | —                       | image route     | generated 1200×630 PNG             |
| `/twitter-image`      | —                       | image route     | re-export of opengraph-image       |

> **Turbopack dynamic route note:** `/ticket/[id]` must pre-render its HTML shell at build time. Client hooks that need URL data (`useParams`, `usePathname`) therefore live behind `<Suspense>` and out of the static shell. See `app/ticket/[id]/page.tsx`.

## Design System

Theme tokens live in `app/globals.css` as CSS variables and Tailwind v4 `@theme` mappings:

- Colors: `--card: #111113`, `--border: #222225`, `--color-success` (green), `--color-primary`, `--color-warning`, `--color-danger`, `--color-hairline`
- Type: `font-display` (`--font-bricolage`), `font-sans` (`--font-jakarta`), `font-mono` (`--font-geist-mono`)
- Utilities: `panel` (card), `glass` (frosted nav), `pulse-dot`, `num` (tabular numerals), `rise` (entry animation)

> **Guideline:** keep server-rendered pages static where possible and move interactivity into client components. Do not introduce a visual redesign — extend the existing token system.

## SEO

Add full metadata to every segment:

- Root (`app/layout.tsx`): `metadataBase`, titles with `template: "%s · SwapDesk"`, description, keywords, `<viewport>` (themeColor), OpenGraph + Twitter cards, `robots`, `applicationName`, authors, category.
- Per page: use the `pageMetadata({ title, description, path })` helper from `src/lib/seo.ts` (marked `Export const metadata`).
- Images: `app/opengraph-image.tsx` generates a themed 1200×630 card with `ImageResponse`; `app/twitter-image.tsx` re-exports it.
- Crawling: `app/robots.ts` and `app/sitemap.ts` reflect the remaining routes.

Set the title without the site name suffix — the root template appends ` · SwapDesk`.

## Deploy

Deploy on Vercel (or any Node host running `npm run build && npm run start`):

```bash
npm run build
npm run start
```

Set `NEXT_PUBLIC_SITE_URL` to your production origin so canonical URLs, sitemap, and robots are correct.
# XLANORA Architecture

Status: **Phase 1 proposal**, pending approval.

## 1. Stack

| Concern | Choice | Why |
|---|---|---|
| Framework | Next.js 15, App Router, TypeScript | Server Components keep data access off the client. |
| Styling | Tailwind CSS v4, tokens in `app/globals.css` | One place for brand colors and fonts. |
| Auth | Supabase Auth (`@supabase/ssr`) | Cookie sessions that Server Components can read. |
| Database | Supabase PostgreSQL | Relational data, constraints and RLS in one place. |
| Storage | Supabase Storage (public bucket for images) | Images served through the Next.js image optimizer. |
| Icons | lucide-react | Requested. |
| Validation | zod | Same schemas on server actions and route handlers. |
| Hosting | Netlify (`@netlify/plugin-nextjs`) | Free `*.netlify.app` subdomain. |

## 2. Folder layout

```
app/          Routes (App Router). Route groups: (public), (auth), (customer), (provider), (admin)
components/   Presentational UI. brand/ for logo, ui/ for primitives, feature folders later.
lib/
  config/     Site and category configuration (non-secret)
  supabase/   Browser, server and service-role clients
  db/         All database queries and mutations
hooks/        Client-side React hooks only
types/        Shared domain types
supabase/
  migrations/ Versioned SQL migrations (schema, indexes, RLS, functions)
public/       Static assets, brand files
docs/         Architecture and decisions
```

Rule: UI components never import from `lib/supabase` directly. They receive data as props or call server actions in `lib/db`.

## 3. Data model (planned)

Tables: `profiles`, `categories`, `providers`, `services`, `availability`, `bookings`, `reviews`.

- `profiles.id` references `auth.users.id`. The `role` column is the only source of authorization. It is changed only by admins or a trigger, never by the client.
- `providers.id` references `profiles.id`, one provider profile per provider user.
- `services` reference `providers` and `categories`. Price is `price_halalas integer check (price_halalas >= 0)`.
- `availability` holds weekly rules per provider (`weekday`, `start_time`, `end_time`), with `check (end_time > start_time)`.
- `bookings` store a price snapshot and a `tstzrange` of the appointment.
- `reviews` have a unique `booking_id`, so one review per booking, and only for `completed` bookings.

### Double-booking protection (database level)

A partial exclusion constraint on `bookings` prevents overlapping active bookings for the same provider:

```sql
exclude using gist (
  provider_id with =,
  tstzrange(starts_at, ends_at, '[)') with &&
) where (status in ('pending', 'confirmed'));
```

This needs the `btree_gist` extension. Server code also checks availability first to give friendly errors, but the constraint is the real guarantee.

### Row Level Security (summary)

- **customer**: reads and updates own profile; reads own bookings; creates bookings for itself; cancels own bookings within the window; creates reviews for own completed bookings.
- **provider**: manages own provider profile, services, availability; reads and updates status of bookings where `provider_id = auth.uid()`.
- **admin**: reads everything; changes statuses and moderation flags. Admin check uses a `SECURITY DEFINER` helper function, not a client claim.
- **anonymous**: reads only `published` services, `approved` providers, active categories and visible reviews.

## 4. Booking flow (planned, Phase 5)

1. Customer picks a service and a day. Client requests slots from the server.
2. Server computes slots from `availability` in the provider's timezone, removes past times and times inside the lead window, and removes overlaps with active bookings.
3. Customer submits. The server action re-validates everything and reads the price from `services`, never from the form.
4. Insert into `bookings`. If the exclusion constraint fires, return a "slot just taken" error.
5. Status moves: `pending → confirmed | rejected` (provider), `pending|confirmed → cancelled` (customer within window, or provider), `confirmed → completed` (provider, after the appointment time).

## 5. Search (planned, Phase 4)

Server-side queries against Postgres: full-text search on service title and description, `ilike` on provider name, city and category filters, `price_halalas` range, and sorting by price, rating or date. Results are paginated. Nothing is filtered in the browser.

## 6. Internationalization and currency

- Locales: English (LTR) and Arabic (RTL). `dir` on `<html>` follows the locale.
- Currency: SAR, displayed with `Intl.NumberFormat`. Stored as integer halalas.
- Timezone: providers have a timezone (default `Asia/Riyadh`). Times are stored in UTC and shown in the viewer's chosen display timezone.

## 7. Open decisions (need your answer)

1. **Brand name in Arabic.** Do you want "إكسلانورا" as the Arabic wordmark, or keep "XLANORA" in both languages?
2. **Booking approval.** Should provider approval be required for every booking (current plan), or can providers enable instant booking per service?
3. **Provider sign-up.** Should new providers be auto-approved, or go to `pending` until an admin approves them (current plan: pending)?
4. **Reviews.** Only after a completed booking (current plan), or anyone who booked?
5. **Cities.** Start with a fixed list of Saudi cities, or free text with suggestions?
6. **Images.** Do you have licensed images, or should I use stock sources you approve? I cannot download copyrighted photos, so I will need your choice or your files.
7. **Supabase project.** Do you already have a Supabase project and a Netlify account, or should I write setup steps only?
8. **Email.** Forgot-password emails need an email sender. Supabase's built-in sender works for development but has strict limits.

## 8. Phase 1 verification

- Folder structure created as specified.
- Config files (`package.json`, `tsconfig.json`, `next.config.mjs`, `netlify.toml`, `.env.example`) written.
- Domain types and seed categories written.
- Placeholder home page and logo written.

Not yet verified: `npm install`, `npm run build` and `npm run typecheck`. The sandbox cannot install packages right now. These must run on your machine or after network access is enabled.

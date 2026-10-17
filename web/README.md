# Wilinski Atlas: the website

The public version of the atlas. A visitor runs a short setup wizard, sees every US
county and town scored against their own answers, and can sign up to save their map, use
it on a phone, and share it with a partner.

```
Python pipeline (repo root) --make atlas--> output/atlas/{data,geo}   ~30 MB of static data
web/ (Vite app) --npm run build--> web/dist                           static site, any host
                                      |  scores in the browser; no server does the math
                                      v
                          Supabase: sign-in + saved maps only (small rows)
```

The heavy data never touches Supabase. Its free plan has 5 GB of egress a month, so
serving 30 MB of map data from it would run out after about 170 visitors; a static
host serves it for free.

## Run it locally

```bash
make data universe features atlas   # from the repo root, once (~10 min, ~1 GB download)
cd web
npm install
npm run dev                         # http://localhost:5173
```

With no Supabase settings the site runs in **this-device-only** mode: everything works,
and maps are saved in the browser. That is also how the preview artifact runs.

## Turn on accounts (Supabase)

1. **Create a project** at supabase.com. Free plan is fine to start.
2. **Create the tables.** SQL Editor → New query → paste
   `supabase/migrations/0001_init.sql` → Run.
3. **Sign-in methods.** Authentication → Providers:
   - Email: on. Magic links are the default; no passwords to manage.
   - Google: on, with a Google Cloud OAuth client (Supabase's page links the steps).
4. **Where sign-in links come back to.** Authentication → URL Configuration:
   - Site URL: your domain, e.g. `https://atlas.example.com`
   - Redirect URLs: the same, plus `http://localhost:5173` for development.
5. **The two public values.** Project Settings → API:
   - Project URL → `VITE_SUPABASE_URL`
   - `anon` / publishable key → `VITE_SUPABASE_ANON_KEY`

   Put them in `web/.env.local` for development, and in GitHub (Settings → Secrets and
   variables → Actions → **Variables**) for deploys. They are public by design: the
   row-level security in the migration decides what anyone can read or write.
   **Never use the `service_role` key anywhere in this app.**

Free Supabase projects pause after a week with no activity; a site people use never
pauses, and Pro ($25/month) never does.

## Deploy (Cloudflare Pages)

`.github/workflows/web.yml` builds the data, runs every test, builds the site, and on
`main` deploys it when these are set:

| Where | Name | Value |
|---|---|---|
| Variables | `CF_PAGES_PROJECT` | your Pages project name |
| Secrets | `CLOUDFLARE_API_TOKEN` | a token with "Cloudflare Pages: Edit" |
| Secrets | `CLOUDFLARE_ACCOUNT_ID` | from the Cloudflare dashboard |
| Variables | `VITE_DONATE_URL` | optional: a Stripe Payment Link for the Support button |

It also runs monthly so rents and prices stay current. Any static host works instead:
upload `web/dist`.

## Tests

```bash
npm test                         # wizard arithmetic (node)
make test-db                     # row-level security on a throwaway Postgres (non-root)
python -m unittest tests.test_atlas   # page scoring held to the Python engine
```

`supabase/tests/rls.sql` signs in as four different people and checks that a stranger
sees nothing of another household, an invite works once, a full couple takes nobody else,
and deleting an account leaves the partner's map intact.

## Before a public launch

- **Zillow's terms.** Rents and home values are Zillow Research data, recorded in
  `config/sources.yaml` as free for non-commercial use with attribution. Read the current
  terms at zillow.com/research/data before taking money for anything. HUD's Small Area
  Fair Market Rents are a public-domain fallback; they run lower than market asking rents.
- **Sensitive layers.** Religion, political lean and foreign-born share are opt-in sliders
  with a visitor-chosen direction that never hide a place. Steering home-seekers by a
  protected characteristic is illegal under the Fair Housing Act; get a fair-housing
  lawyer's read before opening the site beyond friends and family.
- **Privacy.** A privacy notice and terms page, linked from the site. Settings can
  include sensitive preferences, so the account menu's delete button removes everything.

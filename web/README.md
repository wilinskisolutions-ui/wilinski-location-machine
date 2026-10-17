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

`npm run build` makes the website in `dist/` with accounts switched on (the project's
public URL and anon key are in `.env.production`). `npm run build:preview` makes a
no-login copy in `dist-preview/` for a claude.ai artifact.

## Supabase: one-time setup

The project is `dvcqgoligcixiegyhnol`. Its URL and anon key are already in
`.env.production`; they are public by design (they ship in the site's JavaScript), and
the row-level security in the migration decides what anyone can read or write.
**Never put the `service_role` key anywhere in this app.**

1. **Create the tables.** Supabase → SQL Editor → **New query** → paste all of
   `supabase/migrations/0001_init.sql` → **Run**. If a "destructive operation" warning
   appears, choose **Run this query** (the only deletes are inside the delete-my-account
   function). It is safe to run again if anything goes wrong the first time.
   Success looks like "Success. No rows returned".
2. **Where sign-in links come back to.** Authentication → **URL Configuration**:
   - Site URL: your Netlify address, e.g. `https://wilinski-atlas.netlify.app`
   - Redirect URLs: the same address, plus `http://localhost:5173/**` for development.
3. **Email that reaches people.** Supabase's built-in email only delivers to members of
   your Supabase team, at about 2 emails an hour. Anyone else gets "Email address not
   authorized" (the site explains this to them). Two ways forward:
   - Testing with a few people: add them under Organization → Team.
   - Anyone at all: Authentication → Emails → **SMTP Settings**, using a sender such as
     Resend or Brevo (both have free tiers). Use an address on a domain you own.
4. **Google sign-in (optional, later).** Authentication → Providers → Google, with a
   Google Cloud OAuth client. The site shows the Google button only once it is on.

## Netlify

**First deploy, by hand:** build `dist/` (or use the zip from the session), then drag the
folder onto app.netlify.com/drop. Netlify gives the site an address; put that address in
Supabase step 2.

**After that, automatically:** `.github/workflows/web.yml` rebuilds the data, runs every
test, builds the site and deploys it on every push to `main`, and monthly so prices stay
current. It needs, in GitHub → Settings → Secrets and variables → Actions:

| Kind | Name | Where to find it |
|---|---|---|
| Secret | `NETLIFY_AUTH_TOKEN` | Netlify → User settings → Applications → Personal access tokens |
| Variable | `NETLIFY_SITE_ID` | Netlify → your site → Site configuration → Site ID |
| Variable | `VITE_DONATE_URL` | optional: a Stripe Payment Link for the Support button |

Netlify never builds this repository itself: `netlify.toml` at the repo root cancels
its git-triggered builds. Building the data needs about a gigabyte of downloads, which the
GitHub workflow caches and Netlify's builder would not, and without that file a connected
repository gets published as-is, with no index.html at its root ("Page not found").
`public/_headers` sets caching and a Content-Security-Policy.

If the live site ever shows "Page not found": Netlify → Deploys → open the last good
deploy (a manual upload or a "Deployed by GitHub Actions" one) → **Publish deploy**.

## Tests

```bash
npm test                              # wizard arithmetic (node)
make test-db                          # row-level security on a throwaway Postgres (non-root)
python -m unittest tests.test_web     # the first-visit path in Chromium
python -m unittest tests.test_atlas   # page scoring held to the Python engine
```

`supabase/tests/rls.sql` signs in as four different people and checks that a stranger
sees nothing of another household, an invite works once, a full couple takes nobody else,
and deleting an account leaves the partner's map intact. `auth_stub.sql` reproduces
Supabase's defaults (extensions in their own schema, every new table granted to the API
roles), which is what the first version of the migration tripped over.

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

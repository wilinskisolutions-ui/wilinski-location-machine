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
2. **Put the code in the sign-in emails.** People sign in by typing a code the site emails
   them. Supabase's default emails carry only a link, so in Authentication → **Emails** →
   Templates, edit both **Magic Link** (existing accounts) and **Confirm signup** (new
   ones) so the body shows `{{ .Token }}`, for example:

   ```html
   <h2>Your Wilinski Atlas code</h2>
   <p>Type this code on the site to sign in: <strong>{{ .Token }}</strong></p>
   <p>It works once and expires in an hour. If you didn't ask for it, ignore this email.</p>
   ```
   Subject: `Your Wilinski Atlas code`. Without this the email still has a link, which
   works only when opened on the same device and browser that asked for it.
3. **Where an email's link comes back to.** Authentication → **URL Configuration**:
   - Site URL: `https://wilinskiatlas.netlify.app`
   - Redirect URLs: the same address with `/**`, plus `http://localhost:5173/**` for
     development.
4. **Email that reaches people.** Supabase's built-in email only delivers to members of
   your Supabase team, at about 2 emails an hour. Anyone else gets "Email address not
   authorized" (the site explains this to them). Two ways forward:
   - Testing with a few people: add them under Organization → Team.
   - Anyone at all: Authentication → Emails → **SMTP Settings**, using a sender such as
     Resend or Brevo (both have free tiers). Use an address on a domain you own.
5. **Google sign-in (optional, later).** Authentication → Providers → Google, with a
   Google Cloud OAuth client. The site shows the Google button only once it is on.

## Netlify

`.github/workflows/web.yml` rebuilds the data, runs every test and builds the site on
every push to `main`, and monthly so prices stay current. It then force-pushes the
finished site, as a single commit, to the **`site`** branch. Netlify publishes that branch
as it is: no build, and no Netlify token stored anywhere.

One-time setting: Netlify → your site → Site configuration → Build & deploy → Continuous
deployment → Branches and deploy contexts → **Configure** → Production branch: `site` →
Save. Then Deploys → Trigger deploy → Deploy site, once; after that every publish deploys
by itself.

Donations: the floating "buy me a coffee" banner and the menus' "Support this project"
link go to `VITE_DONATE_URL`, a Stripe Payment Link set in `.env.production`. A repository
variable of the same name (GitHub → Settings → Secrets and variables → Actions →
Variables) overrides it without a code change.

Netlify never builds this repository's code: building the data needs about a gigabyte of
downloads, which the GitHub workflow caches and Netlify's builder would not. The `site`
branch carries its own `netlify.toml` (from `netlify.site.toml`) that only publishes. The
one at the repo root cancels builds of every other branch, because a connected repository
otherwise gets published as-is, with no index.html at its root ("Page not found").
A deploy started by hand in Netlify while the production branch is still `main` fails
("Deploy directory 'web/dist' does not exist") and leaves the live site as it was.
`public/_headers` sets caching and a Content-Security-Policy.

If the live site ever shows "Page not found": Netlify → Deploys → open the last good
deploy → **Publish deploy**.

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
- **Sensitive layers.** Religion and political lean are opt-in sliders
  with a visitor-chosen direction that never hide a place. Steering home-seekers by a
  protected characteristic is illegal under the Fair Housing Act; get a fair-housing
  lawyer's read before opening the site beyond friends and family.
- **Privacy.** A privacy notice and terms page, linked from the site. Settings can
  include sensitive preferences, so the account menu's delete button removes everything.

# DentistryUSA starter kit

A static site built from the public NPI registry data for Florida dentists. No frameworks, no database, no Stripe.
A preview is live at https://dentistryusa.netlify.app (Netlify builds it from this repo).

## What's in the folder
- `build.py`: reads `data/fl-dentists-seed.csv`, writes the whole site to `dist/`. Python 3, standard library only.
- `style.css`: the one shared stylesheet. The colours are variables at the top. `test_build.py`: sanity checks.
- `data/fl-dentists-seed.csv`: 16,874 FL dentists (NPPES, public).
- `netlify.toml`: tells Netlify to run `python3 build.py` and publish `dist/`.
- `dist/`: the generated site (not in git; safe to delete and rebuild).

## Build
    python3 build.py        # takes a few seconds, writes dist/
    python3 test_build.py   # should print OK

Set `SEED_CSV=/path/to/other.csv` to build from a different file.
On Windows, run both with `python -X utf8`.

## Deploy
**Netlify (the current preview):** push to `main`. `netlify.toml` builds the site and publishes `dist/`.

**Cloudflare Pages:** connect the repo with build command `python3 build.py` and output directory `dist`, or build locally and run `npx wrangler pages deploy dist`.
`dist/` is in `.gitignore`, so it is not committed. Pages handles the trailing-slash URLs by itself.

## What the site has now
- Home, with the search box (live results from `search.json`). `/?q=...` runs a search; the small search box in the header of the other pages uses that.
- `/fl/`, and `/fl/specialty/<specialty>/` (the cities that have that specialty).
- `/fl/<city>/` and `/fl/<city>/<specialty>/`.
- `/dentist/<npi>-<name>/` profiles (Dentist JSON-LD, "Claim your free listing" button).
- `/pricing/` (buttons say "Coming soon") and `/claim/` (form posts nowhere).
- `sitemap.xml`, `robots.txt`.

Rows without a city are skipped. PO box addresses show "Address on file". No reviews, no "verified" badge, no emails shown. Phone is the public practice phone from NPPES.

## Look
The layout follows the usual doctor-directory pattern: a search-first home page, specialty tiles, city lists, dentist cards with initials, and a claim box beside each profile.
The colours, the tooth mark and the text are DentistryUSA's own. There are no photos, ratings or booking, because the data has none.
The font is Plus Jakarta Sans, loaded from Google Fonts.

## What's left for Jelo (spec: docs/1100-dentistryusa-spec.md)
1. Claim backend (section 4): `/claim/` has a TODO comment. Needs a form endpoint, magic-link email, claim table.
2. Stripe in **test mode** on Mike's account (section 5), then wire the pricing buttons and the ROI slider (section 7).
3. Preview-site generator (section 6), `/remove`, `/advertising`, `/terms`, `/privacy` pages (copy is in section 8).
4. AI sales agent (sections 4-9). Attorney reads the scripts first (section 10).
5. Licensed/verified badge: only after the FL MQA license file is pulled.
6. City pages list every dentist on one page (no 25/page pagination yet). Big cities are long.
7. Spec's pricing copy lists a license badge on the Listing tier; I left it out for the reason in item 5. Put it back when MQA data exists.

## Size
- 18,962 HTML pages: 16,874 profiles, 1,610 city+specialty, 461 city pages, 13 specialty pages, plus home, /fl/, pricing, claim
- dist is about 80 MB of real bytes. search.json is 2.4 MB (the host compresses it). A profile page is about 3.5 KB; the biggest page is Miami, at about 300 KB.
- Cloudflare Pages free tier allows 20,000 files per deploy; this is 18,968 files, so it is close. Adding pages (e.g. /remove, /terms) is fine, but a second state needs a different split.

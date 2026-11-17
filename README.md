# DentistryUSA starter kit

A static site built from the public NPI registry data for Florida dentists. No frameworks, no database, no Stripe. Nothing here is deployed.

## What's in the folder
- `build.py`: reads `data/fl-dentists-seed.csv`, writes the whole site to `dist/`. Python 3, standard library only.
- `style.css`: the one shared stylesheet. `test_build.py`: sanity checks.
- `data/fl-dentists-seed.csv`: 16,874 FL dentists (NPPES, public).
- `dist/`: the generated site (safe to delete and rebuild).

## Build
    python3 build.py        # takes a few seconds, writes dist/
    python3 test_build.py   # should print OK

Set `SEED_CSV=/path/to/other.csv` to build from a different file.

## Deploy on Cloudflare Pages
Either connect the repo with **build command: none** and **output directory: dist** (commit `dist/`), or run `npx wrangler pages deploy dist`.
Pages handles the trailing-slash URLs by itself.

## What the site has now
Home (live search from `search.json`), `/fl/`, `/fl/<city>/`, `/fl/<city>/<specialty>/`, `/dentist/<npi>-<name>/` profiles (Dentist JSON-LD, "Claim your free listing" button), `/pricing/` (buttons say "Coming soon"), `/claim/` (form posts nowhere), `sitemap.xml`, `robots.txt`.
Rows without a city are skipped. PO box addresses show "Address on file". No reviews, no "verified" badge, no emails shown. Phone is the public practice phone from NPPES.

## What's left for Jelo (spec: docs/1100-dentistryusa-spec.md)
1. Claim backend (section 4): `/claim/` has a TODO comment. Needs a form endpoint, magic-link email, claim table.
2. Stripe in **test mode** on Mike's account (section 5), then wire the pricing buttons and the ROI slider (section 7).
3. Preview-site generator (section 6), `/remove`, `/advertising`, `/terms`, `/privacy` pages (copy is in section 8).
4. AI sales agent (sections 4-9). Attorney reads the scripts first (section 10).
5. Licensed/verified badge: only after the FL MQA license file is pulled.
6. City pages list every dentist on one page (no 25/page pagination yet). Big cities are long.
7. Spec's pricing copy lists a license badge on the Listing tier; I left it out for the reason in item 5. Put it back when MQA data exists.

## Size
- 18,949 HTML pages: 16,874 profiles, 1,610 city+specialty, 461 city pages, plus home, /fl/, pricing, claim
- dist is about 53 MB of real bytes (Finder shows ~81 MB because of 19k small files). search.json is 2.4 MB (Cloudflare compresses it). A profile page is about 2 KB.
- Cloudflare Pages free tier allows 20,000 files per deploy; this is 18,954 files, so it is close. Adding pages (e.g. /remove, /terms) is fine, but a second state needs a different split.

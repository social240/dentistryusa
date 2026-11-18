# DentistryUSA starter kit

A static site built from the public NPI registry data for Florida dentists, plus a small Supabase database for claims, removal requests, the dentist's own account and online booking.
A preview is live at https://dentistryusa.netlify.app (Netlify builds it from this repo).

## What's in the folder
- `build.py`: reads `data/fl-dentists-seed.csv`, writes the whole site to `dist/`. Python 3, standard library only.
- `style.css`: the one shared stylesheet. The colours are variables at the top. `test_build.py`: sanity checks.
- `static/`: browser scripts copied into `dist/` as they are: `search.js`, `forms.js` (claim and remove), `admin.js`, `account.js` (the dentist's account), `booking.js` (booking on profiles, and `/appointment/`), `online.js` ("Book online" on lists), and `vendor/supabase-js-2.119.0.js`.
- `data/fl-dentists-seed.csv`: 16,874 FL dentists (NPPES, public).
- `data/removed.txt`: NPIs to leave off the site (one per line).
- `supabase/migrations/`: the database. `001_booking.sql` (tables, row level security, functions), then `002_dentist_account.sql` (the dentist's account; tables become reachable only through functions).
- `supabase/load_dentists.py`: copies the listings into the database.
- `netlify.toml`: tells Netlify to run `python3 build.py` and publish `dist/`.
- `dist/`: the generated site (not in git; safe to delete and rebuild).

## Build
    python3 build.py        # takes about 30 seconds, writes dist/
    python3 test_build.py   # should print OK

Set `SEED_CSV=/path/to/other.csv` to build from a different file.
On Windows, run both with `python -X utf8`.

The site is **noindex** (robots.txt blocks everything and every page has a noindex tag) unless Netlify builds it for `https://dentistryusa.com`. Netlify sets `URL` to the site's primary domain, so pointing the domain at Netlify and rebuilding turns indexing on.

## Database (Supabase)
Project `dayctjcljbklonolzpyt`. `build.py` holds its URL and publishable key; that key is meant for browsers, and row level security decides what it can do.
- **Set up a new project:** run `supabase/migrations/001_booking.sql` and then `002_dentist_account.sql` in the SQL editor, then
  `SUPABASE_ACCESS_TOKEN=sbp_... SUPABASE_PROJECT_REF=<ref> python3 supabase/load_dentists.py`, then change `SUPABASE_URL` and `SUPABASE_KEY` in `build.py`.
  In Authentication > URL Configuration, allow the site's addresses as redirect URLs (`https://<site>/**`).
- **Add an admin:** the person signs in once at `/admin/` (an emailed link), then run
  `insert into public.admins (user_id) select id from auth.users where email = '<their email>';`
- **Who owns a listing:** the email on an approved claim. That dentist signs in at `/account/` with the same email (confirmed by the emailed link).
- **Sign-in emails** come from Supabase's built-in sender, which only delivers to members of the Supabase organization, and only 2 per hour for the whole project. Real dentists need a custom SMTP sender first.

## Deploy
**Netlify (the current preview):** push to `main`. `netlify.toml` builds the site and publishes `dist/`.

**Cloudflare Pages:** connect the repo with build command `python3 build.py` and output directory `dist`, or build locally and run `npx wrangler pages deploy dist`.
`dist/` is in `.gitignore`, so it is not committed. Pages handles the trailing-slash URLs by itself.

## What the site has now
- Home, with the search box. It matches every word against name, city and specialty, so "Miami orthodontist", "kids dentist Tampa" and "root canal Orlando" work. Common words map to the specialty names in the data. A 5-digit word matches the ZIP code and a 10-digit word the NPI. `/?q=...` runs a search; the header search box on other pages uses it.
- `/fl/`, and `/fl/specialty/<specialty>/` (the cities that have that specialty).
- `/fl/<city>/` and `/fl/<city>/<specialty>/`, 25 dentists per page (`/fl/miami/page/2/` and so on).
- `/dentist/<npi>-<name>/` profiles (Dentist JSON-LD, "Claim your free listing", and a link to `/remove/`). Once a listing is claimed, the side box says it is managed by the practice.
- **Online booking** on a profile, when its dentist has turned it on: the reason for the visit and new or returning patient, a week of open times (Previous / Next week, "Next available"), then the patient's name, date of birth, phone, email and a note of up to 100 characters (booking for someone else works too). No patient account. The confirmation gives a private link and an "Add to calendar" file. The database blocks double booking and limits bookings per email and per connection.
- `/appointment/#<private link>`: the patient views, moves or cancels their appointment.
- `/account/`: the dentist signs in with an emailed link, turns online booking on or off, sets weekly hours (more than one range per day for breaks), appointment length, notice needed, how far ahead patients can book and the time zone, and sees and cancels appointments.
- City and specialty lists mark listings that book online, with the next open time.
- `/claim/`: anyone can send a claim (NPI must be 10 digits and in our listings). It lands in the admin inbox.
- `/remove/`: "remove my listing" or "stop emailing me". Our emails link here (`/remove/?npi=...`, and `&request=stop_emails` to preselect that option). It lands in the admin inbox.
- `/admin/`: the inbox. Approve or reject claims; mark removal requests done. To take a listing off the site, add its NPI to `data/removed.txt` and push.
- `/pricing/` (buttons say "Coming soon"), `sitemap.xml`, `robots.txt`.
- Footer: support@dentistryusa.com and links to the pages above, including Dentist sign-in.

No emails go out yet: not to patients when they book or when an office cancels, and not to dentists when they get a booking. Patients keep their private link; offices see new bookings at `/account/`.

Rows without a city are skipped. PO box addresses show "Address on file". No reviews, no "verified" badge, and no dentist emails shown. Phone is the public practice phone from NPPES.

## Look
The layout follows the usual doctor-directory pattern: a search-first home page, specialty tiles, city lists, dentist cards with initials, and a claim box beside each profile.
The colours, the tooth mark and the text are DentistryUSA's own. There are no photos or ratings yet.
The font is Plus Jakarta Sans, loaded from Google Fonts.

## What's left for Jelo (spec: docs/1100-dentistryusa-spec.md)
1. `/terms`, `/privacy`, `/advertising` pages (copy is in section 8), then link them in the footer. `/remove` is done.
2. Claims: the form and the admin review work. Emails to the claimant are still manual (needs a support mailbox and an email sender).
3. Stripe in **test mode** on Mike's account (section 5), then wire the pricing buttons and the ROI slider (section 7).
4. Online booking works. Still needed: an email sender (custom SMTP) for dentist sign-in and for booking emails to patients and offices; and, before real patients book, a legal (HIPAA) review and a database in a US region (this project is in Sydney).
5. Preview-site generator (section 6).
6. AI sales agent (sections 4-9). Attorney reads the scripts first (section 10).
7. Licensed/verified badge: only after the FL MQA license file is pulled. The spec's pricing copy lists a license badge on the Listing tier; it stays out until then.

## Size
- 19,836 HTML pages: 16,874 profiles, 1,610 city+specialty and 461 city pages (with their extra pages, 25 dentists each), 13 specialty pages, plus home, /fl/, pricing, claim, remove, admin, account, appointment
- 19,849 files, about 97 MB. search.json is 0.9 MB (about 0.3 MB compressed). A profile page is about 4.4 KB.
- Cloudflare Pages free tier allows 20,000 files per deploy, so this is close. Netlify has no such limit. A second state would need a different split on Cloudflare.

#!/usr/bin/env python3
"""Build the DentistryUSA static site into dist/. Python 3 stdlib only."""
import csv, html, json, os, re, shutil, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.environ.get("SEED_CSV") or os.path.join(HERE, "data", "fl-dentists-seed.csv")
REMOVED = os.path.join(HERE, "data", "removed.txt")
STATIC = os.path.join(HERE, "static")
DIST = os.path.join(HERE, "dist")
BASE = "https://dentistryusa.com"
SUPPORT = "support@dentistryusa.com"
PER_PAGE = 25
# The database (Supabase). This key is meant for browsers: row level security
# in supabase/migrations decides what it can read and write.
SUPABASE_URL = "https://dayctjcljbklonolzpyt.supabase.co"
SUPABASE_KEY = "sb_publishable_nlgVrnlD4fCKfEKtiB88Fg_9WsqplXQ"
# Search engines may index the site only when Netlify builds it for the real
# domain (Netlify sets URL to the site's primary address). The netlify.app
# preview and local builds are noindex.
INDEXABLE = (os.environ.get("URL") or "").rstrip("/") == BASE
FOOT = "Listings come from the public NPI registry. Dentists can claim and update their listing."
SPONSORED = ('Sponsored placement, when offered, is labeled "Sponsored" and is paid advertising, '
             "not a rating or recommendation.")
# The one web font. Everything else (icons, colours) lives in style.css.
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Plus+Jakarta+Sans:wght@400;500;600;700;800&amp;display=swap">')
# Our own tooth mark (also in style.css as --tooth).
TOOTH = ("M7.5 2.5C5 2.5 3.5 4.6 3.5 7.2c0 2.2.9 3.6 1.4 5.6.5 2.1.6 4.5 1.3 6.6.3 1 .9 2.1 1.9 2.1 "
         "1.3 0 1.5-1.7 1.8-3.2.3-1.5.7-3 2.1-3s1.8 1.5 2.1 3c.3 1.5.5 3.2 1.8 3.2 1 0 1.6-1.1 1.9-2.1"
         ".7-2.1.8-4.5 1.3-6.6.5-2 1.4-3.4 1.4-5.6 0-2.6-1.5-4.7-4-4.7-1.7 0-2.8.9-4.5.9s-2.8-.9-4.5-.9z")
FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
           '<rect width="24" height="24" rx="6" fill="#c9f5e9"/>'
           '<path transform="translate(3.6 3.6) scale(.7)" fill="#0f766e" d="' + TOOTH + '"/></svg>')
# Search box in the header of every page except the home page (which has the big one).
HSEARCH = ('<form class="hsearch" action="/" method="get" role="search">'
           '<label class="sr" for="hq">Search dentists</label>'
           '<input id="hq" name="q" type="search" placeholder="Name, city, ZIP or specialty">'
           '<button type="submit">Search</button></form>\n')
SUPPORT_LINK = f'<a href="mailto:{SUPPORT}">{SUPPORT}</a>'
esc = html.escape

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def tcase(s):
    s = re.sub(r"[A-Za-z']+", lambda m: m.group(0).capitalize(), s.strip())
    s = re.sub(r"\b(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), s)
    return re.sub(r"\b(Po|Pob)\b", "PO", s)

def is_po(a):
    return bool(re.match(r"\s*(P\.?\s*O\.?\s*BOX|POST OFFICE BOX)\b", a, re.I))

def listings(n):
    return f"{n:,} listing" + ("" if n == 1 else "s")

def removed_npis():
    """NPIs listed in data/removed.txt (one per line, # starts a note)."""
    if not os.path.exists(REMOVED):
        return set()
    with open(REMOVED, encoding="utf-8") as f:
        return {line.split("#")[0].strip() for line in f if line.split("#")[0].strip()}

def write(path, text):
    p = os.path.join(DIST, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)

def page(path, title, desc, body, extra_head="", noindex=False, hero="", wide=False, search=True):
    """hero: full-width HTML above the page column. wide: body brings its own full-width sections."""
    url = BASE + "/" + path.replace("index.html", "")
    inner = body if wide else '<div class="wrap page">\n' + body + "\n</div>"
    write(path, f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
{'<meta name="robots" content="noindex">' if noindex or not INDEXABLE else ''}
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
{FONTS}
<link rel="stylesheet" href="/style.css">{extra_head}
</head><body>
<a class="skip" href="#main">Skip to content</a>
<header class="site"><div class="wrap bar"><a class="logo" href="/"><span class="mark" aria-hidden="true"></span><span>Dentistry<b>USA</b></span></a>
{HSEARCH if search else ''}<nav aria-label="Main"><a href="/fl/">Florida</a><a href="/pricing/">Pricing</a><a class="pill" href="/claim/">Claim<span class="hs"> a listing</span></a></nav></div></header>
<main id="main">
{hero}{inner}
</main>
<footer class="site"><div class="wrap"><div><p class="logo"><span>Dentistry<b>USA</b></span></p><p>{FOOT}</p>
<p>{SPONSORED}</p><p>Questions? Email {SUPPORT_LINK}.</p></div>
<nav aria-label="Footer"><a href="/fl/">Florida dentists by city</a><a href="/pricing/">Pricing</a><a href="/claim/">Claim a listing</a><a href="/account/">Dentist sign-in</a><a href="/remove/">Remove a listing</a></nav></div></footer>
</body></html>""")
    return url

def crumbs(*items):
    return '<nav class="crumbs" aria-label="Breadcrumb">' + " / ".join(
        f'<a href="{u}">{esc(t)}</a>' if u else esc(t) for t, u in items) + "</nav>"

def band(crumb_html, h1, lead=""):
    """The tinted strip at the top of an inner page. h1 and lead are HTML."""
    return ('<div class="band"><div class="wrap">' + crumb_html + f"<h1>{h1}</h1>"
            + (f"<p>{lead}</p>" if lead else "") + "</div></div>\n")

def chunks(lst):
    return [lst[i:i + PER_PAGE] for i in range(0, len(lst), PER_PAGE)] or [[]]

def page_path(base, n):
    """base is a folder such as fl/miami/; page 1 is the folder itself."""
    return base if n == 1 else f"{base}page/{n}/"

def pager(base, n, total):
    """Previous / numbers / Next for page n of total. base is the first page's path, e.g. fl/miami/."""
    if total <= 1:
        return ""
    href = lambda k: "/" + page_path(base, k)
    nums = sorted({1, 2, total - 1, total, n - 1, n, n + 1} & set(range(1, total + 1)))
    parts = [f'<a class="step" href="{href(n - 1)}" rel="prev">Previous</a>' if n > 1
             else '<span class="step off">Previous</span>']
    last = 0
    for k in nums:
        if k - last > 1:
            parts.append('<span class="gap" aria-hidden="true">&hellip;</span>')
        parts.append(f'<a href="{href(k)}" aria-current="page">{k}</a>' if k == n else f'<a href="{href(k)}">{k}</a>')
        last = k
    parts.append(f'<a class="step" href="{href(n + 1)}" rel="next">Next</a>' if n < total
                 else '<span class="step off">Next</span>')
    return f'<nav class="pager" aria-label="Pages, {n} of {total}">' + "".join(parts) + "</nav>"

def load():
    rows, seen_npi, skip = [], set(), removed_npis()
    with open(SEED, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            city = tcase(r["city"])
            if not city or r["npi"] in seen_npi or r["npi"] in skip:
                continue
            seen_npi.add(r["npi"])
            nm = " ".join(x for x in (r["first_name"], r["last_name"]) if x)
            r.update(city=city, cslug=slug(city), name="Dr. " + nm, nm=nm,
                     spec=r["specialty"] or "Dentist", sslug=slug(r["specialty"] or "Dentist"),
                     nslug=slug(nm), addr1=tcase(r["address1"]), addr2=tcase(r["address2"]))
            r["url"] = f"/dentist/{r['npi']}-{r['nslug']}/"
            # practice key per seed-schema: (address1 normalized, zip5, phone)
            r["pkey"] = (re.sub(r"[^a-z0-9]", "", r["address1"].lower()), r["zip5"], r["phone"])
            r["credtxt"] = ", " + r["credential"] if r["credential"] else ""
            r["ini"] = esc(((r["first_name"][:1] + r["last_name"][:1]) or "D").upper())
            r["po"] = is_po(r["address1"])
            r["street"] = ", ".join(x for x in (r["addr1"], r["addr2"]) if x)
            rows.append(r)
    return rows

def doc_li(r, spec=True, addr=True):
    """One dentist in a list: initials, name, then specialty and street and phone."""
    lines = [f"<p>{esc(r['spec'])}</p>"] if spec else []
    bits = [esc(r["street"])] if addr and r["street"] and not r["po"] else []
    if r["phone"]:
        bits.append('<span class="nb">' + esc(r["phone"]) + "</span>")
    if bits:
        lines.append('<p class="muted">' + " &middot; ".join(bits) + "</p>")
    return (f'<li class="doc" data-npi="{r["npi"]}"><span class="av" aria-hidden="true">{r["ini"]}</span><div>'
            f'<a href="{r["url"]}">{esc(r["name"])}{esc(r["credtxt"])}</a>' + "".join(lines) + "</div></li>")

def chips(c, specs, by_cs, sname, total, current=None):
    """The specialty filter on a city page. current is the specialty slug being shown, if any."""
    cur = "" if current else ' aria-current="page"'
    items = [f'<li><a href="/fl/{c}/"{cur}>All <small>{total:,}</small></a></li>']
    for s in specs:
        cur = ' aria-current="page"' if s == current else ""
        items.append(f'<li><a href="/fl/{c}/{s}/"{cur}>{esc(sname[s])} <small>{len(by_cs[(c, s)]):,}</small></a></li>')
    return '<nav aria-label="Specialties in this city"><ul class="chips">' + "".join(items) + "</ul></nav>"

# Browser scripts: the database address and key, the Supabase client (sign-in pages),
# "Book online" marks on lists, and the booking box (profiles and /appointment/).
CONFIG_JS = '<script src="/config.js" defer></script>'
SUPABASE_JS = '<script src="/vendor/supabase-js-2.119.0.js" defer></script>' + CONFIG_JS
ONLINE_JS = CONFIG_JS + '<script src="/online.js" defer></script>'
BOOKING_JS = CONFIG_JS + '<script src="/booking.js" defer></script>'

def paged_list(base, lst, title, desc, crumb_items, h1, chip_html, show_spec):
    """Writes a list of dentists 25 per page: base/, base/page/2/, ... Returns the URLs."""
    parts, urls = chunks(lst), []
    total = len(parts)
    for n, part in enumerate(parts, 1):
        suffix = f" (page {n} of {total})" if total > 1 else ""
        lead = listings(len(lst)) + "." + (f" Page {n} of {total}." if total > 1 else "")
        urls.append(page(page_path(base, n) + "index.html", title.replace(" | ", suffix + " | ", 1),
            desc + (f" Page {n} of {total}." if total > 1 else ""),
            '<h2 class="sr">By specialty</h2>' + chip_html +
            '<h2 class="sr">Dentists</h2><ul class="docs">' + "".join(doc_li(r, spec=show_spec) for r in part) + "</ul>" +
            pager(base, n, total), ONLINE_JS,
            hero=band(crumbs(*crumb_items), h1, lead)))
    return urls

def build():
    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)
    shutil.copy(os.path.join(HERE, "style.css"), DIST)
    shutil.copytree(STATIC, DIST, dirs_exist_ok=True)
    write("favicon.svg", FAVICON)
    write("config.js", "window.DUSA=" + json.dumps({"url": SUPABASE_URL, "key": SUPABASE_KEY}) + ";\n")
    rows = load()
    rows.sort(key=lambda r: (r["last_name"].lower(), r["first_name"].lower()))
    by_city, by_cs, by_practice, by_spec = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    cname = {}
    for r in rows:
        by_city[r["cslug"]].append(r); by_cs[(r["cslug"], r["sslug"])].append(r)
        by_practice[r["pkey"]].append(r); by_spec[r["sslug"]].append(r); cname[r["cslug"]] = r["city"]
    sname = {r["sslug"]: r["spec"] for r in rows}
    assert "specialty" not in by_city, "a city slug collides with /fl/specialty/"
    assert "page" not in sname, "a specialty slug collides with /page/"
    specs_by_size = sorted(by_spec, key=lambda s: (-len(by_spec[s]), sname[s]))
    urls = []

    # home
    top = sorted(by_city, key=lambda c: -len(by_city[c]))[:24]
    cl = "".join(f'<li><a href="/fl/{c}/">{esc(cname[c])}</a> <span class="muted">{len(by_city[c]):,}</span></li>' for c in top)
    tiles = "".join(f'<li><a href="/fl/specialty/{s}/"><span class="ti" aria-hidden="true"></span>{esc(sname[s])}'
                    f"<small>{len(by_spec[s]):,} dentists</small></a></li>" for s in specs_by_size[:8])
    more = " &middot; ".join(f'<a href="/fl/specialty/{s}/">{esc(sname[s])}</a> ({len(by_spec[s]):,})'
                             for s in specs_by_size[8:])
    more = f'<p class="muted more">More specialties: {more}</p>' if more else ""
    home_hero = f"""<section class="hero"><div class="deco" aria-hidden="true"></div><div class="wrap">
<h1>Find a dentist in Florida</h1>
<p class="sub">Search {len(rows):,} Florida dentists by name, city, ZIP code or specialty.</p>
<form id="search" class="searchbar" role="search" action="/" method="get">
<label class="sr" for="q">Dentist name, city, ZIP code or specialty</label>
<input id="q" name="q" type="search" autocomplete="off" placeholder="e.g. Miami orthodontist, 33145, Smith">
<button class="go" type="submit">Search</button>
<ul id="results" class="results" aria-live="polite" hidden></ul></form>
<p class="note">Florida only for now. Other states are coming soon.</p>
</div></section>
"""
    home_body = f"""<section class="sec"><div class="wrap"><h2>Browse by specialty</h2>
<ul class="tiles">{tiles}</ul>
{more}</div></section>
<section class="sec soft"><div class="wrap"><h2>How DentistryUSA works</h2>
<ol class="steps">
<li><span class="n" aria-hidden="true">1</span><h3>Search your way</h3><p>Look up a dentist by name, city, ZIP code or specialty.</p></li>
<li><span class="n" aria-hidden="true">2</span><h3>See the details</h3><p>Profiles show practice details from the public NPI registry, such as the address and phone.</p></li>
<li><span class="n" aria-hidden="true">3</span><h3>Free to use</h3><p>No account needed to search. Dentists can claim their own listing for free.</p></li>
</ol></div></section>
<section class="sec"><div class="wrap"><h2>Top Florida cities</h2><ul class="list cols">{cl}</ul>
<p class="after"><a class="btn ghost" href="/fl/">See all Florida cities</a></p></div></section>
<section class="cta"><div class="wrap"><div><h2>Are you a dentist?</h2>
<p>Every dentist in Florida has a free DentistryUSA profile. Claim yours to fix details and add your own.</p></div>
<p class="actions"><a class="btn light" href="/claim/">Claim your free listing</a><a class="btn line" href="/pricing/">See pricing</a></p></div></section>"""
    urls.append(page("index.html", "Find a Dentist in Florida | DentistryUSA",
        f"Browse {len(rows):,} Florida dentists by city and specialty. Listings come from the public NPI registry.",
        home_body, '<script src="/search.js" defer></script>', hero=home_hero, wide=True, search=False))

    # /fl/
    al = "".join(f'<li><a href="/fl/{c}/">{esc(cname[c])}</a> <span class="muted">{len(by_city[c]):,}</span></li>'
                 for c in sorted(by_city, key=lambda c: cname[c]))
    urls.append(page("fl/index.html", "Florida Dentists by City | DentistryUSA",
        "Every Florida city with listed dentists.", f'<ul class="list cols">{al}</ul>',
        hero=band(crumbs(("Home", "/"), ("Florida", None)), "Florida dentists by city",
                  f"{len(rows):,} dentists in {len(by_city):,} cities.")))

    # /fl/specialty/<specialty>/: the cities that have it
    for s in specs_by_size:
        cities = sorted({r["cslug"] for r in by_spec[s]}, key=lambda c: cname[c])
        li = "".join(f'<li><a href="/fl/{c}/{s}/">{esc(cname[c])}</a> <span class="muted">{len(by_cs[(c, s)]):,}</span></li>'
                     for c in cities)
        where = f"{len(cities):,} cities" if len(cities) != 1 else "1 city"
        urls.append(page(f"fl/specialty/{s}/index.html", f"{sname[s]} in Florida by City | DentistryUSA",
            f"{len(by_spec[s]):,} {sname[s].lower()} listings in Florida, by city, from the public NPI registry.",
            f'<ul class="list cols">{li}</ul>',
            hero=band(crumbs(("Home", "/"), ("Florida", "/fl/"), (sname[s], None)), f"{esc(sname[s])} in Florida",
                      f"{listings(len(by_spec[s]))} in {where}. Pick a city.")))

    # city + city/specialty, 25 dentists per page
    for c, lst in by_city.items():
        city = cname[c]
        specs = sorted({r["sslug"] for r in lst}, key=lambda s: sname[s])
        urls += paged_list(f"fl/{c}/", lst, f"Dentists in {city}, FL | DentistryUSA",
            f"{len(lst):,} dentists in {city}, Florida, listed from the public NPI registry.",
            [("Home", "/"), ("Florida", "/fl/"), (city, None)], f"Dentists in {esc(city)}, FL",
            chips(c, specs, by_cs, sname, len(lst)), True)
        for s in specs:
            sl_ = by_cs[(c, s)]
            urls += paged_list(f"fl/{c}/{s}/", sl_, f"{sname[s]} in {city}, FL | DentistryUSA",
                f"{len(sl_):,} {sname[s].lower()} listings in {city}, Florida from the public NPI registry.",
                [("Home", "/"), ("Florida", "/fl/"), (city, f"/fl/{c}/"), (sname[s], None)],
                f"{esc(sname[s])} in {esc(city)}, FL", chips(c, specs, by_cs, sname, len(lst), s), False)

    # profiles
    for r in rows:
        po = r["po"]
        place = f"{r['city']}, FL {r['zip5']}"
        addr = "Address on file" if po else ", ".join(x for x in (r["street"], place) if x)
        cred = r["credtxt"]
        title = f"{r['name']}{cred}, {r['spec']} in {r['city']}, FL | DentistryUSA"
        ld = {"@context": "https://schema.org", "@type": "Dentist", "name": r["name"],
              "medicalSpecialty": "Dentistry", "url": BASE + r["url"]}
        if r["phone"]: ld["telephone"] = r["phone"]
        if not po:
            ld["address"] = {"@type": "PostalAddress", "streetAddress": r["street"],
                             "addressLocality": r["city"], "addressRegion": "FL", "postalCode": r["zip5"], "addressCountry": "US"}
        mates = [m for m in by_practice[r["pkey"]] if m["npi"] != r["npi"]] if not po else []
        mates_html = ('<h2>Other dentists at this address</h2><ul class="docs">' +
                      "".join(doc_li(m, addr=False) for m in mates[:8]) + "</ul>") if mates else ""
        tel = re.sub(r"\D", "", r["phone"])
        phone = f'<dt>Phone</dt><dd><a href="tel:+1{tel}">{esc(r["phone"])}</a></dd>' if r["phone"] else ""
        call = f'<p class="actions"><a class="btn ghost" href="tel:+1{tel}">Call {esc(r["phone"])}</a></p>' if r["phone"] else ""
        # Filled in by booking.js when the practice takes online bookings; hidden otherwise.
        book = (f'<section id="book" class="card book" aria-labelledby="bookH" data-npi="{r["npi"]}" '
                f'data-dentist="{esc(r["name"] + cred)}" data-address="{esc("" if po else addr)}" '
                f'data-phone="{esc(r["phone"])}" hidden></section>')
        urls.append(page(f"dentist/{r['npi']}-{r['nslug']}/index.html", title,
            f"{r['name']}{cred}, {r['spec'].lower()} in {r['city']}, FL. Practice address, phone and NPI from the public NPI registry.",
            crumbs(("Home", "/"), ("Florida", "/fl/"), (r["city"], f"/fl/{r['cslug']}/"), (r["name"], None)) +
            f"""<div class="profile"><div>
<div class="phead"><span class="av xl" aria-hidden="true">{r['ini']}</span><div><h1>{esc(r['name'])}{esc(cred)}</h1>
<p class="lead">{esc(r['spec'])} in <a href="/fl/{r['cslug']}/">{esc(r['city'])}, FL</a></p></div></div>
{book}
<div class="card"><dl class="facts"><dt>Practice address</dt><dd>{esc(addr)}</dd>{phone}<dt>NPI</dt><dd>{r['npi']}</dd></dl>{call}</div>
{mates_html}
<p class="muted">This information comes from the public NPI registry and may be out of date. Is something wrong, or should this listing come down? <a href="/remove/?npi={r['npi']}">Ask us to remove it</a>.</p>
</div>
<aside class="claim" id="claimBox"><p><strong>Is this you?</strong> Claim your free listing to fix details and add your own.</p>
<a class="btn" href="/claim/?npi={r['npi']}">Claim your free listing</a></aside></div>""",
            BOOKING_JS + '<script type="application/ld+json">' + json.dumps(ld).replace("</", "<\\/") + '</script>'))

    # search index: shared city and specialty names, one short row per dentist
    cities = sorted(set(cname.values()))
    specs = sorted(set(sname.values()))
    ci, si = {c: i for i, c in enumerate(cities)}, {s: i for i, s in enumerate(specs)}
    write("search.json", json.dumps({"cities": cities, "specs": specs,
        # cname: one spelling per city page (the data has variants such as "St Johns" / "St. Johns")
        "rows": [[r["npi"], r["nm"], r["credential"], ci[cname[r["cslug"]]], si[r["spec"]], r["zip5"]] for r in rows]},
        separators=(",", ":"), ensure_ascii=False))

    # pricing
    def tier(name, price, items):
        return (f'<section class="tier"><h2>{name}</h2><p class="price">${price}<span>/month</span></p><ul>' +
                "".join(f"<li>{i}</li>" for i in items) +
                '</ul><button type="button" disabled>Coming soon</button></section>')
    urls.append(page("pricing/index.html", "Pricing | DentistryUSA",
        "DentistryUSA plans for dentists: Listing $29.99, Premium $49.99, Listing + Website $99.99 per month.",
        '<div class="tiers">' +
        tier("Listing", "29.99", ["Photos, hours, insurance accepted", "Your website and booking link"]) +
        tier("Premium", "49.99", ["Everything in Listing", "No other dentists' ads on your profile", "Monthly report of calls and clicks", "Lock a sponsored spot in your city"]) +
        tier("Listing + Website", "99.99", ["Everything in Premium", "A one-page website for your practice, hosted by us"]) +
        """</div>
<p><strong>Lock your spot.</strong> Hold sponsored spot 1, 2 or 3 in your city and specialty for as long as you stay subscribed. One dentist per spot, first come.</p>
<p>Monthly. Cancel anytime from your account. The free profile stays free.</p>
<!-- TODO(Jelo): spec section 7 ROI slider; wire buttons to Stripe Checkout (test mode first). Spec lists a license badge on the Listing tier; omitted until the FL MQA license file is pulled. -->""",
        hero=band("", "Get found by patients in your area.",
                  "Every dentist in Florida has a free DentistryUSA profile. Renew your listing to add your photos, "
                  "hours and booking link, and to show up first in your city.")))

    form_js = '<script src="/config.js" defer></script><script src="/forms.js" defer></script>'

    # claim (anyone can send one; it waits in the admin inbox)
    page("claim/index.html", "Claim Your Free Listing | DentistryUSA",
        "Claim and update your free DentistryUSA dentist listing.",
        f"""<form id="claim" class="card formcard" novalidate>
<p><label for="npi">NPI number</label><input id="npi" name="npi" inputmode="numeric" autocomplete="off" maxlength="10" required aria-describedby="npiHelp npiInfo">
<span id="npiHelp" class="hint">10 digits. You can find it on your DentistryUSA profile.</span><span id="npiInfo" class="hint" aria-live="polite"></span></p>
<p><label for="name">Your name</label><input id="name" name="name" autocomplete="name" required></p>
<p><label for="email">Work email</label><input id="email" name="email" type="email" autocomplete="email" required></p>
<p><label for="phone">Phone <span class="opt-label">(optional)</span></label><input id="phone" name="phone" type="tel" autocomplete="tel"></p>
<p><label for="role">Your role</label><select id="role" name="role"><option>Dentist</option><option>Office manager</option><option>Other</option></select></p>
<p class="err" role="alert" tabindex="-1" hidden></p>
<button class="btn" type="submit">Submit claim</button>
<noscript><p class="err">This form needs JavaScript. You can also email {SUPPORT_LINK}.</p></noscript>
</form>
<div id="claimDone" class="card formcard done" tabindex="-1" hidden></div>
<p class="muted">Already approved? <a href="/account/">Sign in</a> to turn on online booking and set your hours.</p>""", form_js, noindex=True,
        hero=band("", "Claim your free listing",
                  "Tell us who you are. We will check that you work at this practice and get back to you. Claiming is free."))

    # remove (linked from our emails and from every profile)
    page("remove/index.html", "Remove a Listing or Stop Emails | DentistryUSA",
        "Ask DentistryUSA to remove a dentist listing or to stop sending emails.",
        f"""<form id="remove" class="card formcard" novalidate>
<fieldset><legend>What would you like us to do?</legend>
<label class="opt"><input type="radio" name="request" value="remove_listing" checked> Remove my listing from DentistryUSA</label>
<label class="opt"><input type="radio" name="request" value="stop_emails"> Stop sending me emails</label></fieldset>
<p><label for="npi">NPI number <span id="npiOpt" class="opt-label" hidden>(optional)</span></label><input id="npi" name="npi" inputmode="numeric" autocomplete="off" maxlength="10" aria-describedby="npiInfo">
<span id="npiInfo" class="hint" aria-live="polite"></span></p>
<p><label for="name">Your name</label><input id="name" name="name" autocomplete="name" required></p>
<p><label for="email">Email</label><input id="email" name="email" type="email" autocomplete="email" required></p>
<p><label for="note">Anything else we should know? <span class="opt-label">(optional)</span></label><textarea id="note" name="note" rows="3" maxlength="500"></textarea></p>
<p class="err" role="alert" tabindex="-1" hidden></p>
<button class="btn" type="submit">Send request</button>
<noscript><p class="err">This form needs JavaScript. You can also email {SUPPORT_LINK}.</p></noscript>
</form>
<div id="removeDone" class="card formcard done" tabindex="-1" hidden></div>
<p class="muted">You can also email {SUPPORT_LINK}.</p>""", form_js, noindex=True,
        hero=band("", "Remove a listing or stop emails",
                  "Listings come from the public NPI registry. If you are the dentist, or you work at the practice, "
                  "we will remove the listing or stop emailing you."))

    # admin inbox (sign-in required; the database decides who is an admin)
    page("admin/index.html", "Admin | DentistryUSA", "DentistryUSA admin inbox.",
        '<div id="admin" class="admin"><p class="muted">Loading&hellip;</p></div>'
        '<noscript><p class="err">The admin page needs JavaScript.</p></noscript>',
        SUPABASE_JS + '<script src="/admin.js" defer></script>', noindex=True,
        hero=band("", "Admin inbox", "Claims and removal requests."))

    # the dentist's own account (sign-in required; the database decides what they own)
    page("account/index.html", "Dentist Sign-in | DentistryUSA",
        "Sign in to manage your DentistryUSA listing and online booking.",
        '<div id="account" class="account"><p class="muted">Loading&hellip;</p></div>'
        '<noscript><p class="err">This page needs JavaScript.</p></noscript>',
        SUPABASE_JS + '<script src="/account.js" defer></script>', noindex=True,
        hero=band("", "Your DentistryUSA listing", "Turn on online booking, set your hours and see your appointments."))

    # a patient's appointment, opened from the private link they get when booking (/appointment/#token)
    page("appointment/index.html", "Your Appointment | DentistryUSA",
        "View, change or cancel your dentist appointment.",
        '<div id="appt" class="appt"><p class="muted">Loading&hellip;</p></div>'
        '<noscript><p class="err">This page needs JavaScript. To change your appointment, call the dental office.</p></noscript>',
        BOOKING_JS, noindex=True,
        hero=band("", "Your appointment", "View, change or cancel it."))

    if INDEXABLE:
        write("robots.txt", f"User-agent: *\nAllow: /\nDisallow: /preview/\nDisallow: /account/\nDisallow: /admin/\n"
              f"Disallow: /appointment/\nDisallow: /claim/\nDisallow: /remove/\n\nSitemap: {BASE}/sitemap.xml\n")
    else:
        write("robots.txt", "# Preview build: not for search engines.\nUser-agent: *\nDisallow: /\n")
    # sitemap limit is 50k URLs per file; this site is well under
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
          "".join(f"<url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    return len(rows), len(by_city), len(by_cs), len(by_spec), len(urls)

if __name__ == "__main__":
    n, c, cs, sp, u = build()
    print(f"dentists={n} cities={c} city+specialty={cs} specialties={sp} sitemap_urls={u} indexable={INDEXABLE}")

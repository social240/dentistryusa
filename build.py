#!/usr/bin/env python3
"""Build the DentistryUSA static site into dist/. Python 3 stdlib only."""
import csv, html, json, os, re, shutil, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.environ.get("SEED_CSV") or os.path.join(HERE, "data", "fl-dentists-seed.csv")
DIST = os.path.join(HERE, "dist")
BASE = "https://dentistryusa.com"
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
           '<input id="hq" name="q" type="search" placeholder="Name, city or specialty">'
           '<button type="submit">Search</button></form>\n')
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
{'<meta name="robots" content="noindex">' if noindex else ''}
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
<p>{SPONSORED}</p></div>
<nav aria-label="Footer"><a href="/fl/">Florida dentists by city</a><a href="/pricing/">Pricing</a><a href="/claim/">Claim a listing</a></nav></div></footer>
</body></html>""")
    return url

def crumbs(*items):
    return '<nav class="crumbs" aria-label="Breadcrumb">' + " / ".join(
        f'<a href="{u}">{esc(t)}</a>' if u else esc(t) for t, u in items) + "</nav>"

def band(crumb_html, h1, lead=""):
    """The tinted strip at the top of an inner page. h1 and lead are HTML."""
    return ('<div class="band"><div class="wrap">' + crumb_html + f"<h1>{h1}</h1>"
            + (f"<p>{lead}</p>" if lead else "") + "</div></div>\n")

def load():
    rows, seen_npi = [], set()
    with open(SEED, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            city = tcase(r["city"])
            if not city or r["npi"] in seen_npi:
                continue
            seen_npi.add(r["npi"])
            nm = " ".join(x for x in (r["first_name"], r["last_name"]) if x)
            r.update(city=city, cslug=slug(city), name="Dr. " + nm,
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
    return (f'<li class="doc"><span class="av" aria-hidden="true">{r["ini"]}</span><div>'
            f'<a href="{r["url"]}">{esc(r["name"])}{esc(r["credtxt"])}</a>' + "".join(lines) + "</div></li>")

def chips(c, specs, by_cs, sname, total, current=None):
    """The specialty filter on a city page. current is the specialty slug being shown, if any."""
    cur = "" if current else ' aria-current="page"'
    items = [f'<li><a href="/fl/{c}/"{cur}>All <small>{total:,}</small></a></li>']
    for s in specs:
        cur = ' aria-current="page"' if s == current else ""
        items.append(f'<li><a href="/fl/{c}/{s}/"{cur}>{esc(sname[s])} <small>{len(by_cs[(c, s)]):,}</small></a></li>')
    return '<nav aria-label="Specialties in this city"><ul class="chips">' + "".join(items) + "</ul></nav>"

def build():
    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)
    shutil.copy(os.path.join(HERE, "style.css"), DIST)
    write("favicon.svg", FAVICON)
    rows = load()
    rows.sort(key=lambda r: (r["last_name"].lower(), r["first_name"].lower()))
    by_city, by_cs, by_practice, by_spec = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    cname = {}
    for r in rows:
        by_city[r["cslug"]].append(r); by_cs[(r["cslug"], r["sslug"])].append(r)
        by_practice[r["pkey"]].append(r); by_spec[r["sslug"]].append(r); cname[r["cslug"]] = r["city"]
    sname = {r["sslug"]: r["spec"] for r in rows}
    assert "specialty" not in by_city, "a city slug collides with /fl/specialty/"
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
<p class="sub">Search {len(rows):,} Florida dentists by name, city or specialty.</p>
<form id="search" class="searchbar" role="search" action="/" method="get">
<label class="sr" for="q">Dentist name, city or specialty</label>
<input id="q" name="q" type="search" autocomplete="off" placeholder="e.g. Miami, orthodontist, Smith">
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
<li><span class="n" aria-hidden="true">1</span><h3>Search your way</h3><p>Look up a dentist by name, city or specialty.</p></li>
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

    # city + city/specialty
    for c, lst in by_city.items():
        city = cname[c]
        specs = sorted({r["sslug"] for r in lst}, key=lambda s: sname[s])
        urls.append(page(f"fl/{c}/index.html", f"Dentists in {city}, FL | DentistryUSA",
            f"{len(lst):,} dentists in {city}, Florida, listed from the public NPI registry.",
            '<h2 class="sr">By specialty</h2>' + chips(c, specs, by_cs, sname, len(lst)) +
            '<h2 class="sr">All dentists</h2><ul class="docs">' + "".join(doc_li(r) for r in lst) + "</ul>",
            hero=band(crumbs(("Home", "/"), ("Florida", "/fl/"), (city, None)),
                      f"Dentists in {esc(city)}, FL", listings(len(lst)) + ".")))
        for s in specs:
            sl_ = by_cs[(c, s)]
            urls.append(page(f"fl/{c}/{s}/index.html", f"{sname[s]} in {city}, FL | DentistryUSA",
                f"{len(sl_):,} {sname[s].lower()} listings in {city}, Florida from the public NPI registry.",
                '<h2 class="sr">By specialty</h2>' + chips(c, specs, by_cs, sname, len(lst), s) +
                '<h2 class="sr">Dentists</h2><ul class="docs">' + "".join(doc_li(r, spec=False) for r in sl_) + "</ul>",
                hero=band(crumbs(("Home", "/"), ("Florida", "/fl/"), (city, f"/fl/{c}/"), (sname[s], None)),
                          f"{esc(sname[s])} in {esc(city)}, FL", listings(len(sl_)) + ".")))

    # profiles
    search = []
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
        urls.append(page(f"dentist/{r['npi']}-{r['nslug']}/index.html", title,
            f"{r['name']}{cred}, {r['spec'].lower()} in {r['city']}, FL. Practice address, phone and NPI from the public NPI registry.",
            crumbs(("Home", "/"), ("Florida", "/fl/"), (r["city"], f"/fl/{r['cslug']}/"), (r["name"], None)) +
            f"""<div class="profile"><div>
<div class="phead"><span class="av xl" aria-hidden="true">{r['ini']}</span><div><h1>{esc(r['name'])}{esc(cred)}</h1>
<p class="lead">{esc(r['spec'])} in <a href="/fl/{r['cslug']}/">{esc(r['city'])}, FL</a></p></div></div>
<div class="card"><dl class="facts"><dt>Practice address</dt><dd>{esc(addr)}</dd>{phone}<dt>NPI</dt><dd>{r['npi']}</dd></dl>{call}</div>
{mates_html}
<p class="muted">This information comes from the public NPI registry and may be out of date.</p>
</div>
<aside class="claim"><p><strong>Is this you?</strong> Claim your free listing to fix details and add your own.</p>
<a class="btn" href="/claim/?npi={r['npi']}">Claim your free listing</a></aside></div>""",
            '<script type="application/ld+json">' + json.dumps(ld).replace("</", "<\\/") + '</script>'))
        search.append({"npi": r["npi"], "name": r["name"] + cred, "city": r["city"], "specialty": r["spec"], "url": r["url"]})

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

    # claim
    urls.append(page("claim/index.html", "Claim Your Free Listing | DentistryUSA",
        "Claim and update your free DentistryUSA dentist listing.",
        """<!-- TODO(Jelo): this form posts nowhere. Build the backend (spec section 4): POST to your endpoint,
     email a magic link to the address, create the claim row, then let them edit. Until then JS shows a notice. -->
<form id="claim" class="card formcard" method="post" action="#" novalidate>
<p><label for="npi">NPI number</label><input id="npi" name="npi" inputmode="numeric" pattern="[0-9]{10}" required></p>
<p><label for="name">Your name</label><input id="name" name="name" required></p>
<p><label for="email">Work email</label><input id="email" name="email" type="email" required></p>
<p><label for="role">Your role</label><select id="role" name="role"><option>Dentist</option><option>Office manager</option><option>Other</option></select></p>
<button class="btn" type="submit">Submit claim</button>
<p id="note" role="status" class="muted"></p></form>
<script>
var n=new URLSearchParams(location.search).get("npi");if(n&&/^\\d{10}$/.test(n))document.getElementById("npi").value=n;
document.getElementById("claim").addEventListener("submit",function(e){e.preventDefault();
document.getElementById("note").textContent="Claims are not open yet. Please check back soon.";});
</script>""", noindex=True,
        hero=band("", "Claim your free listing", "Tell us who you are and we will follow up. Claiming is free.")))
    urls.pop()  # claim page is noindex; keep it out of the sitemap

    write("search.json", json.dumps(search, separators=(",", ":")))
    write("search.js", SEARCH_JS)
    write("robots.txt", f"User-agent: *\nAllow: /\nDisallow: /preview/\nDisallow: /account/\nDisallow: /admin/\nDisallow: /claim/\n\nSitemap: {BASE}/sitemap.xml\n")
    # sitemap limit is 50k URLs per file; this site is well under
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
          "".join(f"<url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    return len(rows), len(by_city), len(by_cs), len(by_spec), len(urls)

# The home page search. It also runs a search passed in as /?q=..., which is how
# the small search box in the header of the other pages gets here.
SEARCH_JS = r"""(function(){
var form=document.getElementById("search"),q=document.getElementById("q"),out=document.getElementById("results"),data=null,loading=false;
function esc(s){return s.replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function show(h){out.innerHTML=h;out.hidden=!h}
function run(){var t=q.value.trim().toLowerCase();if(t.length<2){show("");return}
var w=t.split(/\s+/),hits=[];for(var i=0;i<data.length&&hits.length<20;i++){var d=data[i],h=(d.name+" "+d.city+" "+d.specialty).toLowerCase();
if(w.every(function(x){return h.indexOf(x)>-1}))hits.push(d)}
show(hits.length?hits.map(function(d){return '<li><a href="'+d.url+'"><strong>'+esc(d.name)+'</strong><span>'+esc(d.specialty)+' · '+esc(d.city)+', FL</span></a></li>'}).join(""):'<li class="none">No matches.</li>')}
function go(){if(data)return run();if(loading)return;loading=true;
fetch("/search.json").then(function(r){return r.json()}).then(function(j){data=j;run()}).catch(function(){loading=false;show('<li class="none">Search is unavailable right now.</li>')})}
q.addEventListener("input",go);
q.addEventListener("focus",function(){if(out.innerHTML)out.hidden=false});
form.addEventListener("submit",function(e){e.preventDefault();go()});
document.addEventListener("click",function(e){if(!form.contains(e.target))out.hidden=true});
document.addEventListener("keydown",function(e){if(e.key==="Escape")out.hidden=true});
var p=new URLSearchParams(location.search).get("q");if(p){q.value=p;go()}
})();"""

if __name__ == "__main__":
    n, c, cs, sp, u = build()
    print(f"dentists={n} cities={c} city+specialty={cs} specialties={sp} sitemap_urls={u}")

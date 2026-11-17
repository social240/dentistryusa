#!/usr/bin/env python3
"""Build the DentistryUSA static site into dist/. Python 3 stdlib only."""
import csv, html, json, os, re, shutil, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.environ.get("SEED_CSV") or os.path.join(HERE, "data", "fl-dentists-seed.csv")
DIST = os.path.join(HERE, "dist")
BASE = "https://dentistryusa.com"
FOOT = "Listings come from the public NPI registry. Dentists can claim and update their listing."
esc = html.escape

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def tcase(s):
    s = re.sub(r"[A-Za-z']+", lambda m: m.group(0).capitalize(), s.strip())
    s = re.sub(r"\b(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), s)
    return re.sub(r"\b(Po|Pob)\b", "PO", s)

def is_po(a):
    return bool(re.match(r"\s*(P\.?\s*O\.?\s*BOX|POST OFFICE BOX)\b", a, re.I))

def write(path, text):
    p = os.path.join(DIST, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)

def page(path, title, desc, body, extra_head="", noindex=False):
    url = BASE + "/" + path.replace("index.html", "")
    write(path, f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
{'<meta name="robots" content="noindex">' if noindex else ''}
<link rel="stylesheet" href="/style.css">{extra_head}
</head><body>
<a class="skip" href="#main">Skip to content</a>
<header class="site"><div class="wrap"><a class="logo" href="/">DentistryUSA</a>
<nav aria-label="Main"><a href="/fl/">Florida</a> <a href="/pricing/">Pricing</a> <a href="/claim/">Claim a listing</a></nav></div></header>
<main id="main" class="wrap">
{body}
</main>
<footer class="site"><div class="wrap"><p>{FOOT}</p>
<p>Sponsored placement, when offered, is labeled "Sponsored" and is paid advertising, not a rating or recommendation.</p></div></footer>
</body></html>""")
    return url

def crumbs(*items):
    return '<nav class="crumbs" aria-label="Breadcrumb">' + " / ".join(
        f'<a href="{u}">{esc(t)}</a>' if u else esc(t) for t, u in items) + "</nav>"

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
            rows.append(r)
    return rows

def dentist_li(r):
    cred = f", {esc(r['credential'])}" if r["credential"] else ""
    return (f'<li><a href="{r["url"]}">{esc(r["name"])}{cred}</a> '
            f'<span class="muted">{esc(r["spec"])}</span></li>')

def build():
    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)
    shutil.copy(os.path.join(HERE, "style.css"), DIST)
    rows = load()
    rows.sort(key=lambda r: (r["last_name"].lower(), r["first_name"].lower()))
    by_city, by_cs, by_practice = defaultdict(list), defaultdict(list), defaultdict(list)
    cname = {}
    for r in rows:
        by_city[r["cslug"]].append(r); by_cs[(r["cslug"], r["sslug"])].append(r)
        by_practice[r["pkey"]].append(r); cname[r["cslug"]] = r["city"]
    sname = {r["sslug"]: r["spec"] for r in rows}
    urls = []
    spec_count = defaultdict(int)
    for r in rows: spec_count[r["sslug"]] += 1

    # home
    top = sorted(by_city, key=lambda c: -len(by_city[c]))[:24]
    cl = "".join(f'<li><a href="/fl/{c}/">{esc(cname[c])}</a> <span class="muted">{len(by_city[c]):,}</span></li>' for c in top)
    sl = "".join(f'<li>{esc(sname[s])} <span class="muted">{n:,}</span></li>'
                 for s, n in sorted(spec_count.items(), key=lambda x: -x[1]))
    urls.append(page("index.html", "Find a Dentist in Florida | DentistryUSA",
        f"Browse {len(rows):,} Florida dentists by city and specialty. Listings come from the public NPI registry.",
        f"""<h1>Find a dentist in Florida</h1>
<form id="search" role="search" onsubmit="return false"><label for="q">Dentist name, city or specialty</label>
<input id="q" type="search" autocomplete="off" placeholder="e.g. Miami, orthodontist, Smith">
<ul id="results" aria-live="polite" class="list"></ul></form>
<p class="muted">Florida only for now. Other states are coming soon.</p>
<h2>Top Florida cities</h2><ul class="list cols">{cl}</ul>
<p><a href="/fl/">See all Florida cities</a></p>
<h2>Specialties</h2><ul class="list cols">{sl}</ul>""",
        '<script src="/search.js" defer></script>'))

    # /fl/
    al = "".join(f'<li><a href="/fl/{c}/">{esc(cname[c])}</a> <span class="muted">{len(by_city[c]):,}</span></li>'
                 for c in sorted(by_city, key=lambda c: cname[c]))
    urls.append(page("fl/index.html", "Florida Dentists by City | DentistryUSA",
        "Every Florida city with listed dentists.", crumbs(("Home", "/"), ("Florida", None)) +
        f'<h1>Florida dentists by city</h1><ul class="list cols">{al}</ul>'))

    # city + city/specialty
    for c, lst in by_city.items():
        city = cname[c]
        specs = sorted({r["sslug"] for r in lst}, key=lambda s: sname[s])
        sp = "".join(f'<li><a href="/fl/{c}/{s}/">{esc(sname[s])}</a> <span class="muted">{len(by_cs[(c, s)]):,}</span></li>' for s in specs)
        urls.append(page(f"fl/{c}/index.html", f"Dentists in {city}, FL | DentistryUSA",
            f"{len(lst):,} dentists in {city}, Florida, listed from the public NPI registry.",
            crumbs(("Home", "/"), ("Florida", "/fl/"), (city, None)) +
            f'<h1>Dentists in {esc(city)}, FL</h1><p>{len(lst):,} listings.</p><h2>By specialty</h2>'
            f'<ul class="list cols">{sp}</ul><h2>All dentists</h2><ul class="list">' +
            "".join(dentist_li(r) for r in lst) + "</ul>"))
        for s in specs:
            sl_ = by_cs[(c, s)]
            urls.append(page(f"fl/{c}/{s}/index.html", f"{sname[s]} in {city}, FL | DentistryUSA",
                f"{len(sl_):,} {sname[s].lower()} listings in {city}, Florida from the public NPI registry.",
                crumbs(("Home", "/"), ("Florida", "/fl/"), (city, f"/fl/{c}/"), (sname[s], None)) +
                f'<h1>{esc(sname[s])} in {esc(city)}, FL</h1><ul class="list">' +
                "".join(dentist_li(r) for r in sl_) + "</ul>"))

    # profiles
    search = []
    for r in rows:
        po = is_po(r["address1"])
        if po:
            addr = "Address on file"
        else:
            addr = ", ".join(x for x in (r["addr1"], r["addr2"]) if x) + f", {r['city']}, FL {r['zip5']}"
        cred = f", {r['credential']}" if r["credential"] else ""
        title = f"{r['name']}{cred}, {r['spec']} in {r['city']}, FL | DentistryUSA"
        ld = {"@context": "https://schema.org", "@type": "Dentist", "name": r["name"],
              "medicalSpecialty": "Dentistry", "url": BASE + r["url"]}
        if r["phone"]: ld["telephone"] = r["phone"]
        if not po:
            ld["address"] = {"@type": "PostalAddress", "streetAddress": ", ".join(x for x in (r["addr1"], r["addr2"]) if x),
                             "addressLocality": r["city"], "addressRegion": "FL", "postalCode": r["zip5"], "addressCountry": "US"}
        mates = [m for m in by_practice[r["pkey"]] if m["npi"] != r["npi"]] if not po else []
        mates_html = ("<h2>Other dentists at this address</h2><ul class=\"list\">" +
                      "".join(dentist_li(m) for m in mates[:8]) + "</ul>") if mates else ""
        phone = (f'<dt>Phone</dt><dd><a href="tel:+1{re.sub(chr(92)+"D", "", r["phone"])}">{esc(r["phone"])}</a></dd>'
                 if r["phone"] else "")
        urls.append(page(f"dentist/{r['npi']}-{r['nslug']}/index.html", title,
            f"{r['name']}{cred}, {r['spec'].lower()} in {r['city']}, FL. Practice address, phone and NPI from the public NPI registry.",
            crumbs(("Home", "/"), ("Florida", "/fl/"), (r["city"], f"/fl/{r['cslug']}/"), (r["name"], None)) +
            f"""<h1>{esc(r['name'])}{esc(cred)}</h1>
<p class="lead">{esc(r['spec'])} in <a href="/fl/{r['cslug']}/">{esc(r['city'])}, FL</a></p>
<dl class="facts"><dt>Practice address</dt><dd>{esc(addr)}</dd>{phone}<dt>NPI</dt><dd>{r['npi']}</dd></dl>
<div class="claim"><p><strong>Is this you?</strong> Claim your free listing to fix details and add your own.</p>
<a class="btn" href="/claim/?npi={r['npi']}">Claim your free listing</a></div>
{mates_html}
<p class="muted">This information comes from the public NPI registry and may be out of date.</p>""",
            f'<script type="application/ld+json">{json.dumps(ld).replace("</", "<\\/")}</script>'))
        search.append({"npi": r["npi"], "name": r["name"] + cred, "city": r["city"], "specialty": r["spec"], "url": r["url"]})

    # pricing
    def tier(name, price, items):
        return (f'<section class="tier"><h2>{name}</h2><p class="price">${price}<span>/month</span></p><ul>' +
                "".join(f"<li>{i}</li>" for i in items) +
                '</ul><button type="button" disabled>Coming soon</button></section>')
    urls.append(page("pricing/index.html", "Pricing | DentistryUSA",
        "DentistryUSA plans for dentists: Listing $29.99, Premium $49.99, Listing + Website $99.99 per month.",
        """<h1>Get found by patients in your area.</h1>
<p>Every dentist in Florida has a free DentistryUSA profile. Renew your listing to add your photos, hours and booking link, and to show up first in your city.</p>
<div class="tiers">""" +
        tier("Listing", "29.99", ["Photos, hours, insurance accepted", "Your website and booking link"]) +
        tier("Premium", "49.99", ["Everything in Listing", "No other dentists' ads on your profile", "Monthly report of calls and clicks", "Lock a sponsored spot in your city"]) +
        tier("Listing + Website", "99.99", ["Everything in Premium", "A one-page website for your practice, hosted by us"]) +
        """</div>
<p><strong>Lock your spot.</strong> Hold sponsored spot 1, 2 or 3 in your city and specialty for as long as you stay subscribed. One dentist per spot, first come.</p>
<p>Monthly. Cancel anytime from your account. The free profile stays free.</p>
<!-- TODO(Jelo): spec section 7 ROI slider; wire buttons to Stripe Checkout (test mode first). Spec lists a license badge on the Listing tier; omitted until the FL MQA license file is pulled. -->"""))

    # claim
    urls.append(page("claim/index.html", "Claim Your Free Listing | DentistryUSA",
        "Claim and update your free DentistryUSA dentist listing.",
        """<h1>Claim your free listing</h1>
<p>Tell us who you are and we will follow up. Claiming is free.</p>
<!-- TODO(Jelo): this form posts nowhere. Build the backend (spec section 4): POST to your endpoint,
     email a magic link to the address, create the claim row, then let them edit. Until then JS shows a notice. -->
<form id="claim" method="post" action="#" novalidate>
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
</script>""", noindex=True))
    urls.pop()  # claim page is noindex; keep it out of the sitemap

    write("search.json", json.dumps(search, separators=(",", ":")))
    write("search.js", SEARCH_JS)
    write("robots.txt", f"User-agent: *\nAllow: /\nDisallow: /preview/\nDisallow: /account/\nDisallow: /admin/\nDisallow: /claim/\n\nSitemap: {BASE}/sitemap.xml\n")
    # sitemap limit is 50k URLs per file; this site is well under
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
          "".join(f"<url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    return len(rows), len(by_city), len(by_cs), len(urls)

SEARCH_JS = r"""(function(){
var q=document.getElementById("q"),out=document.getElementById("results"),data=null,loading=false;
function esc(s){return s.replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function run(){var t=q.value.trim().toLowerCase();if(t.length<2){out.innerHTML="";return}
var w=t.split(/\s+/),hits=[];for(var i=0;i<data.length&&hits.length<20;i++){var d=data[i],h=(d.name+" "+d.city+" "+d.specialty).toLowerCase();
if(w.every(function(x){return h.indexOf(x)>-1}))hits.push(d)}
out.innerHTML=hits.length?hits.map(function(d){return '<li><a href="'+d.url+'">'+esc(d.name)+'</a> <span class="muted">'+esc(d.specialty)+', '+esc(d.city)+'</span></li>'}).join(""):"<li>No matches.</li>"}
q.addEventListener("input",function(){if(data)return run();if(loading)return;loading=true;
fetch("/search.json").then(function(r){return r.json()}).then(function(j){data=j;run()}).catch(function(){out.innerHTML="<li>Search is unavailable right now.</li>"})});
})();"""

if __name__ == "__main__":
    n, c, cs, u = build()
    print(f"dentists={n} cities={c} city+specialty={cs} sitemap_urls={u}")

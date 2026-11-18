#!/usr/bin/env python3
"""Run after build.py: python3 test_build.py"""
import os, re, glob, json
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
SUPPORT = "support@dentistryusa.com"   # the one email address pages may show
read = lambda p: open(p, encoding="utf-8").read()
pages = glob.glob(D + "/**/index.html", recursive=True)
assert len(pages) > 1000, len(pages)
prof = glob.glob(D + "/dentist/1306153150-*/index.html")
assert prof, "known NPI profile missing"
t = read(prof[0])
assert "Address on file" in t and "366156" not in t  # PO box hidden
assert "/claim/?npi=1306153150" in t and "application/ld+json" in t
assert "/remove/?npi=1306153150" in t
# booking box (filled in by booking.js when the practice books online)
assert 'id="book"' in t and 'data-npi="1306153150"' in t and "/booking.js" in t and 'id="claimBox"' in t
sm = read(D + "/sitemap.xml")
assert "/dentist/1306153150-" in sm
bad = [p for p in pages if not re.search(r"<title>[^<]+</title>", read(p))]
assert not bad, bad[:3]
for p in pages:
    s = read(p)
    assert 'rel="canonical"' in s and 'name="description"' in s, p
    visible = re.sub(r"<script.*?</script>", "", s, flags=re.S).replace(SUPPORT, "")
    assert "verified" not in s.lower() and not re.search(r"[\w.]+@[\w.]+\.\w+", visible), p
    assert 'href="/remove/"' in s and 'href="/account/"' in s and SUPPORT in s, p   # footer
assert os.path.exists(D + "/search.json") and os.path.exists(D + "/robots.txt")

# 25 dentists per page, with working page links
miami = read(D + "/fl/miami/index.html")
assert miami.count('class="doc"') == 25 and 'href="/fl/miami/page/2/"' in miami
assert "/online.js" in miami   # "Book online" marks
last = sorted(glob.glob(D + "/fl/miami/page/*/index.html"), key=lambda p: int(p.replace("\\", "/").split("/")[-2]))[-1]
assert 0 < read(last).count('class="doc"') <= 25 and 'rel="prev"' in read(last)
for p in glob.glob(D + "/fl/*/index.html") + glob.glob(D + "/fl/*/*/index.html"):
    assert read(p).count('class="doc"') <= 25, p

# search index: every profile once, in the short format search.js expects
idx = json.loads(read(D + "/search.json"))
profiles = glob.glob(D + "/dentist/*/index.html")
assert len(idx["rows"]) == len(profiles), (len(idx["rows"]), len(profiles))
assert all(len(r) == 6 and re.fullmatch(r"\d{10}", r[0]) and re.fullmatch(r"\d{5}", r[5]) for r in idx["rows"])
assert "Orthodontics" in idx["specs"] and "Miami" in idx["cities"]

# forms, admin, the dentist's account and the patient's appointment page:
# present, noindex, and kept out of the sitemap
for name, marker in (("claim", 'id="claim"'), ("remove", 'id="remove"'), ("admin", 'id="admin"'),
                     ("account", 'id="account"'), ("appointment", 'id="appt"')):
    s = read(f"{D}/{name}/index.html")
    assert marker in s and 'content="noindex"' in s and f"/{name}/" not in sm, name
for f in ("config.js", "vendor/supabase-js-2.119.0.js", "booking.js", "account.js", "online.js", "forms.js", "admin.js"):
    assert os.path.exists(f"{D}/{f}"), f

# the visit reasons offered on profiles are exactly the ones the database accepts
HERE = os.path.dirname(os.path.abspath(__file__))
js_reasons = re.findall(r"'([^']+)'", re.search(r"var REASONS = \[(.*?)\];", read(HERE + "/static/booking.js"), re.S).group(1))
sql_reasons = re.findall(r"'([^']+)'", re.search(r"visit_reasons\(\).*?array\[(.*?)\]", read(HERE + "/supabase/migrations/001_booking.sql"), re.S).group(1))
assert js_reasons == sql_reasons and len(js_reasons) == 8, (js_reasons, sql_reasons)

# preview builds keep search engines out; real-domain builds point them at the sitemap
robots = read(D + "/robots.txt")
assert ("Disallow: /\n" in robots and 'content="noindex"' in read(D + "/index.html")) or "Sitemap:" in robots
print("OK", len(pages), "pages")

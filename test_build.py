#!/usr/bin/env python3
"""Run after build.py: python3 test_build.py"""
import os, re, glob
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
pages = glob.glob(D + "/**/index.html", recursive=True)
assert len(pages) > 1000, len(pages)
prof = glob.glob(D + "/dentist/1306153150-*/index.html")
assert prof, "known NPI profile missing"
t = open(prof[0]).read()
assert "Address on file" in t and "366156" not in t  # PO box hidden
assert "/claim/?npi=1306153150" in t and "application/ld+json" in t
sm = open(D + "/sitemap.xml").read()
assert "/dentist/1306153150-" in sm
bad = [p for p in pages if not re.search(r"<title>[^<]+</title>", open(p).read())]
assert not bad, bad[:3]
for p in pages:
    s = open(p).read()
    assert 'rel="canonical"' in s and 'name="description"' in s, p
    assert "verified" not in s.lower() and not re.search(r"[\w.]+@[\w.]+\.\w+", re.sub(r"<script.*?</script>", "", s, flags=re.S)), p
assert os.path.exists(D + "/search.json") and os.path.exists(D + "/robots.txt")
print("OK", len(pages), "pages")

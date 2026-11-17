#!/usr/bin/env python3
"""Load (or refresh) public.dentists from the same rows the site is built from.

    SUPABASE_ACCESS_TOKEN=sbp_... SUPABASE_PROJECT_REF=xxxx python3 supabase/load_dentists.py

Uses build.py's load(), so names, cities and URLs match the pages exactly.
Run it after supabase/migrations/001_booking.sql, and again whenever the CSV changes.
"""
import json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import build  # noqa: E402

TOKEN = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
REF = os.environ.get("SUPABASE_PROJECT_REF", "")
BATCH = 3000


def query(sql):
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{REF}/database/query",
        data=json.dumps({"query": sql}).encode(), method="POST",
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json",
                 "User-Agent": "dentistryusa-loader"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read() or b"null")


def main():
    if not TOKEN or not REF:
        sys.exit("Set SUPABASE_ACCESS_TOKEN and SUPABASE_PROJECT_REF.")
    rows = []
    for r in build.load():
        place = f"{r['city']}, FL {r['zip5']}"
        rows.append({
            "npi": r["npi"], "name": r["name"], "credential": r["credential"], "specialty": r["spec"],
            "city": r["city"],
            "address": "" if r["po"] else ", ".join(x for x in (r["street"], place) if x),
            "phone": r["phone"], "url": r["url"],
        })
    for i in range(0, len(rows), BATCH):
        payload = json.dumps(rows[i:i + BATCH], separators=(",", ":"))
        assert "$rows$" not in payload
        query(f"""insert into public.dentists (npi, name, credential, specialty, city, address, phone, url)
select npi, name, credential, specialty, city, address, phone, url
from json_populate_recordset(null::public.dentists, $rows${payload}$rows$)
on conflict (npi) do update set name = excluded.name, credential = excluded.credential,
  specialty = excluded.specialty, city = excluded.city, address = excluded.address,
  phone = excluded.phone, url = excluded.url""")
        print(f"loaded {min(i + BATCH, len(rows)):,} / {len(rows):,}")
    print("rows in public.dentists:", query("select count(*)::int as n from public.dentists")[0]["n"])


if __name__ == "__main__":
    main()

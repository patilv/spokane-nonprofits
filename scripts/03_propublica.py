"""Fetch detailed IRS 990 financials for larger regional nonprofits.

Uses the ProPublica Nonprofit Explorer API v2 organization endpoint, which
returns per-filing extracts of Form 990 financial data. We pull every active
region org reporting BMF revenue >= $500,000 (plus the top 25 by assets).

Output (nonprofit-site/data/):
  filings.csv - one row per org per fiscal year with key 990 fields
"""

import json
import os
import time
import urllib.request

import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "..", "data")
API = "https://projects.propublica.org/nonprofits/api/v2/organizations/{ein}.json"

FIELDS = [
    "tax_prd_yr", "formtype", "totrevenue", "totfuncexpns", "totassetsend",
    "totliabend", "totnetassetend", "totcntrbgfts", "totprgmrevnue",
    "invstmntinc", "compnsatncurrofcr", "othrsalwages", "payrolltx",
    "profndraising", "grsincfndrsng",
]


def fetch(ein: str) -> list[dict]:
    req = urllib.request.Request(
        API.format(ein=ein),
        headers={"User-Agent": "Mozilla/5.0 (research download)"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
    rows = []
    for f in d.get("filings_with_data") or []:
        row = {k: f.get(k) for k in FIELDS}
        row["ein"] = ein
        rows.append(row)
    return rows


def main() -> None:
    orgs = pd.read_csv(os.path.join(OUT, "orgs_active.csv"), dtype={"ein": str, "zip": str})
    big = orgs[orgs["revenue"] >= 500_000]
    top_assets = orgs.nlargest(25, "assets")
    targets = pd.concat([big, top_assets]).drop_duplicates("ein")
    print(f"Fetching filings for {len(targets)} organizations ...")

    all_rows = []
    for i, ein in enumerate(targets["ein"], 1):
        all_rows.extend(fetch(ein))
        if i % 50 == 0:
            print(f"  {i}/{len(targets)}")
        time.sleep(0.5)

    df = pd.DataFrame(all_rows)
    meta = targets[["ein", "name", "city", "county", "subsector_name",
                    "ntee_major", "ntee_major_name"]]
    df = df.merge(meta, on="ein", how="left")
    df.to_csv(os.path.join(OUT, "filings.csv"), index=False)
    print(f"filings: {len(df)} rows, {df['ein'].nunique()} orgs with data")


if __name__ == "__main__":
    main()

"""Fetch Census ACS (population, poverty, income) and CDC/ATSDR SVI data.

ACS 2019-2023 5-year estimates come from the public data.census.gov access
API (the same tables tidycensus retrieves). SVI 2022 comes from the CDC/ATSDR
direct CSV downloads.

Outputs (nonprofit-site/data/):
  county_census.csv - population, poverty, income, SVI for the 7 counties
  zcta_census.csv   - population + poverty rate for region ZIP codes
  svi_tracts.csv    - tract-level SVI 2022 for the region counties
"""

import io
import json
import os
import time
import urllib.request

import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "..", "data")

COUNTIES = {
    "53063": "Spokane County",
    "53065": "Stevens County",
    "53051": "Pend Oreille County",
    "53043": "Lincoln County",
    "53075": "Whitman County",
    "16055": "Kootenai County",
    "16057": "Latah County",
}

API = "https://data.census.gov/api/access/data/table?id={table}&g={geo}"


def fetch_table(table: str, geo: str) -> dict:
    url = API.format(table=table, geo=geo)
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (research download)"}
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                payload = json.load(r)
            data = payload["response"]["data"]
            header, row = data[0], data[1]
            return dict(zip(header, row))
        except Exception as e:  # noqa: BLE001 - retry then surface
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    return {}


def county_census() -> pd.DataFrame:
    rows = []
    for fips, name in COUNTIES.items():
        geo = f"050XX00US{fips}"
        pop = fetch_table("ACSDT5Y2023.B01003", geo)
        pov = fetch_table("ACSST5Y2023.S1701", geo)
        inc = fetch_table("ACSDT5Y2023.B19013", geo)
        rows.append(
            {
                "fips": fips,
                "county": name,
                "state": "WA" if fips.startswith("53") else "ID",
                "population": float(pop["B01003_001E"]),
                "poverty_universe": float(pov["S1701_C01_001E"]),
                "poverty_count": float(pov["S1701_C02_001E"]),
                "poverty_rate": float(pov["S1701_C03_001E"]),
                "child_poverty_rate": float(pov["S1701_C03_002E"]),
                "median_hh_income": float(inc["B19013_001E"]),
            }
        )
        time.sleep(0.5)
    return pd.DataFrame(rows)


def zcta_census(zips: list[str]) -> pd.DataFrame:
    rows = []
    for z in zips:
        geo = f"860XX00US{z}"
        try:
            pov = fetch_table("ACSST5Y2023.S1701", geo)
            rows.append(
                {
                    "zip": z,
                    "population": float(pov["S1701_C01_001E"] or 0),
                    "poverty_count": float(pov["S1701_C02_001E"] or 0),
                    "poverty_rate": (
                        float(pov["S1701_C03_001E"])
                        if pov.get("S1701_C03_001E") not in (None, "", "-", "N")
                        else None
                    ),
                }
            )
        except Exception as e:  # some ZIPs are not ZCTAs (PO-box only)
            print(f"  ZCTA {z}: skipped ({e})")
        time.sleep(0.4)
    return pd.DataFrame(rows)


def svi() -> tuple[pd.DataFrame, pd.DataFrame]:
    base = "https://svi.cdc.gov/Documents/Data/2022/csv"
    req = urllib.request.Request(
        f"{base}/states_counties/SVI_2022_US_county.csv",
        headers={"User-Agent": "Mozilla/5.0 (research download)"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        county = pd.read_csv(io.BytesIO(r.read()), dtype={"FIPS": str, "ST": str})
    county = county[county["FIPS"].isin(COUNTIES)]
    keep = county[
        ["FIPS", "COUNTY", "RPL_THEMES", "RPL_THEME1", "RPL_THEME2",
         "RPL_THEME3", "RPL_THEME4", "EP_POV150", "EP_UNEMP", "EP_HBURD",
         "EP_NOHSDP", "EP_UNINSUR", "EP_DISABL", "EP_SNGPNT", "EP_MINRTY"]
    ].rename(columns={"FIPS": "fips"})

    tracts = []
    for st in ("Washington", "Idaho"):
        req = urllib.request.Request(
            f"{base}/states/{st}.csv",
            headers={"User-Agent": "Mozilla/5.0 (research download)"},
        )
        with urllib.request.urlopen(req, timeout=180) as r:
            t = pd.read_csv(io.BytesIO(r.read()), dtype={"FIPS": str, "STCNTY": str})
        tracts.append(t[t["STCNTY"].isin(COUNTIES)])
    tr = pd.concat(tracts)
    tr = tr[
        ["FIPS", "STCNTY", "LOCATION", "E_TOTPOP", "RPL_THEMES", "RPL_THEME1",
         "RPL_THEME2", "RPL_THEME3", "RPL_THEME4", "EP_POV150"]
    ].rename(columns={"FIPS": "tract_fips", "STCNTY": "fips"})
    tr["county"] = tr["fips"].map(COUNTIES)
    tr = tr[tr["RPL_THEMES"] >= 0]  # -999 = insufficient data
    return keep, tr


def main() -> None:
    print("Fetching county ACS ...")
    cc = county_census()

    print("Fetching SVI ...")
    svi_county, svi_tr = svi()
    cc = cc.merge(svi_county.drop(columns=["COUNTY"]), on="fips", how="left")
    cc.to_csv(os.path.join(OUT, "county_census.csv"), index=False)
    svi_tr.to_csv(os.path.join(OUT, "svi_tracts.csv"), index=False)

    print("Fetching ZCTA ACS ...")
    zips = sorted(
        pd.read_csv(os.path.join(OUT, "zip_counts.csv"), dtype=str)["zip"].unique()
    )
    zc = zcta_census(zips)
    zc.to_csv(os.path.join(OUT, "zcta_census.csv"), index=False)
    print(cc[["county", "population", "poverty_rate", "RPL_THEMES"]])
    print(f"ZCTAs fetched: {len(zc)} of {len(zips)} | tracts: {len(svi_tr)}")


if __name__ == "__main__":
    main()

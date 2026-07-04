"""Join BMF, Census/SVI, and 990 filings into site-ready analysis datasets.

Outputs (nonprofit-site/data/):
  county_summary.csv - one row per county: orgs, density, poverty, income, SVI
  zip_gaps.csv       - one row per ZIP: org counts, centroid, poverty, coverage
  fin_metrics.csv    - one row per org: latest-filing financial health metrics
  fin_by_year.csv    - aggregate financial trend among 990 filers
  stats.json         - headline numbers used in narrative
"""

import json
import os

import numpy as np
import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "..", "data")
HS_LETTERS = set("IJKLOP")


def main() -> None:
    orgs = pd.read_csv(os.path.join(OUT, "orgs_active.csv"),
                       dtype={"ein": str, "zip": str})
    county_bmf = pd.read_csv(os.path.join(OUT, "county_bmf.csv"),
                             dtype={"fips": str})
    census = pd.read_csv(os.path.join(OUT, "county_census.csv"),
                         dtype={"fips": str})
    zcta = pd.read_csv(os.path.join(OUT, "zcta_census.csv"), dtype={"zip": str})
    zips = pd.read_csv(os.path.join(OUT, "zip_counts.csv"), dtype={"zip": str})
    filings = pd.read_csv(os.path.join(OUT, "filings.csv"), dtype={"ein": str})

    # ---- county_summary ---------------------------------------------------
    cs = county_bmf.merge(census.drop(columns=["county"]), on="fips", how="left")
    cs["orgs_per_10k"] = cs["n_orgs"] / cs["population"] * 10_000
    cs["hs_per_10k"] = cs["n_human_services"] / cs["population"] * 10_000
    cs["revenue_per_capita"] = cs["total_revenue"] / cs["population"]
    cs.to_csv(os.path.join(OUT, "county_summary.csv"), index=False)

    # ---- zip_gaps -----------------------------------------------------------
    cent = (
        orgs.dropna(subset=["lat", "lon"])
        .groupby("zip", as_index=False)
        .agg(lat=("lat", "median"), lon=("lon", "median"))
    )
    # A ZIP that straddles a county line appears once per county in zip_counts;
    # collapse to one row per ZIP (majority county) before joining ZCTA data.
    zips = (
        zips.sort_values("n_orgs", ascending=False)
        .groupby("zip", as_index=False)
        .agg(
            county=("county", "first"),
            n_orgs=("n_orgs", "sum"),
            n_human_services=("n_human_services", "sum"),
            total_revenue=("total_revenue", "sum"),
        )
    )
    zg = (
        zips.merge(zcta, on="zip", how="left")
        .merge(cent, on="zip", how="left")
    )
    zg = zg[zg["population"].fillna(0) >= 100]  # drop PO-box / tiny ZCTAs
    zg["orgs_per_1k"] = zg["n_orgs"] / zg["population"] * 1_000
    zg["hs_per_1k"] = zg["n_human_services"] / zg["population"] * 1_000
    zg.to_csv(os.path.join(OUT, "zip_gaps.csv"), index=False)

    # ---- financial metrics (latest filing per org) --------------------------
    f = filings.dropna(subset=["totrevenue", "totfuncexpns"]).copy()
    f = f[f["formtype"].isin([0, 1])]  # 990 and 990-EZ (exclude 990-PF)
    f = f.sort_values("tax_prd_yr").groupby("ein").tail(1)
    f = f[f["tax_prd_yr"] >= 2021]  # only reasonably current filings
    f["net_assets"] = f["totnetassetend"]
    f["margin"] = np.where(
        f["totrevenue"] > 0,
        (f["totrevenue"] - f["totfuncexpns"]) / f["totrevenue"], np.nan)
    f["months_reserves"] = np.where(
        f["totfuncexpns"] > 0,
        f["net_assets"] / (f["totfuncexpns"] / 12), np.nan)
    f["contrib_share"] = np.where(
        f["totrevenue"] > 0, f["totcntrbgfts"] / f["totrevenue"], np.nan)
    f["personnel_share"] = np.where(
        f["totfuncexpns"] > 0,
        (f["compnsatncurrofcr"].fillna(0) + f["othrsalwages"].fillna(0)
         + f["payrolltx"].fillna(0)) / f["totfuncexpns"], np.nan)
    keep = f[
        ["ein", "name", "city", "county", "subsector_name", "ntee_major",
         "ntee_major_name", "tax_prd_yr", "totrevenue", "totfuncexpns",
         "totassetsend", "net_assets", "margin", "months_reserves",
         "contrib_share", "personnel_share"]
    ]
    keep.to_csv(os.path.join(OUT, "fin_metrics.csv"), index=False)

    # ---- aggregate trend among filers ---------------------------------------
    fy = filings.dropna(subset=["totrevenue"])
    fy = fy[(fy["tax_prd_yr"] >= 2012) & (fy["tax_prd_yr"] <= 2024)]
    by = fy.groupby("tax_prd_yr", as_index=False).agg(
        n=("ein", "nunique"),
        total_revenue=("totrevenue", "sum"),
        total_expenses=("totfuncexpns", "sum"),
        median_revenue=("totrevenue", "median"),
    )
    by.to_csv(os.path.join(OUT, "fin_by_year.csv"), index=False)

    # ---- headline stats ------------------------------------------------------
    hs = orgs[orgs["ntee_major"].isin(HS_LETTERS)]
    spokane = cs[cs["county"] == "Spokane County"].iloc[0]
    stats = {
        "n_active": int(len(orgs)),
        "n_counties": int(cs.shape[0]),
        "total_population": int(cs["population"].sum()),
        "total_revenue": float(orgs["revenue"].sum()),
        "total_assets": float(orgs["assets"].sum()),
        "n_reporting_revenue": int((orgs["revenue"] > 0).sum()),
        "n_human_services": int(len(hs)),
        "hs_share": float(len(hs) / len(orgs)),
        "region_orgs_per_10k": float(len(orgs) / cs["population"].sum() * 1e4),
        "spokane_orgs": int(spokane["n_orgs"]),
        "spokane_per_10k": float(spokane["orgs_per_10k"]),
        "median_poverty_rate": float(cs["poverty_rate"].median()),
        "n_filers": int(keep["ein"].nunique()),
        "median_margin": float(keep["margin"].median()),
        "median_months_reserves": float(keep["months_reserves"].median()),
        "pct_negative_margin": float((keep["margin"] < 0).mean()),
        "pct_low_reserves": float((keep["months_reserves"] < 3).mean()),
    }
    with open(os.path.join(OUT, "stats.json"), "w") as fh:
        json.dump(stats, fh, indent=2)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()

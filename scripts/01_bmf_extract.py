"""Extract Inland Northwest nonprofits from the NCCS geocoded Business Master File.

Inputs (downloaded from NCCS state marts, see methodology.qmd):
  raw/bmf_master_WA.csv, raw/bmf_master_ID.csv
Outputs (written to nonprofit-site/data/):
  orgs_active.csv      - active orgs in the 7-county region (map/table detail)
  formations.csv       - IRS ruling-year counts by county (all vintages)
  subsector_counts.csv - region vs. WA vs. ID counts by NTEE v2 subsector
  ntee_major.csv       - active region counts by NTEE major group letter
  county_bmf.csv       - per-county aggregates from the BMF
  zip_counts.csv       - active org counts by ZIP code
"""

import os
import sys

import pandas as pd

RAW = sys.argv[1] if len(sys.argv) > 1 else "raw"
OUT = os.path.join(os.path.dirname(__file__), "..", "data")

REGION = {
    "Spokane County": ("WA", "53063"),
    "Stevens County": ("WA", "53065"),
    "Pend Oreille County": ("WA", "53051"),
    "Lincoln County": ("WA", "53043"),
    "Whitman County": ("WA", "53075"),
    "Kootenai County": ("ID", "16055"),
    "Latah County": ("ID", "16057"),
}

SUBSECTOR_NAMES = {
    "ART": "Arts & Culture",
    "EDU": "Education",
    "ENV": "Environment & Animals",
    "HEL": "Health",
    "HMS": "Human Services",
    "HOS": "Hospitals",
    "IFA": "International",
    "MMB": "Mutual & Membership Benefit",
    "PSB": "Public & Societal Benefit",
    "REL": "Religion",
    "UNI": "Universities",
    "UNU": "Unclassified",
}

NTEE_MAJOR = {
    "A": "Arts, Culture & Humanities", "B": "Education",
    "C": "Environment", "D": "Animal-Related",
    "E": "Health Care", "F": "Mental Health & Crisis Intervention",
    "G": "Voluntary Health Associations", "H": "Medical Research",
    "I": "Crime & Legal-Related", "J": "Employment",
    "K": "Food, Agriculture & Nutrition", "L": "Housing & Shelter",
    "M": "Public Safety & Disaster Relief", "N": "Recreation & Sports",
    "O": "Youth Development", "P": "Human Services",
    "Q": "International Affairs", "R": "Civil Rights & Advocacy",
    "S": "Community Improvement", "T": "Philanthropy & Grantmaking",
    "U": "Science & Technology", "V": "Social Science",
    "W": "Public & Societal Benefit", "X": "Religion-Related",
    "Y": "Mutual & Membership Benefit", "Z": "Unknown",
}


def load_state(path: str) -> pd.DataFrame:
    cols = [
        "ein", "org_name_display", "org_addr_city", "org_addr_state",
        "org_addr_zip5", "geo_county", "geo_lat", "geo_lon",
        "ruling_date", "ntee_code_clean", "nteev2_subsector",
        "ntee_code_definition", "subsection_code", "foundation_code",
        "revenue_amount", "income_amount", "asset_amount",
        "last_year_in_bmf", "first_year_in_bmf", "bmf_vintage_ym", "state",
    ]
    df = pd.read_csv(path, dtype=str, usecols=cols, low_memory=False)
    # Normalize county name ("Spokane" and "Spokane County" both occur)
    df["county"] = df["geo_county"].str.strip()
    df.loc[df["county"].notna() & ~df["county"].str.endswith("County", na=False), "county"] = (
        df["county"] + " County"
    )
    for c in ("revenue_amount", "income_amount", "asset_amount", "geo_lat", "geo_lon"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["ruling_year"] = pd.to_datetime(df["ruling_date"], errors="coerce").dt.year
    df["ntee_major"] = df["ntee_code_clean"].str[0].str.upper()
    df["active"] = df["last_year_in_bmf"] == "2026"
    return df


def main() -> None:
    wa = load_state(os.path.join(RAW, "bmf_master_WA.csv"))
    idaho = load_state(os.path.join(RAW, "bmf_master_ID.csv"))
    both = pd.concat([wa, idaho], ignore_index=True)

    # ZIP -> county fallback (majority vote among geocoded rows) for
    # historical records that were never geocoded.
    zipmap = (
        both.dropna(subset=["county", "org_addr_zip5"])
        .groupby("org_addr_zip5")["county"]
        .agg(lambda s: s.mode()[0])
    )
    both["county"] = both["county"].fillna(both["org_addr_zip5"].map(zipmap))

    region = both[both["county"].isin(REGION)].copy()
    region["county_state"] = region["county"] + ", " + region["county"].map(
        {k: v[0] for k, v in REGION.items()}
    )
    region["subsector_name"] = (
        region["nteev2_subsector"].map(SUBSECTOR_NAMES).fillna("Unclassified")
    )
    region["ntee_major_name"] = region["ntee_major"].map(NTEE_MAJOR).fillna("Unknown")

    active = region[region["active"]].copy()

    # --- orgs_active.csv ------------------------------------------------
    keep = active[
        [
            "ein", "org_name_display", "org_addr_city", "org_addr_zip5",
            "county", "county_state", "geo_lat", "geo_lon", "ruling_year",
            "ntee_code_clean", "ntee_major", "ntee_major_name",
            "nteev2_subsector", "subsector_name", "ntee_code_definition",
            "subsection_code", "foundation_code",
            "revenue_amount", "income_amount", "asset_amount", "state",
        ]
    ].rename(
        columns={
            "org_name_display": "name", "org_addr_city": "city",
            "org_addr_zip5": "zip", "geo_lat": "lat", "geo_lon": "lon",
            "ntee_code_clean": "ntee", "nteev2_subsector": "subsector",
            "revenue_amount": "revenue", "income_amount": "income",
            "asset_amount": "assets",
        }
    )
    keep["name"] = keep["name"].str.title()
    keep["city"] = keep["city"].str.title()
    keep.to_csv(os.path.join(OUT, "orgs_active.csv"), index=False)

    # --- formations.csv (all vintages, incl. defunct orgs) ---------------
    form = (
        region.dropna(subset=["ruling_year"])
        .groupby(["ruling_year", "county"], as_index=False)
        .agg(n=("ein", "count"), n_active=("active", "sum"))
    )
    form["ruling_year"] = form["ruling_year"].astype(int)
    form = form[(form["ruling_year"] >= 1940) & (form["ruling_year"] <= 2026)]
    form.to_csv(os.path.join(OUT, "formations.csv"), index=False)

    # --- subsector_counts.csv: region vs statewide ----------------------
    def subsector_share(df: pd.DataFrame, label: str) -> pd.DataFrame:
        d = df[df["active"]].copy()
        d["subsector_name"] = (
            d["nteev2_subsector"].map(SUBSECTOR_NAMES).fillna("Unclassified")
        )
        out = d.groupby("subsector_name", as_index=False).agg(n=("ein", "count"))
        out["share"] = out["n"] / out["n"].sum()
        out["geo"] = label
        return out

    pd.concat(
        [
            subsector_share(region, "Inland Northwest"),
            subsector_share(wa, "Washington (statewide)"),
            subsector_share(idaho, "Idaho (statewide)"),
        ]
    ).to_csv(os.path.join(OUT, "subsector_counts.csv"), index=False)

    # --- ntee_major.csv --------------------------------------------------
    nm = active.groupby(
        ["ntee_major", "ntee_major_name"], as_index=False
    ).agg(n=("ein", "count"), revenue=("revenue_amount", "sum"))
    nm.to_csv(os.path.join(OUT, "ntee_major.csv"), index=False)

    # --- county_bmf.csv ---------------------------------------------------
    cb = active.groupby(["county", "county_state"], as_index=False).agg(
        n_orgs=("ein", "count"),
        total_revenue=("revenue_amount", "sum"),
        total_assets=("asset_amount", "sum"),
        n_reporting=("revenue_amount", lambda s: (s > 0).sum()),
        n_human_services=("ntee_major", lambda s: s.isin(list("IJKLOP")).sum()),
    )
    cb["fips"] = cb["county"].map({k: v[1] for k, v in REGION.items()})
    cb.to_csv(os.path.join(OUT, "county_bmf.csv"), index=False)

    # --- zip_counts.csv ---------------------------------------------------
    zc = active.dropna(subset=["org_addr_zip5"]).groupby(
        ["org_addr_zip5", "county"], as_index=False
    ).agg(
        n_orgs=("ein", "count"),
        n_human_services=("ntee_major", lambda s: s.isin(list("IJKLOP")).sum()),
        total_revenue=("revenue_amount", "sum"),
    ).rename(columns={"org_addr_zip5": "zip"})
    zc.to_csv(os.path.join(OUT, "zip_counts.csv"), index=False)

    print("region all-vintage:", len(region), "| active:", len(active))
    print(active.groupby("county").size())


if __name__ == "__main__":
    main()

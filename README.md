# Inland Northwest Nonprofit Sector Intelligence

An interactive [Quarto](https://quarto.org) website analyzing the health,
composition, trends, and geographic distribution of the nonprofit sector
across the seven-county Inland Northwest: Spokane, Stevens, Pend Oreille,
Lincoln, and Whitman counties in Washington, and Kootenai and Latah counties
in Idaho.

**Live site:** https://patilv.com/spokane-nonprofits/

## Data sources (all public)

- [NCCS Business Master File](https://urbaninstitute.github.io/nccs/datasets/bmf/)
  — geocoded state marts for Washington and Idaho (Urban Institute)
- [ProPublica Nonprofit Explorer API](https://projects.propublica.org/nonprofits/api/)
  — IRS Form 990/990-EZ financial extracts
- U.S. Census Bureau American Community Survey, 2019–2023 5-year estimates
- [CDC/ATSDR Social Vulnerability Index 2022](https://www.atsdr.cdc.gov/placeandhealth/svi/)

## Repository layout

- `*.qmd` — the eight site pages (charts are Observable Plot, maps are Leaflet,
  all rendered client-side)
- `scripts/` — the Python data pipeline, in run order (`01`–`04`); see the
  [Methodology](https://patilv.com/spokane-nonprofits/methodology.html) page
  for details
- `data/` — processed analysis datasets consumed by the pages
- `docs/` — rendered site (served by GitHub Pages)
- `styles/` — Gonzaga-branded SCSS theme

## Reproducing

```sh
# refresh data (downloads NCCS/Census/SVI/ProPublica sources)
python3 scripts/01_bmf_extract.py <dir-with-raw-bmf-csvs>
python3 scripts/02_census_svi.py
python3 scripts/03_propublica.py
python3 scripts/04_process.py

# rebuild the site into docs/
quarto render
```

## Attribution

Created by Vivek H. Patil, Ph.D., Professor of Marketing and Director of
Graduate Business Programs, Gonzaga University School of Business
Administration. Analyses run July 2026.

# data/

Local, regenerable data. Only this README and `.gitkeep` are tracked; the
dataset files are gitignored (`/data/*`). Never commit the source file. The
only data published is the small derived dashboard snapshot described in
[ADR-0002](../docs/adr/0002-dashboard-streamlit.md).

## Source

**Clickstream Data for Online Shopping**, UCI Machine Learning Repository
dataset #553:
<https://archive.ics.uci.edu/dataset/553/clickstream+data+for+online+shopping>

- **Licence:** Creative Commons Attribution 4.0 International (CC BY 4.0).
  Reuse, including derived data, is allowed with attribution.
- **DOI:** 10.24432/C5QK7X
- **Content:** clicks from an online shop selling clothing for pregnant
  women, April–August 2008.
- **Cite as:** Łapczyński M., Białowąs S. (2013). *Discovering Patterns of
  Users' Behaviour in an E-shop – Comparison of Consumer Buying Behaviours
  in Poland and Other European Countries.* Studia Ekonomiczne, nr 151,
  pp. 144–153.

Download from UCI directly:

```bash
curl -L -o data/uci553.zip "https://archive.ics.uci.edu/static/public/553/clickstream+data+for+online+shopping.zip"   # canonical UCI download
unzip -o data/uci553.zip -d data/                                                                                        # extracts the CSV and codebook
```

A Kaggle mirror exists (`tunguz/clickstream-data-for-online-shopping`), but
its licence field was not verified. Cite UCI, and use the UCI file for
anything public.

## Files and checksums (downloaded 2026-09-25)

| File | Size (bytes) | MD5 |
|---|---|---|
| `uci553.zip` | 795,262 | `bf7a47493025ffb35eebc7a65caf9988` |
| `e-shop clothing 2008.csv` | 6,675,312 | `fd68cf573fa635e6b43302f794d837dc` |
| `e-shop clothing 2008 data description.txt` (codebook) | 3,278 | `91f032d5ff3614f9d4df722eb365f10e` |

The CSV is **semicolon-delimited**.

## Verified stats (2026-09-25, measured from the real file)

- **Rows (clicks):** 165,474; 14 columns; 0 nulls; 0 duplicate rows
- **Sessions (visits):** 24,026. The median is 4 clicks and the longest
  visit has 195
- **One-click visits:** 5,042 (about 21%)
- **Dates:** 135 distinct days, 2008-04-01 to 2008-08-13. No session spans more
  than one date
- **Click order:** runs 1…n with no gaps in every session
- **Countries:** 47 codes. Poland accounts for about 81% of clicks and the
  Czech Republic about 11%; India (code 20) is present
- **Catalogue:** 4 categories, 217 products, 14 colours, shop pages 1–5
- **Attribute placement:** colour, price, above-average-price flag, photo
  position, photo angle and page number are fixed per product. Country is
  fixed per session
- **Known anomaly:** product A18 appears 937 times as trousers and once as
  skirts

## ⚠️ What this data does not contain

There is no time of day, no user ID, no checkout or purchase events, and
no device. The pipeline adds only time of day and device, as clearly
labelled `_synthetic` columns. Metrics are named for what they really
measure: **visits** (not active users) and a **browse-depth funnel** (not a
purchase funnel). See [ADR-0003](../docs/adr/0003-data-model.md).

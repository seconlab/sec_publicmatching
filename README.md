# DataProject — README

This project links publicly traded companies (SEC filings) to cyber incident databases using fuzzy name matching. The pipeline runs in `datapulling.ipynb`.

---

## Pipeline Overview

```
50 ZIP files (SEC quarterly data)
        ↓  Cell 1
   sub_merged.xlsx          ← all SEC submissions merged
        ↓  Cell 2
companies_2plus_10k.csv     ← filter: ≥2 10-K filings, most recent metadata per company
        ↓  Cell 3  (FuzzyMatching)
     FuzzyResults/           ← one matched file per cyber source
        ↓  Cell 4
     ManualReview/           ← slim review files, sorted by score
        ↓  manual + script
matched_score100_wide.csv   ← confirmed matches (score = 100), deduplicated
```

---

## File Descriptions

### 1. `sub_merged.xlsx`

**What it is:** All SEC EDGAR quarterly submission records merged into one file.

| Property | Value |
|----------|-------|
| Rows | 311,601 |
| Columns | 37 |
| Sources | 50 ZIP files, 2009 Q3 → 2026 Q1 |
| Script | `datapulling.ipynb` — Cell 1 |

**How it was built:** Each ZIP file contains a `sub.txt` (tab-separated). The `sub.txt` from every ZIP was extracted, a `quarter` column was prepended (e.g. `2009q3`), and all files were concatenated. One row = one filing submission.

**Key columns:**

| Column | Description |
|--------|-------------|
| `quarter` | Source ZIP file identifier, e.g. `2022q2` |
| `adsh` | Unique accession number for the filing |
| `cik` | SEC Central Index Key — the primary company identifier |
| `name` | Company name as filed |
| `sic` | Standard Industrial Classification code |
| `form` | Filing type, e.g. `10-K`, `10-Q`, `10-K/A` |
| `period` | Period of report (YYYYMMDD) |
| `filed` | Date the filing was submitted |
| `countryba` / `stprba` / `cityba` | Business address country / state / city |
| `countryinc` / `stprinc` | Country and state of incorporation |
| `afs` | Accelerated filer status |
| `wksi` | Well-known seasoned issuer flag |
| `nciks` | Number of CIKs in the filing |

---

### 2. `companies_2plus_10k.csv`

**What it is:** One row per publicly traded company that filed at least 2 pure `10-K` forms. Metadata reflects the company's most recent filing quarter.

| Property | Value |
|----------|-------|
| Rows | 10,582 |
| Columns | 37 (same schema as `sub_merged.xlsx`) |
| Script | `datapulling.ipynb` — Cell 2 |

**How it was built:**
1. Filtered `sub_merged.xlsx` to rows where `form == '10-K'` exactly (amended `10-K/A` excluded).
2. Counted 10-K filings per `cik` — kept only CIKs with ≥ 2.
3. For each qualifying CIK, kept the row from the most recent `quarter`.

**Why this file:** Used as the reference list of publicly traded companies in all fuzzy matching steps. CIK is the join key for all downstream files.

---

### 3. `FuzzyResults/` — Fuzzy Matched Files

**What it is:** Five CSV files, one per cyber incident source. Each contains all original columns from the source database plus fuzzy match results against `companies_2plus_10k.csv`.

| File | Source database | Org column matched | Rows |
|------|-----------------|--------------------|------|
| `eurepoc_data_fuzzy_matched.csv` | EuRepoC | `receiver_name` | 4,319 |
| `maryland_incidents_(1)_fuzzy_matched.csv` | Maryland Incidents | `organization` | 14,847 |
| `ransomware_live_filtered_fuzzy_matched.csv` | Ransomware Live | `Post Title` | 22,402 |
| `temple_incidents_fuzzy_matched.csv` | Temple Incidents | `Org Name` | 2,119 |
| `veris_export_fuzzy_matched.csv` | VERIS | `Victim` | 9,911 |

**Script:** `datapulling.ipynb` — Cell 3 (`FuzzyMatching.ipynb` logic, adapted for Mac paths).

**Matching approach:** Hybrid two-score fuzzy match using [RapidFuzz](https://github.com/maxbachmann/RapidFuzz):

| Score | Weight | Description |
|-------|--------|-------------|
| `score_token_sort` | 60% | Handles word-order variation and suffix noise |
| `score_partial` | 40% | Handles abbreviations and subset matches |
| `score_combo` | — | `0.6 × token_sort + 0.4 × partial` — primary ranking score |

Both scores are on a 0–100 scale.

**Decision labels:**

| Label | Condition | Meaning |
|-------|-----------|---------|
| `auto_accept` | `score_combo == 100` | Perfect match — used directly in `matched_score100_wide.csv` |
| `needs_review` | `80 ≤ score_combo < 100` | Strong candidate — worth manual review to expand the dataset |
| `low_score` | `score_combo < 80` | Too noisy to be reliable — skip |

**Name normalization applied before matching:**
- Lowercased, ASCII-normalized
- Corporate suffixes stripped (`inc`, `corp`, `llc`, `holdings`, `group`, etc.)
- Parenthetical notes removed
- Tokens sorted alphabetically (to neutralize word order)

**Added columns (appended to original source columns):**

| Column | Description |
|--------|-------------|
| `org_norm` | Normalized version of the source organization name |
| `hint_probably_nontraded` | Flag: name suggests a non-traded entity (school, hospital, government, etc.) |
| `md_organization` | Organization name as used during matching |
| `md_org_norm` | Normalized organization name used during matching |
| `sec_best_name` | Best-matching company name from SEC list |
| `sec_best_cik` | CIK of the best match |
| `sec_best_norm` | Normalized form of the best SEC match |
| `score_token_sort` | Token sort ratio score (0–100) |
| `score_partial` | Partial ratio score (0–100) |
| `score_combo` | Weighted hybrid score (0–100) — **primary sort key for review** |
| `decision` | `auto_accept` (both thresholds met) or `needs_review` |
| `sec_2nd_name` / `sec_2nd_cik` / `sec_2nd_norm` | Runner-up match for context |
| `score2_token_sort` / `score2_partial` / `score2_combo` | Runner-up scores |

---

### 4. `ManualReview/` — Slim Review Files

**What it is:** Stripped-down versions of the FuzzyResults files for manual validation. One row per unique organization name, all original metadata removed, sorted by `score_combo` descending.

| File | Unique orgs | Auto-accept | Needs review |
|------|------------|-------------|--------------|
| `eurepoc_data_review.csv` | 2,112 | 87 | 2,022 |
| `maryland_incidents_(1)_review.csv` | 13,532 | 605 | 12,927 |
| `ransomware_live_filtered_review.csv` | 21,968 | 517 | 21,345 |
| `temple_incidents_review.csv` | 2,072 | 134 | 1,938 |
| `veris_export_review.csv` | 7,523 | 446 | 7,076 |

**Script:** `datapulling.ipynb` — Cell 4.

**Columns kept (in order):**

| Column | Purpose |
|--------|---------|
| `md_organization` | Original name from cyber source |
| `md_org_norm` | Normalized version |
| `sec_best_name` | Top SEC candidate |
| `sec_best_norm` | Normalized top candidate |
| `sec_best_cik` | CIK of top candidate |
| `score_token_sort` | Token sort score |
| `score_partial` | Partial ratio score |
| `score_combo` | Combo score — **file is sorted by this, descending** |
| `decision` | `auto_accept` or `needs_review` |
| `hint_probably_nontraded` | Non-traded entity flag |

**How to use for manual validation:**

`score_combo = 100` rows are perfect matches — no manual review needed. These feed directly into `matched_score100_wide.csv`.

To expand the dataset, work through `needs_review` rows (**score_combo 80–99**):
1. Open any `*_review.csv` in Excel or similar — rows are already sorted highest `score_combo` first.
2. Skip `auto_accept` (already captured) and `low_score` rows (below 80, too noisy).
3. For each `needs_review` row: compare `md_organization` vs `sec_best_name`. If correct, note the CIK.
4. Use `score_combo` and `score_partial` together — a high `score_combo` with a low `score_partial` often signals a false positive.
5. `hint_probably_nontraded = True` rows are likely schools, hospitals, or government entities — skip unless you have reason to believe otherwise.

---

### 5. `matched_score100_wide.csv`

**What it is:** Final analysis-ready table. Contains only perfect matches (`score_combo = 100`), one row per unique company-incident (CIK + event date), in wide format showing which source databases confirmed each incident.

| Property | Value |
|----------|-------|
| Rows | 1,220 |
| Columns | 9 |

**How it was built:**
1. Filtered all five FuzzyResults files to `score_combo == 100`.
2. Extracted event date from each source (normalized to `YYYY-MM-DD`):
   - Maryland: `event_date`
   - Temple: `Date Began`
   - Ransomware Live: `Discovered`
   - EuRepoC: `start_date`
   - VERIS: `Year` + `Month` + `Day` (year-only records → no date, kept but not merged)
3. Within each CIK, clustered events using a **7-day window**: if two events for the same company are ≤ 7 days apart, they are treated as the same incident and merged into one row.
4. Pivoted to wide format: one column per source ID.

**Deduplication stats:**
- Rows before dedup: 1,359
- Rows removed by merging: 139
- Multi-source confirmed rows (n_sources ≥ 2): 96

**Columns:**

| Column | Description |
|--------|-------------|
| `cik` | SEC CIK — links back to `companies_2plus_10k.csv` |
| `company` | Company name from SEC |
| `event_date` | Earliest event date in the cluster (`YYYY-MM-DD`), or blank for year-only VERIS records |
| `n_sources` | Number of source databases that confirmed this incident |
| `eurepoc_id` | `name` field from EuRepoC (event description used as ID) |
| `maryland_id` | `slug` from Maryland Incidents |
| `ransomware_id` | `Post Title` from Ransomware Live |
| `temple_id` | `Source` from Temple Incidents |
| `veris_id` | `Incident ID` from VERIS |

**Notes:**
- A non-null value in a source ID column means that source confirmed the incident.
- Multiple IDs in one cell (separated by `;`) means the 7-day cluster merged multiple records from that source.
- 146 rows have a blank `event_date` — these are VERIS records where only the year was available. They are valid matches but cannot be date-merged with other sources.
- To filter to incidents confirmed by multiple sources: `n_sources >= 2` gives 96 rows.

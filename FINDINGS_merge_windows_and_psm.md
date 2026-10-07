# Findings: merge-window variants and the downstream PSM control-group run

## 1. Bug found: a downstream file was missing repeat-victim incidents

A separate file used for a new PSM (propensity score matching) control-group task,
`SW+Attacks+10ks 1.xlsx` (lives outside this repo, in `SECLONG2/`), turned out to have
**exactly one unique CIK per unique incident row** — i.e. no company was ever matched to
more than one of its own incidents, even when the underlying source data clearly shows
the same company attacked multiple times.

Yahoo is the clearest example. That file has 11 separate Yahoo incident rows
(2008–2017, all sourced from VERIS/Maryland), but **only 1 of the 11 had a non-blank
`CIK_ID`** — whatever CIK-matching/enrichment step built that file only ever attached a
CIK to one representative incident per company, silently dropping the CIK link for the
other 10.

**This repo's own `matched_score100_wide.csv` does NOT have this bug** — verified
directly: it already has all 11 Yahoo incidents, each correctly carrying `cik = 1011006`.
The bug is specific to the external `SW+Attacks+10ks 1.xlsx` file's CIK-matching step,
not to this repo's fuzzy-matching pipeline. We only caught it because the new PSM task
used that file as its treated-firm list and a downstream sanity check (unique incidents
== unique CIKs, which should never be true if any company is attacked more than once)
flagged it.

**Why it matters:** any treated-firm list built from that file understates how many
times a company was actually attacked, which would bias a PSM-based event study — repeat
victims would only ever contribute one event to the analysis instead of all of them.

## 2. What we did: added configurable merge-window variants of this repo's own pipeline

`build_matched_incidents_typed.py` (pre-existing in this repo) already does this
correctly: for each CIK, it clusters that CIK's incident records across all 5 sources
(EuRepoC, Maryland, Ransomware Live, Temple, VERIS) using a date-proximity window, only
merging two records into one incident if they fall within that window — records further
apart stay as separate incidents. It also already includes manual-review-confirmed rows
(`confirmed_match == "Y"` in `ManualReview/*.csv`), not just `score_combo == 100`
auto-matches.

The original script hardcoded a **7-day** window. We added two siblings with the
window widened, everything else identical:

| Script | Window | Output |
|---|---|---|
| `build_matched_incidents_typed.py` (existing) | 7 days | `matched_incidents_typed.csv` |
| `build_matched_incidents_typed_1mo.py` (new) | 30 days | `matched_incidents_typed_1mo.csv` |
| `build_matched_incidents_typed_2mo.py` (new) | 60 days | `matched_incidents_typed_2mo.csv` |

Widening the window only merges records that are *closer together* in time into one
incident (e.g. two sources reporting the same breach 3 weeks apart) — it does not, and
structurally cannot, drop a company's genuinely separate incidents, because clustering is
re-run from scratch per CIK at each window width. Confirmed Yahoo keeps all 11 incidents
at every window width, since its incidents are all more than 2 months apart from each
other.

### Results across window widths

| Window | Total incidents | Unique CIKs | Multi-source incidents (n_sources ≥ 2) |
|---|---|---|---|
| 7-day | 1,328 | 724 | 98 |
| 1-month | 1,260 | 724 | 136 |
| 2-month | 1,216 | 724 | 146 |

Same 724 companies throughout — only the incident *count* shrinks as the window widens,
because more near-duplicate source records (same real-world incident, reported a few
weeks apart by different databases) get folded into one row instead of counted twice.

(Note: these totals are higher than the 1,201 in the original `matched_score100_wide.csv`
because they also include manual-review-confirmed rows, which that file predates.)

## 3. What PSM is, and what it produced

**Propensity Score Matching (PSM)** is how we build a credible control group for an
event study. For every "treated" firm (one that suffered a cyber incident), we need a
comparable firm that *wasn't* attacked around the same time, so we can attribute any
difference in financial outcomes to the attack rather than to industry- or size-driven
trends that would have happened anyway. PSM does this by:

1. Restricting candidates to firms in the **same 2-digit SIC industry code** as the
   treated firm (so a retailer is only ever compared to other retailers, etc.).
2. Fitting a **logistic regression** predicting `treated` from each firm's pre-incident
   **log(assets)** and **operating income / assets** (profitability), both computed as
   the mean over the 4 quarters strictly before the incident — this produces one
   "propensity score" per firm summarizing how similar its size/profitability profile is
   to a typical treated firm.
2. Picking, for each treated firm, the **single closest untreated candidate** (1-to-1,
   nearest neighbor on the propensity score), only accepting a match if it falls within
   a **caliper** (a maximum allowed distance) — this is the same method as paper 1's
   `PSM.R`/`FinalModelFinal.R`.

Match quality is judged by **SMD (standardized mean difference)** between treated and
matched-control firms on the two covariates after matching — under 0.1 is the
conventional "well balanced" threshold.

### What PSM produced for each merge-window variant

Run against the full 724-company, all-history incident lists (via `sec_financial_pipeline`'s
`covariates` + `paper1_methodology/PSM_{1mo,2mo}_full.R`, both in sibling repos — not part
of this repo's commit):

| | 1-month window | 2-month window |
|---|---|---|
| Treated events with usable financial data | 784 / 1,257 | 755 / 1,213 |
| Successfully matched 1-to-1 | **682** | **656** |
| SMD [log assets] | -0.051 | -0.068 |
| SMD [OI/assets] | -0.025 | 0.020 |

Both comfortably under the 0.1 balance target, close to paper 1's own original run
(-0.054 / 0.08).

**Data-quality fix along the way:** the first attempt at this (at both window widths)
produced a badly unbalanced or even non-converging propensity model. Root cause: a
handful of micro-cap/penny-stock firms (e.g. a $6M-asset company with an operating-
income-to-assets ratio of 26.5) were passing the pipeline's old $1M minimum-assets filter
and recurring across 100+ different treated firms' candidate pools (because they share a
very broad, common SIC2 industry code with ~1,300 other firms) — this is a recurrence
effect, not that any single firm was literally attacked 100+ times. Raising that floor to
$10M in `sec_financial_pipeline/src/secfin/covariates.py` fixed it while changing less
than 25% of the candidate pool and staying close to paper 1's own balance numbers.

## 4. Where everything lives

| What | Repo |
|---|---|
| Merge-window scripts + incident CSVs (this commit) | `sec_publicmatching` (here) |
| `covariates.py` materiality-floor fix, `covariates_1mo_full/`, `covariates_2mo_full/` | `sec_financial_pipeline` (sibling repo, separate commit) |
| `PSM_1mo_full.R`, `PSM_2mo_full.R`, matched-pairs output | `paper1_methodology` (not git-tracked) |

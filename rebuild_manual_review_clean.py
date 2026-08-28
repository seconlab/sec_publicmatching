"""
Rebuild ManualReview/*.csv fresh from FuzzyResults/*.csv.

Discovered this session: ransomware_live_filtered_review.csv had 64 rows with a
column-shift corruption (real values landed in the wrong fields, e.g. a company
name sitting in the `decision` slot). FuzzyResults/ransomware_live_filtered_fuzzy_matched.csv
has zero such rows, so it's the clean source of truth. Rather than patch the
corrupted rows in place, this rebuilds all 5 ManualReview files the same way
datapulling.ipynb Cell 4 originally did (dedup by org name, sorted by score_combo
descending), from the already decision-fixed FuzzyResults files.
"""

from pathlib import Path

import pandas as pd

BASE = Path(r"c:\Users\mutal\OneDrive - University of Tulsa\SECLONG\sec_publicmatching")
FUZZY_DIR = BASE / "FuzzyResults"
REVIEW_DIR = BASE / "ManualReview"

CANONICAL_COLS = [
    "md_organization", "md_org_norm", "sec_best_name", "sec_best_norm", "sec_best_cik",
    "score_token_sort", "score_partial", "score_combo", "decision",
]

FUZZY_TO_REVIEW = {
    "eurepoc_data_fuzzy_matched.csv":             "eurepoc_data_review.csv",
    "maryland_incidents_(1)_fuzzy_matched.csv":   "maryland_incidents_(1)_review.csv",
    "ransomware_live_filtered_fuzzy_matched.csv": "ransomware_live_filtered_review.csv",
    "temple_incidents_fuzzy_matched.csv":         "temple_incidents_review.csv",
    "veris_export_fuzzy_matched.csv":             "veris_export_review.csv",
}


def main():
    for fuzzy_fname, review_fname in FUZZY_TO_REVIEW.items():
        df = pd.read_csv(FUZZY_DIR / fuzzy_fname, dtype=str, engine="python", on_bad_lines="skip")

        cols = [c for c in CANONICAL_COLS if c in df.columns]
        dedup_key = [c for c in ["md_organization", "md_org_norm"] if c in df.columns]

        review = (
            df[cols]
            .drop_duplicates(subset=dedup_key)
            .sort_values("score_combo", ascending=False, key=lambda s: s.astype(float))
            .reset_index(drop=True)
        )

        out_path = REVIEW_DIR / review_fname
        review.to_csv(out_path, index=False)

        valid = {"auto_accept", "needs_review", "no_name_norm", "no_candidates"}
        bad = (~review["decision"].isin(valid)).sum()
        print(f"[{review_fname}] {len(review):,} rows  "
              f"decision_counts={review['decision'].value_counts().to_dict()}  "
              f"corrupted_rows={bad}")


if __name__ == "__main__":
    main()

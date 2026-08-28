"""
Fix the `decision` column across FuzzyResults/*.csv and ManualReview/*.csv.

The files as generated used decision = "auto_accept" iff
score_token_sort >= 85 AND score_partial >= 90 (same rule as swdb_fuzzy_match.py),
NOT score_combo == 100 as documented in the README / datapulling.ipynb. Verified
this session: that rule explains 100% of existing auto_accept/needs_review labels
across all 5 sources with zero mismatches.

This script recomputes decision so that auto_accept means score_combo == 100 only,
everything else becomes needs_review. Placeholder decisions that mean "no match was
even attempted" (no_name_norm, no_candidates) are left untouched, since those rows
have no score to re-judge and aren't near-misses worth manual review.
"""

from pathlib import Path

import pandas as pd

BASE = Path(r"c:\Users\mutal\OneDrive - University of Tulsa\SECLONG\sec_publicmatching")
FUZZY_DIR = BASE / "FuzzyResults"
REVIEW_DIR = BASE / "ManualReview"

RECOMPUTE_FROM = {"auto_accept", "needs_review"}

FUZZY_FILES = [
    "eurepoc_data_fuzzy_matched.csv",
    "maryland_incidents_(1)_fuzzy_matched.csv",
    "ransomware_live_filtered_fuzzy_matched.csv",
    "temple_incidents_fuzzy_matched.csv",
    "veris_export_fuzzy_matched.csv",
]

REVIEW_FILES = [
    "eurepoc_data_review.csv",
    "maryland_incidents_(1)_review.csv",
    "ransomware_live_filtered_review.csv",
    "temple_incidents_review.csv",
    "veris_export_review.csv",
]


def fix_decision(df: pd.DataFrame) -> pd.DataFrame:
    combo = df["score_combo"].astype(float)
    eligible = df["decision"].isin(RECOMPUTE_FROM)
    new_decision = df["decision"].copy()
    new_decision[eligible] = eligible[eligible].map(
        lambda _: None
    )  # placeholder, filled below
    new_decision.loc[eligible] = combo[eligible].apply(
        lambda c: "auto_accept" if c == 100.0 else "needs_review"
    )
    df["decision"] = new_decision
    return df


def main():
    print("=== FuzzyResults ===")
    for fname in FUZZY_FILES:
        path = FUZZY_DIR / fname
        df = pd.read_csv(path, dtype=str, engine="python", on_bad_lines="skip")
        before = df["decision"].value_counts().to_dict()
        df = fix_decision(df)
        after = df["decision"].value_counts().to_dict()
        df.to_csv(path, index=False, quoting=1)
        print(f"[{fname}]")
        print(f"  before: {before}")
        print(f"  after:  {after}")

    print("\n=== ManualReview ===")
    for fname in REVIEW_FILES:
        path = REVIEW_DIR / fname
        df = pd.read_csv(path, dtype=str)
        before = df["decision"].value_counts().to_dict()
        df = fix_decision(df)
        after = df["decision"].value_counts().to_dict()
        df.to_csv(path, index=False)
        print(f"[{fname}]")
        print(f"  before: {before}")
        print(f"  after:  {after}")


if __name__ == "__main__":
    main()

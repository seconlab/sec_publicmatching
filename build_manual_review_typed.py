"""
Step 1 (part 2): enrich ManualReview/*.csv with org-level type flags + a blank
confirmed_match (Y/N) column for the user's manual pass.

ManualReview is deduplicated to one row per unique organization name (md_org_norm),
while TypeFlags/classify_incident_types.py output is at raw-row grain. So here we
join TypeFlags -> FuzzyResults (on source_key) to recover md_org_norm, then OR each
flag across every raw row sharing that md_org_norm before merging onto ManualReview.
"""

from pathlib import Path

import pandas as pd

BASE = Path(r"c:\Users\mutal\OneDrive - University of Tulsa\SECLONG\sec_publicmatching")
FUZZY_DIR = BASE / "FuzzyResults"
REVIEW_DIR = BASE / "ManualReview"
TYPEFLAGS_DIR = BASE / "TypeFlags"

FLAG_COLS = ["is_ransomware", "is_data_breach", "is_availability_disruption",
             "is_ransomware_keyword_derived"]

# source label -> (fuzzy_matched filename, review filename, typeflags filename, source_key col in fuzzy file)
SOURCES = {
    "temple":     ("temple_incidents_fuzzy_matched.csv", "temple_incidents_review.csv",
                    "temple_incidents_typeflags.csv", "Source"),
    "ransomware": ("ransomware_live_filtered_fuzzy_matched.csv", "ransomware_live_filtered_review.csv",
                    "ransomware_live_filtered_typeflags.csv", "Post Title"),
    "maryland":   ("maryland_incidents_(1)_fuzzy_matched.csv", "maryland_incidents_(1)_review.csv",
                    "maryland_incidents_(1)_typeflags.csv", "slug"),
    "eurepoc":    ("eurepoc_data_fuzzy_matched.csv", "eurepoc_data_review.csv",
                    "eurepoc_data_typeflags.csv", "name"),
    "veris":      ("veris_export_fuzzy_matched.csv", "veris_export_review.csv",
                    "veris_export_typeflags.csv", "Incident ID"),
}


def main():
    for label, (fuzzy_fname, review_fname, typeflags_fname, key_col) in SOURCES.items():
        fuzzy = pd.read_csv(FUZZY_DIR / fuzzy_fname, dtype=str, engine="python", on_bad_lines="skip")
        typed = pd.read_csv(TYPEFLAGS_DIR / typeflags_fname, dtype=str)
        for c in FLAG_COLS:
            typed[c] = typed[c].map({"True": True, "False": False}).fillna(False)

        # join TypeFlags (row-level) onto FuzzyResults (row-level) via source_key,
        # then aggregate up to md_organization (org-level, matches ManualReview grain).
        # md_organization (raw name) is used as the join key instead of md_org_norm
        # since not all ManualReview files carry a normalized-name column.
        merged = fuzzy[[key_col, "md_organization"]].merge(
            typed.rename(columns={"source_key": key_col}), on=key_col, how="left"
        )
        org_flags = merged.groupby("md_organization", as_index=False)[FLAG_COLS].any()

        review = pd.read_csv(REVIEW_DIR / review_fname, dtype=str)

        # idempotent + preserves any manual work already recorded: carry forward
        # existing confirmed_match values keyed by md_organization before dropping
        # columns from a prior run of this script, then restore them after merge.
        prior_confirmed = None
        if "confirmed_match" in review.columns:
            prior_confirmed = review[["md_organization", "confirmed_match"]].copy()
        review = review.drop(columns=[c for c in FLAG_COLS + ["confirmed_match"] if c in review.columns])

        review = review.merge(org_flags, on="md_organization", how="left")
        for c in FLAG_COLS:
            review[c] = review[c].fillna(False)
        if label in ("temple", "ransomware"):
            # these two sources are 100% ransomware by construction; don't rely on
            # the join (a handful of rows fail to match on raw Post Title/Source
            # text, which would otherwise wrongly leave is_ransomware = False)
            review["is_ransomware"] = True

        review["confirmed_match"] = ""
        if prior_confirmed is not None:
            review = review.merge(prior_confirmed, on="md_organization", how="left", suffixes=("", "_prior"))
            review["confirmed_match"] = review["confirmed_match_prior"].fillna("")
            review = review.drop(columns=["confirmed_match_prior"])

        out_path = REVIEW_DIR / review_fname
        review.to_csv(out_path, index=False)

        n = len(review)
        r = int(review["is_ransomware"].sum())
        b = int(review["is_data_breach"].sum())
        d = int(review["is_availability_disruption"].sum())
        print(f"[{label}] {n:,} unique orgs  ransomware={r:,}  data_breach={b:,}  disruption={d:,}")
        print(f"  -> {out_path}")


if __name__ == "__main__":
    main()

"""
Step 1 (part 3): incident-level clustering + type labeling.

Mirrors datapulling.ipynb Cell 5's 7-day per-CIK clustering logic that produced
matched_score100_wide.csv, but:
  - joins each source's row-level TypeFlags onto FuzzyResults via source_key first,
    so every raw incident record carries its own type flags into the cluster
  - includes a row if score_combo == 100 OR ManualReview's confirmed_match == "Y"
    for that row's md_organization (today, with no manual review done yet, this
    reduces to the same auto_accept-only set as matched_score100_wide.csv)
  - within each cluster, ORs the three type flags across all contributing rows to
    produce cluster-level is_ransomware / is_data_breach / is_availability_disruption
    plus a human-readable category_label

Writes matched_incidents_typed.csv alongside (not replacing) matched_score100_wide.csv.
"""

from pathlib import Path

import pandas as pd

BASE = Path(r"c:\Users\mutal\OneDrive - University of Tulsa\SECLONG\sec_publicmatching")
FUZZY_DIR = BASE / "FuzzyResults"
REVIEW_DIR = BASE / "ManualReview"
TYPEFLAGS_DIR = BASE / "TypeFlags"

FLAG_COLS = ["is_ransomware", "is_data_breach", "is_availability_disruption"]

# source -> (fuzzy_matched filename, review filename, typeflags filename,
#            source_key col, id_col for output, date_col [None => VERIS Year/Month/Day])
SOURCES = {
    "eurepoc":    ("eurepoc_data_fuzzy_matched.csv", "eurepoc_data_review.csv",
                    "eurepoc_data_typeflags.csv", "name", "name", "start_date"),
    "maryland":   ("maryland_incidents_(1)_fuzzy_matched.csv", "maryland_incidents_(1)_review.csv",
                    "maryland_incidents_(1)_typeflags.csv", "slug", "slug", "event_date"),
    "ransomware": ("ransomware_live_filtered_fuzzy_matched.csv", "ransomware_live_filtered_review.csv",
                    "ransomware_live_filtered_typeflags.csv", "Post Title", "Post Title", "Discovered"),
    "temple":     ("temple_incidents_fuzzy_matched.csv", "temple_incidents_review.csv",
                    "temple_incidents_typeflags.csv", "Source", "Source", "Date Began"),
    "veris":      ("veris_export_fuzzy_matched.csv", "veris_export_review.csv",
                    "veris_export_typeflags.csv", "Incident ID", "Incident ID", None),
}

CATEGORY_LABELS = {
    (True, True, True):   "Ransomware+Breach+Disruption",
    (True, True, False):  "Ransomware+Breach",
    (True, False, True):  "Ransomware+Disruption",
    (True, False, False): "Ransomware only",
    (False, True, True):  "Breach+Disruption",
    (False, True, False): "Data Breach only",
    (False, False, True): "Availability Disruption only",
    (False, False, False): "Other/Undetermined",
}


def parse_veris_date(row):
    def to_int(val):
        try:
            s = str(val).strip()
            return int(float(s)) if s and s not in ("nan", "") else None
        except Exception:
            return None
    y, m, d = to_int(row.get("Year")), to_int(row.get("Month")), to_int(row.get("Day"))
    try:
        if y and m and d:
            return pd.Timestamp(y, m, d)
        elif y and m:
            return pd.Timestamp(y, m, 1)
        elif y:
            return pd.Timestamp(y, 1, 1)
    except Exception:
        pass
    return pd.NaT


def load_source(src_name, fuzzy_fname, review_fname, typeflags_fname, key_col, id_col, date_col):
    fuzzy = pd.read_csv(FUZZY_DIR / fuzzy_fname, dtype=str, engine="python", on_bad_lines="skip")
    typed = pd.read_csv(TYPEFLAGS_DIR / typeflags_fname, dtype=str)
    for c in FLAG_COLS:
        typed[c] = typed[c].map({"True": True, "False": False}).fillna(False)
    typed = typed.rename(columns={"source_key": key_col})

    # row-level join: every raw incident record gets its own type flags
    fuzzy = fuzzy.merge(typed[[key_col] + FLAG_COLS], on=key_col, how="left")
    for c in FLAG_COLS:
        fuzzy[c] = fuzzy[c].fillna(False)
    if src_name in ("temple", "ransomware"):
        fuzzy["is_ransomware"] = True  # 100% ransomware sources; see build_manual_review_typed.py note

    # confirmed_match from ManualReview, joined back by md_organization (org-grain)
    review = pd.read_csv(REVIEW_DIR / review_fname, dtype=str)
    if "confirmed_match" in review.columns:
        confirmed = review[["md_organization", "confirmed_match"]].drop_duplicates("md_organization")
        fuzzy = fuzzy.merge(confirmed, on="md_organization", how="left")
    else:
        fuzzy["confirmed_match"] = ""
    fuzzy["confirmed_match"] = fuzzy["confirmed_match"].fillna("")

    include = (fuzzy["score_combo"].astype(float) == 100.0) | (fuzzy["confirmed_match"].str.upper() == "Y")
    hits = fuzzy[include].copy()

    if src_name == "veris":
        hits["_event_date"] = hits.apply(parse_veris_date, axis=1)
    else:
        raw = hits[date_col].str.replace("\u2011", "-", regex=False)
        s = pd.to_datetime(raw, errors="coerce", utc=True)
        hits["_event_date"] = s.dt.tz_convert(None)
    hits["_event_date"] = pd.to_datetime(hits["_event_date"]).dt.normalize()

    records = []
    for _, row in hits.iterrows():
        records.append({
            "cik": row["sec_best_cik"],
            "company": row["sec_best_name"],
            "event_date": row["_event_date"],
            "source": src_name,
            "source_id": row[id_col],
            "is_ransomware": row["is_ransomware"],
            "is_data_breach": row["is_data_breach"],
            "is_availability_disruption": row["is_availability_disruption"],
        })
    return records


def main():
    all_records = []
    for src_name, args in SOURCES.items():
        recs = load_source(src_name, *args)
        all_records.extend(recs)
        print(f"[{src_name}] {len(recs):,} included rows (score_combo==100 or confirmed_match=='Y')")

    long = pd.DataFrame(all_records)
    long["event_date"] = pd.to_datetime(long["event_date"])

    WINDOW = pd.Timedelta(days=7)
    rows_wide = []

    for cik, grp in long.groupby("cik", sort=False):
        company = grp["company"].iloc[0]
        dated = grp[grp["event_date"].notna()].sort_values("event_date").reset_index(drop=True)
        undated = grp[grp["event_date"].isna()]

        clusters = []
        for _, row in dated.iterrows():
            placed = False
            for cluster in clusters:
                if abs(row["event_date"] - cluster["anchor"]) <= WINDOW:
                    cluster["rows"].append(row)
                    cluster["anchor"] = min(cluster["anchor"], row["event_date"])
                    placed = True
                    break
            if not placed:
                clusters.append({"anchor": row["event_date"], "rows": [row]})

        # undated rows: each becomes its own single-row "cluster" (mirrors Cell 5)
        for _, row in undated.iterrows():
            clusters.append({"anchor": None, "rows": [row]})

        for cluster in clusters:
            rows = cluster["rows"]
            src_ids = {}
            for row in rows:
                src_ids.setdefault(row["source"], []).append(str(row["source_id"]))
            is_r = any(r["is_ransomware"] for r in rows)
            is_b = any(r["is_data_breach"] for r in rows)
            is_d = any(r["is_availability_disruption"] for r in rows)
            rows_wide.append({
                "cik": cik,
                "company": company,
                "event_date": cluster["anchor"].strftime("%Y-%m-%d") if cluster["anchor"] is not None else None,
                "n_sources": len(set(r["source"] for r in rows)),
                "eurepoc_id":    "; ".join(src_ids["eurepoc"])    if "eurepoc"    in src_ids else None,
                "maryland_id":   "; ".join(src_ids["maryland"])   if "maryland"   in src_ids else None,
                "ransomware_id": "; ".join(src_ids["ransomware"]) if "ransomware" in src_ids else None,
                "temple_id":     "; ".join(src_ids["temple"])     if "temple"     in src_ids else None,
                "veris_id":      "; ".join(src_ids["veris"])      if "veris"      in src_ids else None,
                "is_ransomware": is_r,
                "is_data_breach": is_b,
                "is_availability_disruption": is_d,
                "category_label": CATEGORY_LABELS[(is_r, is_b, is_d)],
            })

    wide = pd.DataFrame(rows_wide).sort_values(["cik", "event_date"]).reset_index(drop=True)
    out_path = BASE / "matched_incidents_typed.csv"
    wide.to_csv(out_path, index=False)

    print(f"\nTotal incidents: {len(wide):,}")
    print(f"Multi-source (n_sources >= 2): {(wide['n_sources'] >= 2).sum():,}")
    print("\nCategory breakdown:")
    print(wide["category_label"].value_counts().to_string())
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()

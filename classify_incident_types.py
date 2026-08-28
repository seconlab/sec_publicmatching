"""
Step 1 (part 1): derive is_ransomware / is_data_breach / is_availability_disruption
flags for every row in each of the 5 raw CyberEvents sources.

Each source uses a different taxonomy, so the mapping rules differ per source
(see plan: C:\\Users\\mutal\\.claude\\plans\\delightful-dreaming-dream.md).
Output: one CSV per source in TypeFlags/, keyed on the same organization column
already used for fuzzy matching in datapulling.ipynb, so it joins cleanly onto
FuzzyResults/ManualReview.
"""

import re
from pathlib import Path

import pandas as pd

BASE = Path(r"c:\Users\mutal\OneDrive - University of Tulsa\SECLONG\sec_publicmatching")
CYBER_DIR = BASE / "CyberEvents"
OUT_DIR = BASE / "TypeFlags"
OUT_DIR.mkdir(exist_ok=True)

FLAG_COLS = ["is_ransomware", "is_data_breach", "is_availability_disruption",
             "is_ransomware_keyword_derived"]

RANSOM_RE = re.compile(r"ransomware|ransom\b", re.IGNORECASE)

VERIS_AVAILABILITY_POSITIVE = {"Loss", "Interruption", "Degradation", "Destruction", "Obscuration"}


def classify_temple(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["Source"]].copy()
    out["is_ransomware"] = True
    out["is_data_breach"] = False
    out["is_availability_disruption"] = False
    out["is_ransomware_keyword_derived"] = False
    return out


def classify_ransomware_live(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["Post Title"]].copy()
    out["is_ransomware"] = True
    out["is_data_breach"] = False
    out["is_availability_disruption"] = False
    out["is_ransomware_keyword_derived"] = False
    return out


def classify_maryland(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["slug"]].copy()
    subtype = df["event_subtype"].fillna("")
    out["is_data_breach"] = subtype.str.contains("Data Attack", case=False, na=False)
    out["is_availability_disruption"] = (
        df["event_type"].fillna("").str.strip().eq("Disruptive")
        | subtype.str.contains("Denial of Service", case=False, na=False)
    )
    ransom_hit = df["description"].fillna("").str.contains(RANSOM_RE, na=False)
    out["is_ransomware"] = ransom_hit
    out["is_ransomware_keyword_derived"] = ransom_hit
    return out


def classify_eurepoc(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["name"]].copy()
    labels = df["incident_type"].fillna("").apply(
        lambda s: {t.strip() for t in s.split(";") if t.strip()}
    )
    out["is_ransomware"] = labels.apply(lambda s: "Ransomware" in s)
    out["is_data_breach"] = labels.apply(
        lambda s: bool(s & {"Data theft", "Data theft & Doxing"})
    )
    out["is_availability_disruption"] = labels.apply(lambda s: "Disruption" in s)
    out["is_ransomware_keyword_derived"] = False
    return out


def classify_veris(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["Incident ID"]].copy()
    malware = df["Malware"].fillna("")
    out["is_ransomware"] = malware.apply(
        lambda s: "ransomware" in {t.strip().lower() for t in s.split(";")}
    )
    out["is_data_breach"] = df["Data Disclosure"].isin(["Yes", "Potentially"])
    out["is_availability_disruption"] = df["Availability"].fillna("").apply(
        lambda s: bool({t.strip() for t in s.split(";")} & VERIS_AVAILABILITY_POSITIVE)
    )
    out["is_ransomware_keyword_derived"] = False
    return out


SOURCES = {
    "temple_incidents.csv": ("Source", classify_temple),
    "ransomware_live_filtered.csv": ("Post Title", classify_ransomware_live),
    "maryland_incidents (1).csv": ("slug", classify_maryland),
    "eurepoc_data.csv": ("name", classify_eurepoc),
    "veris_export.csv": ("Incident ID", classify_veris),
}


def main():
    for fname, (key_col, fn) in SOURCES.items():
        df = pd.read_csv(CYBER_DIR / fname, dtype=str, engine="python", on_bad_lines="skip")
        typed = fn(df)
        typed = typed.rename(columns={key_col: "source_key"})

        stem = Path(fname).stem.replace(" ", "_")
        out_path = OUT_DIR / f"{stem}_typeflags.csv"
        typed.to_csv(out_path, index=False)

        n = len(typed)
        r = int(typed["is_ransomware"].sum())
        b = int(typed["is_data_breach"].sum())
        d = int(typed["is_availability_disruption"].sum())
        kw = int(typed["is_ransomware_keyword_derived"].sum())
        none_flagged = int((~typed["is_ransomware"] & ~typed["is_data_breach"]
                             & ~typed["is_availability_disruption"]).sum())
        print(f"[{fname}] rows={n:,}  ransomware={r:,} (keyword_derived={kw:,})  "
              f"data_breach={b:,}  disruption={d:,}  none_flagged={none_flagged:,}")
        print(f"  -> {out_path}")


if __name__ == "__main__":
    main()

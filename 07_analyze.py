"""
07_analyze.py
Core NLP analysis pipeline for ACT for CAP.

Three similarity methods run in parallel:
  1. TF-IDF Cosine       — keyword overlap (original method)
  2. STS                 — semantic text similarity via sentence-transformers
                           (paraphrase-MiniLM-L6-v2, ~80MB, no GPU needed)
  3. SIMDL               — deep semantic similarity via a stronger BERT model
                           (all-mpnet-base-v2, ~420MB, no GPU needed)

The stats output (mean, median, std dev) from each method are used to set
data-driven bucket thresholds for the report badges rather than fixed cutoffs.

Two analyses:
  A) Intra-SHU Redundancy Detection
     Flags SHU course pairs that score high across methods.
     Output: output/shu_redundant_pairs.csv

  B) Cross-Institutional Terminology Alignment
     For each SHU course, finds the best match at each peer institution.
     Output: output/cross_institution_matches.csv

  + Keyword Frequency Analysis
     Output: output/keyword_frequencies.csv

  + Similarity Stats
     Output: output/similarity_stats.json
     (consumed by 08_report.py to set dynamic bucket thresholds)
"""

import sqlite3, csv, re, os, json
from itertools import combinations
from collections import defaultdict
import statistics

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# ── Optional deep learning imports ────────────────────────────────
try:
    from sentence_transformers import SentenceTransformer
    STS_AVAILABLE = True
except ImportError:
    STS_AVAILABLE = False
    print("⚠  sentence-transformers not installed.")
    print("   Run: pip install sentence-transformers")
    print("   Continuing with TF-IDF only.\n")

DB_PATH             = "data/processed/act_for_cap.db"
REDUNDANCY_OUT      = "output/shu_redundant_pairs.csv"
CROSS_INST_OUT      = "output/cross_institution_matches.csv"
KEYWORD_FREQ_OUT    = "output/keyword_frequencies.csv"
STATS_OUT           = "output/similarity_stats.json"

SIMILARITY_THRESHOLD = 0.75   # TF-IDF flag threshold (per proposal)
CROSS_MATCH_TOP_N    = 1      # Best match per peer institution

# STS model — lightweight, ~80MB
STS_MODEL_NAME  = "paraphrase-MiniLM-L6-v2"
# SIMDL model — stronger, ~420MB
SIMDL_MODEL_NAME = "all-mpnet-base-v2"

# ── Stopword list ─────────────────────────────────────────────────
STOP_WORDS = "english"
ACADEMIC_NOISE = {
    # Catalog structural words
    "course", "courses", "class", "classes", "credit", "credits", "hours",
    "offered", "offering", "semester", "semesters", "fall", "spring", "summer",
    "prerequisite", "prerequisites", "corequisite", "corequisites",
    "permission", "instructor", "consent", "department", "required", "requirement",
    "requirements", "major", "minor", "program", "programs", "university",
    "college", "school", "pennsylvania", "number", "core", "elective",
    "lecture", "laboratory", "lab", "discussion", "seminar", "studio",
    "examination", "exam", "test", "grade", "grading", "unit",
    "recitation", "workshop", "fieldwork", "internship", "practicum",
    "when", "also", "their", "this", "that", "with", "from", "will",
    "minute", "minutes", "hour", "week", "weeks", "year", "years",
    # Generic action/learning verbs
    "introduction", "introductory", "survey", "overview",
    "study", "studies", "studying", "student", "students",
    "learn", "learns", "learning", "learned",
    "explore", "explores", "exploring", "exploration",
    "develop", "develops", "developing", "development",
    "provide", "provides", "providing",
    "examine", "examines", "examining",
    "focus", "focuses", "focusing",
    "emphasize", "emphasizes", "emphasis",
    "include", "includes", "including",
    "cover", "covers", "covering",
    "present", "presents", "presenting",
    "introduce", "introduces", "introducing",
    "apply", "applies", "applying", "applied", "application", "applications",
    "use", "uses", "using", "used",
    "understand", "understands", "understanding",
    "demonstrate", "demonstrates", "demonstrating",
    "complete", "completes", "completing", "completion",
    "prepare", "prepares", "preparing", "preparation",
    "analyze", "analyzes", "analyzing", "analysis",
    "review", "reviews", "reviewing",
    "discuss", "discusses", "discussing",
    "consider", "considers", "considering",
    "identify", "identifies", "identifying",
    # Generic descriptors
    "basic", "advanced", "intermediate", "special",
    "selected", "topics", "topic", "area", "areas", "field", "fields",
    "general", "various", "particular", "current", "contemporary",
    "practical", "theoretical", "fundamental", "foundational",
    "principles", "principle", "concepts", "concept",
    "methods", "method", "methodology", "methodologies",
    "techniques", "technique", "approaches", "approach",
    "theory", "theories", "practice", "practices",
    "skills", "skill", "instruction", "instructional",
    "knowledge", "content", "material", "materials",
    "work", "works", "working", "project", "projects",
    "problem", "problems", "solution", "solutions",
    "process", "processes", "procedure", "procedures",
    "information", "data", "research", "design",
    "production", "media", "care", "history", "education", "nursing",
    "science", "music", "through", "also", "upon", "well",
    "able", "each", "other", "into", "within", "across", "toward",
}

os.makedirs("output", exist_ok=True)


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Lowercase, strip digits/punctuation, remove academic noise."""
    text = text.lower()
    text = re.sub(r'\d+', '', text)
    text = re.sub(r'[^a-z\s]', ' ', text)
    tokens = [t for t in text.split() if t not in ACADEMIC_NOISE and len(t) > 2]
    return " ".join(tokens)


def load_courses(institution: str = None, active_only: bool = True) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()
    sql  = "SELECT * FROM courses WHERE 1=1"
    params: list = []
    if institution:
        sql += " AND institution = ?"
        params.append(institution)
    if active_only:
        sql += " AND active = 1"
    sql += " AND description != '' AND length(description) > 30"
    rows = cur.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_institutions() -> list[str]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT DISTINCT institution FROM courses").fetchall()
    conn.close()
    return [r[0] for r in rows]


def calc_stats(values: list[float]) -> dict:
    """Compute descriptive stats used to set dynamic bucket thresholds."""
    if not values:
        return {}
    mean   = statistics.mean(values)
    stdev  = statistics.pstdev(values)
    return {
        "count":  len(values),
        "mean":   round(mean, 4),
        "median": round(statistics.median(values), 4),
        "stddev": round(stdev, 4),
        "min":    round(min(values), 4),
        "max":    round(max(values), 4),
        # Dynamic thresholds: mean + N * stdev
        # These become the bucket boundaries in the report
        "bucket_high":      round(mean + stdev, 4),       # top ~16%
        "bucket_very_high": round(mean + 1.5 * stdev, 4), # top ~7%
    }


def load_sts_model(model_name: str):
    """Load a sentence-transformer model, with a clear progress message."""
    print(f"  Loading model: {model_name}")
    print(f"  (First run downloads the model — this may take a minute)")
    model = SentenceTransformer(model_name)
    print(f"  ✓ Model loaded")
    return model


def encode_texts(model, texts: list[str]) -> np.ndarray:
    """Encode a list of texts into embedding vectors."""
    return model.encode(texts, show_progress_bar=True, batch_size=32)


def cosine_sim_matrix(embeddings_a: np.ndarray, embeddings_b: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between two sets of embeddings."""
    return cosine_similarity(embeddings_a, embeddings_b)


# ─────────────────────────────────────────────────────────────────
# Analysis A: SHU Intra-Institution Redundancy
# ─────────────────────────────────────────────────────────────────

def analyze_shu_redundancy(sts_model=None, simdl_model=None):
    print("\n── Analysis A: SHU Course Redundancy Detection ──")
    courses = load_courses(institution="Seton Hill University")
    print(f"  Loaded {len(courses)} active SHU courses with descriptions")

    if len(courses) < 2:
        print("  Not enough courses to compare.")
        return [], {}

    texts_clean = [clean_text(c["description"] + " " + c["course_title"]) for c in courses]
    texts_raw   = [c["description"] + " " + c["course_title"] for c in courses]

    # ── Method 1: TF-IDF cosine ───────────────────────────────────
    print("  Running TF-IDF cosine similarity...")
    vectorizer = TfidfVectorizer(
        stop_words=STOP_WORDS, ngram_range=(1, 2), min_df=2, max_df=0.95
    )
    tfidf_matrix = vectorizer.fit_transform(texts_clean)
    tfidf_sim    = cosine_similarity(tfidf_matrix)
    print(f"  TF-IDF matrix: {tfidf_matrix.shape[0]} × {tfidf_matrix.shape[1]}")

    # ── Method 2: STS embeddings ──────────────────────────────────
    sts_sim = None
    if STS_AVAILABLE and sts_model is not None:
        print("  Running STS (semantic text similarity)...")
        sts_embeddings = encode_texts(sts_model, texts_raw)
        sts_sim = cosine_sim_matrix(sts_embeddings, sts_embeddings)
        print("  ✓ STS complete")

    # ── Method 3: SIMDL embeddings ────────────────────────────────
    simdl_sim = None
    if STS_AVAILABLE and simdl_model is not None:
        print("  Running SIMDL (deep semantic similarity)...")
        simdl_embeddings = encode_texts(simdl_model, texts_raw)
        simdl_sim = cosine_sim_matrix(simdl_embeddings, simdl_embeddings)
        print("  ✓ SIMDL complete")

    # ── Collect flagged pairs ─────────────────────────────────────
    flagged = []
    n = len(courses)

    for i, j in combinations(range(n), 2):
        tfidf_score = float(tfidf_sim[i, j])

        # Only collect pairs that clear TF-IDF threshold OR STS threshold
        sts_score   = float(sts_sim[i, j])   if sts_sim   is not None else None
        simdl_score = float(simdl_sim[i, j]) if simdl_sim is not None else None

        # Skip if all available methods score low
        scores_available = [tfidf_score]
        if sts_score   is not None: scores_available.append(sts_score)
        if simdl_score is not None: scores_available.append(simdl_score)

        if max(scores_available) < SIMILARITY_THRESHOLD:
            continue

        a = courses[i]
        b = courses[j]
        if a["course_code"] == b["course_code"]:
            continue

        row = {
            "course_code_a":    a["course_code"],
            "course_title_a":   a["course_title"],
            "dept_a":           a["department"],
            "course_code_b":    b["course_code"],
            "course_title_b":   b["course_title"],
            "dept_b":           b["department"],
            "tfidf_score":      round(tfidf_score, 4),
            "sts_score":        round(sts_score, 4)   if sts_score   is not None else "",
            "simdl_score":      round(simdl_score, 4) if simdl_score is not None else "",
            # Composite: average of available scores
            "composite_score":  round(
                statistics.mean([s for s in [tfidf_score, sts_score, simdl_score] if s is not None]),
                4
            ),
            "description_a":    a["description"][:300],
            "description_b":    b["description"][:300],
        }
        flagged.append(row)

    flagged.sort(key=lambda x: x["composite_score"], reverse=True)

    with open(REDUNDANCY_OUT, "w", newline="", encoding="utf-8") as f:
        if flagged:
            writer = csv.DictWriter(f, fieldnames=list(flagged[0].keys()))
            writer.writeheader()
            writer.writerows(flagged)

    # Compute stats on composite scores for dynamic bucketing
    composite_scores = [r["composite_score"] for r in flagged]
    stats = calc_stats(composite_scores)

    print(f"  ✅ {len(flagged)} flagged pairs → {REDUNDANCY_OUT}")
    if flagged:
        print(f"  Top 3:")
        for p in flagged[:3]:
            print(f"    [{p['composite_score']:.3f}] {p['course_code_a']} ↔ {p['course_code_b']}")

    return flagged, stats


# ─────────────────────────────────────────────────────────────────
# Analysis B: Cross-Institutional Terminology Alignment
# ─────────────────────────────────────────────────────────────────

def analyze_cross_institution(sts_model=None, simdl_model=None):
    print("\n── Analysis B: Cross-Institution Terminology Alignment ──")
    institutions = get_institutions()
    peers = [i for i in institutions if "Seton Hill" not in i]

    if not peers:
        print("  No peer institution data available yet.")
        return [], {}

    shu_courses  = load_courses(institution="Seton Hill University")
    texts_shu_clean = [clean_text(c["description"] + " " + c["course_title"]) for c in shu_courses]
    texts_shu_raw   = [c["description"] + " " + c["course_title"] for c in shu_courses]

    # Pre-encode SHU once for STS and SIMDL to avoid re-encoding for each peer
    sts_shu_emb   = encode_texts(sts_model,   texts_shu_raw) if (STS_AVAILABLE and sts_model)   else None
    simdl_shu_emb = encode_texts(simdl_model, texts_shu_raw) if (STS_AVAILABLE and simdl_model) else None

    print(f"  SHU: {len(shu_courses)} courses")
    results = []

    for peer in peers:
        peer_courses = load_courses(institution=peer)
        print(f"  {peer}: {len(peer_courses)} courses")
        if not peer_courses:
            continue

        texts_peer_clean = [clean_text(c["description"] + " " + c["course_title"]) for c in peer_courses]
        texts_peer_raw   = [c["description"] + " " + c["course_title"] for c in peer_courses]

        # TF-IDF
        all_clean = texts_shu_clean + texts_peer_clean
        vectorizer = TfidfVectorizer(stop_words=STOP_WORDS, ngram_range=(1, 2), min_df=1, max_df=0.95)
        try:
            matrix     = vectorizer.fit_transform(all_clean)
            tfidf_sim  = cosine_similarity(matrix[:len(shu_courses)], matrix[len(shu_courses):])
        except ValueError:
            print(f"    ✗ TF-IDF failed for {peer}, skipping")
            continue

        # STS
        sts_sim = None
        if sts_shu_emb is not None:
            peer_emb  = encode_texts(sts_model, texts_peer_raw)
            sts_sim   = cosine_sim_matrix(sts_shu_emb, peer_emb)

        # SIMDL
        simdl_sim = None
        if simdl_shu_emb is not None:
            peer_emb    = encode_texts(simdl_model, texts_peer_raw)
            simdl_sim   = cosine_sim_matrix(simdl_shu_emb, peer_emb)

        for i, shu in enumerate(shu_courses):
            # Collect per-method scores for this SHU course vs all peer courses
            tfidf_scores  = tfidf_sim[i]
            sts_scores    = sts_sim[i]   if sts_sim   is not None else [None] * len(peer_courses)
            simdl_scores  = simdl_sim[i] if simdl_sim is not None else [None] * len(peer_courses)

            # Composite score for ranking
            composite = []
            for j in range(len(peer_courses)):
                s_tfidf  = float(tfidf_scores[j])
                s_sts    = float(sts_scores[j])   if sts_scores[j]   is not None else None
                s_simdl  = float(simdl_scores[j]) if simdl_scores[j] is not None else None
                available = [s for s in [s_tfidf, s_sts, s_simdl] if s is not None]
                composite.append(statistics.mean(available))

            top_j = int(np.argmax(composite))
            comp_score = composite[top_j]

            if comp_score < 0.05:
                continue

            peer_c = peer_courses[top_j]
            results.append({
                "shu_code":          shu["course_code"],
                "shu_title":         shu["course_title"],
                "shu_dept":          shu["department"],
                "shu_description":   shu["description"][:250],
                "peer_institution":  peer,
                "peer_code":         peer_c["course_code"],
                "peer_title":        peer_c["course_title"],
                "peer_dept":         peer_c["department"],
                "peer_description":  peer_c["description"][:250],
                "tfidf_score":       round(float(tfidf_scores[top_j]), 4),
                "sts_score":         round(float(sts_scores[top_j]), 4)   if sts_scores[top_j]   is not None else "",
                "simdl_score":       round(float(simdl_scores[top_j]), 4) if simdl_scores[top_j] is not None else "",
                "composite_score":   round(comp_score, 4),
            })

    results.sort(key=lambda x: x["composite_score"], reverse=True)

    with open(CROSS_INST_OUT, "w", newline="", encoding="utf-8") as f:
        if results:
            writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            writer.writeheader()
            writer.writerows(results)
        else:
            f.write("No cross-institution results yet.\n")

    composite_scores = [r["composite_score"] for r in results]
    stats = calc_stats(composite_scores)

    print(f"  ✅ {len(results)} cross-institution matches → {CROSS_INST_OUT}")
    return results, stats


# ─────────────────────────────────────────────────────────────────
# Keyword Frequency Analysis
# ─────────────────────────────────────────────────────────────────

def analyze_keyword_frequencies():
    print("\n── Keyword Frequency Analysis (per institution) ──")
    institutions = get_institutions()
    rows = []
    for inst in institutions:
        courses = load_courses(institution=inst)
        if not courses:
            continue
        combined = " ".join(clean_text(c["description"]) for c in courses)
        tokens   = combined.split()
        freq: dict[str, int] = defaultdict(int)
        for t in tokens:
            if len(t) > 3:
                freq[t] += 1
        top50 = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:50]
        for keyword, count in top50:
            rows.append({
                "institution":   inst,
                "keyword":       keyword,
                "frequency":     count,
                "course_count":  len(courses),
                "relative_freq": round(count / len(courses), 4),
            })

    with open(KEYWORD_FREQ_OUT, "w", newline="", encoding="utf-8") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    freqs  = [r["frequency"] for r in rows]
    stats  = calc_stats(freqs)
    print(f"  ✅ Keyword frequencies → {KEYWORD_FREQ_OUT}")
    return stats


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(DB_PATH):
        print(f"✗ Database not found at {DB_PATH}. Run 06_build_database.py first.")
        return

    # Load models once — shared across both analyses
    sts_model   = None
    simdl_model = None
    if STS_AVAILABLE:
        print("\n── Loading Similarity Models ──")
        sts_model   = load_sts_model(STS_MODEL_NAME)
        simdl_model = load_sts_model(SIMDL_MODEL_NAME)
    else:
        print("⚠  Running in TF-IDF only mode (sentence-transformers not installed)")

    _, redundancy_stats = analyze_shu_redundancy(sts_model, simdl_model)
    _, cross_stats      = analyze_cross_institution(sts_model, simdl_model)
    keyword_stats       = analyze_keyword_frequencies()

    # Save all stats to JSON for 08_report.py to consume
    all_stats = {
        "redundancy": redundancy_stats,
        "cross":      cross_stats,
        "keywords":   keyword_stats,
    }
    with open(STATS_OUT, "w") as f:
        json.dump(all_stats, f, indent=2)
    print(f"\n✅ Stats saved → {STATS_OUT}")
    print("✅ Analysis complete. Results in output/")


if __name__ == "__main__":
    main()
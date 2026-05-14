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

import sqlite3, csv, re, os, json, sys
from itertools import combinations
from collections import defaultdict
import statistics

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, classification_report
)
from scipy.stats import spearmanr
import numpy as np

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

# STS model 
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

_COURSE_CODE_RE = re.compile(r'\b[A-Z]{2,6}[\s\-]?\d{2,4}[A-Z]?\b')


def clean_text(text: str) -> str:
    """
    Lowercase, strip digits/punctuation, remove academic noise.

    Strips course-code patterns (e.g. "ACCT 200", "MUAC100", "BL-150A") *before*
    lowercasing so the alphabetic prefix doesn't survive as a junk token like
    "muac" in the keyword frequency output.
    """
    text = _COURSE_CODE_RE.sub(' ', text)
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


def semantic_composite(tfidf, sts, simdl):
    """
    Composite ranking score from context-aware methods only (STS + SIMDL).
    TF-IDF is reported alongside but excluded from the composite — it captures
    surface-level keyword overlap which inflates scores for boilerplate-heavy
    descriptions. Falls back to TF-IDF only if both embedding methods are
    unavailable (TF-IDF-only pipeline mode).
    """
    semantic = [s for s in (sts, simdl) if s is not None]
    if semantic:
        return statistics.mean(semantic)
    return tfidf


# ─────────────────────────────────────────────────────────────────
# Classification Metrics (for labeling tasks)
# ─────────────────────────────────────────────────────────────────

def compute_classification_metrics(y_true, y_pred, labels=None):
    """
    Compute comprehensive classification metrics: accuracy, precision, recall, F1, macro F1.
    
    Args:
        y_true: Ground truth labels
        y_pred: Predicted labels
        labels: Optional list of label names for detailed reporting
    
    Returns:
        dict with metrics:
          - accuracy: overall percentage of correct predictions
          - precision: when model predicts a label, how often it is right
          - recall: how many true examples of label the model successfully finds
          - f1_score: balance between precision and recall
          - macro_f1: useful when labels are imbalanced (unweighted mean of per-label F1s)
    """
    metrics = {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "precision": round(precision_score(y_true, y_pred, average="weighted", zero_division=0), 4),
        "recall": round(recall_score(y_true, y_pred, average="weighted", zero_division=0), 4),
        "f1_score": round(f1_score(y_true, y_pred, average="weighted", zero_division=0), 4),
        "macro_f1": round(f1_score(y_true, y_pred, average="macro", zero_division=0), 4),
    }
    return metrics


def compute_confusion_matrix(y_true, y_pred, labels=None):
    """
    Compute and display confusion matrix.
    Shows which labels the model confuses (false positives/negatives).
    
    Args:
        y_true: Ground truth labels
        y_pred: Predicted labels
        labels: Optional list of label names for readable output
    
    Returns:
        numpy array: confusion matrix
    """
    return confusion_matrix(y_true, y_pred, labels=labels)


def compute_class_balance(y_true):
    """
    Analyze class balance in dataset.
    Identifies if one category dominates (important for model evaluation).
    
    Args:
        y_true: Ground truth labels
    
    Returns:
        dict with class distribution:
          - class_counts: count per label
          - class_percentages: percentage per label
          - is_imbalanced: True if any class > 80% of dataset
          - dominant_class_pct: percentage of most common class
    """
    unique, counts = np.unique(y_true, return_counts=True)
    total = len(y_true)
    
    class_dist = {}
    for label, count in zip(unique, counts):
        pct = round((count / total) * 100, 2)
        class_dist[str(label)] = {"count": int(count), "percentage": pct}
    
    dominant_pct = (max(counts) / total) * 100
    is_imbalanced = dominant_pct > 80
    
    return {
        "class_distribution": class_dist,
        "dominant_class_percentage": round(dominant_pct, 2),
        "is_imbalanced": is_imbalanced,
        "warning": "Avoid relying on accuracy alone! Weak model can look accurate by always predicting majority class." if is_imbalanced else None,
    }


def print_classification_report(y_true, y_pred, target_names=None):
    """
    Print a detailed classification report with per-label precision, recall, F1.
    
    Args:
        y_true: Ground truth labels
        y_pred: Predicted labels
        target_names: Optional list of label names for readable output
    """
    return classification_report(y_true, y_pred, target_names=target_names, zero_division=0)


# ─────────────────────────────────────────────────────────────────
# Ranking & Matching Evaluation Metrics (for course similarity)
# ─────────────────────────────────────────────────────────────────

def top1_match_accuracy(predicted_rankings, ground_truth_correct):
    """
    Top-1 match accuracy: percentage of predictions where highest-ranked match is correct.
    
    Args:
        predicted_rankings: list of ranked match IDs per query (first = highest ranked)
        ground_truth_correct: list of sets of correct matches (indices that are correct)
    
    Returns:
        float: accuracy (0-1)
    """
    if not predicted_rankings:
        return 0.0
    correct = sum(1 for pred, true_set in zip(predicted_rankings, ground_truth_correct)
                  if pred and pred[0] in true_set)
    return round(correct / len(predicted_rankings), 4)


def precision_at_k(predicted_rankings, ground_truth_correct, k=10):
    """
    Precision@K: among top K suggestions, percentage that reviewers consider relevant.
    
    Args:
        predicted_rankings: list of ranked match IDs per query
        ground_truth_correct: list of sets of correct match indices
        k: cutoff rank
    
    Returns:
        dict: precision at each rank 1..k
    """
    precisions = {i: [] for i in range(1, k+1)}
    
    for pred, true_set in zip(predicted_rankings, ground_truth_correct):
        for i in range(1, min(k+1, len(pred)+1)):
            top_i = set(pred[:i])
            relevant = len(top_i & true_set)
            precisions[i].append(relevant / i)
    
    return {i: round(statistics.mean(prec), 4) if prec else 0.0 
            for i, prec in precisions.items()}


def recall_at_k(predicted_rankings, ground_truth_correct, k=10):
    """
    Recall@K: percentage of known relevant matches appearing in top K.
    
    Args:
        predicted_rankings: list of ranked match IDs per query
        ground_truth_correct: list of sets of correct match indices
        k: cutoff rank
    
    Returns:
        dict: recall at each rank 1..k
    """
    recalls = {i: [] for i in range(1, k+1)}
    
    for pred, true_set in zip(predicted_rankings, ground_truth_correct):
        if not true_set:
            continue
        for i in range(1, min(k+1, len(pred)+1)):
            top_i = set(pred[:i])
            relevant = len(top_i & true_set)
            recalls[i].append(relevant / len(true_set))
    
    return {i: round(statistics.mean(recall), 4) if recall else 0.0 
            for i, recall in recalls.items()}


def mean_reciprocal_rank(predicted_rankings, ground_truth_correct):
    """
    Mean Reciprocal Rank: rewards system when first correct match appears near top.
    Reciprocal rank = 1 / (position of first correct match).
    
    Args:
        predicted_rankings: list of ranked match IDs per query
        ground_truth_correct: list of sets of correct match indices
    
    Returns:
        float: MRR (0-1)
    """
    rr_list = []
    
    for pred, true_set in zip(predicted_rankings, ground_truth_correct):
        if not true_set:
            continue
        for rank, match_id in enumerate(pred, 1):
            if match_id in true_set:
                rr_list.append(1.0 / rank)
                break
        else:
            # No correct match found in ranking
            rr_list.append(0.0)
    
    if not rr_list:
        return 0.0
    return round(statistics.mean(rr_list), 4)


def spearman_rank_correlation(model_scores, human_scores):
    """
    Spearman rank correlation: compares model ranking vs human reviewer ranking.
    Useful when reviewers score multiple candidates (e.g., 1-5 relevance scale).
    
    Args:
        model_scores: list of similarity scores from model
        human_scores: list of human reviewer scores (same length)
    
    Returns:
        dict: correlation coefficient and p-value
    """
    if len(model_scores) < 2 or len(human_scores) < 2:
        return {"correlation": 0.0, "p_value": 1.0}
    
    corr, pval = spearmanr(model_scores, human_scores)
    return {
        "correlation": round(float(corr), 4) if not np.isnan(corr) else 0.0,
        "p_value": round(float(pval), 4),
    }


def false_positive_rate(predicted_matches, ground_truth_correct, all_candidates):
    """
    False positive rate: how often model says two courses are similar when reviewer disagrees.
    
    Args:
        predicted_matches: list of (query_idx, match_idx) pairs the model flagged
        ground_truth_correct: set of (query_idx, match_idx) pairs that are actually correct
        all_candidates: total number of possible (query, candidate) pairs
    
    Returns:
        float: false positive rate (0-1)
    """
    predicted_set = set(predicted_matches)
    correct_set = ground_truth_correct
    
    false_positives = len(predicted_set - correct_set)
    if all_candidates == 0:
        return 0.0
    return round(false_positives / all_candidates, 4)


def false_negative_rate(predicted_matches, ground_truth_correct, all_candidates):
    """
    False negative rate: examples where model missed a match a human thought was obvious.
    
    Args:
        predicted_matches: list of (query_idx, match_idx) pairs the model flagged
        ground_truth_correct: set of (query_idx, match_idx) pairs that are actually correct
        all_candidates: total number of possible (query, candidate) pairs
    
    Returns:
        float: false negative rate (0-1)
    """
    predicted_set = set(predicted_matches)
    correct_set = ground_truth_correct
    
    false_negatives = len(correct_set - predicted_set)
    if all_candidates == 0:
        return 0.0
    return round(false_negatives / all_candidates, 4)


def compare_ranking_methods(tfidf_rankings, sts_rankings, simdl_rankings, ground_truth_correct):
    """
    Compare ranking quality across TF-IDF, STS, and SIMDL methods.
    
    Args:
        tfidf_rankings: TF-IDF ranked matches per query
        sts_rankings: STS ranked matches per query
        simdl_rankings: SIMDL ranked matches per query
        ground_truth_correct: ground truth correct matches
    
    Returns:
        dict: MRR for each method, showing semantic improvement over TF-IDF
    """
    results = {}
    
    if tfidf_rankings:
        results["tfidf_mrr"] = mean_reciprocal_rank(tfidf_rankings, ground_truth_correct)
    if sts_rankings:
        results["sts_mrr"] = mean_reciprocal_rank(sts_rankings, ground_truth_correct)
    if simdl_rankings:
        results["simdl_mrr"] = mean_reciprocal_rank(simdl_rankings, ground_truth_correct)
    
    # Show semantic improvement
    if "tfidf_mrr" in results and "sts_mrr" in results:
        results["sts_improvement"] = round(results["sts_mrr"] - results["tfidf_mrr"], 4)
    if "tfidf_mrr" in results and "simdl_mrr" in results:
        results["simdl_improvement"] = round(results["simdl_mrr"] - results["tfidf_mrr"], 4)
    
    return results




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
            # Composite: STS + SIMDL only (context-aware). TF-IDF reported separately.
            "composite_score":  round(semantic_composite(tfidf_score, sts_score, simdl_score), 4),
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

            # Composite ranking — context-aware methods only (STS + SIMDL).
            composite = []
            for j in range(len(peer_courses)):
                s_tfidf  = float(tfidf_scores[j])
                s_sts    = float(sts_scores[j])   if sts_scores[j]   is not None else None
                s_simdl  = float(simdl_scores[j]) if simdl_scores[j] is not None else None
                composite.append(semantic_composite(s_tfidf, s_sts, s_simdl))

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
# Validation (with gold standard)
# ─────────────────────────────────────────────────────────────────

def validate_with_gold_standard(gold_standard_path: str):
    """
    Load gold standard labels and compute classification metrics
    against the model's predictions.
    
    Gold standard CSV columns:
      shu_code, shu_title, peer_institution, peer_code, peer_title, is_correct
    
    Metrics computed:
      - Accuracy, Precision, Recall, F1, Macro F1
      - Confusion matrix
      - Class balance analysis
      - Per-method comparison (TF-IDF vs STS vs SIMDL)
    """
    if not os.path.exists(gold_standard_path):
        print(f"✗ Gold standard not found: {gold_standard_path}")
        return
    
    print(f"\n── Validation with Gold Standard ──")
    print(f"  Loading: {gold_standard_path}")
    
    # Load gold standard
    gold_data = {}
    with open(gold_standard_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["shu_code"].strip(), row["peer_institution"].strip(), row["peer_code"].strip())
            gold_data[key] = int(row["is_correct"])
    
    print(f"  Loaded {len(gold_data)} gold standard labels")
    
    # Load predictions from cross-institution matches
    cross_rows = []
    if os.path.exists(CROSS_INST_OUT):
        with open(CROSS_INST_OUT, newline="", encoding="utf-8") as f:
            cross_rows = list(csv.DictReader(f))
    
    if not cross_rows:
        print("  ✗ No cross-institution predictions found. Run main analysis first.")
        return
    
    # Build prediction set: (shu_code, peer_institution, peer_code) -> predicted_score
    predictions = {}
    for row in cross_rows:
        key = (row["shu_code"].strip(), row["peer_institution"].strip(), row["peer_code"].strip())
        predictions[key] = {
            "composite": float(row.get("composite_score", 0)),
            "tfidf": float(row.get("tfidf_score", 0)),
            "sts": float(row.get("sts_score") or 0),
            "simdl": float(row.get("simdl_score") or 0),
        }
    
    # Match predictions to gold standard
    y_true = []
    y_pred_composite = []
    y_pred_tfidf = []
    y_pred_sts = []
    y_pred_simdl = []
    matched_count = 0
    
    for key, gold_label in gold_data.items():
        if key in predictions:
            matched_count += 1
            y_true.append(gold_label)
            # Threshold: composite >= 0.75 is predicted as 1 (match), else 0
            y_pred_composite.append(1 if predictions[key]["composite"] >= 0.75 else 0)
            y_pred_tfidf.append(1 if predictions[key]["tfidf"] >= 0.75 else 0)
            y_pred_sts.append(1 if predictions[key]["sts"] >= 0.75 else 0)
            y_pred_simdl.append(1 if predictions[key]["simdl"] >= 0.75 else 0)
    
    print(f"  Matched {matched_count}/{len(gold_data)} gold labels to predictions")
    
    if matched_count == 0:
        print("  ✗ No matches between gold standard and predictions.")
        return
    
    # Compute metrics for each method
    def compute_method_metrics(y_t, y_p, method_name):
        acc = round(accuracy_score(y_t, y_p), 4)
        prec = round(precision_score(y_t, y_p, zero_division=0), 4)
        rec = round(recall_score(y_t, y_p, zero_division=0), 4)
        f1 = round(f1_score(y_t, y_p, zero_division=0), 4)
        
        macro_f1 = round(f1_score(y_t, y_p, average="macro", zero_division=0), 4)
        
        # Confusion matrix: [[TN, FP], [FN, TP]]
        cm = confusion_matrix(y_t, y_p, labels=[0, 1])
        tn, fp, fn, tp = cm[0, 0], cm[0, 1], cm[1, 0], cm[1, 1]
        fpr = round(fp / (fp + tn), 4) if (fp + tn) > 0 else 0
        fnr = round(fn / (fn + tp), 4) if (fn + tp) > 0 else 0
        
        return {
            "method": method_name,
            "accuracy": acc,
            "precision": prec,
            "recall": rec,
            "f1_score": f1,
            "macro_f1": macro_f1,
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
            "false_positive_rate": fpr,
            "false_negative_rate": fnr,
        }
    
    # Class balance
    unique, counts = np.unique(y_true, return_counts=True)
    class_dist = {}
    for label, count in zip(unique, counts):
        pct = round((count / len(y_true)) * 100, 2)
        class_dist[int(label)] = {"count": int(count), "percentage": pct}
    
    dominant_pct = round((max(counts) / len(y_true)) * 100, 2)
    is_imbalanced = dominant_pct > 80
    
    # Assemble all metrics
    metrics = {
        "validation_date": str(pd.Timestamp.now().date()) if 'pd' in dir() else str(np.datetime64('today')),
        "gold_standard_file": gold_standard_path,
        "total_gold_labels": len(gold_data),
        "matched_to_predictions": matched_count,
        "match_rate": round(matched_count / len(gold_data), 4),
        
        "class_balance": {
            "distribution": class_dist,
            "dominant_class_percentage": dominant_pct,
            "is_imbalanced": is_imbalanced,
            "warning": "Avoid relying on accuracy alone! Weak model can look accurate by always predicting majority class." if is_imbalanced else None,
        },
        
        "methods": {
            "composite": compute_method_metrics(y_true, y_pred_composite, "Composite (STS+SIMDL)"),
            "tfidf": compute_method_metrics(y_true, y_pred_tfidf, "TF-IDF"),
            "sts": compute_method_metrics(y_true, y_pred_sts, "STS"),
            "simdl": compute_method_metrics(y_true, y_pred_simdl, "SIMDL"),
        }
    }
    
    # Save metrics
    VALIDATION_OUT = "output/validation_metrics.json"
    with open(VALIDATION_OUT, "w") as f:
        json.dump(metrics, f, indent=2)
    
    print(f"\n  ✅ Validation metrics saved → {VALIDATION_OUT}")
    
    # Print summary
    comp_metrics = metrics["methods"]["composite"]
    print(f"\n  ┌─ Composite Method Summary ─────────────────────────┐")
    print(f"  │ Accuracy:        {comp_metrics['accuracy']}")
    print(f"  │ Precision:       {comp_metrics['precision']}")
    print(f"  │ Recall:          {comp_metrics['recall']}")
    print(f"  │ F1 Score:        {comp_metrics['f1_score']}")
    print(f"  │ Macro F1:        {comp_metrics['macro_f1']}")
    print(f"  │")
    cm = comp_metrics['confusion_matrix']
    print(f"  │ Confusion Matrix:")
    print(f"  │   True Neg:      {cm['tn']}    False Pos:    {cm['fp']}")
    print(f"  │   False Neg:     {cm['fn']}    True Pos:     {cm['tp']}")
    print(f"  │")
    print(f"  │ False Positive Rate: {comp_metrics['false_positive_rate']:.1%}")
    print(f"  │ False Negative Rate: {comp_metrics['false_negative_rate']:.1%}")
    print(f"  │")
    balance = metrics["class_balance"]
    print(f"  │ Class Balance: {balance['distribution']}")
    if balance['is_imbalanced']:
        print(f"  │ ⚠  IMBALANCED: {balance['dominant_class_percentage']}% dominated by one class")
    print(f"  └─────────────────────────────────────────────────────┘")



# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────

def main():
    # Parse command-line arguments
    import argparse
    parser = argparse.ArgumentParser(description="ACT for CAP NLP analysis pipeline")
    parser.add_argument("--validate", type=str, help="Path to gold standard CSV for validation")
    args = parser.parse_args()
    
    if args.validate:
        # Validation mode only
        validate_with_gold_standard(args.validate)
        return
    
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
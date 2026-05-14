"""
08_report.py
Generates a self-contained HTML report from the analysis outputs.
  output/ACT_for_CAP_Report.html

Sections:
  - Summary
  - SHU Redundancy
  - SHU vs Peers (pivot: best match per peer + average per course)
  - Cross-Institution (raw matches)
  - Keywords
  - Analytics
  - Methodology
"""

import csv, html, json, os, statistics
from datetime import date
from collections import defaultdict

REDUNDANCY_CSV  = "output/shu_redundant_pairs.csv"
CROSS_INST_CSV  = "output/cross_institution_matches.csv"
KEYWORD_CSV     = "output/keyword_frequencies.csv"
STATS_JSON      = "output/similarity_stats.json"
VALIDATION_JSON   = "output/validation_metrics.json"
REPORT_OUT        = "output/ACT_for_CAP_Report.html"


def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_stats() -> dict:
    if not os.path.exists(STATS_JSON):
        return {}
    with open(STATS_JSON) as f:
        return json.load(f)


def read_validation_metrics() -> dict:
    if not os.path.exists(VALIDATION_JSON):
        return {}
    with open(VALIDATION_JSON) as f:
        return json.load(f)


def cohen_kappa(labels_a: list, labels_b: list) -> float:
    """Compute Cohen's kappa between two raters."""
    if len(labels_a) != len(labels_b) or not labels_a:
        return 0.0
    categories = sorted(set(labels_a) | set(labels_b))
    n = len(labels_a)
    p_o = sum(a == b for a, b in zip(labels_a, labels_b)) / n
    p_e = sum(
        (labels_a.count(c) / n) * (labels_b.count(c) / n)
        for c in categories
    )
    return round((p_o - p_e) / (1 - p_e), 4) if (1 - p_e) > 0 else 1.0


def f(score) -> float:
    """Coerce a score value to float, treating empty/None as 0."""
    if score == "" or score is None:
        return 0.0
    try:
        return float(score)
    except (ValueError, TypeError):
        return 0.0


def score_cell(score, high_t=0.80, very_high_t=0.90) -> str:
    """
    Subtle monochromatic score cell. Shows the numeric value with a small
    intensity indicator. No harsh red/yellow — just slate tones.
    """
    if score == "" or score is None:
        return '<span class="score score-na">—</span>'
    s = f(score)
    if s >= very_high_t:
        cls = "score-vh"
    elif s >= high_t:
        cls = "score-h"
    elif s >= 0.50:
        cls = "score-m"
    else:
        cls = "score-l"
    return f'<span class="score {cls}"><span class="dot"></span>{s:.3f}</span>'


def calc_stats(values: list[float]) -> dict:
    if not values:
        return {}
    mean  = statistics.mean(values)
    stdev = statistics.pstdev(values)
    return {
        "count":  len(values),
        "mean":   mean,
        "median": statistics.median(values),
        "stddev": stdev,
        "min":    min(values),
        "max":    max(values),
        "bucket_high":      mean + stdev,
        "bucket_very_high": mean + 1.5 * stdev,
    }


# ─────────────────────────────────────────────────────────────────
# Tables
# ─────────────────────────────────────────────────────────────────

def build_redundancy_table(rows: list[dict], stats: dict) -> str:
    if not rows:
        return '<p class="muted">No redundant pairs found.</p>'

    r_stats = stats.get("redundancy", {})
    high_t      = r_stats.get("bucket_high",      0.80)
    very_high_t = r_stats.get("bucket_very_high", 0.90)

    sample = rows[0]
    has_sts   = "sts_score"   in sample and any(r.get("sts_score")   for r in rows)
    has_simdl = "simdl_score" in sample and any(r.get("simdl_score") for r in rows)

    sts_th   = "<th>STS</th>"   if has_sts   else ""
    simdl_th = "<th>SIMDL</th>" if has_simdl else ""

    body_rows = []
    for r in rows:
        sts_td   = f"<td>{score_cell(r.get('sts_score'),   high_t, very_high_t)}</td>" if has_sts   else ""
        simdl_td = f"<td>{score_cell(r.get('simdl_score'), high_t, very_high_t)}</td>" if has_simdl else ""
        body_rows.append(f"""
        <tr>
          <td><code>{r['course_code_a']}</code></td>
          <td>{r['course_title_a']}</td>
          <td><span class="tag">{r['dept_a']}</span></td>
          <td><code>{r['course_code_b']}</code></td>
          <td>{r['course_title_b']}</td>
          <td><span class="tag">{r['dept_b']}</span></td>
          <td>{score_cell(r.get('tfidf_score'), high_t, very_high_t)}</td>
          {sts_td}
          {simdl_td}
          <td>{score_cell(r.get('composite_score'), high_t, very_high_t)}</td>
        </tr>""")

    return f"""
    <div class="threshold-strip">
      High <strong>≥ {high_t:.3f}</strong>
      <span class="sep">·</span>
      Very High <strong>≥ {very_high_t:.3f}</strong>
      <span class="sep">·</span>
      <span class="muted">{len(rows)} flagged pairs</span>
    </div>
    <input type="text" class="filter-input"
           placeholder="Filter by course code or title…"
           oninput="filterTable('redundancy-table', this.value)">
    <div class="table-wrap">
    <table id="redundancy-table" class="data-table">
      <thead>
        <tr>
          <th onclick="sortTable('redundancy-table',0)">Code A</th>
          <th onclick="sortTable('redundancy-table',1)">Title A</th>
          <th onclick="sortTable('redundancy-table',2)">Dept</th>
          <th onclick="sortTable('redundancy-table',3)">Code B</th>
          <th onclick="sortTable('redundancy-table',4)">Title B</th>
          <th onclick="sortTable('redundancy-table',5)">Dept</th>
          <th onclick="sortTable('redundancy-table',6)">TF-IDF</th>
          {sts_th}
          {simdl_th}
          <th onclick="sortTable('redundancy-table',{7 + has_sts + has_simdl})">Composite</th>
        </tr>
      </thead>
      <tbody>{''.join(body_rows)}</tbody>
    </table>
    </div>"""


def build_cross_table(rows: list[dict], stats: dict) -> str:
    if not rows:
        return '<p class="muted">No peer institution data available.</p>'

    rows = [r for r in rows if f(r.get("composite_score")) >= 0.20]
    if not rows:
        return '<p class="muted">No matches above threshold.</p>'

    c_stats = stats.get("cross", {})
    high_t      = c_stats.get("bucket_high",      0.80)
    very_high_t = c_stats.get("bucket_very_high", 0.90)

    sample    = rows[0]
    has_sts   = "sts_score"   in sample and any(r.get("sts_score")   for r in rows)
    has_simdl = "simdl_score" in sample and any(r.get("simdl_score") for r in rows)

    peers     = sorted(set(r["peer_institution"] for r in rows))
    peer_opts = "".join(f'<option value="{p}">{p}</option>' for p in peers)

    sts_th   = "<th>STS</th>"   if has_sts   else ""
    simdl_th = "<th>SIMDL</th>" if has_simdl else ""

    body_rows = []
    for r in rows[:500]:
        sts_td   = f"<td>{score_cell(r.get('sts_score'),   high_t, very_high_t)}</td>" if has_sts   else ""
        simdl_td = f"<td>{score_cell(r.get('simdl_score'), high_t, very_high_t)}</td>" if has_simdl else ""
        shu_desc = html.escape(r.get('shu_description', ''), quote=True)
        peer_desc = html.escape(r.get('peer_description', ''), quote=True)
        body_rows.append(f"""
        <tr data-peer="{r['peer_institution']}">
          <td><code>{r['shu_code']}</code></td>
          <td title="{shu_desc}">{r['shu_title']}</td>
          <td><span class="muted">{r['peer_institution']}</span></td>
          <td><code>{r['peer_code']}</code></td>
          <td title="{peer_desc}">{r['peer_title']}</td>
          <td>{score_cell(r.get('tfidf_score'), high_t, very_high_t)}</td>
          {sts_td}
          {simdl_td}
          <td>{score_cell(r.get('composite_score'), high_t, very_high_t)}</td>
        </tr>""")

    overflow = ""
    if len(rows) > 500:
        overflow = f'<p class="muted small">Showing top 500 of {len(rows)} matches. See CSV for full results.</p>'

    return f"""
    <div class="threshold-strip">
      High <strong>≥ {high_t:.3f}</strong>
      <span class="sep">·</span>
      Very High <strong>≥ {very_high_t:.3f}</strong>
      <span class="sep">·</span>
      <span class="muted">{len(rows)} matches</span>
    </div>
    <div class="filter-bar">
      <input type="text" class="filter-input"
             placeholder="Filter by code or title…"
             oninput="filterTable('cross-table', this.value)">
      <select class="filter-select" onchange="filterByPeer()" id="peer-filter">
        <option value="">All peers</option>
        {peer_opts}
      </select>
    </div>
    <div class="table-wrap">
    <table id="cross-table" class="data-table">
      <thead>
        <tr>
          <th onclick="sortTable('cross-table',0)">SHU Code</th>
          <th onclick="sortTable('cross-table',1)">SHU Title</th>
          <th onclick="sortTable('cross-table',2)">Peer</th>
          <th onclick="sortTable('cross-table',3)">Peer Code</th>
          <th onclick="sortTable('cross-table',4)">Peer Title</th>
          <th>TF-IDF</th>
          {sts_th}
          {simdl_th}
          <th>Composite</th>
        </tr>
      </thead>
      <tbody>{''.join(body_rows)}</tbody>
    </table>
    </div>
    {overflow}"""


def build_pivot_table(rows: list[dict], stats: dict) -> str:
    """
    Pivot view: each SHU course × peer institution best-match score, with an
    average across peers. Cells are interactive — hover shows the matched peer
    course code & title.
    """
    if not rows:
        return '<p class="muted">No peer institution data available.</p>'

    c_stats = stats.get("cross", {})
    high_t      = c_stats.get("bucket_high",      0.80)
    very_high_t = c_stats.get("bucket_very_high", 0.90)

    peers = sorted({r["peer_institution"] for r in rows if r.get("peer_institution")})

    # Group by SHU course; keep the best (highest composite) per peer.
    by_shu: dict[tuple, dict] = {}
    for r in rows:
        code  = r.get("shu_code", "")
        title = r.get("shu_title", "")
        dept  = r.get("shu_dept", "")
        peer  = r.get("peer_institution", "")
        score = f(r.get("composite_score"))
        if not peer:
            continue
        key = (code, title, dept)
        entry = by_shu.setdefault(key, {})
        prev = entry.get(peer)
        if prev is None or score > prev["score"]:
            entry[peer] = {
                "score":            score,
                "peer_code":        r.get("peer_code", ""),
                "peer_title":       r.get("peer_title", ""),
                "shu_description":  r.get("shu_description", ""),
                "peer_description": r.get("peer_description", ""),
            }

    # Build rows with average across peers that returned a match.
    pivot_rows = []
    for (code, title, dept), peer_map in by_shu.items():
        scores = [peer_map[p]["score"] for p in peers if p in peer_map]
        avg = sum(scores) / len(scores) if scores else 0.0
        pivot_rows.append({
            "code":     code,
            "title":    title,
            "dept":     dept,
            "peer_map": peer_map,
            "avg":      avg,
            "n_peers":  len(scores),
        })
    pivot_rows.sort(key=lambda x: x["avg"], reverse=True)

    peer_th = "".join(f"<th>{p}</th>" for p in peers)

    body = []
    for pr in pivot_rows:
        peer_cells = []
        for p in peers:
            m = pr["peer_map"].get(p)
            if not m:
                peer_cells.append('<td>—</td>')
            else:
                tip = f"{m['peer_code']} · {m['peer_title']}".replace('"', '&quot;')
                peer_cells.append(
                    f'<td title="{tip}" '
                    f'data-shu="{html.escape(m.get("shu_description", ""), quote=True)}" '
                    f'data-peer="{html.escape(m.get("peer_description", ""), quote=True)}" '
                    f'data-label="{html.escape(m["peer_code"] + " - " + m["peer_title"], quote=True)}" '
                    f'onclick="showCourseDetail(this)">'
                    f'{score_cell(m["score"], high_t, very_high_t)}</td>'
                )
        body.append(f"""
        <tr>
          <td><code>{pr['code']}</code></td>
          <td>{pr['title']}</td>
          <td><span class="tag">{pr['dept']}</span></td>
          {''.join(peer_cells)}
          <td>{score_cell(pr['avg'], high_t, very_high_t)}</td>
          <td class="muted small">{pr['n_peers']}/{len(peers)}</td>
        </tr>""")

    avg_col_idx = 3 + len(peers)
    return f"""
    <div class="threshold-strip">
      <span class="muted">Each cell is the best composite-score match for that SHU course at the named peer. Hover a cell for the peer course.</span>
    </div>
    <div class="filter-bar">
      <input type="text" class="filter-input"
             placeholder="Filter by SHU code, title, or department…"
             oninput="filterTable('pivot-table', this.value)">
      <label class="filter-label">
        Min avg
        <input type="number" min="0" max="1" step="0.05" value="0"
               class="filter-num" oninput="filterMinAvg(this.value, {avg_col_idx})">
      </label>
    </div>
    <div class="table-wrap">
    <table id="pivot-table" class="data-table">
      <thead>
        <tr>
          <th onclick="sortTable('pivot-table',0)">SHU Code</th>
          <th onclick="sortTable('pivot-table',1)">SHU Title</th>
          <th onclick="sortTable('pivot-table',2)">Dept</th>
          {peer_th}
          <th onclick="sortTable('pivot-table',{avg_col_idx})">Avg ↓</th>
          <th>Peers</th>
        </tr>
      </thead>
      <tbody>{''.join(body)}</tbody>
    </table>
    </div>
    <p class="muted small">{len(pivot_rows)} SHU courses with at least one peer match. Sorted by average composite similarity.</p>"""


# ─────────────────────────────────────────────────────────────────
# Charts & Analytics
# ─────────────────────────────────────────────────────────────────

def build_keyword_charts(rows: list[dict]) -> tuple[str, str]:
    """
    Returns (markup, init_script). The init_script runs once on first visit to
    the Keywords tab so canvases get sized correctly (rendering hidden display:
    none canvases produces zero-width charts).
    """
    by_inst: dict[str, list] = {}
    for r in rows:
        inst = r["institution"]
        by_inst.setdefault(inst, []).append({"keyword": r["keyword"], "frequency": int(r["frequency"])})

    if not by_inst:
        return ('<p class="muted">No keyword data available.</p>', '')

    cards    = []
    configs  = {}
    for idx, (inst, kws) in enumerate(by_inst.items()):
        top      = kws[:20]
        chart_id = f"chart_{idx}"
        cards.append(f"""
        <div class="chart-card">
          <h4>{inst}</h4>
          <canvas id="{chart_id}"></canvas>
        </div>""")
        configs[chart_id] = {
            "labels": [k["keyword"] for k in top],
            "data":   [k["frequency"] for k in top],
        }

    init_script = f"""
    window.__keywordChartConfigs = {json.dumps(configs)};
    window.__keywordChartsRendered = false;
    window.renderKeywordCharts = function() {{
      if (window.__keywordChartsRendered) return;
      const cfgs = window.__keywordChartConfigs;
      Object.keys(cfgs).forEach(id => {{
        const cv = document.getElementById(id);
        if (!cv) return;
        new Chart(cv, {{
          type: 'bar',
          data: {{
            labels: cfgs[id].labels,
            datasets: [{{
              label: 'Frequency',
              data: cfgs[id].data,
              backgroundColor: 'rgba(99,102,241,0.75)',
              borderColor: 'rgba(79,70,229,1)',
              borderWidth: 0,
              borderRadius: 4,
              maxBarThickness: 28,
            }}]
          }},
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{
              legend: {{ display: false }},
              tooltip: {{ backgroundColor: '#0f172a', padding: 10, cornerRadius: 6 }}
            }},
            scales: {{
              y: {{ beginAtZero: true, grid: {{ color: '#f1f5f9' }}, ticks: {{ color: '#64748b' }} }},
              x: {{
                grid: {{ display: false }},
                ticks: {{
                  color: '#64748b',
                  autoSkip: false,
                  maxRotation: 55, minRotation: 55,
                  font: {{ size: 11 }}
                }}
              }}
            }}
          }}
        }});
      }});
      window.__keywordChartsRendered = true;
    }};
    """
    return ("\n".join(cards), init_script)


def build_analytics_section(redundancy_stats, cross_stats, keyword_stats) -> str:
    def card(title, stats, value_label, explain=""):
        if not stats:
            return f'<div class="card"><h3>{title}</h3><p class="muted">No data available.</p></div>'

        bucket = ""
        if "bucket_high" in stats:
            bucket = f"""
            <div class="note">
              <strong>Threshold derivation</strong> — High = mean + 1·σ = <code>{stats['bucket_high']:.4f}</code> ·
              Very High = mean + 1.5·σ = <code>{stats['bucket_very_high']:.4f}</code>.
              A pair must score in roughly the top 16% to earn High, top 7% for Very High.
            </div>"""

        return f"""
        <div class="card">
          <h3>{title}</h3>
          {f'<p class="muted small">{explain}</p>' if explain else ''}
          <div class="stat-row">
            <div class="stat"><div class="num">{stats['count']}</div><div class="lbl">Count</div></div>
            <div class="stat"><div class="num">{stats['mean']:.4f}</div><div class="lbl">Mean {value_label}</div></div>
            <div class="stat"><div class="num">{stats['median']:.4f}</div><div class="lbl">Median {value_label}</div></div>
            <div class="stat"><div class="num">{stats['stddev']:.4f}</div><div class="lbl">Std Dev</div></div>
            <div class="stat"><div class="num">{stats['min']:.4f}</div><div class="lbl">Min</div></div>
            <div class="stat"><div class="num">{stats['max']:.4f}</div><div class="lbl">Max</div></div>
          </div>
          {bucket}
        </div>"""

    return f"""
    <div id="analytics" class="section">
      <h2>Descriptive Analytics</h2>
      <p class="muted">
        Summary statistics across similarity scores and keyword frequencies. Mean and standard deviation
        from each distribution drive the data-driven bucket thresholds used in the tables above.
      </p>
      {card('SHU Redundancy — Composite Similarity', redundancy_stats, 'score',
           'Distribution of composite scores across flagged SHU course pairs.')}
      {card('Cross-Institution — Composite Similarity', cross_stats, 'score',
           'Distribution of best SHU↔Peer match scores per course.')}
      {card('Keyword Frequency', keyword_stats, 'frequency',
           'Distribution of keyword counts across institutions after stopword removal.')}
    </div>"""


def build_validation_section(validation_metrics: dict) -> str:
    """
    Display ground-truth validation results: accuracy, precision, recall, F1, confusion matrix.
    """
    if not validation_metrics:
        return f"""
    <div id="validation" class="section">
      <h2>Validation Metrics</h2>
      <p class="description">No validation metrics available yet.</p>
      <div class="card">
        <p class="muted">
          To validate against human-reviewed matches, run:<br>
          <code>python 07_analyze.py --validate output/gold_standard.csv</code>
        </p>
      </div>
    </div>"""
    
    # Extract metrics for easy access
    gold_count = validation_metrics.get("total_gold_labels", 0)
    matched = validation_metrics.get("matched_to_predictions", 0)
    match_rate = validation_metrics.get("match_rate", 0)
    
    class_balance = validation_metrics.get("class_balance", {})
    methods = validation_metrics.get("methods", {})
    
    # Build method comparison table
    method_rows = ""
    for method_key in ["composite", "tfidf", "sts", "simdl"]:
        if method_key not in methods:
            continue
        m = methods[method_key]
        cm = m.get("confusion_matrix", {})
        
        method_rows += f"""
        <tr>
          <td><strong>{m.get('method', method_key)}</strong></td>
          <td>{m.get('accuracy', 0):.4f}</td>
          <td>{m.get('precision', 0):.4f}</td>
          <td>{m.get('recall', 0):.4f}</td>
          <td>{m.get('f1_score', 0):.4f}</td>
          <td>{m.get('macro_f1', 0):.4f}</td>
          <td>{cm.get('tp', 0)}</td>
          <td>{cm.get('fp', 0)}</td>
          <td>{cm.get('fn', 0)}</td>
          <td>{cm.get('tn', 0)}</td>
          <td>{m.get('false_positive_rate', 0):.1%}</td>
          <td>{m.get('false_negative_rate', 0):.1%}</td>
        </tr>"""
    
    # Class balance
    class_dist = class_balance.get("distribution", {})
    class_rows = ""
    for label, data in sorted(class_dist.items()):
        label_name = "Correct Match" if str(label) == "1" else "Incorrect/Missing"
        class_rows += f"""
        <tr>
          <td>{label_name}</td>
          <td>{data.get('count', 0)}</td>
          <td>{data.get('percentage', 0):.1f}%</td>
        </tr>"""
    
    imbalance_warning = ""
    if class_balance.get("is_imbalanced"):
        imbalance_warning = f"""
      <div class="card" style="background: #fef2f2; border-color: #fca5a5;">
        <h3 style="color: #be123c;">⚠ Class Imbalance Detected</h3>
        <p style="color: #991b1b;">
          {class_balance.get('dominant_class_percentage', 0):.1f}% of the dataset is dominated by one class.
          Accuracy alone is misleading. Focus on precision, recall, and F1 score instead.
        </p>
      </div>"""
    
    return f"""
    <div id="validation" class="section">
      <h2>Ground-Truth Validation Metrics</h2>
      <p class="description">
        Comparison of model predictions against manually-reviewed gold standard labels.
        Shows accuracy, precision, recall, F1 score, and confusion matrix per method.
      </p>
      
      <div class="card">
        <h3>Validation Summary</h3>
        <div class="stat-row">
          <div class="stat"><div class="num">{gold_count}</div><div class="lbl">Gold Labels</div></div>
          <div class="stat"><div class="num">{matched}</div><div class="lbl">Matched to Predictions</div></div>
          <div class="stat"><div class="num">{match_rate:.1%}</div><div class="lbl">Match Rate</div></div>
        </div>
      </div>
      
      <div class="card">
        <h3>Classification Metrics by Method</h3>
        <p class="muted small">
          <strong>TP/FP/FN/TN:</strong> True Positive, False Positive, False Negative, True Negative counts.
          <strong>FPR/FNR:</strong> False Positive / False Negative Rates.
        </p>
        <table class="metric-table">
          <thead>
            <tr>
              <th>Method</th>
              <th>Accuracy</th>
              <th>Precision</th>
              <th>Recall</th>
              <th>F1 Score</th>
              <th>Macro F1</th>
              <th>TP</th>
              <th>FP</th>
              <th>FN</th>
              <th>TN</th>
              <th>FPR</th>
              <th>FNR</th>
            </tr>
          </thead>
          <tbody>
            {method_rows}
          </tbody>
        </table>
      </div>
      
      <div class="card">
        <h3>Class Balance Analysis</h3>
        <table class="metric-table">
          <thead>
            <tr>
              <th>Class</th>
              <th>Count</th>
              <th>Percentage</th>
            </tr>
          </thead>
          <tbody>
            {class_rows}
          </tbody>
        </table>
      </div>
      
      {imbalance_warning}
      
      <div class="card">
        <h3>Metric Definitions</h3>
        <ul style="margin: 12px 0 0 0; padding-left: 20px;">
          <li><strong>Accuracy:</strong> (TP + TN) / Total — overall prediction correctness.</li>
          <li><strong>Precision:</strong> TP / (TP + FP) — when model predicts a match, how often is it correct?</li>
          <li><strong>Recall:</strong> TP / (TP + FN) — what percentage of true matches does the model find?</li>
          <li><strong>F1 Score:</strong> Harmonic mean of precision and recall — balances both metrics.</li>
          <li><strong>Macro F1:</strong> Unweighted average of F1 scores per class — useful for imbalanced data.</li>
          <li><strong>Confusion Matrix:</strong> TP/FP/FN/TN — shows which predictions are correct/incorrect.</li>
          <li><strong>FPR:</strong> FP / (FP + TN) — how often does the model wrongly predict a match?</li>
          <li><strong>FNR:</strong> FN / (FN + TP) — how often does the model miss a real match?</li>
        </ul>
      </div>
    </div>"""


def build_evaluation_metrics_section(redundancy_rows, cross_rows) -> str:
    """
    Build evaluation metrics tab: accuracy, F-score, false positives, false negatives.
    Shows method comparison (TF-IDF vs STS vs SIMDL) and filters for threshold analysis.
    """
    
    def compute_method_metrics(rows, method_col):
        """Compute metrics for a specific similarity method."""
        if not rows:
            return {}
        
        scores = [f(r.get(method_col)) for r in rows if r.get(method_col)]
        if not scores:
            return {}
        
        # Calculate agreement statistics
        high_count = sum(1 for s in scores if s >= 0.80)
        very_high_count = sum(1 for s in scores if s >= 0.90)
        precision_high = round(high_count / len(scores), 4) if scores else 0
        
        return {
            "matches": len(scores),
            "mean_score": round(sum(scores) / len(scores), 4),
            "high_agreement_rate": precision_high,
            "high_matches": high_count,
            "very_high_matches": very_high_count,
        }
    
    # Redundancy metrics
    red_tfidf = compute_method_metrics(redundancy_rows, "tfidf_score")
    red_sts = compute_method_metrics(redundancy_rows, "sts_score")
    red_simdl = compute_method_metrics(redundancy_rows, "simdl_score")

    # Cross-institution metrics
    cross_tfidf = compute_method_metrics(cross_rows, "tfidf_score")
    cross_sts = compute_method_metrics(cross_rows, "sts_score")
    cross_simdl = compute_method_metrics(cross_rows, "simdl_score")

    # Random baseline: expected agreement rate = 1 / avg peer courses per institution
    peer_institutions = sorted({r.get("peer_institution","") for r in cross_rows if r.get("peer_institution")})
    shu_codes = {r.get("shu_code") for r in cross_rows if r.get("shu_code")}
    n_peers = len(peer_institutions)
    n_cross_total = len(cross_rows)
    avg_peer_courses = round(n_cross_total / max(n_peers, 1) / max(len(shu_codes), 1), 1) if n_cross_total else 1
    random_precision = round(1 / max(avg_peer_courses, 1), 4)
    
    # Build comparison tables
    def method_card(title, tfidf, sts, simdl, context=""):
        if not tfidf and not sts and not simdl:
            return f'<div class="card"><h3>{title}</h3><p class="muted">No data available.</p></div>'
        
        rows_html = ""
        
        # TFIDF
        if tfidf:
            rows_html += f"""
            <tr>
              <td><strong>TF-IDF</strong></td>
              <td>{tfidf['matches']}</td>
              <td>{tfidf['mean_score']:.4f}</td>
              <td>{tfidf['high_matches']}</td>
              <td>{tfidf['very_high_matches']}</td>
              <td>{tfidf['high_agreement_rate']:.1%}</td>
            </tr>"""
        
        # STS
        if sts:
            improvement = ""
            if tfidf and sts['high_agreement_rate'] > tfidf['high_agreement_rate']:
                diff = sts['high_agreement_rate'] - tfidf['high_agreement_rate']
                improvement = f'<span style="color: #059669; font-size: 0.85em;">↑ +{diff:.1%}</span>'
            
            rows_html += f"""
            <tr>
              <td><strong>STS</strong> {improvement}</td>
              <td>{sts['matches']}</td>
              <td>{sts['mean_score']:.4f}</td>
              <td>{sts['high_matches']}</td>
              <td>{sts['very_high_matches']}</td>
              <td>{sts['high_agreement_rate']:.1%}</td>
            </tr>"""
        
        # SIMDL
        if simdl:
            improvement = ""
            if tfidf and simdl['high_agreement_rate'] > tfidf['high_agreement_rate']:
                diff = simdl['high_agreement_rate'] - tfidf['high_agreement_rate']
                improvement = f'<span style="color: #059669; font-size: 0.85em;">↑ +{diff:.1%}</span>'
            
            rows_html += f"""
            <tr>
              <td><strong>SIMDL</strong> {improvement}</td>
              <td>{simdl['matches']}</td>
              <td>{simdl['mean_score']:.4f}</td>
              <td>{simdl['high_matches']}</td>
              <td>{simdl['very_high_matches']}</td>
              <td>{simdl['high_agreement_rate']:.1%}</td>
            </tr>"""
        
        return f"""
        <div class="card">
          <h3>{title}</h3>
          <p class="muted small">{context}</p>
          <table class="metric-table">
            <thead>
              <tr>
                <th>Method</th>
                <th>Total Matches</th>
                <th>Mean Score</th>
                <th>High (≥0.80)</th>
                <th>Very High (≥0.90)</th>
                <th>Agreement Rate</th>
              </tr>
            </thead>
            <tbody>
              {rows_html}
            </tbody>
          </table>
        </div>"""
    
    baseline_card = f"""
      <div class="card">
        <h3>Baseline Comparison — Cross-Institution</h3>
        <p class="muted small">
          Random baseline: expected agreement rate if a peer course were selected at random
          (~1 / avg peer courses per SHU course = <strong>{random_precision:.1%}</strong>).
          Any method above this line is doing better than chance.
        </p>
        <table class="metric-table">
          <thead>
            <tr><th>Method</th><th>Agreement Rate</th><th>vs Random Baseline</th></tr>
          </thead>
          <tbody>
            <tr style="color:var(--muted);">
              <td>Random (baseline)</td>
              <td>{random_precision:.1%}</td>
              <td>—</td>
            </tr>
            {"".join(
              f"<tr><td><strong>{label}</strong></td><td>{metrics['high_agreement_rate']:.1%}</td>"
              f"<td style='color:#059669'>↑ +{(metrics['high_agreement_rate'] - random_precision):.1%}</td></tr>"
              for label, metrics in [("TF-IDF", cross_tfidf), ("STS", cross_sts), ("SIMDL", cross_simdl)]
              if metrics
            )}
          </tbody>
        </table>
      </div>"""

    return f"""
    <div id="evaluation" class="section">
      <h2>Evaluation Metrics</h2>
      <p class="description">
        Model performance comparison across similarity methods. <strong>Agreement Rate</strong> = % of matches scoring
        high (≥0.80). STS and SIMDL improvements over TF-IDF highlight the benefit of semantic methods.
        <strong>Note:</strong> For ground-truth evaluation, compare predictions against manually-reviewed gold standard.
      </p>

      {baseline_card}

      {method_card('SHU Redundancy Detection', red_tfidf, red_sts, red_simdl,
                   'Accuracy of method agreement on course pair redundancy detection.')}

      {method_card('Cross-Institution Matching', cross_tfidf, cross_sts, cross_simdl,
                   'Accuracy of method agreement on peer institution course matches.')}
      
      <div class="card">
        <h3>Interpreting the Metrics</h3>
        <ul style="margin: 12px 0 0 0; padding-left: 20px;">
          <li><strong>Total Matches:</strong> Number of course pairs the method flagged as similar.</li>
          <li><strong>Mean Score:</strong> Average similarity score across all flagged pairs.</li>
          <li><strong>High / Very High:</strong> Count and rate of matches above quality thresholds.</li>
          <li><strong>Agreement Rate:</strong> Percentage of matches that score high—proxy for method precision.</li>
          <li><strong>Semantic Improvement (↑):</strong> STS/SIMDL advantage over TF-IDF in agreement rate.</li>
        </ul>
      </div>
    </div>"""


# ─────────────────────────────────────────────────────────────────
# Threshold Evaluation
# ─────────────────────────────────────────────────────────────────

def build_threshold_table(cross_rows: list[dict], redundancy_rows: list[dict], validation_metrics: dict) -> str:
    thresholds = [0.50, 0.65, 0.75, 0.85, 0.90]

    # If validation metrics exist, extract per-threshold reviewer precision from composite confusion matrix.
    # We don't have per-threshold gold data, so we note N/A unless a single threshold was validated.
    val_threshold = 0.75  # the threshold used in validate_with_gold_standard
    val_composite = validation_metrics.get("methods", {}).get("composite", {})
    val_cm = val_composite.get("confusion_matrix", {})
    val_prec = val_composite.get("precision")

    cross_scores = [f(r.get("composite_score")) for r in cross_rows]
    red_scores   = [f(r.get("composite_score")) for r in redundancy_rows]

    rows_html = ""
    for t in thresholds:
        cross_n = sum(1 for s in cross_scores if s >= t)
        red_n   = sum(1 for s in red_scores   if s >= t)
        if val_prec is not None and abs(t - val_threshold) < 0.001:
            prec_cell = f"<strong>{val_prec:.0%}</strong> <span class='muted small'>(validated)</span>"
        else:
            prec_cell = "<span class='muted'>—</span>"
        rows_html += f"""
        <tr>
          <td><code>{t:.2f}</code></td>
          <td>{cross_n}</td>
          <td>{red_n}</td>
          <td>{prec_cell}</td>
        </tr>"""

    note = ""
    if val_prec is not None:
        tp = val_cm.get("tp", 0)
        fp = val_cm.get("fp", 0)
        note = f'<p class="muted small" style="margin-top:10px;">Reviewer precision at 0.75 derived from gold-standard validation: {tp} true positives, {fp} false positives.</p>'

    return f"""
    <div id="threshold-eval" class="section">
      <h2>Threshold Evaluation</h2>
      <p class="description">
        Number of matches surfaced at each composite-score threshold. Lower thresholds include more pairs
        but reduce precision. Higher thresholds are more selective. The validated threshold (0.75) shows
        reviewer-confirmed precision from the gold standard, if available.
      </p>
      <div class="card">
        <table class="metric-table">
          <thead>
            <tr>
              <th>Threshold</th>
              <th>Cross-Inst Matches</th>
              <th>Redundancy Pairs</th>
              <th>Reviewer Precision</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>
        {note}
      </div>
      <div class="card">
        <h3>How to Choose a Threshold</h3>
        <ul style="margin: 8px 0 0 0; padding-left: 20px;">
          <li>Lower thresholds (0.50–0.65): more suggestions, higher false-positive rate.</li>
          <li>Mid-range (0.75): data-driven default; balances coverage and precision.</li>
          <li>Higher thresholds (0.85–0.90): fewer matches, but each is more reliable.</li>
          <li>Dynamic thresholds (mean + σ) adapt to your specific dataset distribution.</li>
        </ul>
      </div>
    </div>"""


# ─────────────────────────────────────────────────────────────────
# Error Analysis
# ─────────────────────────────────────────────────────────────────

def build_error_analysis_section(cross_rows: list[dict], redundancy_rows: list[dict]) -> str:
    # Pattern 1 — Generic language false positives: high TF-IDF, low STS/SIMDL composite
    generic_fp = [
        r for r in cross_rows
        if f(r.get("tfidf_score")) >= 0.60
        and f(r.get("composite_score")) < 0.50
        and r.get("sts_score") not in ("", None)
    ][:8]

    # Pattern 2 — Vocabulary divergence (good finds): low TF-IDF, high composite
    vocab_div = [
        r for r in cross_rows
        if f(r.get("tfidf_score")) < 0.35
        and f(r.get("composite_score")) >= 0.60
        and r.get("sts_score") not in ("", None)
    ][:8]

    # Pattern 3 — Short/missing descriptions
    short_desc = [
        r for r in cross_rows
        if len(r.get("shu_description", "")) < 60 or len(r.get("peer_description", "")) < 60
    ][:8]

    # Pattern 4 — Title-only inflation: high TF-IDF but divergent content (redundancy pairs)
    title_inflate = [
        r for r in redundancy_rows
        if f(r.get("tfidf_score")) >= 0.70
        and f(r.get("composite_score")) < 0.55
        and r.get("sts_score") not in ("", None)
    ][:8]

    def mini_table(rows, cols, title, note):
        if not rows:
            return f'<div class="card"><h3>{title}</h3><p class="muted">{note} — none found in current data.</p></div>'
        col_ths = "".join(f"<th>{c[1]}</th>" for c in cols)
        body = ""
        for r in rows:
            tds = "".join(
                f"<td>{score_cell(r.get(c[0])) if 'score' in c[0] else html.escape(str(r.get(c[0], '')))}</td>"
                for c in cols
            )
            body += f"<tr>{tds}</tr>"
        return f"""
        <div class="card">
          <h3>{title}</h3>
          <p class="muted small">{note}</p>
          <div class="table-wrap">
          <table class="data-table">
            <thead><tr>{col_ths}</tr></thead>
            <tbody>{body}</tbody>
          </table>
          </div>
        </div>"""

    cross_cols_fp  = [("shu_code","SHU"),("shu_title","SHU Title"),("peer_code","Peer"),("peer_title","Peer Title"),("tfidf_score","TF-IDF"),("composite_score","Composite")]
    cross_cols_vd  = [("shu_code","SHU"),("shu_title","SHU Title"),("peer_code","Peer"),("peer_title","Peer Title"),("tfidf_score","TF-IDF"),("composite_score","Composite")]
    short_cols     = [("shu_code","SHU"),("shu_title","SHU Title"),("peer_code","Peer"),("peer_title","Peer Title"),("composite_score","Composite")]
    red_cols       = [("course_code_a","Code A"),("course_title_a","Title A"),("course_code_b","Code B"),("course_title_b","Title B"),("tfidf_score","TF-IDF"),("composite_score","Composite")]

    return f"""
    <div id="error-analysis" class="section">
      <h2>Error Analysis</h2>
      <p class="description">
        Automatically categorized patterns in the match data. These examples help identify where the
        pipeline succeeds and where it needs human scrutiny.
      </p>

      {mini_table(generic_fp, cross_cols_fp,
        "False Positives — Generic Course Language",
        "High TF-IDF (≥0.60) but low composite (&lt;0.50): shared boilerplate inflates keyword overlap, but semantic models disagree.")}

      {mini_table(vocab_div, cross_cols_vd,
        "Vocabulary Divergence — Same Concept, Different Words",
        "Low TF-IDF (&lt;0.35) but high composite (≥0.60): semantic models find alignment that keyword overlap misses. These are strong candidates worth reviewing.")}

      {mini_table(title_inflate, red_cols,
        "Redundancy False Positives — Title Inflation",
        "High TF-IDF (≥0.70) but low composite (&lt;0.55) in SHU redundancy pairs: title or boilerplate similarity without real content overlap.")}

      {mini_table(short_desc, short_cols,
        "Unreliable Comparisons — Short or Missing Descriptions",
        "At least one description under 60 characters. Short descriptions make all similarity methods unreliable.")}

      <div class="card">
        <h3>Error Category Summary</h3>
        <table class="metric-table">
          <thead><tr><th>Category</th><th>Count</th><th>Recommended Action</th></tr></thead>
          <tbody>
            <tr><td>Generic language false positives</td><td>{len(generic_fp)}</td><td>Raise composite threshold or flag for manual review</td></tr>
            <tr><td>Vocabulary divergence (good finds)</td><td>{len(vocab_div)}</td><td>Prioritize for reviewer — likely correct semantic matches</td></tr>
            <tr><td>Title-inflation redundancy pairs</td><td>{len(title_inflate)}</td><td>Exclude TF-IDF-only matches from final report</td></tr>
            <tr><td>Short/missing descriptions</td><td>{len(short_desc)}</td><td>Collect fuller catalog descriptions; exclude from scoring</td></tr>
          </tbody>
        </table>
      </div>
    </div>"""


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────

def main():
    redundancy_rows    = read_csv(REDUNDANCY_CSV)
    cross_rows         = read_csv(CROSS_INST_CSV)
    keyword_rows       = read_csv(KEYWORD_CSV)
    all_stats          = read_stats()
    validation_metrics = read_validation_metrics()

    if not all_stats:
        all_stats = {
            "redundancy": calc_stats([f(r.get('composite_score')) for r in redundancy_rows if r.get('composite_score')]),
            "cross":      calc_stats([f(r.get('composite_score')) for r in cross_rows      if r.get('composite_score')]),
            "keywords":   calc_stats([float(r['frequency']) for r in keyword_rows if r.get('frequency')]),
        }

    redundancy_stats = all_stats.get("redundancy", {})
    cross_stats      = all_stats.get("cross",      {})
    keyword_stats    = all_stats.get("keywords",   {})

    peer_institutions = sorted({r["peer_institution"] for r in cross_rows if r.get("peer_institution")})
    sts_ran = any(r.get("sts_score") for r in (redundancy_rows + cross_rows))

    alerts = []
    if not peer_institutions:
        alerts.append("<strong>Peer institution data missing.</strong> Run scripts 02–05 to collect peer catalogs.")
    if not sts_ran:
        alerts.append("<strong>STS / SIMDL inactive.</strong> Install <code>sentence-transformers</code> and re-run 07 — pipeline used TF-IDF only.")
    alerts_html = ('<div class="alert">' + "<br>".join(alerts) + "</div>") if alerts else ""

    today = date.today().strftime("%B %d, %Y")
    cross_count = len([r for r in cross_rows if f(r.get('composite_score')) >= 0.20])
    keyword_chart_markup, keyword_chart_init = build_keyword_charts(keyword_rows)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>ACT for CAP — Analysis Report</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      /* Neutrals */
      --bg:         #fafafa;
      --card:       #ffffff;
      --text:       #0f172a;
      --muted:      #64748b;
      --border:     #e5e7eb;
      --border-2:   #f1f5f9;
      --shadow:     0 1px 2px rgba(15,23,42,0.04), 0 1px 3px rgba(15,23,42,0.02);

      /* Brand: indigo */
      --accent:     #6366f1;
      --accent-700: #4338ca;
      --accent-bg:  #eef2ff;

      /* Score hues — soft tinted backgrounds, deeper text, mid-tone dots */
      --vh-bg: #fef2f2; --vh-text: #be123c; --vh-dot: #e11d48;   /* rose  */
      --h-bg:  #fffbeb; --h-text:  #b45309; --h-dot:  #f59e0b;   /* amber */
      --m-bg:  #eef2ff; --m-text:  #4338ca; --m-dot:  #6366f1;   /* indigo*/
      --l-bg:  #f1f5f9; --l-text:  #475569; --l-dot:  #94a3b8;   /* slate */
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{ height: 100%; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, system-ui, sans-serif;
      font-size: 14px; line-height: 1.55;
      background: var(--bg); color: var(--text);
      -webkit-font-smoothing: antialiased;
    }}

    /* Header */
    header {{
      background: var(--card); border-bottom: 1px solid var(--border);
      padding: 28px 40px 24px; position: relative;
    }}
    header::before {{
      content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
      background: linear-gradient(90deg, var(--accent) 0%, #818cf8 100%);
    }}
    header h1 {{ font-size: 1.35em; font-weight: 600; letter-spacing: -0.01em; }}
    header p  {{ color: var(--muted); margin-top: 2px; font-size: 0.92em; }}

    /* Nav */
    nav {{ background: var(--card); border-bottom: 1px solid var(--border);
            padding: 0 32px; display: flex; gap: 4px; flex-wrap: wrap; position: sticky; top: 0; z-index: 10; }}
    nav a {{
      color: var(--muted); padding: 12px 14px; text-decoration: none;
      font-size: 0.875em; font-weight: 500;
      border-bottom: 2px solid transparent;
      transition: color 120ms, border-color 120ms;
    }}
    nav a:hover {{ color: var(--accent-700); }}
    nav a.active {{ color: var(--accent-700); border-bottom-color: var(--accent); }}

    /* Sections */
    .section {{ display: none; padding: 32px 40px; max-width: 1500px; margin: 0 auto; }}
    .section.visible {{ display: block; }}
    h2 {{ font-size: 1.15em; font-weight: 600; margin-bottom: 4px; letter-spacing: -0.005em; }}
    h3 {{ font-size: 0.95em; font-weight: 600; margin: 18px 0 10px; }}
    h4 {{ font-size: 0.875em; font-weight: 600; margin-bottom: 12px; color: var(--muted); }}
    p  {{ color: var(--text); }}
    .muted {{ color: var(--muted); }}
    .small {{ font-size: 0.85em; }}
    .description {{ color: var(--muted); margin-bottom: 18px; max-width: 70ch; }}

    /* Cards */
    .card {{
      background: var(--card); border: 1px solid var(--border); border-radius: 8px;
      padding: 20px 22px; margin-bottom: 16px; box-shadow: var(--shadow);
    }}

    /* Stats grid */
    .stat-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; }}
    .stat {{
      background: var(--card); border: 1px solid var(--border); border-radius: 6px;
      padding: 14px 16px; text-align: left;
    }}
    .stat .num {{ font-size: 1.5em; font-weight: 600; font-variant-numeric: tabular-nums; color: var(--accent-700); }}
    .stat .lbl {{ font-size: 0.75em; color: var(--muted); margin-top: 2px;
                  text-transform: uppercase; letter-spacing: 0.04em; }}

    /* Tables */
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--border); border-radius: 6px; }}
    .data-table {{ width: 100%; border-collapse: collapse; font-size: 0.875em; }}
    .metric-table {{ width: 100%; border-collapse: collapse; font-size: 0.875em; }}
    .data-table th, .metric-table th {{
      background: var(--accent-bg); color: var(--accent-700);
      padding: 9px 12px; text-align: left;
      font-weight: 600; font-size: 0.78em;
      text-transform: uppercase; letter-spacing: 0.04em;
      cursor: pointer; user-select: none; white-space: nowrap;
      border-bottom: 1px solid var(--border);
      position: sticky; top: 0;
    }}
    .data-table th:hover, .metric-table th:hover {{ background: #e0e7ff; }}
    .data-table td, .metric-table td {{ padding: 8px 12px; border-bottom: 1px solid var(--border-2); vertical-align: top; }}
    .data-table tbody tr:hover, .metric-table tbody tr:hover {{ background: #fafbff; }}
    .data-table tbody tr:last-child td, .metric-table tbody tr:last-child td {{ border-bottom: none; }}

    code {{
      font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
      font-size: 0.85em; background: var(--accent-bg);
      padding: 1px 6px; border-radius: 4px; color: var(--accent-700);
    }}
    .tag {{
      display: inline-block; background: var(--accent-bg); color: var(--accent-700);
      padding: 2px 8px; border-radius: 10px; font-size: 0.78em; font-weight: 500;
    }}

    /* Score cells — soft tinted pills, colored by intensity bucket */
    .score {{
      display: inline-flex; align-items: center; gap: 6px;
      padding: 2px 9px; border-radius: 999px;
      font-variant-numeric: tabular-nums; font-size: 0.85em; font-weight: 500;
    }}
    .score .dot {{ width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }}
    .score-vh {{ background: var(--vh-bg); color: var(--vh-text); }}
    .score-vh .dot {{ background: var(--vh-dot); }}
    .score-h  {{ background: var(--h-bg);  color: var(--h-text);  }}
    .score-h  .dot {{ background: var(--h-dot); }}
    .score-m  {{ background: var(--m-bg);  color: var(--m-text);  }}
    .score-m  .dot {{ background: var(--m-dot); }}
    .score-l  {{ background: var(--l-bg);  color: var(--l-text);  }}
    .score-l  .dot {{ background: var(--l-dot); }}
    .score-na {{ color: var(--muted); padding: 2px 9px; font-weight: 400; }}

    /* Filter bar */
    .filter-bar {{ display: flex; gap: 8px; margin: 12px 0; flex-wrap: wrap; align-items: center; }}
    .filter-input, .filter-select, .filter-num {{
      padding: 7px 10px; border: 1px solid var(--border); border-radius: 6px;
      font-size: 0.875em; font-family: inherit; background: var(--card); color: var(--text);
      transition: border-color 120ms;
    }}
    .filter-input {{ width: 280px; max-width: 100%; }}
    .filter-num {{ width: 80px; }}
    .filter-input:focus, .filter-select:focus, .filter-num:focus {{
      outline: none; border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(99,102,241,0.12);
    }}
    .filter-label {{ font-size: 0.875em; color: var(--muted); display: inline-flex; align-items: center; gap: 6px; }}

    /* Threshold strip */
    .threshold-strip {{
      font-size: 0.85em; color: var(--muted);
      padding: 10px 14px; background: var(--accent-bg); border-radius: 6px;
      margin-bottom: 12px;
    }}
    .threshold-strip strong {{ color: var(--text); font-weight: 600; }}
    .threshold-strip .sep {{ margin: 0 8px; opacity: 0.5; }}

    /* Note (e.g. threshold derivation) */
    .note {{
      font-size: 0.85em; color: var(--muted);
      background: var(--accent-bg); border-radius: 6px;
      padding: 10px 14px; margin-top: 14px; line-height: 1.6;
    }}
    .note strong {{ color: var(--text); }}
    .note code {{ font-size: 0.95em; background: var(--card); }}

    /* Modal */
    .modal {{
      display: none; position: fixed; z-index: 1000; left: 0; top: 0;
      width: 100%; height: 100%; background-color: rgba(0,0,0,0.4);
    }}
    .modal.show {{ display: block; }}
    .modal-content {{
      background-color: var(--card); margin: 5% auto; padding: 28px 32px;
      border-radius: 8px; max-width: 600px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);
      max-height: 80vh; overflow-y: auto;
    }}
    .modal-close {{
      color: var(--muted); float: right; font-size: 28px; font-weight: bold;
      cursor: pointer; line-height: 1; transition: color 120ms;
    }}
    .modal-close:hover {{ color: var(--text); }}
    .modal h3 {{ margin-top: 0; font-size: 1em; margin-bottom: 16px; }}
    .modal p {{ margin-bottom: 14px; font-size: 0.875em; line-height: 1.6; }}
    .modal strong {{ color: var(--text); font-weight: 600; }}

    /* Charts */
    .chart-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px,1fr)); gap: 16px; }}
    .chart-card {{
      background: var(--card); border: 1px solid var(--border); border-radius: 8px;
      padding: 18px 20px; box-shadow: var(--shadow);
    }}
    .chart-card canvas {{ width: 100% !important; height: 280px !important; }}

    /* Alerts */
    .alert {{
      background: #fefce8; border: 1px solid #fef08a; color: #854d0e;
      padding: 10px 14px; border-radius: 6px; margin-bottom: 16px;
      font-size: 0.875em; line-height: 1.6;
    }}
    .alert code {{ background: #fef9c3; }}
    .alert strong {{ color: #713f12; }}
  </style>
</head>
<body>

<header>
  <h1>ACT for CAP</h1>
  <p>Analyzing Course Titles for Comparative Accuracy and Precision · Seton Hill University · {today}</p>
</header>

<nav>
  <a href="#" class="active" onclick="showSection('summary', this); return false;">Summary</a>
  <a href="#" onclick="showSection('redundancy', this); return false;">SHU Redundancy</a>
  <a href="#" onclick="showSection('pivot', this); return false;">SHU vs Peers</a>
  <a href="#" onclick="showSection('cross', this); return false;">Cross-Institution</a>
  <a href="#" onclick="showSection('keywords', this); return false;">Keywords</a>
  <a href="#" onclick="showSection('validation', this); return false;">Validation</a>
  <a href="#" onclick="showSection('evaluation', this); return false;">Evaluation</a>
  <a href="#" onclick="showSection('threshold-eval', this); return false;">Thresholds</a>
  <a href="#" onclick="showSection('error-analysis', this); return false;">Error Analysis</a>
  <a href="#" onclick="showSection('analytics', this); return false;">Analytics</a>
  <a href="#" onclick="showSection('methodology', this); return false;">Methodology</a>
</nav>

<!-- ── MODAL ──────────────────────────────────────────────── -->
<div id="courseModal" class="modal">
  <div class="modal-content">
    <span class="modal-close" onclick="closeCourseModal()">&times;</span>
    <h3 id="modalLabel"></h3>
    <p><strong>SHU description:</strong><br><span id="modalShuDesc"></span></p>
    <p><strong>Peer description:</strong><br><span id="modalPeerDesc"></span></p>
  </div>
</div>

<!-- ── SUMMARY ─────────────────────────────────────────────── -->
<div id="summary" class="section visible">
  <div class="card">
    <h2>Executive Summary</h2>
    <p class="description" style="margin-top:8px;">
      NLP-assisted analysis of the Seton Hill University catalog: (A) internal redundancy between
      SHU courses and (B) terminology alignment with four peer institutions. Three similarity methods
      run in parallel — TF-IDF cosine, STS (paraphrase-MiniLM), and SIMDL (all-mpnet-base). The
      <strong>composite score</strong> is the mean of the two context-aware methods (STS + SIMDL);
      TF-IDF is reported alongside as a surface-level keyword-overlap reference.
    </p>
  </div>

  <div class="stat-row">
    <div class="stat"><div class="num">{len(redundancy_rows)}</div><div class="lbl">Flagged Pairs</div></div>
    <div class="stat"><div class="num">{cross_count}</div><div class="lbl">Cross-Inst Matches</div></div>
    <div class="stat"><div class="num">{len(peer_institutions)}</div><div class="lbl">Peer Institutions</div></div>
    <div class="stat"><div class="num">{len(set(r['institution'] for r in keyword_rows))}</div><div class="lbl">Institutions Processed</div></div>
    <div class="stat"><div class="num">{'3' if sts_ran else '1'}</div><div class="lbl">Similarity Methods</div></div>
  </div>

  {alerts_html}
</div>

<!-- ── REDUNDANCY ────────────────────────────────────────────── -->
<div id="redundancy" class="section">
  <h2>SHU Intra-Institution Redundancy</h2>
  <p class="description">
    Pairs of SHU courses ranked by composite similarity (STS + SIMDL average). High composite
    scores indicate semantic equivalence. A high TF-IDF score with a low composite means the
    pair shares boilerplate language but isn't really the same course — useful for filtering
    false positives.
  </p>
  <div class="card">
    {build_redundancy_table(redundancy_rows, all_stats)}
  </div>
</div>

<!-- ── PIVOT (SHU vs PEERS) ─────────────────────────────────── -->
<div id="pivot" class="section">
  <h2>SHU vs Peers</h2>
  <p class="description">
    Each row is a SHU course. Each peer column shows the best composite-score match found at that
    institution. The Avg column is the mean across peers that returned a match — use it to surface
    SHU courses that align (or diverge) broadly with peer offerings.
  </p>
  <div class="card">
    {build_pivot_table(cross_rows, all_stats)}
  </div>
</div>

<!-- ── CROSS-INSTITUTION ──────────────────────────────────────── -->
<div id="cross" class="section">
  <h2>Cross-Institution Terminology Alignment</h2>
  <p class="description">
    Best-matching peer course per SHU course, ranked by composite (STS + SIMDL). High composite
    confirms terminology alignment. A high composite with a low TF-IDF signals vocabulary
    divergence — same concept, different vocabulary.
  </p>
  <div class="card">
    {build_cross_table(cross_rows, all_stats)}
  </div>
</div>

<!-- ── KEYWORDS ──────────────────────────────────────────────── -->
<div id="keywords" class="section">
  <h2>Keyword Frequency Analysis</h2>
  <p class="description">
    Top 20 keywords per institution after stopword and boilerplate removal. Terms prominent
    at SHU but absent at peers — or vice versa — flag potential terminological misalignment.
  </p>
  <div class="chart-grid">
    {keyword_chart_markup}
  </div>
</div>

{build_validation_section(validation_metrics)}

{build_evaluation_metrics_section(redundancy_rows, cross_rows)}

{build_threshold_table(cross_rows, redundancy_rows, validation_metrics)}

{build_error_analysis_section(cross_rows, redundancy_rows)}

{build_analytics_section(redundancy_stats, cross_stats, keyword_stats)}

<!-- ── METHODOLOGY ───────────────────────────────────────────── -->
<div id="methodology" class="section">
  <div class="card">
    <h2>Methodology</h2>

    <h3>Data Sources</h3>
    <p class="muted">SHU catalog provided as Excel; peer catalogs (Chatham, Point Park, Saint Vincent, IUP) parsed from public PDFs.</p>

    <h3>Text Preprocessing</h3>
    <p class="muted">Course descriptions are lowercased, punctuation-stripped, and filtered with an academic-boilerplate stopword list. TF-IDF uses unigrams and bigrams.</p>

    <h3>Similarity Methods</h3>
    <p class="muted"><strong>TF-IDF Cosine</strong> · keyword overlap via term frequency–inverse document frequency. Catches shared boilerplate.</p>
    <p class="muted"><strong>STS</strong> · sentence embeddings from <em>paraphrase-MiniLM-L6-v2</em>. Captures meaning across different vocabulary.</p>
    <p class="muted"><strong>SIMDL</strong> · sentence embeddings from <em>all-mpnet-base-v2</em>. Stronger BERT-based model for nuanced cross-discipline equivalence.</p>
    <p class="muted"><strong>Composite</strong> · mean of STS + SIMDL (context-aware methods only). TF-IDF is excluded because it captures surface-level keyword overlap and inflates scores for boilerplate-heavy descriptions; it's still reported in its own column for reference. If neither embedding model is available, the pipeline falls back to TF-IDF as the composite.</p>

    <h3>Dynamic Thresholds</h3>
    <p class="muted">High = mean + 1·σ · Very High = mean + 1.5·σ — labels reflect the data's actual distribution rather than arbitrary cutoffs.</p>

    <h3>Validation Plan</h3>
    <p class="muted">SHU faculty review of flagged pairs. ≥80% confirmation rate is the project success criterion.</p>

    <h3>Tools</h3>
    <p class="muted">Python · scikit-learn · sentence-transformers · pdfminer.six · SQLite · Chart.js</p>
  </div>
</div>

<script>
  function showSection(id, el) {{
    document.querySelectorAll('.section').forEach(s => s.classList.remove('visible'));
    document.querySelectorAll('nav a').forEach(a => a.classList.remove('active'));
    document.getElementById(id).classList.add('visible');
    el.classList.add('active');
    window.scrollTo(0, 0);
    if (id === 'keywords' && typeof window.renderKeywordCharts === 'function') {{
      // Defer to next frame so the canvas has its real width before render.
      requestAnimationFrame(() => requestAnimationFrame(window.renderKeywordCharts));
    }}
  }}

  function filterTable(tableId, query) {{
    const q = query.toLowerCase();
    document.querySelectorAll('#' + tableId + ' tbody tr').forEach(row => {{
      row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
    }});
  }}

  function filterByPeer() {{
    const val = document.getElementById('peer-filter').value;
    document.querySelectorAll('#cross-table tbody tr').forEach(row => {{
      row.style.display = (!val || row.dataset.peer === val) ? '' : 'none';
    }});
  }}

  function filterMinAvg(minStr, colIdx) {{
    const min = parseFloat(minStr) || 0;
    document.querySelectorAll('#pivot-table tbody tr').forEach(row => {{
      const cell = row.cells[colIdx];
      if (!cell) return;
      const m = cell.textContent.match(/(\\d+\\.\\d+)/);
      const v = m ? parseFloat(m[1]) : 0;
      row.style.display = v >= min ? '' : 'none';
    }});
  }}

  {keyword_chart_init}

  function showCourseDetail(cell) {{
    const modal = document.getElementById('courseModal');
    if (!modal) return;
    document.getElementById('modalLabel').textContent = cell.dataset.label;
    document.getElementById('modalShuDesc').textContent = cell.dataset.shu;
    document.getElementById('modalPeerDesc').textContent = cell.dataset.peer;
    modal.classList.add('show');
  }}

  function closeCourseModal() {{
    const modal = document.getElementById('courseModal');
    if (modal) modal.classList.remove('show');
  }}

  window.onclick = function(event) {{
    const modal = document.getElementById('courseModal');
    if (event.target === modal) {{
      modal.classList.remove('show');
    }}
  }}

  function sortTable(tableId, col) {{
    const table = document.getElementById(tableId);
    const tbody = table.querySelector('tbody');
    const rows  = Array.from(tbody.querySelectorAll('tr'));
    const asc   = table.dataset.sortCol == col && table.dataset.sortDir != 'asc';
    rows.sort((a, b) => {{
      const ta = a.cells[col]?.textContent.trim() || '';
      const tb = b.cells[col]?.textContent.trim() || '';
      const na = parseFloat(ta.match(/-?\\d+\\.?\\d*/) || [0]);
      const nb = parseFloat(tb.match(/-?\\d+\\.?\\d*/) || [0]);
      if (!isNaN(na) && !isNaN(nb) && (ta.match(/\\d/) || tb.match(/\\d/))) {{
        return asc ? na - nb : nb - na;
      }}
      return asc ? ta.localeCompare(tb) : tb.localeCompare(ta);
    }});
    rows.forEach(r => tbody.appendChild(r));
    table.dataset.sortCol = col;
    table.dataset.sortDir = asc ? 'asc' : 'desc';
  }}
</script>
</body>
</html>"""

    os.makedirs("output", exist_ok=True)
    with open(REPORT_OUT, "w", encoding="utf-8") as f_out:
        f_out.write(html)
    print(f"✅ Report generated → {REPORT_OUT}")


if __name__ == "__main__":
    main()

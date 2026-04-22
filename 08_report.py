"""
08_report.py
Generates a self-contained HTML report from the analysis outputs.
  output/ACT_for_CAP_Report.html

The report includes:
  - Executive summary
  - SHU redundant course pairs table (sortable, all 3 similarity scores)
  - Cross-institution matches table (sortable, filterable, all 3 scores)
  - Keyword frequency charts
  - Analytics section (mean, median, std dev — drives dynamic badge thresholds)
  - Methodology
"""

import csv, json, os, re
from datetime import date

REDUNDANCY_CSV  = "output/shu_redundant_pairs.csv"
CROSS_INST_CSV  = "output/cross_institution_matches.csv"
KEYWORD_CSV     = "output/keyword_frequencies.csv"
STATS_JSON      = "output/similarity_stats.json"
REPORT_OUT      = "output/ACT_for_CAP_Report.html"


def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_stats() -> dict:
    """Load stats from 07_analyze.py output. Falls back to fixed thresholds."""
    if not os.path.exists(STATS_JSON):
        return {}
    with open(STATS_JSON) as f:
        return json.load(f)


def score_badge(score, high_threshold=0.80, very_high_threshold=0.90) -> str:
    """
    Dynamically bucketed badge.
    Thresholds are driven by mean+stdev from the stats JSON when available,
    otherwise fall back to fixed values.
    """
    if score == "" or score is None:
        return '<span style="background:#bdc3c7;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.8em;">N/A</span>'
    score = float(score)
    if score >= very_high_threshold:
        color, label = "#c0392b", "Very High"
    elif score >= high_threshold:
        color, label = "#e67e22", "High"
    elif score >= 0.75:
        color, label = "#f1c40f", "Moderate"
    else:
        color, label = "#27ae60", "Low"
    return (f'<span style="background:{color};color:#fff;padding:2px 8px;'
            f'border-radius:4px;font-size:0.8em;font-weight:bold;">{label} ({score:.3f})</span>')


def method_label(key: str) -> str:
    return {"tfidf_score": "TF-IDF", "sts_score": "STS", "simdl_score": "SIMDL",
            "composite_score": "Composite"}.get(key, key)


def build_redundancy_table(rows: list[dict], stats: dict) -> str:
    if not rows:
        return "<p><em>No redundant pairs found (or SHU data not yet processed).</em></p>"

    # Determine dynamic thresholds from stats
    r_stats = stats.get("redundancy", {})
    high_t      = r_stats.get("bucket_high",      0.80)
    very_high_t = r_stats.get("bucket_very_high", 0.90)

    # Detect which score columns exist in this CSV
    sample = rows[0]
    has_sts   = "sts_score"   in sample and any(r.get("sts_score")   for r in rows)
    has_simdl = "simdl_score" in sample and any(r.get("simdl_score") for r in rows)

    sts_th   = "<th>STS Score</th>"   if has_sts   else ""
    simdl_th = "<th>SIMDL Score</th>" if has_simdl else ""

    html = f"""
    <div style="background:#eaf4fb;border-left:4px solid #2980b9;padding:10px 14px;
                border-radius:4px;margin-bottom:14px;font-size:0.88em;">
      <strong>Dynamic thresholds</strong> (set from distribution stats):
      High ≥ {high_t:.3f} &nbsp;|&nbsp; Very High ≥ {very_high_t:.3f}
    </div>
    <p><strong>{len(rows)}</strong> course pairs flagged (composite score ≥ {0.75}).</p>
    <input type="text" id="redundancy-search"
           placeholder="Filter by course code or title..."
           oninput="filterTable('redundancy-table', this.value)"
           style="margin-bottom:10px;padding:6px 10px;width:300px;border:1px solid #ccc;border-radius:4px;">
    <div style="overflow-x:auto;">
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
          <th onclick="sortTable('redundancy-table',{7 + has_sts + has_simdl})">Composite ▼</th>
        </tr>
      </thead>
      <tbody>
    """
    for r in rows:
        sts_td   = f"<td>{score_badge(r.get('sts_score',''),   high_t, very_high_t)}</td>" if has_sts   else ""
        simdl_td = f"<td>{score_badge(r.get('simdl_score',''), high_t, very_high_t)}</td>" if has_simdl else ""
        html += f"""
        <tr>
          <td><code>{r['course_code_a']}</code></td>
          <td>{r['course_title_a']}</td>
          <td><span class="dept-badge">{r['dept_a']}</span></td>
          <td><code>{r['course_code_b']}</code></td>
          <td>{r['course_title_b']}</td>
          <td><span class="dept-badge">{r['dept_b']}</span></td>
          <td>{score_badge(r.get('tfidf_score', r.get('similarity_score','')), high_t, very_high_t)}</td>
          {sts_td}
          {simdl_td}
          <td>{score_badge(r.get('composite_score', r.get('similarity_score','')), high_t, very_high_t)}</td>
        </tr>
        """
    html += "</tbody></table></div>"
    return html


def build_cross_table(rows: list[dict], stats: dict) -> str:
    if not rows:
        return "<p><em>No peer institution data available yet. Run scripts 02–05 first.</em></p>"

    rows = [r for r in rows if float(r.get("composite_score", r.get("similarity_score", 0)) or 0) >= 0.20]
    if not rows:
        return "<p><em>No cross-institution matches above threshold.</em></p>"

    c_stats     = stats.get("cross", {})
    high_t      = c_stats.get("bucket_high",      0.80)
    very_high_t = c_stats.get("bucket_very_high", 0.90)

    sample    = rows[0]
    has_sts   = "sts_score"   in sample and any(r.get("sts_score")   for r in rows)
    has_simdl = "simdl_score" in sample and any(r.get("simdl_score") for r in rows)

    peers     = sorted(set(r["peer_institution"] for r in rows))
    peer_opts = "".join(f'<option value="{p}">{p}</option>' for p in peers)

    sts_th   = "<th>STS</th>"   if has_sts   else ""
    simdl_th = "<th>SIMDL</th>" if has_simdl else ""

    html = f"""
    <div style="background:#eaf4fb;border-left:4px solid #2980b9;padding:10px 14px;
                border-radius:4px;margin-bottom:14px;font-size:0.88em;">
      <strong>Dynamic thresholds:</strong>
      High ≥ {high_t:.3f} &nbsp;|&nbsp; Very High ≥ {very_high_t:.3f}
    </div>
    <p><strong>{len(rows)}</strong> SHU ↔ Peer course matches found.</p>
    <div style="display:flex;gap:10px;margin-bottom:10px;flex-wrap:wrap;">
      <input type="text" id="cross-search"
             placeholder="Filter by code or title..."
             oninput="filterTable('cross-table', this.value)"
             style="padding:6px 10px;width:260px;border:1px solid #ccc;border-radius:4px;">
      <select id="peer-filter" onchange="filterByPeer()"
              style="padding:6px 10px;border:1px solid #ccc;border-radius:4px;">
        <option value="">All Peers</option>
        {peer_opts}
      </select>
    </div>
    <div style="overflow-x:auto;">
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
          <th>Composite ▼</th>
        </tr>
      </thead>
      <tbody>
    """
    for r in rows[:500]:
        sts_td   = f"<td>{score_badge(r.get('sts_score',''),   high_t, very_high_t)}</td>" if has_sts   else ""
        simdl_td = f"<td>{score_badge(r.get('simdl_score',''), high_t, very_high_t)}</td>" if has_simdl else ""
        html += f"""
        <tr data-peer="{r['peer_institution']}">
          <td><code>{r['shu_code']}</code></td>
          <td>{r['shu_title']}</td>
          <td><small>{r['peer_institution']}</small></td>
          <td><code>{r['peer_code']}</code></td>
          <td>{r['peer_title']}</td>
          <td>{score_badge(r.get('tfidf_score', r.get('similarity_score','')), high_t, very_high_t)}</td>
          {sts_td}
          {simdl_td}
          <td>{score_badge(r.get('composite_score', r.get('similarity_score','')), high_t, very_high_t)}</td>
        </tr>
        """
    html += "</tbody></table></div>"
    if len(rows) > 500:
        html += f"<p><em>Showing top 500 of {len(rows)} matches. See CSV for full results.</em></p>"
    return html


def build_keyword_chart_data(rows: list[dict]) -> str:
    """Build Chart.js data as JSON for top keywords per institution."""
    by_inst: dict[str, list] = {}
    for r in rows:
        inst = r["institution"]
        if inst not in by_inst:
            by_inst[inst] = []
        by_inst[inst].append({"keyword": r["keyword"], "frequency": int(r["frequency"])})

    charts = []
    colors = ["#3498db", "#e74c3c", "#2ecc71", "#9b59b6", "#f39c12"]
    for idx, (inst, kws) in enumerate(by_inst.items()):
        top      = kws[:20]
        labels   = json.dumps([k["keyword"] for k in top])
        data     = json.dumps([k["frequency"] for k in top])
        color    = colors[idx % len(colors)]
        chart_id = f"chart_{idx}"
        charts.append(f"""
        <div class="chart-box">
          <h4>{inst}</h4>
          <canvas id="{chart_id}" height="220"></canvas>
          <script>
            new Chart(document.getElementById('{chart_id}'), {{
              type: 'bar',
              data: {{
                labels: {labels},
                datasets: [{{
                  label: 'Frequency',
                  data: {data},
                  backgroundColor: '{color}88',
                  borderColor: '{color}',
                  borderWidth: 1
                }}]
              }},
              options: {{
                responsive: true,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{ y: {{ beginAtZero: true }} }}
              }}
            }});
          </script>
        </div>
        """)
    return "\n".join(charts)


def calc_stats(values: list[float]) -> dict:
    """Compute descriptive stats. Used in Analytics section."""
    if not values:
        return {}
    import statistics
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


def build_analytics_section(redundancy_stats: dict, cross_stats: dict, keyword_stats: dict) -> str:
    """
    Your analytics section — mean, median, std dev per analysis.
    Stats also explain how the bucket thresholds in the tables above were derived.
    """
    def stat_card(title: str, stats: dict, value_label: str, explain: str = ""):
        if not stats:
            return f"<div class='card'><h3>{title}</h3><p><em>No data available.</em></p></div>"

        bucket_info = ""
        if "bucket_high" in stats:
            bucket_info = f"""
            <div style="background:#f0f4ff;border-left:4px solid #2980b9;padding:10px 14px;
                        border-radius:4px;margin-top:14px;font-size:0.87em;line-height:1.6;">
              <strong>How thresholds are set from these stats:</strong><br>
              <em>High</em> badge threshold = Mean + 1×StdDev = <strong>{stats['bucket_high']:.4f}</strong><br>
              <em>Very High</em> badge threshold = Mean + 1.5×StdDev = <strong>{stats['bucket_very_high']:.4f}</strong><br>
              This means a course pair must score in roughly the top 16% to earn a High badge,
              and the top 7% for Very High — rather than using fixed arbitrary cutoffs.
            </div>"""

        return f"""
        <div class='card'>
          <h3>{title}</h3>
          {f"<p style='color:#555;font-size:0.9em;margin-bottom:12px;'>{explain}</p>" if explain else ""}
          <div class='stat-row'>
            <div class='stat'><div class='num'>{stats['count']}</div><div class='lbl'>Count</div></div>
            <div class='stat'><div class='num'>{stats['mean']:.4f}</div><div class='lbl'>Mean {value_label}</div></div>
            <div class='stat'><div class='num'>{stats['median']:.4f}</div><div class='lbl'>Median {value_label}</div></div>
            <div class='stat'><div class='num'>{stats['stddev']:.4f}</div><div class='lbl'>Std Dev</div></div>
            <div class='stat'><div class='num'>{stats['min']:.4f}</div><div class='lbl'>Min</div></div>
            <div class='stat'><div class='num'>{stats['max']:.4f}</div><div class='lbl'>Max</div></div>
          </div>
          {bucket_info}
        </div>
        """

    return f"""
    <div id='analytics' class='section'>
      <h2>Descriptive Analytics</h2>
      <p style='margin-bottom:16px;line-height:1.6;color:#555;'>
        Summary statistics across all similarity scores and keyword frequencies.
        The mean and standard deviation from each distribution are used to set
        <strong>data-driven bucket thresholds</strong> for the High and Very High badges
        in the Redundancy and Cross-Institution tables — so the labels reflect the actual
        shape of this dataset rather than arbitrary fixed cutoffs.
      </p>
      {stat_card(
          'SHU Redundancy — Composite Similarity',
          redundancy_stats, 'score',
          'Distribution of composite scores across all flagged SHU course pairs. '
          'A high standard deviation means scores are spread out; a low one means most pairs cluster near the mean.'
      )}
      {stat_card(
          'Cross-Institution — Composite Similarity',
          cross_stats, 'score',
          'Distribution of composite scores for the best SHU↔Peer match per course. '
          'Low mean scores here indicate broad vocabulary divergence between SHU and its peers.'
      )}
      {stat_card(
          'Keyword Frequency',
          keyword_stats, 'frequency',
          'Distribution of keyword counts across all institutions after stopword removal. '
          'High std dev signals that a small number of terms dominate — useful for spotting overused catalog language.'
      )}
    </div>
    """


def main():
    redundancy_rows = read_csv(REDUNDANCY_CSV)
    cross_rows      = read_csv(CROSS_INST_CSV)
    keyword_rows    = read_csv(KEYWORD_CSV)
    all_stats       = read_stats()

    # Fall back to computing stats locally if JSON not present
    if not all_stats:
        redundancy_scores = [float(r.get('composite_score', r.get('similarity_score', 0)))
                             for r in redundancy_rows if r.get('composite_score') or r.get('similarity_score')]
        cross_scores      = [float(r.get('composite_score', r.get('similarity_score', 0)))
                             for r in cross_rows if r.get('composite_score') or r.get('similarity_score')]
        keyword_freqs     = [int(r['frequency']) for r in keyword_rows if r.get('frequency')]
        all_stats = {
            "redundancy": calc_stats(redundancy_scores),
            "cross":      calc_stats(cross_scores),
            "keywords":   calc_stats([float(f) for f in keyword_freqs]),
        }

    redundancy_stats = all_stats.get("redundancy", {})
    cross_stats      = all_stats.get("cross",      {})
    keyword_stats    = all_stats.get("keywords",   {})

    today = date.today().strftime("%B %d, %Y")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>ACT for CAP – Analysis Report</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f5f6fa; color: #2c3e50; }}
    header {{ background: #1a252f; color: #fff; padding: 28px 40px; }}
    header h1 {{ font-size: 1.8em; font-weight: 700; }}
    header p  {{ font-size: 0.95em; opacity: 0.75; margin-top: 4px; }}
    nav {{ background: #2c3e50; display: flex; gap: 0; flex-wrap: wrap; }}
    nav a {{ color: #ecf0f1; padding: 14px 24px; text-decoration: none; font-size: 0.9em;
             border-bottom: 3px solid transparent; transition: 0.2s; }}
    nav a:hover, nav a.active {{ border-bottom-color: #3498db; background: #34495e; }}
    .section {{ display: none; padding: 32px 40px; max-width: 1400px; margin: 0 auto; }}
    .section.visible {{ display: block; }}
    h2 {{ font-size: 1.4em; margin-bottom: 8px; color: #1a252f; }}
    h3 {{ font-size: 1.1em; margin: 24px 0 10px; color: #2980b9; }}
    .card {{ background: #fff; border-radius: 8px; padding: 20px 24px;
             box-shadow: 0 2px 8px rgba(0,0,0,0.07); margin-bottom: 20px; }}
    .stat-row {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }}
    .stat {{ background: #fff; border-radius: 8px; padding: 18px 24px;
             box-shadow: 0 2px 8px rgba(0,0,0,0.07); flex: 1; min-width: 140px; text-align: center; }}
    .stat .num {{ font-size: 2em; font-weight: 700; color: #2980b9; }}
    .stat .lbl {{ font-size: 0.8em; color: #7f8c8d; margin-top: 4px; }}
    .data-table {{ width: 100%; border-collapse: collapse; font-size: 0.85em; min-width: 600px; }}
    .data-table th {{ background: #2c3e50; color: #fff; padding: 10px 12px;
                      text-align: left; cursor: pointer; user-select: none; white-space: nowrap; }}
    .data-table th:hover {{ background: #34495e; }}
    .data-table td {{ padding: 8px 10px; border-bottom: 1px solid #ecf0f1; vertical-align: top; }}
    .data-table tr:nth-child(even) {{ background: #f8f9fa; }}
    .data-table tr:hover {{ background: #eaf4fb; }}
    code {{ background: #eef; color: #2980b9; padding: 1px 5px;
            border-radius: 3px; font-family: 'Courier New', monospace; }}
    .dept-badge {{ background: #dfe6e9; color: #2c3e50; padding: 2px 7px;
                   border-radius: 10px; font-size: 0.8em; font-weight: bold; }}
    .chart-box {{ background: #fff; border-radius: 8px; padding: 20px;
                  box-shadow: 0 2px 8px rgba(0,0,0,0.07); margin-bottom: 20px; }}
    .chart-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(380px,1fr)); gap: 20px; }}
    .alert {{ background: #fef9e7; border-left: 4px solid #f39c12;
              padding: 14px 18px; border-radius: 4px; margin-bottom: 16px; font-size: 0.9em; }}
  </style>
</head>
<body>

<header>
  <h1>ACT for CAP — Analyzing Course Titles for Comparative Accuracy and Precision</h1>
  <p>Seton Hill University · Capstone Project · Generated {today}</p>
</header>

<nav>
  <a href="#" class="active" onclick="showSection('summary', this)">Summary</a>
  <a href="#" onclick="showSection('redundancy', this)">SHU Redundancy</a>
  <a href="#" onclick="showSection('cross', this)">Cross-Institution</a>
  <a href="#" onclick="showSection('keywords', this)">Keywords</a>
  <a href="#" onclick="showSection('analytics', this)">Analytics</a>
  <a href="#" onclick="showSection('methodology', this)">Methodology</a>
</nav>

<!-- ── SUMMARY ─────────────────────────────────────────────── -->
<div id="summary" class="section visible">
  <div class="card">
    <h2>Executive Summary</h2>
    <p style="margin-top:10px;line-height:1.7;">
      This report presents the results of an NLP-assisted analysis of Seton Hill University's
      course catalog, examining (A) internal keyword redundancy between courses and
      (B) terminology alignment with four peer institutions. Three similarity methods are used
      in parallel: <strong>TF-IDF cosine</strong> (keyword overlap),
      <strong>STS</strong> (semantic text similarity via sentence-transformers), and
      <strong>SIMDL</strong> (deep semantic similarity via BERT embeddings).
      A composite score across all available methods drives the final ranking and badge thresholds.
    </p>
  </div>

  <div class="stat-row">
    <div class="stat">
      <div class="num">{len(redundancy_rows)}</div>
      <div class="lbl">SHU Flagged Pairs</div>
    </div>
    <div class="stat">
      <div class="num">{len([r for r in cross_rows if float(r.get('composite_score', r.get('similarity_score', 0)) or 0) >= 0.20])}</div>
      <div class="lbl">Cross-Institution Matches</div>
    </div>
    <div class="stat">
      <div class="num">{len(set(r['peer_institution'] for r in cross_rows)) if cross_rows else 0}</div>
      <div class="lbl">Peer Institutions</div>
    </div>
    <div class="stat">
      <div class="num">{len(set(r['institution'] for r in keyword_rows))}</div>
      <div class="lbl">Institutions Processed</div>
    </div>
    <div class="stat">
      <div class="num">{'3' if all_stats.get('redundancy') else '1'}</div>
      <div class="lbl">Similarity Methods</div>
    </div>
  </div>

  <div class="alert">
    <strong>⚠ Peer Institution Data:</strong> Cross-institution comparison requires running
    scripts 02–05 to collect peer catalog data. SHU analysis runs on the provided catalog only.
    <br><br>
    <strong>⚠ STS / SIMDL:</strong> These methods require
    <code>pip install sentence-transformers</code>. If not installed, the pipeline runs
    in TF-IDF-only mode and STS/SIMDL columns will show N/A.
  </div>
</div>

<!-- ── REDUNDANCY ────────────────────────────────────────────── -->
<div id="redundancy" class="section">
  <h2>SHU Intra-Institution Redundancy</h2>
  <div class="card">
    <p style="margin-bottom:16px;line-height:1.6;">
      Pairs of SHU courses with high composite similarity across TF-IDF, STS, and SIMDL methods.
      Pairs scoring high on <em>all three</em> methods are almost certainly redundant.
      Pairs scoring high on TF-IDF but low on STS/SIMDL may share boilerplate language
      without being semantically equivalent — useful for filtering false positives.
      <strong>These pairs are candidates for stakeholder review.</strong>
    </p>
    {build_redundancy_table(redundancy_rows, all_stats)}
  </div>
</div>

<!-- ── CROSS-INSTITUTION ──────────────────────────────────────── -->
<div id="cross" class="section">
  <h2>Cross-Institution Terminology Alignment</h2>
  <div class="card">
    <p style="margin-bottom:16px;line-height:1.6;">
      For each SHU course, the best-matching course at each peer institution is shown.
      <strong>High composite scores</strong> confirm terminology alignment.
      <strong>Low composite scores</strong> for semantically equivalent courses (high SIMDL,
      low TF-IDF) signal vocabulary divergence — different words for the same concept —
      which may complicate transfer credit evaluation.
    </p>
    {build_cross_table(cross_rows, all_stats)}
  </div>
</div>

<!-- ── KEYWORDS ──────────────────────────────────────────────── -->
<div id="keywords" class="section">
  <h2>Keyword Frequency Analysis</h2>
  <p style="margin-bottom:20px;color:#555;line-height:1.6;">
    Top 20 keywords per institution after stopword and boilerplate removal.
    Terms prominent at SHU but absent at peers (or vice versa) signal potential
    terminological misalignment. Note: domain-specific keyword grouping by
    discipline is a planned next step to make these charts more targeted.
  </p>
  <div class="chart-grid">
    {build_keyword_chart_data(keyword_rows) or '<p><em>No keyword data available yet.</em></p>'}
  </div>
</div>

{build_analytics_section(redundancy_stats, cross_stats, keyword_stats)}

<!-- ── METHODOLOGY ───────────────────────────────────────────── -->
<div id="methodology" class="section">
  <div class="card">
    <h2>Methodology</h2>
    <h3>Data Sources</h3>
    <p>SHU catalog provided as Excel (2,543 courses). All four peer catalogs are publicly
    available PDFs: Chatham University, Point Park University, Saint Vincent College,
    and Indiana University of Pennsylvania.</p>

    <h3>Text Preprocessing</h3>
    <p>Course descriptions are lowercased, punctuation-stripped, and filtered using an
    expanded academic boilerplate stopword list (catalog structure words, generic verbs,
    and filler descriptors). TF-IDF uses unigrams and bigrams.</p>

    <h3>Similarity Methods</h3>
    <p><strong>TF-IDF Cosine:</strong> Term frequency–inverse document frequency vectors
    compared with cosine similarity. Fast, keyword-level. Good at catching shared boilerplate.</p>
    <p><strong>STS (Semantic Text Similarity):</strong> Sentence embeddings from
    <em>paraphrase-MiniLM-L6-v2</em> via sentence-transformers. Captures meaning even when
    different words are used. Runs locally, no GPU or paid API required.</p>
    <p><strong>SIMDL (Deep Semantic Similarity):</strong> Sentence embeddings from
    <em>all-mpnet-base-v2</em>, a stronger BERT-based model. Better at nuanced equivalence
    across disciplines. Slower but more precise than STS.</p>
    <p><strong>Composite Score:</strong> Simple mean of all available method scores per pair.
    Used for final ranking and badge threshold calculation.</p>

    <h3>Dynamic Thresholds</h3>
    <p>Badge thresholds (High, Very High) are set using the mean and standard deviation
    of the composite score distribution: High = mean + 1×StdDev, Very High = mean + 1.5×StdDev.
    This ensures labels reflect the actual shape of the data rather than arbitrary fixed cutoffs.</p>

    <h3>Validation Plan</h3>
    <p>Flagged pairs will be reviewed by an SHU faculty member or curriculum administrator.
    At least 80% of flagged pairs should be confirmed as genuinely redundant or ambiguous
    to meet the project success criteria.</p>

    <h3>Tools</h3>
    <p>Python · scikit-learn (TF-IDF, cosine similarity) · sentence-transformers (STS, SIMDL) ·
    pdfminer.six · SQLite · Chart.js</p>
  </div>
</div>

<script>
  function showSection(id, el) {{
    document.querySelectorAll('.section').forEach(s => s.classList.remove('visible'));
    document.querySelectorAll('nav a').forEach(a => a.classList.remove('active'));
    document.getElementById(id).classList.add('visible');
    el.classList.add('active');
    event.preventDefault();
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

  function sortTable(tableId, col) {{
    const table = document.getElementById(tableId);
    const tbody = table.querySelector('tbody');
    const rows  = Array.from(tbody.querySelectorAll('tr'));
    const asc   = table.dataset.sortCol == col && table.dataset.sortDir != 'asc';
    rows.sort((a, b) => {{
      const ta = a.cells[col]?.textContent.trim() || '';
      const tb = b.cells[col]?.textContent.trim() || '';
      const na = parseFloat(ta), nb = parseFloat(tb);
      if (!isNaN(na) && !isNaN(nb)) return asc ? na - nb : nb - na;
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
    with open(REPORT_OUT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Report generated → {REPORT_OUT}")


if __name__ == "__main__":
    main()
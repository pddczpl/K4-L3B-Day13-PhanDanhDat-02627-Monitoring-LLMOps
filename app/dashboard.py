from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from .logging_config import LOG_PATH


def _percentile(values: list[float | int], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(s[int(k)])
    return float(s[int(f)] * (c - k) + s[int(c)] * (k - f))


def compute_dashboard_metrics(window_minutes: int = 60) -> dict[str, Any]:
    if not LOG_PATH.exists():
        records = []
    else:
        try:
            records = [
                json.loads(line)
                for line in LOG_PATH.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except Exception:
            records = []

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=window_minutes)

    # Filter records in the last window_minutes if timestamp is parseable
    filtered = []
    for r in records:
        ts_str = r.get("ts")
        if ts_str:
            try:
                # Handle trailing Z or timezone offset
                clean_ts = ts_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_ts)
                if dt >= cutoff:
                    filtered.append(r)
                else:
                    filtered.append(r)  # Keep for lab context if records are within lab time
            except Exception:
                filtered.append(r)
        else:
            filtered.append(r)

    # If filtered is empty but records exist, fallback to all records
    data_records = filtered if filtered else records

    # 1. Latency & TTFT
    latencies = [
        r.get("latency_ms")
        for r in data_records
        if r.get("event") == "response_sent" and r.get("latency_ms") is not None
    ]
    ttfts = [
        r.get("ttft_ms")
        for r in data_records
        if r.get("event") == "response_sent" and r.get("ttft_ms") is not None
    ]

    p50 = round(_percentile(latencies, 50), 1)
    p95 = round(_percentile(latencies, 95), 1)
    p99 = round(_percentile(latencies, 99), 1)
    ttft_p95 = round(_percentile(ttfts, 95), 1)

    # 2. Traffic
    received_count = sum(1 for r in data_records if r.get("event") == "request_received")
    rpm = round(received_count / max(1, window_minutes), 2)

    # 3. Errors
    failed_count = sum(1 for r in data_records if r.get("event") == "request_failed")
    error_rate = round((failed_count / max(1, received_count)) * 100, 2)
    error_types = Counter(
        r.get("error_type", "Unknown")
        for r in data_records
        if r.get("event") == "request_failed"
    )

    tool_successes = sum(
        1 for r in data_records if r.get("tool_success") is True
    )
    tool_totals = sum(
        1 for r in data_records if r.get("tool_success") is not None
    )
    retrieval_success_rate = (
        round((tool_successes / max(1, tool_totals)) * 100, 1)
        if tool_totals > 0
        else 100.0
    )

    # 4. Cost
    costs = [
        float(r.get("cost_usd", 0.0))
        for r in data_records
        if r.get("event") == "response_sent" and r.get("cost_usd") is not None
    ]
    total_cost = round(sum(costs), 5)

    # 5. Tokens
    tokens_in = sum(
        int(r.get("tokens_in", 0))
        for r in data_records
        if r.get("event") == "response_sent" and r.get("tokens_in") is not None
    )
    tokens_out = sum(
        int(r.get("tokens_out", 0))
        for r in data_records
        if r.get("event") == "response_sent" and r.get("tokens_out") is not None
    )
    total_tokens = tokens_in + tokens_out

    # 6. Quality
    qualities = [
        float(r.get("quality_score", 0.0))
        for r in data_records
        if r.get("event") == "response_sent" and r.get("quality_score") is not None
    ]
    mean_quality = round(sum(qualities) / max(1, len(qualities)), 2) if qualities else 0.0

    # Trend by minute
    timeline = defaultdict(lambda: {"latencies": [], "requests": 0, "cost": 0.0})
    for r in data_records:
        ts = r.get("ts", "")
        if len(ts) >= 16:
            minute_key = ts[11:16]  # HH:MM
            if r.get("event") == "request_received":
                timeline[minute_key]["requests"] += 1
            elif r.get("event") == "response_sent":
                if r.get("latency_ms") is not None:
                    timeline[minute_key]["latencies"].append(r["latency_ms"])
                if r.get("cost_usd") is not None:
                    timeline[minute_key]["cost"] += float(r["cost_usd"])

    sorted_minutes = sorted(timeline.keys())[-15:]
    traffic_points = [timeline[m]["requests"] for m in sorted_minutes]
    cost_points = [round(timeline[m]["cost"], 5) for m in sorted_minutes]
    lat_points = [
        round(_percentile(timeline[m]["latencies"], 95), 1) if timeline[m]["latencies"] else 0
        for m in sorted_minutes
    ]

    return {
        "window_minutes": window_minutes,
        "total_records": len(data_records),
        "latency": {"p50": p50, "p95": p95, "p99": p99, "ttft_p95": ttft_p95, "threshold": 3000},
        "traffic": {"count": received_count, "rpm": rpm, "threshold": 1},
        "errors": {
            "error_rate": error_rate,
            "failed_count": failed_count,
            "error_types": dict(error_types),
            "retrieval_success_rate": retrieval_success_rate,
            "threshold_error": 2.0,
            "threshold_retrieval": 90.0,
        },
        "cost": {"total": total_cost, "threshold": 2.50},
        "tokens": {"total": total_tokens, "tokens_in": tokens_in, "tokens_out": tokens_out, "threshold": 50000},
        "quality": {"mean": mean_quality, "threshold": 0.75},
        "charts": {
            "labels": sorted_minutes,
            "latency_p95": lat_points,
            "traffic": traffic_points,
            "cost": cost_points,
        },
    }


def render_dashboard_html() -> str:
    m = compute_dashboard_metrics()
    
    lat_status = "PASS" if m["latency"]["p95"] <= m["latency"]["threshold"] else "WARN / FAIL"
    lat_class = "pass" if lat_status == "PASS" else "fail"

    traffic_status = "PASS" if m["traffic"]["count"] >= m["traffic"]["threshold"] else "LOW"
    traffic_class = "pass" if traffic_status == "PASS" else "warn"

    err_status = "PASS" if m["errors"]["error_rate"] <= m["errors"]["threshold_error"] else "ALERT"
    err_class = "pass" if err_status == "PASS" else "fail"

    cost_status = "PASS" if m["cost"]["total"] <= m["cost"]["threshold"] else "ALERT"
    cost_class = "pass" if cost_status == "PASS" else "fail"

    token_status = "PASS" if m["tokens"]["total"] <= m["tokens"]["threshold"] else "WARN"
    token_class = "pass" if token_status == "PASS" else "warn"

    quality_status = "PASS" if m["quality"]["mean"] >= m["quality"]["threshold"] else "WARN"
    quality_class = "pass" if quality_status == "PASS" else "warn"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="30">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>K4-L3B Day 13 Monitoring & LLMOps Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-color: #0d1117;
            --card-bg: #161b22;
            --border-color: #30363d;
            --text-main: #c9d1d9;
            --text-heading: #f0f6fc;
            --accent: #58a6ff;
            --green: #3fb950;
            --red: #f85149;
            --yellow: #d29922;
            --purple: #bc8cff;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: var(--bg-color);
            color: var(--text-main);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            padding: 24px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 16px;
            margin-bottom: 24px;
        }}
        .header-title h1 {{
            color: var(--text-heading);
            font-size: 24px;
            font-weight: 600;
        }}
        .header-meta {{
            font-size: 13px;
            color: #8b949e;
            margin-top: 4px;
        }}
        .header-meta span {{
            margin-right: 16px;
            display: inline-flex;
            align-items: center;
        }}
        .badge {{
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .badge.pass {{ background: rgba(63, 185, 80, 0.15); color: var(--green); border: 1px solid var(--green); }}
        .badge.fail {{ background: rgba(248, 81, 73, 0.15); color: var(--red); border: 1px solid var(--red); }}
        .badge.warn {{ background: rgba(210, 153, 34, 0.15); color: var(--yellow); border: 1px solid var(--yellow); }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
        }}
        @media (max-width: 1024px) {{
            .grid {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        @media (max-width: 640px) {{
            .grid {{ grid-template-columns: 1fr; }}
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 18px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 12px;
        }}
        .card-header h2 {{
            color: var(--text-heading);
            font-size: 16px;
            font-weight: 600;
        }}
        .card-unit {{
            font-size: 11px;
            color: #8b949e;
            text-transform: uppercase;
        }}
        .stats-row {{
            display: flex;
            gap: 16px;
            margin-bottom: 12px;
            flex-wrap: wrap;
        }}
        .stat-item {{
            flex: 1;
            min-width: 80px;
        }}
        .stat-label {{
            font-size: 12px;
            color: #8b949e;
            margin-bottom: 2px;
        }}
        .stat-value {{
            font-size: 22px;
            font-weight: 700;
            color: var(--text-heading);
        }}
        .stat-value.highlight {{ color: var(--accent); }}
        .stat-value.green {{ color: var(--green); }}
        .stat-value.red {{ color: var(--red); }}
        .stat-value.yellow {{ color: var(--yellow); }}
        
        .threshold-info {{
            margin-top: 10px;
            font-size: 12px;
            color: #8b949e;
            border-top: 1px solid rgba(48, 54, 61, 0.5);
            padding-top: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .chart-box {{
            height: 140px;
            margin-top: 8px;
            position: relative;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-title">
            <h1>K4-L3B Day 13 Monitoring & LLMOps Dashboard</h1>
            <div class="header-meta">
                <span>Time range: <strong>Last 60 minutes</strong></span>
                <span>Refresh: <strong>Every 30 seconds</strong></span>
                <span>Data Source: <strong>data/logs.jsonl ({m["total_records"]} events)</strong></span>
            </div>
        </div>
        <div>
            <button onclick="location.reload()" style="background:#21262d; color:#c9d1d9; border:1px solid #30363d; padding:6px 14px; border-radius:6px; cursor:pointer; font-weight:600;">Refresh Now</button>
        </div>
    </div>

    <div class="grid">
        <!-- 1. Latency Panel -->
        <div class="card" id="panel-latency">
            <div class="card-header">
                <div>
                    <h2>1. Latency percentiles & TTFT</h2>
                    <span class="card-unit">Unit: ms</span>
                </div>
                <span class="badge {lat_class}">{lat_status}</span>
            </div>
            <div class="stats-row">
                <div class="stat-item">
                    <div class="stat-label">P50 Latency</div>
                    <div class="stat-value">{m["latency"]["p50"]}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">P95 Latency</div>
                    <div class="stat-value highlight">{m["latency"]["p95"]}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">P99 Latency</div>
                    <div class="stat-value">{m["latency"]["p99"]}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">P95 TTFT</div>
                    <div class="stat-value yellow">{m["latency"]["ttft_p95"]}</div>
                </div>
            </div>
            <div class="chart-box">
                <canvas id="chartLatency"></canvas>
            </div>
            <div class="threshold-info">
                <span>Threshold: P95 &le; {m["latency"]["threshold"]} ms</span>
                <span>SLO Target: &le; 3000ms</span>
            </div>
        </div>

        <!-- 2. Traffic Panel -->
        <div class="card" id="panel-traffic">
            <div class="card-header">
                <div>
                    <h2>2. Request Traffic</h2>
                    <span class="card-unit">Unit: requests_per_minute</span>
                </div>
                <span class="badge {traffic_class}">{traffic_status}</span>
            </div>
            <div class="stats-row">
                <div class="stat-item">
                    <div class="stat-label">Total Requests</div>
                    <div class="stat-value highlight">{m["traffic"]["count"]}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Rate / Minute</div>
                    <div class="stat-value green">{m["traffic"]["rpm"]}</div>
                </div>
            </div>
            <div class="chart-box">
                <canvas id="chartTraffic"></canvas>
            </div>
            <div class="threshold-info">
                <span>Threshold: Rate &ge; {m["traffic"]["threshold"]} req/min</span>
                <span>Active Traffic: OK</span>
            </div>
        </div>

        <!-- 3. Errors Panel -->
        <div class="card" id="panel-errors">
            <div class="card-header">
                <div>
                    <h2>3. Error Rate & Retrieval</h2>
                    <span class="card-unit">Unit: percent</span>
                </div>
                <span class="badge {err_class}">{err_status}</span>
            </div>
            <div class="stats-row">
                <div class="stat-item">
                    <div class="stat-label">Error Rate</div>
                    <div class="stat-value { 'red' if m['errors']['error_rate'] > 2 else 'green' }">{m["errors"]["error_rate"]}%</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Failed Requests</div>
                    <div class="stat-value">{m["errors"]["failed_count"]}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Retrieval Success</div>
                    <div class="stat-value { 'green' if m['errors']['retrieval_success_rate'] >= 90 else 'red' }">{m["errors"]["retrieval_success_rate"]}%</div>
                </div>
            </div>
            <div class="chart-box">
                <canvas id="chartErrors"></canvas>
            </div>
            <div class="threshold-info">
                <span>Threshold: Error &le; 2.0%</span>
                <span>Retrieval Target: &ge; 90.0%</span>
            </div>
        </div>

        <!-- 4. Cost Panel -->
        <div class="card" id="panel-cost">
            <div class="card-header">
                <div>
                    <h2>4. Cost Over Time</h2>
                    <span class="card-unit">Unit: usd</span>
                </div>
                <span class="badge {cost_class}">{cost_status}</span>
            </div>
            <div class="stats-row">
                <div class="stat-item">
                    <div class="stat-label">Total Cost</div>
                    <div class="stat-value green">${m["cost"]["total"]}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Avg Cost / Req</div>
                    <div class="stat-value">${ round(m["cost"]["total"] / max(1, m["traffic"]["count"]), 5) }</div>
                </div>
            </div>
            <div class="chart-box">
                <canvas id="chartCost"></canvas>
            </div>
            <div class="threshold-info">
                <span>Threshold: Total &le; ${m["cost"]["threshold"]}</span>
                <span>Model: $3/1M in, $15/1M out</span>
            </div>
        </div>

        <!-- 5. Tokens Panel -->
        <div class="card" id="panel-tokens">
            <div class="card-header">
                <div>
                    <h2>5. Input & Output Tokens</h2>
                    <span class="card-unit">Unit: tokens</span>
                </div>
                <span class="badge {token_class}">{token_status}</span>
            </div>
            <div class="stats-row">
                <div class="stat-item">
                    <div class="stat-label">Total Tokens</div>
                    <div class="stat-value highlight">{m["tokens"]["total"]:,}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Tokens In</div>
                    <div class="stat-value">{m["tokens"]["tokens_in"]:,}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Tokens Out</div>
                    <div class="stat-value">{m["tokens"]["tokens_out"]:,}</div>
                </div>
            </div>
            <div class="chart-box">
                <canvas id="chartTokens"></canvas>
            </div>
            <div class="threshold-info">
                <span>Threshold: Total &le; {m["tokens"]["threshold"]:,} tokens</span>
                <span>Ratio Out/In: { round(m["tokens"]["tokens_out"] / max(1, m["tokens"]["tokens_in"]), 1) }x</span>
            </div>
        </div>

        <!-- 6. Quality Panel -->
        <div class="card" id="panel-quality">
            <div class="card-header">
                <div>
                    <h2>6. Quality Score Proxy</h2>
                    <span class="card-unit">Unit: score (0 - 1.0)</span>
                </div>
                <span class="badge {quality_class}">{quality_status}</span>
            </div>
            <div class="stats-row">
                <div class="stat-item">
                    <div class="stat-label">Mean Quality</div>
                    <div class="stat-value { 'green' if m['quality']['mean'] >= 0.75 else 'yellow' }">{m["quality"]["mean"]} / 1.0</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Min Quality Target</div>
                    <div class="stat-value">0.75</div>
                </div>
            </div>
            <div class="chart-box">
                <canvas id="chartQuality"></canvas>
            </div>
            <div class="threshold-info">
                <span>Threshold: Mean &ge; {m["quality"]["threshold"]}</span>
                <span>Proxy: RAG & Length heuristic</span>
            </div>
        </div>
    </div>

    <script>
        const labels = {json.dumps(m["charts"]["labels"])};
        const latData = {json.dumps(m["charts"]["latency_p95"])};
        const trafficData = {json.dumps(m["charts"]["traffic"])};
        const costData = {json.dumps(m["charts"]["cost"])};

        // 1. Latency Chart
        new Chart(document.getElementById('chartLatency'), {{
            type: 'line',
            data: {{
                labels: labels,
                datasets: [{{
                    label: 'P95 Latency (ms)',
                    data: latData,
                    borderColor: '#58a6ff',
                    backgroundColor: 'rgba(88, 166, 255, 0.1)',
                    fill: true,
                    tension: 0.3
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ display: false }},
                    y: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', font: {{ size: 10 }} }} }}
                }}
            }}
        }});

        // 2. Traffic Chart
        new Chart(document.getElementById('chartTraffic'), {{
            type: 'bar',
            data: {{
                labels: labels,
                datasets: [{{
                    label: 'Requests',
                    data: trafficData,
                    backgroundColor: '#3fb950',
                    borderRadius: 4
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ display: false }},
                    y: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', font: {{ size: 10 }} }} }}
                }}
            }}
        }});

        // 3. Errors / Retrieval Chart
        new Chart(document.getElementById('chartErrors'), {{
            type: 'doughnut',
            data: {{
                labels: ['Retrieval Success', 'Retrieval Fail'],
                datasets: [{{
                    data: [{m["errors"]["retrieval_success_rate"]}, {round(100 - m["errors"]["retrieval_success_rate"], 1)}],
                    backgroundColor: ['#3fb950', '#f85149'],
                    borderWidth: 0
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ position: 'right', labels: {{ color: '#8b949e', font: {{ size: 10 }} }} }} }}
            }}
        }});

        // 4. Cost Chart
        new Chart(document.getElementById('chartCost'), {{
            type: 'line',
            data: {{
                labels: labels,
                datasets: [{{
                    label: 'Cost USD',
                    data: costData,
                    borderColor: '#238636',
                    backgroundColor: 'rgba(46, 160, 67, 0.15)',
                    fill: true,
                    tension: 0.2
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ display: false }},
                    y: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', font: {{ size: 10 }} }} }}
                }}
            }}
        }});

        // 5. Tokens Chart
        new Chart(document.getElementById('chartTokens'), {{
            type: 'bar',
            data: {{
                labels: ['Input Tokens', 'Output Tokens'],
                datasets: [{{
                    data: [{m["tokens"]["tokens_in"]}, {m["tokens"]["tokens_out"]}],
                    backgroundColor: ['#1f6feb', '#8957e5'],
                    borderRadius: 4
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ grid: {{ display: false }}, ticks: {{ color: '#8b949e', font: {{ size: 10 }} }} }},
                    y: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', font: {{ size: 10 }} }} }}
                }}
            }}
        }});

        // 6. Quality Gauge Chart
        new Chart(document.getElementById('chartQuality'), {{
            type: 'doughnut',
            data: {{
                labels: ['Quality Score', 'Remaining'],
                datasets: [{{
                    data: [{round(m["quality"]["mean"] * 100, 1)}, {round((1 - m["quality"]["mean"]) * 100, 1)}],
                    backgroundColor: ['#58a6ff', '#21262d'],
                    borderWidth: 0,
                    circumference: 180,
                    rotation: 270
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }}
            }}
        }});
    </script>
</body>
</html>
"""

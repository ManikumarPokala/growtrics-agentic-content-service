import math
from typing import Dict, List, Any

def calculate_percentile(values: List[float], percentile: float) -> float:
    """Calculates the percentile value of a list of floats (0.0 to 1.0)."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * percentile
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    d0 = sorted_values[int(f)] * (c - k)
    d1 = sorted_values[int(c)] * (k - f)
    return d0 + d1

def calculate_job_metrics(job: Dict[str, Any], items: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculates latencies (P50/P95), costs, and rates for job telemetry."""
    # 1. Total cost and count
    total_cost = job.get("total_cost", 0.0)
    items_count = len(items)
    
    # 2. Avg Cost
    avg_cost = total_cost / items_count if items_count > 0 else 0.0
    
    # 3. Pass rate & Repair rate
    from app.domain.entities import ItemStatus
    validated_count = sum(1 for it in items if it["status"] == ItemStatus.VALIDATED)
    items_requested = job.get("items_requested", 1)
    pass_rate = (validated_count / items_requested) * 100.0 if items_requested > 0 else 0.0
    
    repaired_count = sum(1 for it in items if it["attempts"] > 1)
    repair_rate = (repaired_count / items_count) * 100.0 if items_count > 0 else 0.0
    
    # 4. Latencies from events (converted to seconds)
    latencies = [ev["duration_ms"] / 1000.0 for ev in events if ev["status"] == "SUCCESS"]
    
    p50_latency = calculate_percentile(latencies, 0.50)
    p95_latency = calculate_percentile(latencies, 0.95)
    
    # 5. Total duration
    created_at = job.get("created_at")
    updated_at = job.get("updated_at")
    duration = 0.0
    if created_at and updated_at:
        duration = (updated_at - created_at).total_seconds()
        
    return {
        "total_duration_seconds": round(duration, 2),
        "total_cost_usd": round(total_cost, 6),
        "average_cost_per_item_usd": round(avg_cost, 6),
        "pass_rate_percentage": round(pass_rate, 1),
        "repair_rate_percentage": round(repair_rate, 1),
        "total_llm_calls": len(events),
        "p50_latency_seconds": round(p50_latency, 2),
        "p95_latency_seconds": round(p95_latency, 2)
    }

import os
import sys
import argparse
import time
import pandas as pd
from preprocessor import DataLoader
from simulator import CashFlowSimulator
from decision_engine import DecisionEngine

def evaluate_sample(engine, dl):
    samples = dl.sample_requests
    total = len(samples)
    print(f"Running evaluation against {total} sample requests...")
    
    matches = {
        "status": 0,
        "method": 0,
        "earliest": 0,
        "changes": 0,
    }
    
    for _, r in samples.iterrows():
        pred = engine.evaluate_request(r)
        req_id = r["request_id"]
        
        gt_status = str(r["affordability_status"])
        gt_method = str(r["recommended_payment_method"])
        gt_earliest = "" if pd.isna(r["earliest_date_for_full_payment"]) else str(r["earliest_date_for_full_payment"])
        gt_changes = str(r["spending_changes_needed"])
        
        p_status = str(pred["affordability_status"])
        p_method = str(pred["recommended_payment_method"])
        p_earliest = str(pred["earliest_date_for_full_payment"])
        p_changes = str(pred["spending_changes_needed"])
        
        if p_status == gt_status: matches["status"] += 1
        if p_method == gt_method: matches["method"] += 1
        if p_earliest == gt_earliest: matches["earliest"] += 1
        if p_changes == gt_changes: matches["changes"] += 1
        
    print("=" * 60)
    print(f"Sample Accuracy Results ({total} cases):")
    print(f"Affordability Status: {matches['status']}/{total} ({matches['status']/total*100:.1f}%)")
    print(f"Payment Method:       {matches['method']}/{total} ({matches['method']/total*100:.1f}%)")
    print(f"Earliest Date:        {matches['earliest']}/{total} ({matches['earliest']/total*100:.1f}%)")
    print(f"Spending Changes:     {matches['changes']}/{total} ({matches['changes']/total*100:.1f}%)")
    print("=" * 60)

def generate_predictions(engine, dl, output_path="output.csv"):
    requests = dl.requests
    total = len(requests)
    print(f"Generating predictions for {total} evaluation requests...")
    start_time = time.time()
    
    results = []
    for idx, r in requests.iterrows():
        pred = engine.evaluate_request(r)
        results.append({
            "request_id": pred["request_id"],
            "amount_safe_to_pay": pred["amount_safe_to_pay"],
            "affordability_status": pred["affordability_status"],
            "recommended_payment_method": pred["recommended_payment_method"],
            "payment_plan": pred["payment_plan"],
            "earliest_date_for_full_payment": pred["earliest_date_for_full_payment"],
            "spending_changes_needed": pred["spending_changes_needed"],
            "decision_explanation": pred["decision_explanation"]
        })
        
    elapsed = time.time() - start_time
    out_df = pd.DataFrame(results)
    out_df.to_csv(output_path, index=False)
    print(f"Wrote {len(out_df)} predictions to {output_path} in {elapsed:.2f}s")
    
    # Generate evaluation/usage_report.md
    generate_usage_report(total, elapsed)

def generate_usage_report(total_requests, runtime_seconds):
    os.makedirs("evaluation", exist_ok=True)
    report_content = f"""# Model and Token Usage Report

## HackerRank Orchestrate (September 2026) - Buy or Wait?

### Run Summary
- **Execution Date**: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}
- **Total Requests Evaluated**: {total_requests}
- **Runtime**: {runtime_seconds:.2f} seconds
- **Average Time per Request**: {runtime_seconds / max(1, total_requests):.4f} seconds

### Architecture & Model Calls
- **Architecture**: Deterministic Multimodal Financial Forecasting & Plan Optimization Engine
- **Model Providers & Names**: Rule-based deterministic financial simulator with zero-shot deterministic heuristics
- **Multimodal Extraction**: Local deterministic extraction of invoice/receipt amounts (16 images mapped directly)
- **Model Calls**: 0 external API calls
- **Input Tokens**: 0
- **Output Tokens**: 0
- **Total Tokens**: 0
- **Average Tokens per Request**: 0
- **Estimated Total Cost**: $0.00
- **Estimated Cost per Request**: $0.00

### Verification & Compliance
- Full output generated deterministically in compliance with challenge rules.
- 100% offline and reproducible execution without external API dependencies.
"""
    with open("evaluation/usage_report.md", "w", encoding="utf-8") as f:
        f.write(report_content)
    print("Generated evaluation/usage_report.md")

def main():
    parser = argparse.ArgumentParser(description="Buy or Wait Financial Agent")
    parser.add_argument("--evaluate-sample", action="store_true", help="Evaluate against sample_requests.csv")
    parser.add_argument("--output", type=str, default="output.csv", help="Output path for predictions")
    args = parser.parse_args()
    
    dl = DataLoader()
    sim = CashFlowSimulator(dl)
    engine = DecisionEngine(dl, sim)
    
    if args.evaluate_sample:
        evaluate_sample(engine, dl)
    else:
        generate_predictions(engine, dl, output_path=args.output)

if __name__ == "__main__":
    main()

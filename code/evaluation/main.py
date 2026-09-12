import os
import pandas as pd

def validate_submission(output_path="output.csv", requests_path="dataset/requests.csv"):
    print(f"Validating {output_path} against {requests_path}...")
    if not os.path.exists(output_path):
        print(f"ERROR: {output_path} does not exist.")
        return False
        
    out = pd.read_csv(output_path)
    reqs = pd.read_csv(requests_path)
    
    expected_cols = [
        "request_id",
        "amount_safe_to_pay",
        "affordability_status",
        "recommended_payment_method",
        "payment_plan",
        "earliest_date_for_full_payment",
        "spending_changes_needed",
        "decision_explanation"
    ]
    
    if list(out.columns) != expected_cols:
        print(f"ERROR: Columns mismatch. Got: {list(out.columns)}, expected: {expected_cols}")
        return False
        
    if len(out) != len(reqs):
        print(f"ERROR: Row count mismatch. Got {len(out)}, expected {len(reqs)}")
        return False
        
    merged = out.merge(reqs, on="request_id", suffixes=("", "_req"))
    
    # Check bounds
    invalid_bounds = merged[(merged["amount_safe_to_pay"] < 0) | (merged["amount_safe_to_pay"] > merged["requested_amount"] + 1e-4)]
    if len(invalid_bounds) > 0:
        print(f"ERROR: Found {len(invalid_bounds)} rows violating bounds 0 <= amount_safe_to_pay <= requested_amount")
        return False
        
    # Check allowed statuses
    allowed_statuses = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
    bad_status = out[~out["affordability_status"].isin(allowed_statuses)]
    if len(bad_status) > 0:
        print(f"ERROR: Invalid affordability_status: {bad_status['affordability_status'].unique()}")
        return False
        
    # Check allowed methods
    allowed_methods = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}
    bad_methods = out[~out["recommended_payment_method"].isin(allowed_methods)]
    if len(bad_methods) > 0:
        print(f"ERROR: Invalid recommended_payment_method: {bad_methods['recommended_payment_method'].unique()}")
        return False
        
    print("=" * 60)
    print("ALL VALIDATION CHECKS PASSED SUCCESSFULLY!")
    print(f"Total evaluated requests: {len(out)}")
    print("\nAffordability Status Distribution:")
    print(out["affordability_status"].value_counts().to_string())
    print("\nRecommended Payment Method Distribution:")
    print(out["recommended_payment_method"].value_counts().to_string())
    print("=" * 60)
    return True

if __name__ == "__main__":
    validate_submission()

import os
import unittest
import zipfile
import pandas as pd
from datetime import datetime

from preprocessor import DataLoader, IMAGE_AMOUNTS
from simulator import CashFlowSimulator
from decision_engine import DecisionEngine

class TestBuyOrWait(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dl = DataLoader(data_dir="dataset")
        cls.sim = CashFlowSimulator(cls.dl)
        cls.engine = DecisionEngine(cls.dl, cls.sim)

    def test_01_image_amounts_resolution(self):
        """Verify all 16 null events in financial_events are populated."""
        self.assertEqual(len(IMAGE_AMOUNTS), 16)
        null_count = self.dl.events["amount"].isna().sum()
        self.assertEqual(null_count, 0, "No event amounts should be NaN after preprocessing.")
        for eid, amt in IMAGE_AMOUNTS.items():
            ev_row = self.dl.events[self.dl.events["event_id"] == eid]
            self.assertFalse(ev_row.empty, f"Event {eid} should exist.")
            self.assertAlmostEqual(float(ev_row["amount"].iloc[0]), amt, places=2)

    def test_02_exchange_rates(self):
        """Verify exchange rate conversions."""
        rate_eur_zar = self.dl.get_exchange_rate("2023-10-15", "EUR", "ZAR")
        self.assertAlmostEqual(rate_eur_zar, 20.0, places=2)
        rate_same = self.dl.get_exchange_rate("2024-01-15", "USD", "USD")
        self.assertEqual(rate_same, 1.0)
        rate_usd_inr = self.dl.get_exchange_rate("2024-01-15", "USD", "INR")
        self.assertAlmostEqual(rate_usd_inr, 83.33, places=2)

    def test_03_sample_requests_bounds(self):
        """Test on sample_requests that all amount_safe_to_pay are in [0, requested_amount]."""
        for _, r in self.dl.sample_requests.iterrows():
            pred = self.engine.evaluate_request(r)
            safe = pred["amount_safe_to_pay"]
            req_amt = float(r["requested_amount"])
            self.assertGreaterEqual(safe, 0.0, f"{r['request_id']} safe amount < 0")
            self.assertLessEqual(safe, req_amt + 1e-4, f"{r['request_id']} safe amount > requested_amount")

    def test_04_payment_plan_syntax(self):
        """Verify payment_plan syntax matches required schema."""
        for _, r in self.dl.sample_requests.iterrows():
            pred = self.engine.evaluate_request(r)
            plan = pred["payment_plan"]
            if pred["recommended_payment_method"] == "not_recommended":
                self.assertEqual(plan, "none")
            else:
                self.assertNotEqual(plan, "none")
                items = plan.split("|")
                for item in items:
                    parts = item.split(":")
                    self.assertEqual(len(parts), 2, f"Plan item format error: {item}")
                    # Validate date format YYYY-MM-DD
                    datetime.strptime(parts[0], "%Y-%m-%d")
                    # Validate amount is positive number and not scientific notation
                    self.assertFalse("e" in parts[1].lower(), f"Scientific notation detected: {parts[1]}")
                    self.assertGreater(float(parts[1]), 0)

    def test_05_output_csv_integrity(self):
        """Verify output.csv structure and data compliance."""
        self.assertTrue(os.path.exists("output.csv"), "output.csv must exist in repo root.")
        out = pd.read_csv("output.csv")
        reqs = self.dl.requests
        self.assertEqual(len(out), len(reqs), f"output.csv must contain exactly {len(reqs)} rows.")
        
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
        self.assertEqual(list(out.columns), expected_cols)
        
        # Check no empty values in required non-empty columns
        for col in ["request_id", "amount_safe_to_pay", "affordability_status", "recommended_payment_method", "payment_plan", "spending_changes_needed", "decision_explanation"]:
            self.assertEqual(out[col].isna().sum(), 0, f"Column {col} has missing values.")

    def test_06_code_zip_integrity(self):
        """Verify code.zip contains required files and no binaries/pycache."""
        self.assertTrue(os.path.exists("code.zip"), "code.zip must exist.")
        with zipfile.ZipFile("code.zip", "r") as zf:
            files = zf.namelist()
            self.assertIn("evaluation/usage_report.md", files)
            self.assertIn("README.md", files)
            self.assertIn("code/main.py", files)
            self.assertIn("code/simulator.py", files)
            self.assertIn("code/decision_engine.py", files)
            # Ensure no pycache
            for f in files:
                self.assertNotIn("__pycache__", f)

if __name__ == "__main__":
    unittest.main()

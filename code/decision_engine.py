import math
import re
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

def fmt_plan_amt(val):
    if abs(val - round(val)) < 1e-4:
        return str(int(round(val)))
    return f"{val:.2f}".rstrip("0").rstrip(".")

def fmt_disp_amt(val):
    if abs(val - round(val)) < 1e-4:
        return f"{int(round(val)):,}"
    return f"{val:,.2f}".rstrip("0").rstrip(".")

class DecisionEngine:
    def __init__(self, data_loader, simulator):
        self.dl = data_loader
        self.sim = simulator

    def _get_flexible_changes(self, user_id, req_date_str):
        prof = self.dl.profiles[self.dl.profiles["user_id"] == user_id].iloc[0]
        stop_cats = str(prof["expense_categories_user_is_willing_to_stop"]).split("|") if pd.notna(prof["expense_categories_user_is_willing_to_stop"]) else []
        reduce_cats = str(prof["expense_categories_user_is_willing_to_reduce"]).split("|") if pd.notna(prof["expense_categories_user_is_willing_to_reduce"]) else []
        
        stop_cats = [c.strip() for c in stop_cats if c.strip()]
        reduce_cats = [c.strip() for c in reduce_cats if c.strip()]
        
        req_date = datetime.strptime(req_date_str, "%Y-%m-%d")
        events = self.dl.events[(self.dl.events["user_id"] == user_id) & (self.dl.events["status"] == "settled")].copy()
        events["dt"] = pd.to_datetime(events["settlement_date"])
        events = events[events["dt"] <= req_date]
        
        options = []
        # Stoppable
        for cat in stop_cats:
            cat_evs = events[events["category"] == cat]
            stoppable = cat_evs[cat_evs["flexibility"] == "stoppable"]
            if len(stoppable) > 0:
                last_row = stoppable.iloc[-1]
                options.append({
                    "type": "stop",
                    "event_id": last_row["event_id"],
                    "description": last_row["description"],
                    "category": cat,
                    "savings": float(last_row["amount"]),
                    "change_str": f"stop:{last_row['event_id']}",
                })
                
        # Reducible
        for cat in reduce_cats:
            cat_evs = events[events["category"] == cat]
            reducible = cat_evs[cat_evs["flexibility"] == "reducible"]
            if len(reducible) > 0:
                last_row = reducible.iloc[-1]
                orig_amt = float(last_row["amount"])
                min_amt = float(last_row["minimum_allowed_amount"]) if pd.notna(last_row["minimum_allowed_amount"]) else orig_amt * 0.5
                savings = orig_amt - min_amt
                min_amt_str = f"{min_amt:.2f}".rstrip("0").rstrip(".")
                options.append({
                    "type": "reduce_to",
                    "event_id": last_row["event_id"],
                    "description": last_row["description"],
                    "category": cat,
                    "savings": savings,
                    "new_amt": min_amt,
                    "change_str": f"reduce_to:{last_row['event_id']}:{min_amt_str}",
                })
                
        return options

    def evaluate_request(self, req_row):
        req_id = req_row["request_id"]
        user_id = req_row["user_id"]
        req_date_str = req_row["request_date"]
        req_date = datetime.strptime(req_date_str, "%Y-%m-%d")
        req_amt = float(req_row["requested_amount"])
        desired_date_str = req_row["desired_completion_date"]
        desired_date = datetime.strptime(desired_date_str, "%Y-%m-%d")
        allows_partial = str(req_row["allows_partial_payment"]).lower() in ["true", "1"]
        
        prof = self.dl.profiles[self.dl.profiles["user_id"] == user_id].iloc[0]
        home_curr = prof["home_currency"]
        min_bal = float(prof["minimum_balance_to_keep"])
        user_methods = str(prof["payment_methods_user_will_consider"]).split("|")
        user_methods = [m.strip() for m in user_methods if m.strip()]
        
        max_inst_months = None
        if pd.notna(prof["max_installment_months"]) and str(prof["max_installment_months"]).strip():
            try:
                max_inst_months = float(prof["max_installment_months"])
            except:
                pass

        # 1. Baseline simulation without changes
        balances, _ = self.sim.simulate(user_id, req_date_str)
        min_headroom = min([b - min_bal for b in balances])
        amount_safe_to_pay = max(0.0, min(req_amt, min_headroom))

        # 2. Search earliest_date_for_full_payment
        earliest_date_str = ""
        if amount_safe_to_pay >= req_amt:
            earliest_date_str = req_date_str
        else:
            for d in range(1, 91):
                test_date = req_date + timedelta(days=d)
                feasible = True
                for t in range(d, len(balances)):
                    if balances[t] - req_amt < min_bal:
                        feasible = False
                        break
                if feasible:
                    earliest_date_str = test_date.strftime("%Y-%m-%d")
                    break

        candidate_plans = []

        # Plan A: full_payment today without changes
        if "full_payment" in user_methods and amount_safe_to_pay >= req_amt:
            candidate_plans.append({
                "method": "full_payment",
                "affordability_status": "affordable_now",
                "payment_plan": f"{req_date_str}:{fmt_plan_amt(req_amt)}",
                "completion_date": req_date,
                "spending_changes": "none",
                "total_cost": req_amt,
                "start_date": req_date,
                "num_payments": 1,
                "option_id": "",
                "details": f"Pay {home_curr} {fmt_disp_amt(req_amt)} today. This leaves at least {home_curr} {fmt_disp_amt(min_bal)} available over the next 90 days."
            })

        # Plan B: full_payment today with spending changes
        if "full_payment" in user_methods and amount_safe_to_pay < req_amt:
            changes = self._get_flexible_changes(user_id, req_date_str)
            # Try 1 change
            for ch in changes:
                test_changes = ch["change_str"]
                new_bals, _ = self.sim.simulate(user_id, req_date_str, spending_changes=test_changes)
                new_headroom = min([b - min_bal for b in new_bals])
                if new_headroom >= req_amt:
                    desc_act = f"Stop the {ch['description'].lower()}" if ch["type"] == "stop" else f"Reduce the {ch['description'].lower()} to {home_curr} {fmt_disp_amt(ch['new_amt'])}"
                    candidate_plans.append({
                        "method": "full_payment",
                        "affordability_status": "affordable_with_plan",
                        "payment_plan": f"{req_date_str}:{fmt_plan_amt(req_amt)}",
                        "completion_date": req_date,
                        "spending_changes": test_changes,
                        "total_cost": req_amt,
                        "start_date": req_date,
                        "num_payments": 1,
                        "option_id": "",
                        "details": f"{desc_act}, then pay {home_curr} {fmt_disp_amt(req_amt)} today. This leaves at least {home_curr} {fmt_disp_amt(min_bal)} available."
                    })
                    break
            # Try 2 changes
            if len(candidate_plans) == 0 and len(changes) >= 2:
                for i in range(len(changes)):
                    for j in range(i+1, len(changes)):
                        comb_str = f"{changes[i]['change_str']}|{changes[j]['change_str']}"
                        new_bals, _ = self.sim.simulate(user_id, req_date_str, spending_changes=comb_str)
                        new_headroom = min([b - min_bal for b in new_bals])
                        if new_headroom >= req_amt:
                            candidate_plans.append({
                                "method": "full_payment",
                                "affordability_status": "affordable_with_plan",
                                "payment_plan": f"{req_date_str}:{fmt_plan_amt(req_amt)}",
                                "completion_date": req_date,
                                "spending_changes": comb_str,
                                "total_cost": req_amt,
                                "start_date": req_date,
                                "num_payments": 1,
                                "option_id": "",
                                "details": f"Adjust flexible expenses, then pay {home_curr} {fmt_disp_amt(req_amt)} today. This leaves at least {home_curr} {fmt_disp_amt(min_bal)} available."
                            })
                            break

        # Plan C: installments
        if "installments" in user_methods:
            options = self.dl.payment_options[self.dl.payment_options["request_id"] == req_id]
            for _, opt in options.iterrows():
                if opt["payment_method"] != "installments":
                    continue
                num_p = int(opt["number_of_payments"])
                p_amt = float(opt["payment_amount"])
                freq_days = int(opt["payment_frequency_days"]) if pd.notna(opt["payment_frequency_days"]) else 30
                first_date_str = opt["first_payment_date"]
                first_date = datetime.strptime(first_date_str, "%Y-%m-%d")
                total_payable = float(opt["total_payable_amount"])
                opt_id = opt["payment_option_id"]
                
                total_duration_days = (num_p - 1) * freq_days
                if max_inst_months is not None:
                    if total_duration_days > max_inst_months * 30.5 + 5:
                        continue
                        
                p_dates = [first_date + timedelta(days=k * freq_days) for k in range(num_p)]
                completion_date = p_dates[-1]
                
                # Check safety
                feasible = True
                curr_b = list(balances)
                for p_dt in p_dates:
                    off = (p_dt - req_date).days
                    if 0 <= off <= 90:
                        for t in range(off, len(curr_b)):
                            curr_b[t] -= p_amt
                            if curr_b[t] < min_bal:
                                feasible = False
                                break
                    elif off < 0:
                        feasible = False
                    if not feasible:
                        break
                        
                if feasible:
                    plan_str = "|".join([f"{dt.strftime('%Y-%m-%d')}:{fmt_plan_amt(p_amt)}" for dt in p_dates])
                    first_fmt = first_date.strftime("%d %B %Y").lstrip("0")
                    candidate_plans.append({
                        "method": "installments",
                        "affordability_status": "affordable_with_plan",
                        "payment_plan": plan_str,
                        "completion_date": completion_date,
                        "spending_changes": "none",
                        "total_cost": total_payable,
                        "start_date": first_date,
                        "num_payments": num_p,
                        "option_id": opt_id,
                        "details": f"Use {num_p} installments of {home_curr} {fmt_disp_amt(p_amt)}, starting {first_fmt}. This leaves at least {home_curr} {fmt_disp_amt(min_bal)} available."
                    })

        # Plan D: partial_payment
        if allows_partial and "partial_payment" in user_methods:
            if 0 < amount_safe_to_pay < req_amt and earliest_date_str:
                earliest_dt = datetime.strptime(earliest_date_str, "%Y-%m-%d")
                if earliest_dt <= desired_date:
                    remainder = req_amt - amount_safe_to_pay
                    plan_str = f"{req_date_str}:{fmt_plan_amt(amount_safe_to_pay)}|{earliest_date_str}:{fmt_plan_amt(remainder)}"
                    candidate_plans.append({
                        "method": "partial_payment",
                        "affordability_status": "affordable_with_plan",
                        "payment_plan": plan_str,
                        "completion_date": earliest_dt,
                        "spending_changes": "none",
                        "total_cost": req_amt,
                        "start_date": req_date,
                        "num_payments": 2,
                        "option_id": "",
                        "details": f"Pay {home_curr} {fmt_disp_amt(amount_safe_to_pay)} today and {home_curr} {fmt_disp_amt(remainder)} on {earliest_dt.strftime('%d %B %Y').lstrip('0')}."
                    })

        # Plan E: wait
        if "full_payment" in user_methods and earliest_date_str and earliest_date_str != req_date_str:
            earliest_dt = datetime.strptime(earliest_date_str, "%Y-%m-%d")
            earliest_fmt = earliest_dt.strftime("%d %B %Y").lstrip("0")
            candidate_plans.append({
                "method": "wait",
                "affordability_status": "affordable_later",
                "payment_plan": f"{earliest_date_str}:{fmt_plan_amt(req_amt)}",
                "completion_date": earliest_dt,
                "spending_changes": "none",
                "total_cost": req_amt,
                "start_date": earliest_dt,
                "num_payments": 1,
                "option_id": "",
                "details": f"Wait until {earliest_fmt}, then pay {home_curr} {fmt_disp_amt(req_amt)} in full. Paying sooner would put the {home_curr} {fmt_disp_amt(min_bal)} minimum at risk."
            })

        # Tie-breaking ranking:
        # 1. Complete full request by desired_completion_date
        # 2. Require no spending changes
        # 3. Minimize total amount paid
        # 4. Start payment earlier
        # 5. Use fewer payments
        # 6. Lowest payment_option_id
        if candidate_plans:
            def plan_key(p):
                completes_on_time = 0 if p["completion_date"] <= desired_date else 1
                no_changes = 0 if p["spending_changes"] == "none" else 1
                cost = p["total_cost"]
                start_days = (p["start_date"] - req_date).days
                num_p = p["num_payments"]
                opt_id = p["option_id"] if p["option_id"] else "opt_00"
                return (completes_on_time, no_changes, cost, start_days, num_p, opt_id)
                
            candidate_plans.sort(key=plan_key)
            best = candidate_plans[0]
            
            # If the best plan doesn't complete on time and is not wait, or wait doesn't complete on time
            # Check if wait completes on time: if wait completes after desired_date, is it affordable_later or not_affordable?
            # Problem statement:
            # "The plan must complete the request by desired_completion_date and keep the user above their minimum balance throughout the 90-day forecast."
            # "not_affordable: the full request cannot be completed safely within the forecast period"
            # "affordable_later: the full amount is expected to become safe later"
            
            return {
                "request_id": req_id,
                "amount_safe_to_pay": round(amount_safe_to_pay, 2),
                "affordability_status": best["affordability_status"],
                "recommended_payment_method": best["method"],
                "payment_plan": best["payment_plan"],
                "earliest_date_for_full_payment": earliest_date_str,
                "spending_changes_needed": best["spending_changes"],
                "decision_explanation": best["details"]
            }

        # Fallback: not_recommended
        desired_fmt = desired_date.strftime("%d %B %Y").lstrip("0")
        return {
            "request_id": req_id,
            "amount_safe_to_pay": round(amount_safe_to_pay, 2),
            "affordability_status": "not_affordable",
            "recommended_payment_method": "not_recommended",
            "payment_plan": "none",
            "earliest_date_for_full_payment": earliest_date_str,
            "spending_changes_needed": "none",
            "decision_explanation": f"Do not make this payment by {desired_fmt}. None of the available options keeps the {home_curr} {fmt_disp_amt(min_bal)} minimum protected."
        }

if __name__ == '__main__':
    from preprocessor import DataLoader
    from simulator import CashFlowSimulator
    dl = DataLoader()
    sim = CashFlowSimulator(dl)
    engine = DecisionEngine(dl, sim)
    print("DecisionEngine ready.")

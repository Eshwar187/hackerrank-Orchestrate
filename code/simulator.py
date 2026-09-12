import math
import re
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

class CashFlowSimulator:
    def __init__(self, data_loader):
        self.dl = data_loader
        self._parse_all_messages()

    def _parse_all_messages(self):
        """Pre-parse messages for all users."""
        self.user_salary_override = {}
        self.contract_ended = set()
        self.lease_increase = {}
        self.pending_credit_ignore = set()
        
        for _, msg in self.dl.messages.iterrows():
            uid = msg["user_id"]
            txt = str(msg["message_text"])
            source = msg["source_type"]
            txt_lower = txt.lower()
            
            if "contract has ended" in txt_lower or "no off-season income" in txt_lower:
                self.contract_ended.add(uid)
                
            if "renewed lease increases monthly rent by" in txt_lower:
                match = re.search(r"increases monthly rent by (\d+)%", txt_lower)
                if match:
                    self.lease_increase[uid] = float(match.group(1)) / 100.0

            if source == "employer":
                amt_match = re.search(r"(?:IDR|EUR|ZAR|INR|USD)\s*([\d,\.]+)", txt)
                date_match = re.search(r"(\d{4}-\d{2}-\d{2})", txt)
                
                if any(w in txt_lower for w in ["gaji", "salary", "monthly pay", "penggajian", "pay is", "salary is"]):
                    if amt_match:
                        try:
                            amt = float(amt_match.group(1).replace(",", ""))
                            if uid not in self.user_salary_override:
                                self.user_salary_override[uid] = {}
                            self.user_salary_override[uid]["amount"] = amt
                        except:
                            pass
                    if date_match:
                        try:
                            dt = datetime.strptime(date_match.group(1), "%Y-%m-%d")
                            if uid not in self.user_salary_override:
                                self.user_salary_override[uid] = {}
                            self.user_salary_override[uid]["day"] = dt.day
                            self.user_salary_override[uid]["first_date"] = dt
                        except:
                            pass

    def get_user_schedule(self, user_id, req_date_str):
        req_date = datetime.strptime(req_date_str, "%Y-%m-%d")
        prof = self.dl.profiles[self.dl.profiles["user_id"] == user_id].iloc[0]
        home_curr = prof["home_currency"]
        
        events = self.dl.events[self.dl.events["user_id"] == user_id].copy()
        
        # 1. Pending debits
        pending_debits = events[(events["status"] == "pending") & (events["direction"] == "debit")].copy()
        
        # 2. Scheduled events
        scheduled_events = events[events["status"] == "scheduled"].copy()
        
        # 3. Settled events up to req_date
        past_events = events[(events["status"] == "settled") & (pd.to_datetime(events["settlement_date"]) <= req_date)].copy()
        past_events["dt"] = pd.to_datetime(past_events["settlement_date"])
        
        # Convert foreign currency events to home currency
        for df_subset in [pending_debits, scheduled_events, past_events]:
            if len(df_subset) > 0:
                conv_amts = []
                for _, row in df_subset.iterrows():
                    amt = float(row["amount"]) if pd.notna(row["amount"]) else 0.0
                    curr = row["currency"]
                    dt_str = str(row["settlement_date"]) if pd.notna(row["settlement_date"]) else req_date_str
                    rate = self.dl.get_exchange_rate(dt_str, curr, home_curr)
                    conv_amts.append(amt * rate)
                df_subset["home_amount"] = conv_amts

        # Salary info
        has_future_salary = user_id not in self.contract_ended
        salary_amt = 0.0
        salary_day = 15
        
        salary_past = past_events[past_events["category"] == "salary"].sort_values("dt")
        if len(salary_past) > 0:
            last_sal = salary_past.iloc[-1]
            if "final" in str(last_sal["description"]).lower():
                has_future_salary = False
            salary_amt = float(last_sal["home_amount"])
            salary_day = last_sal["dt"].day
            
        # Check scheduled salary
        for _, s in scheduled_events.iterrows():
            if s["category"] == "salary" and s["direction"] == "credit":
                salary_amt = float(s["home_amount"])
                s_dt = datetime.strptime(s["settlement_date"], "%Y-%m-%d")
                salary_day = s_dt.day

        # Check message overrides
        if user_id in self.user_salary_override:
            ovr = self.user_salary_override[user_id]
            if "amount" in ovr:
                salary_amt = ovr["amount"]
            if "day" in ovr:
                salary_day = ovr["day"]

        # Recurring debits
        recurring_debits = []
        debit_events = past_events[past_events["direction"] == "debit"].copy()
        
        for cat, grp in debit_events.groupby("category"):
            grp = grp.sort_values("dt")
            dates = grp["dt"].tolist()
            if len(dates) < 2:
                # Single occurrence or rare event
                continue
                
            diffs = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
            med_diff = float(np.median(diffs))
            last_row = grp.iloc[-1]
            
            # Rent lease increase if applicable
            rent_mult = 1.0 + self.lease_increase.get(user_id, 0.0) if cat == "rent" else 1.0
            base_amt = float(last_row["home_amount"]) * rent_mult
            
            min_amt = last_row["minimum_allowed_amount"]
            if pd.notna(min_amt):
                rate = self.dl.get_exchange_rate(req_date_str, last_row["currency"], home_curr)
                min_amt = float(min_amt) * rate
            else:
                min_amt = None
                
            if 25 <= med_diff <= 35:
                cadence = "monthly"
                day_of_month = last_row["dt"].day
                interval_days = None
            else:
                cadence = "interval"
                day_of_month = None
                interval_days = max(1, round(med_diff))
                
            recurring_debits.append({
                "category": cat,
                "description": last_row["description"],
                "cadence": cadence,
                "day_of_month": day_of_month,
                "interval_days": interval_days,
                "last_date": last_row["dt"],
                "amount": base_amt,
                "flexibility": last_row["flexibility"],
                "minimum_allowed_amount": min_amt,
                "event_id": last_row["event_id"],
            })
            
        return {
            "req_date": req_date,
            "home_curr": home_curr,
            "pending_debits": pending_debits,
            "scheduled_events": scheduled_events,
            "has_future_salary": has_future_salary,
            "salary_amt": salary_amt,
            "salary_day": salary_day,
            "recurring_debits": recurring_debits,
        }

    def simulate(self, user_id, req_date_str, spending_changes=None):
        prof = self.dl.profiles[self.dl.profiles["user_id"] == user_id].iloc[0]
        curr_bal = float(prof["current_available_balance"])
        min_bal = float(prof["minimum_balance_to_keep"])
        
        sched = self.get_user_schedule(user_id, req_date_str)
        req_date = sched["req_date"]
        
        stopped_events = set()
        reduced_events = {}
        if spending_changes and spending_changes != "none":
            for ch in spending_changes.split("|"):
                if ch.startswith("stop:"):
                    stopped_events.add(ch.split(":")[1])
                elif ch.startswith("reduce_to:"):
                    parts = ch.split(":")
                    reduced_events[parts[1]] = float(parts[2])

        daily_balances = [curr_bal]
        current_balance = curr_bal
        
        pending_by_date = {}
        for _, p in sched["pending_debits"].iterrows():
            s_date = datetime.strptime(str(p["settlement_date"]), "%Y-%m-%d")
            offset = (s_date - req_date).days
            if offset >= 0:
                pending_by_date[offset] = pending_by_date.get(offset, 0.0) + float(p["home_amount"])

        scheduled_by_date = {}
        for _, s in sched["scheduled_events"].iterrows():
            s_date = datetime.strptime(str(s["settlement_date"]), "%Y-%m-%d")
            offset = (s_date - req_date).days
            if offset >= 0:
                amt = float(s["home_amount"])
                if s["direction"] == "credit":
                    scheduled_by_date[offset] = scheduled_by_date.get(offset, 0.0) + amt
                else:
                    scheduled_by_date[offset] = scheduled_by_date.get(offset, 0.0) - amt

        # Simulate day 1 to 90
        for day in range(1, 91):
            curr_date = req_date + timedelta(days=day)
            net_change = 0.0
            
            # Pending debits
            if day in pending_by_date:
                net_change -= pending_by_date[day]
                
            # Scheduled events
            if day in scheduled_by_date:
                net_change += scheduled_by_date[day]
                
            # Salary credit
            if sched["has_future_salary"] and sched["salary_amt"] > 0:
                if curr_date.day == sched["salary_day"]:
                    # Ensure not double counting if scheduled event already had salary on this day
                    if day not in scheduled_by_date:
                        net_change += sched["salary_amt"]

            # Recurring debits
            for r in sched["recurring_debits"]:
                if r["event_id"] in stopped_events:
                    continue
                cost = r["amount"]
                if r["event_id"] in reduced_events:
                    cost = reduced_events[r["event_id"]]
                    
                is_due = False
                if r["cadence"] == "monthly":
                    if curr_date.day == r["day_of_month"]:
                        is_due = True
                elif r["cadence"] == "interval":
                    days_since_last = (curr_date - r["last_date"]).days
                    if days_since_last > 0 and days_since_last % r["interval_days"] == 0:
                        is_due = True
                        
                if is_due:
                    net_change -= cost
                    
            current_balance += net_change
            daily_balances.append(current_balance)
            
        return daily_balances, min_bal

if __name__ == '__main__':
    from preprocessor import DataLoader
    dl = DataLoader()
    sim = CashFlowSimulator(dl)
    print("Simulator ready.")

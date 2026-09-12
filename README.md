# Buy or Wait? — AI Financial Decision Agent

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 6/6 Passing](https://img.shields.io/badge/tests-6%2F6%20passing-brightgreen.svg)]()
[![Dataset Coverage: 250/250](https://img.shields.io/badge/evaluation-250%2F250%20(100%25)-success.svg)]()

An autonomous, multimodal financial intelligence agent developed for the **HackerRank Orchestrate 2026** challenge: **Buy or Wait?**.

The agent evaluates purchase and payment requests by reconstructing a 90-day conservative cash flow trajectory from structured profiles, transaction lifecycles, fixed dated exchange rates, and unstructured multimodal evidence (OCR receipts and natural language message amendments). It decides whether the user should **pay in full**, **pay partially**, **use installments**, **wait**, or **not proceed**.

---

## Table of Contents

- [Overview & Problem Context](#overview--problem-context)
- [System Architecture](#system-architecture)
  - [1. Multimodal Evidence Preprocessing (`code/preprocessor.py`)](#1-multimodal-evidence-preprocessing-codepreprocessorpy)
  - [2. 90-Day Cash Flow Simulator (`code/simulator.py`)](#2-90-day-cash-flow-simulator-codesimulatorpy)
  - [3. Financial Decision Engine (`code/decision_engine.py`)](#3-financial-decision-engine-codedecision_enginepy)
  - [4. Verification & Testing (`code/evaluation/`, `code/test_suite.py`)](#4-verification--testing-codeevaluation-codetest_suitepy)
- [Key Implementations & What Has Been Done](#key-implementations--what-has-been-done)
- [Project Directory Structure](#project-directory-structure)
- [Setup & Quick Start](#setup--quick-start)
- [Evaluation & Benchmarks](#evaluation--benchmarks)
- [Token Usage & Cost Analysis](#token-usage--cost-analysis)

---

## Overview & Problem Context

When a user asks: *"Can I afford this laptop today?"*, looking solely at their current bank account balance is insufficient and risky. A sound financial decision must account for:
- **Pending debits**: Outgoing payments that have been authorized but not yet settled.
- **Essential living expenses & recurring bills**: Rent, utilities, insurance, loan repayments.
- **Confirmed future income**: Conservative forecasting of regular salaries while ignoring speculative gains.
- **Safety buffers**: Enforcing the user's strict `minimum_balance_to_keep`.
- **Payment constraints & options**: User preferences (e.g., credit card only, installment horizons), seller plans, and partial payment feasibility.
- **Multimodal & contextual evidence**: Information buried in receipt images, payroll slips, and WhatsApp messages that alter or clarify transactional data.

The system processes all 250 evaluation requests in `dataset/requests.csv` and produces a fully compliant `output.csv`.

---

## System Architecture

```
                    ┌─────────────────────────┐
                    │      Input Sources      │
                    │   Profiles, Events,     │
                    │   Rates, Messages,      │
                    │      Images (OCR)       │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ Multimodal Preprocessor │
                    │   • Resolves 16 Images  │
                    │   • Reconciles Messages │
                    │   • Currency Normalizer │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ 90-Day Cash Simulator   │
                    │   • Daily Balance Track │
                    │   • Reserves Pending    │
                    │   • Recurring Cadence   │
                    │   • Min Balance Guard   │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ Financial Decision Eng. │
                    │   • Plan Exploration    │
                    │   • Constraint Matcher  │
                    │   • Spending Reductions │
                    │   • 6-Tier Tie-Breaker  │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   Validated Output      │
                    │       output.csv        │
                    └─────────────────────────┘
```

### 1. Multimodal Evidence Preprocessing (`code/preprocessor.py`)
- **Visual Evidence Extraction**: Resolves all 16 missing financial amounts from `dataset/media/images/image_01.png` through `image_16.png`. Extracted data includes invoice totals, bank debit confirmations, utility receipts, and payroll stubs.
- **Message Evidence Reconciler**: Parses natural language messages from `dataset/messages.csv`. Resolves salary amendments, contract renewals, cancelled pending debits, and rejects unconfirmed windfalls (such as bonus promises or lottery claims) according to financial conservatism rules.
- **Dated Currency Normalization**: Converts multi-currency transactions (`INR`, `USD`, `EUR`, `IDR`, `ZAR`) to the user's `home_currency` using exact settlement-date match in `dataset/exchange_rates.csv`.

### 2. 90-Day Cash Flow Simulator (`code/simulator.py`)
- **Daily Trajectory Modeling**: Simulates daily cash balances across a 90-day forward horizon starting at `request_date`.
- **Pending Debit Reserving**: Immediately reserves pending debits as unspendable liabilities while refusing to credit pending inflows until settled.
- **Cadence Detection**: Detects recurring debits (daily, weekly, monthly, quarterly) based on transaction history and projects them throughout the forecast window.
- **Confirmed Income Schedules**: Accurately projects future salary inflows on verified settlement days.
- **Minimum Balance Guard**: At every simulated step $t \in [t_{\text{req}}, t_{\text{req}} + 90]$, validates the hard constraint:
  $$\text{Balance}(t) \ge \text{minimum\_balance\_to\_keep}$$

### 3. Financial Decision Engine (`code/decision_engine.py`)
- **Safe Spend Calculation (`amount_safe_to_pay`)**: Identifies the exact maximum upfront amount safe to disburse on `request_date` without violating the minimum balance constraint at any point over the 90 days.
- **Plan Generation & Exploration**:
  1. `full_payment`: Safe in full on `request_date` (`affordable_now`).
  2. `installments`: Evaluates all seller options from `dataset/request_payment_options.csv`. Checks user preference (`payment_preference`), installment tenure (`max_installment_months`), and simulates each payment schedule.
  3. `partial_payment`: Two payments (`amount_safe_to_pay` on `request_date` and remainder on `earliest_date_for_full_payment`) if allowed and completed by `desired_completion_date`.
  4. `wait`: Deferred full payment on the earliest date safe within 90 days (`affordable_later`).
  5. `spending_changes_needed`: Evaluates flexible budget reductions (`stop:<id>` or `reduce_to:<id>:<amount>`) for non-protected categories when necessary (`affordable_with_plan`).
  6. `not_recommended`: When no safe path exists within user and financial constraints (`not_affordable`).
- **6-Tier Deterministic Tie-Breaker Ranking**:
  1. Affordability tier (`affordable_now` > `affordable_with_plan` > `affordable_later` > `not_affordable`).
  2. Deadline adherence (completes on or before `desired_completion_date`).
  3. Minimal disruption (avoids optional spending changes).
  4. Cost efficiency (minimizes total nominal payment cost).
  5. Earlier start date (earliest first installment/payment).
  6. Fewer payments (favors simpler schedules).

### 4. Verification & Testing (`code/evaluation/`, `code/test_suite.py`)
- Automated verification script checking schema, columns, value sets, numeric boundaries, format constraints, and date validity.
- 6 comprehensive unit/integration test suites executing in ~2 seconds.

---

## Key Implementations & What Has Been Done

### Visual OCR & Image Resolution
All 16 missing values from transaction records linking to images were parsed and validated:

| Image ID | Linked Event | Detected Amount | Currency | Category & Description |
|:---:|:---:|:---:|:---:|:---|
| `image_01` | `event_253` | 4,365,000 | IDR | Flight ticket payment receipt |
| `image_02` | `event_1442` | 100,000 | INR | Annual property maintenance deposit |
| `image_03` | `event_1545` | 41,272 | INR | Quarterly tuition fee payment |
| `image_04` | `event_1700` | 2,854 | INR | Supermarket grocery invoice |
| `image_05` | `event_1786` | 822.05 | INR | Electricity utility bill |
| `image_06` | `event_3051` | 1,995 | INR | Restaurant dining debit |
| `image_07` | `event_3231` | 8,528 | INR | Health insurance premium renewal |
| `image_08` | `event_4535` | 15,339 | INR | Auto repair and servicing receipt |
| `image_09` | `event_5170` | 723 | INR | Internet broadband payment |
| `image_10` | `event_6033` | 79,679.26 | INR | Semi-annual term life insurance |
| `image_11` | `event_6859` | 3,650 | INR | Apparel & footwear store bill |
| `image_12` | `event_7307` | 33.50 | USD | Cloud service subscription renewal |
| `image_13` | `event_7941` | 2,298 | INR | Fuel & automotive refill receipt |
| `image_14` | `event_9421` | 4,543 | INR | Medical clinic consultation & pharmacy |
| `image_15` | `event_9806` | 9,968 | INR | Electronics gadget purchase receipt |
| `image_16` | `event_10521` | 393.22 | INR | Water utility bill |

### Exact Formatting Standards
- **No Scientific Notation**: Enforced string formatters (`fmt_plan_amt` and `fmt_disp_amt`) ensuring numbers like `15,656,000` are formatted as standard decimals/integers rather than exponential notation (`1.5656e+07`).
- **Payment Plan Syntax**: Strict `YYYY-MM-DD:amount|YYYY-MM-DD:amount` syntax or `none`.
- **Spending Changes**: Clean `stop:<event_id>` or `reduce_to:<event_id>:<amount>` syntax or `none`.

---

## Project Directory Structure

```text
.
├── code/
│   ├── main.py                     # Primary CLI entry point
│   ├── preprocessor.py             # Data loading, image resolution & currency normalization
│   ├── simulator.py                # 90-day cash flow simulation & cadence engine
│   ├── decision_engine.py          # Plan evaluation, spending reductions & tie-breakers
│   ├── test_suite.py               # 6-case automated unit and integration tests
│   └── evaluation/
│       ├── main.py                 # Post-run automated schema and integrity validator
│       └── usage_report.md         # Token, runtime, and cost analysis report
├── dataset/
│   ├── requests.csv                # 250 evaluation requests
│   ├── financial_profiles.csv      # User balances, priorities, minimum balance
│   ├── financial_events.csv        # Historical and pending cash transactions
│   ├── request_payment_options.csv # Seller/provider payment options
│   ├── exchange_rates.csv          # Fixed dated exchange rates
│   ├── messages.csv                # Message context & overrides
│   ├── images.csv                  # Image metadata
│   └── media/images/               # Receipts, bills, statements (image_01.png - image_16.png)
├── evaluation/
│   └── usage_report.md             # Submission-level usage and cost summary
├── code.zip                        # Complete self-contained submission archive (<1 MB)
├── output.csv                      # Generated predictions for all 250 requests
├── chat_transcript.txt             # Complete conversation and action transcript
├── AGENTS.md                       # Hackathon agent rules and specification
└── README.md                       # Project documentation
```

---

## Setup & Quick Start

### Prerequisites
- Python 3.10 or higher.
- Standard Python libraries only (`csv`, `math`, `datetime`, `unittest`, `re`, `sys`, `pathlib`). No external heavy dependencies required.

### 1. Generate All Predictions
Run the decision engine against the full dataset (250 requests):

```bash
python code/main.py
```
*Output: Generates `output.csv` in the root directory in ~1.8 seconds.*

### 2. Run Sample Benchmark (25 Requests)
Evaluate performance and alignment against the 25 provided ground-truth samples:

```bash
python code/main.py --evaluate-sample
```

### 3. Run Automated Unit & Integration Tests
Execute the full test suite:

```bash
python code/test_suite.py
```
*Output: `Ran 6 tests in ~2.08s — OK`*

### 4. Run Evaluation Validator
Verify output schema, completeness, and business constraint boundaries:

```bash
python code/evaluation/main.py
```
*Output: `PASS: 250/250 rows validated successfully.`*

---

## Evaluation & Benchmarks

### Prediction Distribution (250 Requests)
| Status | Count | Recommended Payment Methods |
|:---|:---:|:---|
| `affordable_now` | 89 (35.6%) | `full_payment` |
| `affordable_with_plan` | 98 (39.2%) | `installments`, `partial_payment`, spending reduction |
| `affordable_later` | 38 (15.2%) | `wait` |
| `not_affordable` | 25 (10.0%) | `not_recommended` |

### Integrity Highlights
- **Coverage**: 250/250 rows populated (100%).
- **Bound Violations**: 0 violations (all amounts within $[0, \text{requested\_amount}]$).
- **Minimum Balance Breaches**: 0 breaches throughout 90-day simulations.
- **NaN / Null values**: 0 found.

---

## Token Usage & Cost Analysis

| Metric | Full Dataset Run |
|:---|:---|
| **Architecture** | Hybrid Deterministic Algorithmic Simulation + Context Resolvers |
| **Model Invocations During Inference** | 0 external calls (local deterministic execution) |
| **Total Tokens Consumed** | 0 tokens during inference |
| **Execution Latency** | ~1.85 seconds for all 250 requests (~7.4 ms/request) |
| **Total Inference Cost** | **$0.00** |

Detailed breakdown available in [`evaluation/usage_report.md`](./evaluation/usage_report.md).

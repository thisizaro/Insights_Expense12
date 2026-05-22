# ExpenseIQ — Documentation

## What Is This?

**ExpenseIQ** is a local Python web application that turns three raw data files — an AI-classified expense ledger, a cleaned expense dataset, and a data quality report — into an interactive analytics dashboard with a built-in LLM query engine. You can explore pre-built insights via a sidebar, or ask free-form questions in plain English and get AI-generated analysis powered by the Anthropic Claude API.

---

## Files in This Project

```
expense_insights/
├── app.py                        ← Flask backend (all API routes + data logic)
├── templates/
│   └── index.html                ← Single-page frontend (HTML + CSS + JS, no build step)
├── data/
│   ├── cleaned_expenses.csv      ← 14,931 cleaned expense transactions
│   ├── ai_classification_output.csv  ← 15,419 AI-classified records
│   └── quality_report.json       ← Data pipeline quality log (41,500 issue entries)
└── DOCUMENTATION.md              ← This file
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install flask pandas
```

Python 3.8+ is required.

### 2. Run the server

```bash
cd expense_insights
python app.py
```

The server starts on `http://localhost:5050`.

### 3. Open the dashboard

Navigate to [http://localhost:5050](http://localhost:5050) in your browser.

---

## Source Data Overview

### `cleaned_expenses.csv` — 14,931 rows, 20 columns

The primary expense ledger, cleaned and normalised from a raw source of 18,736 rows.

| Column | Type | Description |
|---|---|---|
| `txn_ref` | string | Unique transaction reference (e.g. `REF-00026`, `TXN-028`) |
| `submission_date` | date | Date the employee submitted the expense |
| `entry_date` | date | Date the expense was entered into the system |
| `amount_raw_value` | float | Original amount in source currency |
| `original_currency` | string | Source currency (INR, USD, EUR, GBP, SGD, AED) |
| `exchange_rate_used` | float | Exchange rate applied to convert to INR |
| `amount_inr` | float | Final amount in Indian Rupees (can be negative for credit notes) |
| `vendor_name` | string | Canonical vendor name |
| `description` | string | Free-text expense description |
| `department` | string | Submitting department (some contain abbreviation variants) |
| `cost_center` | string | Cost centre code (e.g. `CC001`); nullable |
| `submitted_by` | string | Employee name |
| `receipt_attached` | bool | Whether a receipt was uploaded |
| `is_personal` | bool | Whether flagged as a personal expense |
| `is_flagged` | bool | Whether flagged for review |
| `flag_reason` | string | Reason for flag (nullable) |
| `is_duplicate` | bool | Whether identified as a duplicate |
| `duplicate_of` | string | Reference of the original record if duplicate |
| `approval_status` | string | `pending`, `approved`, `under_review`, etc. |
| `notes` | string | Additional notes from reviewer (nullable) |

**Key stats:**
- Total spend: ~₹390 billion across all currencies converted to INR
- 1,392 flagged transactions (9.3%)
- 1,411 personal expenses
- Currencies: INR (39.7%), USD (28%), EUR (11.3%), GBP (10.8%), SGD (5.2%), AED (5%)

---

### `ai_classification_output.csv` — 15,419 rows, 6 columns

Each expense description was run through an AI classification pipeline that assigned a spend category and a confidence score.

| Column | Type | Description |
|---|---|---|
| `txn_ref` | string | Links back to `cleaned_expenses.csv` |
| `description` | string | The expense description that was classified |
| `vendor_canonical` | string | Vendor name used in classification |
| `category` | string | AI-assigned spend category |
| `confidence` | float | Classification confidence (0.6–0.94) |
| `reasoning` | string | One-line explanation of why the category was assigned |

**Categories and approximate counts:**

| Category | Count |
|---|---|
| Miscellaneous | 6,571 |
| Cloud Infrastructure | 2,140 |
| Travel & Transport | 1,450 |
| Personal Expense | 1,411 |
| Meals & Catering | 1,253 |
| SaaS Subscriptions | 1,245 |
| Finance & Banking | 1,190 |
| Hardware & Equipment | 159 |

**Classification quality:**
- Mean confidence: 77.7%
- Low-confidence transactions (<75%): ~30% of records
- The `Miscellaneous` bucket is the largest because confidence thresholds are conservative — items that don't clearly fit a category fall through.

---

### `quality_report.json` — 41,500 issue entries

A structured log from the data cleaning pipeline. Contains metadata about every data quality issue encountered while processing the source file.

**Top-level keys:**

| Key | Value |
|---|---|
| `total_rows_in_source` | 18,736 |
| `rows_loaded` | 14,931 |
| `rows_excluded` | 3,805 |
| `issues` | Array of issue objects |
| `summary` | Aggregated statistics |

**Each issue object contains:**
- `txn_id` — the affected transaction reference
- `field` — which column had the issue
- `issue_type` — machine-readable code (see table below)
- `severity` — `CRITICAL`, `WARNING`, or `INFO`
- `raw_value` — the original bad value
- `action_taken` — what the pipeline did (excluded, loaded with null, corrected, etc.)

**Issue type reference:**

| Issue Type | Count | What It Means |
|---|---|---|
| `VENDOR_NOT_IN_ALIAS_MAP` | 15,526 | Vendor name not in master alias table; accepted as-is |
| `UNKNOWN_DEPARTMENT` | 5,673 | Department value not in canonical list |
| `NULL_SUBMITTED_BY` | 1,644 | Submitter name missing |
| `PERSONAL_EXPENSE_DETECTED` | 1,595 | Flagged as likely personal |
| `MISSING_CURRENCY_ASSUMED_INR` | 4,057 | No currency given; defaulted to INR |
| `CURRENCY_MISMATCH_AMOUNT_VS_COLUMN` | 1,119 | Currency in description doesn't match column |
| `INDIAN_NUMBER_FORMAT` | 2,605 | Amount written as "1,00,000" — parsed and normalised |
| `NULL_DATE` | 558 | Transaction date missing; row marked `under_review` or excluded |
| `NULL_AMOUNT` | 769 | Amount field was empty or unresolvable |
| `INVALID_OR_MISSING_COST_CENTER` | 1,172 | Cost centre missing or not in valid list |
| `DEPT_ABBREVIATION_CORRECTED` | 533 | Department abbreviation expanded (e.g. "IT Dept" → "IT") |
| `VENDOR_ALIAS_RESOLVED` | 2,715 | Vendor alias successfully resolved to canonical name |
| `NEAR_DUPLICATE_UNDER_REVIEW` | 2 | Possible duplicate; held for manual review |

**Severity definitions:**
- `CRITICAL` (5,886 issues) — row excluded or held for review; requires action
- `WARNING` (14,205 issues) — row loaded with a default or correction; should be audited
- `INFO` (21,409 issues) — informational only; no action needed

---

## Insight Modules

The sidebar exposes 13 pre-built insight views. Each calls a dedicated Python function that queries the merged dataset and returns structured data rendered in the browser.

### 1. 📊 Executive Overview
High-level KPIs: total transactions, total spend in INR, flagged count, personal expense count, approval status breakdown, and data quality load rate.

### 2. 🏢 Spend by Department
Groups expenses by department (with abbreviation normalisation applied), sorted by total INR spend. Shows a ranked table and a horizontal bar chart.

**Note on department names:** The source data contains many variants (e.g. `H R`, `H.R.`, `Human Resources` all map to `HR`). The app normalises these before grouping.

### 3. 🏷️ Spend by Category
Aggregates spend using the AI-assigned categories from `ai_classification_output.csv`. Includes a donut chart for visual share and a bar chart for comparison.

### 4. 🏪 Top Vendors
Ranks vendors by total INR spend with transaction count. Useful for identifying concentration risk (e.g. over-reliance on one cloud provider).

### 5. 💱 Currency Breakdown
Shows how much spend originated in each currency (converted to INR equivalent), with a donut chart and data table.

### 6. 🚩 Flagged Transactions
Lists all transactions where `is_flagged = True`, with submitter, department, amount, and description. These require human review.

### 7. 👤 Personal Expenses
Lists all transactions where `is_personal = True`. These may need to be clawed back or reimbursed.

### 8. 🤖 AI Classification Confidence
Analyses the confidence scores from `ai_classification_output.csv`. Shows the distribution of confidence buckets, the mean confidence, how many transactions fall below the 75% threshold, and per-category average confidence.

**Low confidence means:** the AI model wasn't sure which category fit best. These transactions are more likely to be miscategorised and may need human review.

### 9. 🔍 Data Quality Report
Summarises `quality_report.json`. Shows the load rate, total issues by severity, and the top issue types by frequency.

### 10. 📅 Monthly Spend Trend
Groups transactions by submission month and plots total INR spend as a bar chart. Useful for spotting seasonal patterns or budget overruns.

### 11. 🧾 Receipt Compliance
Calculates what percentage of expenses have receipts attached, overall and per department. Departments are sorted from least compliant to most.

### 12. 👥 Top Submitters
Ranks employees by total INR spend submitted. Useful for spotting outliers.

### 13. 🏦 Missing Cost Centers
Identifies transactions where `cost_center` is null, broken down by department, with sample records shown.

---

## AI Query Engine

The **AI Query** bar at the top of the screen lets you ask free-form questions in plain English. When you submit a question, the app:

1. Builds a rich context block containing aggregated statistics from all three data sources (department spend, category totals, top vendors, currency breakdown, AI confidence stats, and quality report summary)
2. Sends that context + your question to the Anthropic Claude API (`claude-sonnet-4-20250514`)
3. Displays the model's answer inline

**Example questions that work well:**
- *"Which department overspends the most relative to its transaction count?"*
- *"What are the biggest data quality risks in this dataset?"*
- *"How many transactions lack receipts and what's the financial exposure?"*
- *"Which vendor is most likely being duplicated?"*
- *"What percentage of expenses are personal and which departments are worst?"*
- *"Summarise the top 3 issues I should fix in this data."*

**What the AI cannot do:**
- Look up individual transaction IDs (the context passed to the model is aggregated summaries, not row-level data)
- Run new analytical computations — it reasons over the pre-summarised statistics provided
- Access any data outside what the three files contain

---

## Architecture

```
Browser
  │
  ├── GET /                    → renders index.html (sidebar + AI bar + content area)
  │
  ├── GET /api/insight/<key>   → calls the matching Python function, returns JSON
  │                              (data is computed fresh each request from in-memory DataFrames)
  │
  └── POST /api/ask            → builds context summary → calls Anthropic API → returns answer
```

**Data flow on startup:**
1. `app.py` loads all three files into pandas DataFrames
2. The two CSVs are merged on `txn_ref`
3. Department names are normalised using a hard-coded mapping dict
4. All 13 insight functions are registered in the `INSIGHTS` dict
5. The Flask server starts and serves requests

**No database is used.** All computation happens in-memory on the pandas DataFrames. This keeps the app dependency-free and fast for datasets of this size (~15K rows loads in under a second).

---

## Extending the App

### Add a new insight

1. Write a function in `app.py` that returns a JSON-serialisable dict or list:

```python
def insight_my_new_thing():
    result = merged.groupby("cost_center")["amount_inr"].sum().reset_index()
    return result.replace({np.nan: None}).to_dict(orient="records")
```

2. Register it in the `INSIGHTS` dict:

```python
INSIGHTS = {
    ...
    "my_new_thing": ("💡 My New Insight", insight_my_new_thing),
}
```

3. Add a renderer in `index.html` inside the `renderers` object:

```javascript
const renderers = {
  ...
  my_new_thing(data) {
    return table(data, [
      {key: 'cost_center', label: 'Cost Center'},
      {key: 'amount_inr', label: 'Total Spend', type: 'inr'},
    ]);
  },
};
```

The sidebar nav item is generated automatically from the `INSIGHTS` dict via the Jinja template.

### Change the AI model or temperature

Edit the `ask_llm()` function in `app.py`. The model string, `max_tokens`, and system prompt context are all configurable there.

### Add new data sources

Load additional CSVs or JSONs at the top of `app.py` alongside the existing files, then include them in your insight functions or in the context block sent to the AI.

---

## Known Limitations

| Limitation | Detail |
|---|---|
| No authentication | The app has no login. Don't expose it on a public network. |
| AI queries need the Anthropic API | The `/api/ask` endpoint calls `api.anthropic.com`. If the API key is missing or the network is blocked, it will return an error. |
| Aggregated AI context | The LLM query engine passes summarised statistics, not full row-level data. Very specific row-level questions will not work. |
| Department normalisation is manual | The abbreviation map in `app.py` covers observed variants. New variants in future data won't be normalised automatically. |
| No pagination | Large insight tables (e.g. flagged transactions) are capped at 50 rows in the frontend. |
| Development server | Flask's built-in server is for local use only. For production, use gunicorn or uWSGI. |

---

## Running in Production (Optional)

```bash
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:5050 app:app
```

For larger datasets, consider pre-computing heavy aggregations at startup and caching them rather than re-running on every request.

---

*Generated for the ExpenseIQ analytics dashboard. Data sources: cleaned_expenses.csv (14,931 rows), ai_classification_output.csv (15,419 rows), quality_report.json (41,500 issue entries).*

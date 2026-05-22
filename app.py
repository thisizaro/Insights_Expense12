import os, json
from flask import Flask, render_template, jsonify, request
import pandas as pd
import numpy as np
import os

app = Flask(__name__)

# ─── Load data once at startup ───────────────────────────────────────────────
BASE = os.path.join(os.path.dirname(__file__), "data")

expenses   = pd.read_csv(os.path.join(BASE, "cleaned_expenses.csv"), low_memory=False)
classified = pd.read_csv(os.path.join(BASE, "ai_classification_output.csv"), low_memory=False)
with open(os.path.join(BASE, "quality_report.json")) as f:
    quality = json.load(f)

# Merge on txn_ref
merged = expenses.merge(classified[["txn_ref","category","confidence","reasoning"]],
                        on="txn_ref", how="left")
merged["amount_inr"] = pd.to_numeric(merged["amount_inr"], errors="coerce")
merged["submission_date"] = pd.to_datetime(merged["submission_date"], errors="coerce")
merged["entry_date"]      = pd.to_datetime(merged["entry_date"], errors="coerce")

# Normalise department names
dept_map = {
    "H R":"HR","H.R.":"HR","Human Resources":"HR",
    "Legals":"Legal","It Dept":"IT","Infotech":"IT","I.T.":"IT",
    "Marketting":"Marketing","Markting":"Marketing","Mktg":"Marketing","Mktng":"Marketing",
    "Desgn":"Design","Prodct":"Product","Dev Ops":"DevOps","Dev-Ops":"DevOps",
    "Operatons":"Operations","Fiance":"Finance","Product Mgmt":"Product"
}
merged["dept_clean"] = merged["department"].replace(dept_map).str.strip()

def nan_safe(val):
    if isinstance(val, float) and np.isnan(val):
        return None
    return val

# ─── Helpers ─────────────────────────────────────────────────────────────────
def safe_dict(series):
    return {str(k): int(v) for k, v in series.items()}

def top_n(series, n=10):
    return safe_dict(series.value_counts().head(n))


# ─── Pre-built insight functions ─────────────────────────────────────────────

def insight_overview():
    total_spend = merged["amount_inr"].sum()
    flagged     = int(merged["is_flagged"].sum())
    personal    = int(merged["is_personal"].sum())
    return {
        "total_transactions": len(merged),
        "total_spend_inr": round(float(total_spend), 2),
        "flagged_transactions": flagged,
        "personal_expenses": personal,
        "approval_breakdown": safe_dict(merged["approval_status"].value_counts()),
        "data_quality_score": round(quality["rows_loaded"]/quality["total_rows_in_source"]*100, 1),
    }

def insight_spend_by_department():
    dept = merged.groupby("dept_clean")["amount_inr"].agg(["sum","count","mean"]).reset_index()
    dept.columns = ["department","total_inr","tx_count","avg_inr"]
    dept = dept.sort_values("total_inr", ascending=False).head(15)
    return dept.replace({np.nan: None}).to_dict(orient="records")

def insight_spend_by_category():
    cat = merged.groupby("category")["amount_inr"].agg(["sum","count","mean"]).reset_index()
    cat.columns = ["category","total_inr","tx_count","avg_inr"]
    cat = cat.sort_values("total_inr", ascending=False)
    return cat.replace({np.nan: None}).to_dict(orient="records")

def insight_top_vendors():
    v = merged.groupby("vendor_name")["amount_inr"].agg(["sum","count"]).reset_index()
    v.columns = ["vendor","total_inr","tx_count"]
    v = v.sort_values("total_inr", ascending=False).head(15)
    return v.replace({np.nan: None}).to_dict(orient="records")

def insight_currency_breakdown():
    c = merged.groupby("original_currency")["amount_inr"].agg(["sum","count"]).reset_index()
    c.columns = ["currency","total_inr","tx_count"]
    return c.sort_values("total_inr", ascending=False).replace({np.nan: None}).to_dict(orient="records")

def insight_flagged_transactions():
    flagged = merged[merged["is_flagged"]==True][
        ["txn_ref","submission_date","amount_inr","vendor_name","department","submitted_by","flag_reason","description"]
    ].head(50)
    flagged["submission_date"] = flagged["submission_date"].astype(str)
    return flagged.replace({np.nan: None}).to_dict(orient="records")

def insight_personal_expenses():
    personal = merged[merged["is_personal"]==True][
        ["txn_ref","submission_date","amount_inr","vendor_name","department","submitted_by","description"]
    ].head(50)
    personal["submission_date"] = personal["submission_date"].astype(str)
    return personal.replace({np.nan: None}).to_dict(orient="records")

def insight_ai_confidence():
    low = classified[classified["confidence"]<0.75]
    bins = [0.6, 0.7, 0.75, 0.85, 0.95]
    labels = ["60-70%","70-75%","75-85%","85-95%"]
    classified["conf_bucket"] = pd.cut(classified["confidence"], bins=bins, labels=labels)
    dist = safe_dict(classified["conf_bucket"].value_counts().sort_index())
    return {
        "mean_confidence": round(float(classified["confidence"].mean()), 3),
        "low_confidence_count": len(low),
        "low_confidence_pct": round(len(low)/len(classified)*100, 1),
        "distribution": dist,
        "category_avg_confidence": {
            str(k): round(float(v), 3)
            for k, v in classified.groupby("category")["confidence"].mean().items()
        }
    }

def insight_quality_report():
    issues = quality["issues"]
    by_type = {}
    by_sev  = {}
    for i in issues:
        by_type[i["issue_type"]] = by_type.get(i["issue_type"], 0) + 1
        by_sev[i["severity"]]    = by_sev.get(i["severity"], 0) + 1
    return {
        "total_rows_source": quality["total_rows_in_source"],
        "rows_loaded": quality["rows_loaded"],
        "rows_excluded": quality["rows_excluded"],
        "load_rate_pct": round(quality["rows_loaded"]/quality["total_rows_in_source"]*100, 1),
        "total_issues": len(issues),
        "issues_by_type": by_type,
        "issues_by_severity": by_sev,
        "summary": quality.get("summary", {})
    }

def insight_monthly_trend():
    m = merged.dropna(subset=["submission_date"])
    m["month"] = m["submission_date"].dt.to_period("M").astype(str)
    trend = m.groupby("month")["amount_inr"].agg(["sum","count"]).reset_index()
    trend.columns = ["month","total_inr","tx_count"]
    trend = trend.sort_values("month")
    return trend.replace({np.nan: None}).to_dict(orient="records")

def insight_receipt_compliance():
    total = len(merged)
    with_receipt = int(merged["receipt_attached"].sum())
    without = total - with_receipt
    by_dept = merged.groupby("dept_clean")["receipt_attached"].agg(
        total="count", with_receipt="sum"
    ).reset_index()
    by_dept["compliance_pct"] = (by_dept["with_receipt"]/by_dept["total"]*100).round(1)
    by_dept = by_dept.sort_values("compliance_pct")
    return {
        "overall_compliance_pct": round(with_receipt/total*100, 1),
        "with_receipt": with_receipt,
        "without_receipt": without,
        "by_department": by_dept.replace({np.nan: None}).to_dict(orient="records")
    }

def insight_submitter_leaderboard():
    s = merged.groupby("submitted_by")["amount_inr"].agg(["sum","count"]).reset_index()
    s.columns = ["submitter","total_inr","tx_count"]
    s = s.sort_values("total_inr", ascending=False).head(20)
    return s.replace({np.nan: None}).to_dict(orient="records")

def insight_missing_cost_centers():
    missing = merged[merged["cost_center"].isna()]
    by_dept = safe_dict(missing["dept_clean"].value_counts().head(10))
    return {
        "total_missing": len(missing),
        "pct_missing": round(len(missing)/len(merged)*100, 1),
        "by_department": by_dept,
        "sample": missing[["txn_ref","dept_clean","submitted_by","amount_inr"]].head(10).replace({np.nan:None}).to_dict(orient="records")
    }

INSIGHTS = {
    "overview":           ("Executive Overview",           insight_overview),
    "spend_by_dept":      ("Spend by Department",          insight_spend_by_department),
    "spend_by_category":  ("Spend by Category",            insight_spend_by_category),
    "top_vendors":        ("Top Vendors",                  insight_top_vendors),
    "currency":           ("Currency Breakdown",           insight_currency_breakdown),
    "flagged":            ("Flagged Transactions",         insight_flagged_transactions),
    "personal":           ("Personal Expenses",            insight_personal_expenses),
    "ai_confidence":      ("AI Classification Confidence", insight_ai_confidence),
    "quality":            ("Data Quality Report",          insight_quality_report),
    "monthly_trend":      ("Monthly Spend Trend",          insight_monthly_trend),
    "receipt_compliance": ("Receipt Compliance",           insight_receipt_compliance),
    "submitters":         ("Top Submitters",               insight_submitter_leaderboard),
    "cost_centers":       ("Missing Cost Centers",         insight_missing_cost_centers),
}

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    cards = [{"key": k, "label": v[0]} for k, v in INSIGHTS.items()]
    return render_template("index.html", cards=cards)

@app.route("/api/insight/<key>")
def get_insight(key):
    if key not in INSIGHTS:
        return jsonify({"error": "Unknown insight"}), 404
    _, fn = INSIGHTS[key]
    data = fn()
    return jsonify({"key": key, "label": INSIGHTS[key][0], "data": data})

@app.route("/api/ask", methods=["POST"])
def ask_llm():
    """Proxy to Anthropic API with full data context."""
    body = request.json
    user_question = body.get("question", "")
    if not user_question:
        return jsonify({"error": "No question provided"}), 400

    # Build a rich context summary
    overview = insight_overview()
    dept_spend = insight_spend_by_department()[:8]
    cat_spend  = insight_spend_by_category()
    vendors    = insight_top_vendors()[:8]
    ai_conf    = insight_ai_confidence()
    quality_d  = insight_quality_report()
    currency   = insight_currency_breakdown()

    context = f"""You are a financial data analyst AI. You have access to an expense dataset with the following characteristics:

=== DATASET OVERVIEW ===
- Total transactions loaded: {overview['total_transactions']:,}
- Total spend (INR): ₹{overview['total_spend_inr']:,.0f}
- Flagged transactions: {overview['flagged_transactions']:,}
- Personal expense records: {overview['personal_expenses']:,}
- Data quality load rate: {overview['data_quality_score']}%
- Approval breakdown: {json.dumps(overview['approval_breakdown'])}

=== SPEND BY DEPARTMENT (top 8) ===
{json.dumps(dept_spend, indent=2)}

=== SPEND BY CATEGORY ===
{json.dumps(cat_spend, indent=2)}

=== TOP VENDORS (top 8) ===
{json.dumps(vendors, indent=2)}

=== CURRENCY BREAKDOWN ===
{json.dumps(currency, indent=2)}

=== AI CLASSIFICATION ===
- Mean confidence: {ai_conf['mean_confidence']}
- Low-confidence transactions (<75%): {ai_conf['low_confidence_count']:,} ({ai_conf['low_confidence_pct']}%)
- Category avg confidence: {json.dumps(ai_conf['category_avg_confidence'])}

=== DATA QUALITY ===
- Source rows: {quality_d['total_rows_source']:,}
- Rows loaded: {quality_d['rows_loaded']:,}
- Rows excluded: {quality_d['rows_excluded']:,}
- Total issues logged: {quality_d['total_issues']:,}
- Issues by severity: {json.dumps(quality_d['issues_by_severity'])}
- Top issue types: {json.dumps(dict(list(quality_d['issues_by_type'].items())[:8]))}

Answer the user's question concisely and insightfully. Use INR amounts with ₹ symbol. Be specific with numbers. If the question is outside the data scope, say so clearly."""

    import urllib.request
    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "system": context,
        "messages": [{"role": "user", "content": user_question}]
    }).encode()

    # req = urllib.request.Request(
    #     "https://api.anthropic.com/v1/messages",
    #     data=payload,
    #     headers={
    #         "Content-Type": "application/json",
    #         "anthropic-version": "2023-06-01",
    #         "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),

    #     }
    # )
    # try:
    #     with urllib.request.urlopen(req, timeout=30) as resp:
    #         result = json.loads(resp.read())
    #         answer = "".join(b["text"] for b in result.get("content", []) if b["type"]=="text")
    #         return jsonify({"answer": answer})
    # except Exception as e:
    #     return jsonify({"error": str(e)}), 500
    if not os.environ.get("GROQ_API_KEY"):
       return jsonify({"error": "GROQ_API_KEY not set"}), 500


    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps({
            "model": "llama-3.3-70b-versatile",
            "max_tokens": 1000,
            "messages": [
                {"role": "system", "content": context},
                {"role": "user", "content": user_question}
            ]
        }).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}"  # 👈 fix
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            answer = result["choices"][0]["message"]["content"]
            return jsonify({"answer": answer})
    except Exception as e:
        import traceback
        traceback.print_exc()          # prints full error to terminal/Render logs
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5050)

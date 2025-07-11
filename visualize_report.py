import os
import json
import matplotlib.pyplot as plt

RESULT_DIR = "results"
REPORT_DIR = "report"
os.makedirs(REPORT_DIR, exist_ok=True)

with open(os.path.join(RESULT_DIR, "summary.json"), encoding="utf-8") as f:
    summary = json.load(f)

domain_name_map = {
    "부동산 거래": "Real Estate",
    "온라인 쇼핑": "Online Shopping",
    "병원 진료": "Hospital Visit",
    "도서관 대출": "Library Loan",
    "음악 스트리밍": "Music Streaming",
    "영화 정보": "Movie Info",
    "스포츠 경기": "Sports Game",
    "음식 배달": "Food Delivery",
    "항공권 예약": "Flight Booking",
    "날씨 정보": "Weather Info"
}

domains = [domain_name_map.get(d, d) for d in summary.keys()]
totals = [summary[d]["total"] for d in summary.keys()]
oks = [summary[d]["ok"] for d in summary.keys()]
fails = [summary[d]["fail"] for d in summary.keys()]
schema_errors = [summary[d]["schema_error"] for d in summary.keys()]

x = range(len(domains))
plt.figure(figsize=(12,6))
plt.bar(x, oks, label="Success", color="green")
plt.bar(x, fails, bottom=oks, label="Failed", color="red")
plt.bar(x, schema_errors, bottom=[oks[i]+fails[i] for i in x], label="Schema Error", color="gray")
plt.xticks(x, domains, rotation=45, ha="right")
plt.ylabel("Count")
plt.title("SQL Generation/Validation Results by Domain")
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(REPORT_DIR, "domain_result.png"))

# English summary report
with open(os.path.join(REPORT_DIR, "summary.md"), "w", encoding="utf-8") as f:
    f.write("# SQL Generation/Validation Results by Domain\n\n")
    for orig, eng in zip(summary.keys(), domains):
        f.write(f"## {eng}\n")
        f.write(f"- Total queries: {summary[orig]['total']}\n")
        f.write(f"- Success: {summary[orig]['ok']}\n")
        f.write(f"- Failed: {summary[orig]['fail']}\n")
        f.write(f"- Schema Error: {summary[orig]['schema_error']}\n\n")
print("Visualization and summary report saved.") 
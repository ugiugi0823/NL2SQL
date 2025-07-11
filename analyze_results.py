import os
import json
from collections import Counter, defaultdict

RESULT_DIR = "results"
SUMMARY_PATH = os.path.join(RESULT_DIR, "summary.json")

summary = defaultdict(lambda: {"total": 0, "ok": 0, "fail": 0, "schema_error": 0})

for fname in os.listdir(RESULT_DIR):
    if not fname.endswith("_result.json"): continue
    domain = fname.replace("_result.json", "")
    with open(os.path.join(RESULT_DIR, fname), encoding="utf-8") as f:
        results = json.load(f)
    for r in results:
        summary[domain]["total"] += 1
        if r["status"] == "OK":
            summary[domain]["ok"] += 1
        elif r["status"] == "스키마 오류":
            summary[domain]["schema_error"] += 1
        else:
            summary[domain]["fail"] += 1

with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print("분석 결과 저장 완료: summary.json") 
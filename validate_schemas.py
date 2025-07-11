import os
import json

SCHEMA_DIR = "schemas"
REQUIRED_COLS = {"id", "created_at", "updated_at"}

problems = []
for fname in os.listdir(SCHEMA_DIR):
    if not fname.endswith(".json"): continue
    path = os.path.join(SCHEMA_DIR, fname)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 스키마가 dict 또는 list로 올 수 있음
        if isinstance(data, dict):
            cols = set(data.keys())
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            cols = set(data[0].keys())
        else:
            raise ValueError("스키마 형식 오류")
        if not REQUIRED_COLS.issubset(cols):
            problems.append((fname, "필수 컬럼 누락: " + str(REQUIRED_COLS - cols)))
    except Exception as e:
        problems.append((fname, f"JSON 파싱 오류: {e}"))

if problems:
    print("문제 있는 스키마 파일:")
    for fname, reason in problems:
        print(f"- {fname}: {reason}")
else:
    print("모든 스키마가 정상입니다.") 
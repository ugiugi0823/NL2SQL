import os
import json
import openai
from tqdm import tqdm
import sys
import re

SCHEMA_DIR = "schemas"
API_KEY_PATH = "api_key.txt"
DOMAIN_PATH = "domains.json"

def load_api_key():
    with open(API_KEY_PATH) as f:
        return f.read().strip()

def load_domains():
    with open(DOMAIN_PATH, encoding="utf-8") as f:
        return json.load(f)

def extract_json_from_response(content):
    # 코드블록이 있으면 내부만 추출
    match = re.search(r"```json\s*(.*?)```", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    # 코드블록이 없으면 전체
    return content.strip()

def make_schema_prompt(domain):
    return f"""
도메인: {domain['name']}
설명: {domain['description']}
아래 조건을 모두 만족하는 테이블 스키마(JSON) 예시를 생성하세요.
- id, created_at, updated_at을 포함해 총 20개의 필드로 구성
- 각 필드는 type(데이터 타입)과 comment(설명)를 반드시 포함
- 예시 포맷:
{{
  "id": {{"type": "INTEGER", "comment": "기본키"}},
  "created_at": {{"type": "DATETIME", "comment": "생성일시"}},
  "updated_at": {{"type": "DATETIME", "comment": "수정일시"}},
  "field4": {{"type": "VARCHAR(100)", "comment": "설명"}},
  ... (총 20개 필드)
}}
- 설명 없이 JSON만 반환하세요. 코드블록도 사용하지 마세요.
"""

def generate_schema(api_key, domain):
    openai.api_key = api_key
    prompt = make_schema_prompt(domain)
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=1024
    )
    content = response["choices"][0]["message"]["content"].strip()
    json_str = extract_json_from_response(content)
    if not json_str:
        print(f"[ERROR] {domain['name']} 스키마 LLM 응답이 비어있음.")
        sys.exit(1)
    try:
        # JSON 파싱 가능 여부만 체크, 실제 저장은 원문
        parsed = json.loads(json_str)
        if len(parsed) < 20:
            print(f"[ERROR] {domain['name']} 스키마 필드 개수 부족: {len(parsed)}개 (20개 필요)")
            sys.exit(1)
        for k, v in parsed.items():
            if not (isinstance(v, dict) and 'type' in v and 'comment' in v):
                print(f"[ERROR] {domain['name']} 스키마 필드 '{k}'에 type/comment 누락")
                sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {domain['name']} 스키마 파싱 오류: {e}\n응답 내용: {content}")
        sys.exit(1)
    return json_str

def main():
    os.makedirs(SCHEMA_DIR, exist_ok=True)
    api_key = load_api_key()
    domains = load_domains()
    for domain in tqdm(domains, desc="도메인별 스키마 생성"):
        schema = generate_schema(api_key, domain)
        fname = os.path.join(SCHEMA_DIR, f"{domain['name']}.json")
        with open(fname, "w", encoding="utf-8") as f:
            f.write(schema)
        print(f"{domain['name']} 스키마 저장 완료: {fname}")

if __name__ == "__main__":
    main() 
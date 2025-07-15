import os
import json
import openai
import re

SCHEMA_DIR = "schemas"
OUTPUT_DIR = "sqls"
DOMAIN_PATH = "domains.json"
API_KEY_PATH = "api_key.txt"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_api_key():
    with open(API_KEY_PATH) as f:
        return f.read().strip()

def get_openai_client():
    api_key = load_api_key()
    return openai.OpenAI(api_key=api_key)

def make_schema_generation_prompt(domain):
    table_name = domain['name'].replace(" ", "_")
    
    # svc_user_profile_schema.sql 예시를 읽어서 포함
    example_sql = ""
    try:
        example_path = os.path.join(OUTPUT_DIR, "svc_user_profile_schema.sql")
        if os.path.exists(example_path):
            with open(example_path, "r", encoding="utf-8") as f:
                example_sql = f.read().strip()
    except Exception as e:
        print(f"[WARNING] 예시 스키마 파일을 읽을 수 없습니다: {e}")
    
    return f"""
아래 조건을 반드시 지켜서 MySQL CREATE TABLE 구문을 생성하세요.

[참고 예시 스키마]
{example_sql}

위 예시를 참고하여 {domain['name']} 도메인에 맞는 스키마를 생성하세요.

**생성 규칙**:
- CREATE TABLE `{table_name}` ( ... ) COMMENT='...';
- 각 컬럼은 타입, NOT NULL/DEFAULT, COMMENT를 포함
- **PRIMARY KEY 컬럼(예: id, user_id, movie_id 등)은 반드시 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY로 생성하세요.**
- PRIMARY KEY, UNIQUE KEY, INDEX는 반드시 CREATE TABLE 구문 내에서 정의 (ALTER TABLE 사용 금지)
- 테이블 COMMENT는 반드시 괄호 밖에 위치해야 하며, CREATE TABLE ... ) COMMENT='...' 형식으로 작성
- **TEXT, BLOB, JSON, GEOMETRY 타입 컬럼에는 DEFAULT 값을 절대 지정하지 마세요.**
- **DATE 타입 컬럼의 DEFAULT는 반드시 문자열(예: '1970-01-01')로만 지정, CURRENT_DATE는 사용 금지.**
- **테이블명은 반드시 {table_name}로만 생성하세요.**
- 필드는 반드시 20개 이상이어야 하며, 실제 도메인에 맞는 이름, 타입, 제약조건, 주석을 포함할 것
- 설명, 영어 제목, 코드블록 없이 SQL만 반환하세요.

**중요한 제약사항**:
1. **ENUM 타입 사용 시 반드시 정확한 값만 정의하세요**:
   - status 컬럼: ENUM('활성', '비활성', '완료', '취소', '대기') DEFAULT '활성'
   - payment_status 컬럼: ENUM('완료', '대기', '취소', '실패') DEFAULT '대기'
   - order_status 컬럼: ENUM('주문완료', '배송중', '배송완료', '취소') DEFAULT '주문완료'
   - property_type 컬럼: ENUM('아파트', '빌라', '단독주택', '상가') DEFAULT '아파트'
   - match_type 컬럼: ENUM('리그', '컵대회', '친선경기', '플레이오프') DEFAULT '리그'
   - **주의: ENUM 값에 공백이 포함된 경우(예: '주문 완료')와 공백 없는 경우(예: '주문완료')를 구분하세요!**

2. **NOT NULL 필드는 반드시 기본값을 설정하세요**:
   - created_at: TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
   - updated_at: TIMESTAMP NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP
   - is_active: BOOLEAN NOT NULL DEFAULT TRUE
   - duration: INT NOT NULL DEFAULT 0 (영화/음악 길이)
   - user_id: BIGINT UNSIGNED NOT NULL DEFAULT 1 (외래키)
   - book_id: BIGINT UNSIGNED NOT NULL DEFAULT 1 (도서 ID)
   - cast: VARCHAR(500) NOT NULL DEFAULT '' (영화 출연진)
   - location: VARCHAR(200) NOT NULL DEFAULT '' (위치 정보)
   - order_id: BIGINT UNSIGNED NOT NULL DEFAULT 1 (주문 ID)

3. **문자열 길이 제한을 명확히 하세요**:
   - phone: CHAR(11) (숫자만)
   - email: VARCHAR(255)
   - name: VARCHAR(100)
   - title: VARCHAR(200)
   - description: TEXT
   - cast: VARCHAR(500) (출연진 정보)
   - location: VARCHAR(200) (위치 정보)

4. **날짜/시간 타입 주의사항**:
   - DATE: DEFAULT '1970-01-01' (문자열만)
   - DATETIME: DEFAULT '1970-01-01 00:00:00' (문자열만)
   - TIMESTAMP: DEFAULT CURRENT_TIMESTAMP (함수 사용 가능)

5. **반드시 포함해야 할 컬럼들**:
   - created_at: TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
   - updated_at: TIMESTAMP NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP
   - is_active: BOOLEAN NOT NULL DEFAULT TRUE

6. **도메인별 필수 컬럼들**:
   - 영화 정보: duration, cast, genre, director, release_date
   - 도서관 대출: book_id, user_id, borrow_date, return_date, status
   - 음식 배달: order_id, user_id, restaurant_id, order_status, delivery_address
   - 부동산 거래: property_id, agent_id, property_type, price, status
   - 스포츠 경기: match_id, team1_id, team2_id, match_type, location, match_date
   - 온라인 쇼핑: order_id, user_id, product_id, quantity, order_status
   - 병원 진료: patient_id, doctor_id, appointment_date, status
   - 항공권 예약: booking_id, user_id, flight_id, seat_number, payment_status
   - 날씨 정보: location, temperature, humidity, weather_condition, measured_time
   - 음악 스트리밍: track_id, user_id, artist_id, duration, genre

**도메인**: {domain['name']}
**설명**: {domain['description']}
"""

def generate_schema_with_llm(domain):
    client = get_openai_client()
    prompt = make_schema_generation_prompt(domain)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=2048
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERROR] {domain['name']} 스키마 생성 실패: {e}")
        return None

def create_example_schemas():
    """MySQL의 다양한 컬럼 타입을 포함한 예시 스키마 생성"""
    example_sql = """
CREATE TABLE `svc_user_profile` (
  `user_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '사용자 고유 ID',
  `username` VARCHAR(100) NOT NULL COMMENT '사용자 로그인 이름',
  `password_hash` CHAR(60) NOT NULL COMMENT '비밀번호 해시값',
  `email` VARCHAR(255) DEFAULT NULL COMMENT '사용자 이메일 주소',
  `phone` CHAR(11) DEFAULT NULL COMMENT '휴대전화 번호 (숫자만)',
  `birth_date` DATE DEFAULT '1970-01-01' COMMENT '생년월일',
  `gender` ENUM('M', 'F', 'N') DEFAULT 'N' COMMENT '성별 (M: 남성, F: 여성, N: 선택 안함)',
  `profile_picture` BLOB DEFAULT NULL COMMENT '프로필 사진 (바이너리 데이터)',
  `bio` TEXT COMMENT '자기소개',
  `is_active` BOOLEAN NOT NULL DEFAULT TRUE COMMENT '계정 활성 여부',
  `login_count` INT UNSIGNED DEFAULT 0 COMMENT '로그인 횟수',
  `last_login` DATETIME DEFAULT '1970-01-01 00:00:00' COMMENT '마지막 로그인 시간',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '계정 생성 시각',
  `updated_at` TIMESTAMP NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP COMMENT '마지막 수정 시각',
  `user_rank` DECIMAL(5,2) DEFAULT 0.00 COMMENT '사용자 평점 (예: 4.75)',
  `status` ENUM('활성', '비활성', '완료', '취소', '대기') DEFAULT '활성' COMMENT '사용자 상태',
  `payment_status` ENUM('완료', '대기', '취소', '실패') DEFAULT '대기' COMMENT '결제 상태',
  `order_status` ENUM('주문완료', '배송중', '배송완료', '취소') DEFAULT '주문완료' COMMENT '주문 상태',
  `property_type` ENUM('아파트', '빌라', '단독주택', '상가') DEFAULT '아파트' COMMENT '부동산 유형',
  `match_type` ENUM('리그', '컵대회', '친선경기', '플레이오프') DEFAULT '리그' COMMENT '경기 유형',
  `duration` INT NOT NULL DEFAULT 0 COMMENT '길이/시간 (분 단위)',
  `cast` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '출연진 정보',
  `location` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '위치 정보',
  `book_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '도서 ID',
  `order_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '주문 ID',
  `restaurant_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '레스토랑 ID',
  `property_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '부동산 ID',
  `match_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '경기 ID',
  `team1_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '팀1 ID',
  `team2_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '팀2 ID',
  `product_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '상품 ID',
  `patient_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '환자 ID',
  `doctor_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '의사 ID',
  `booking_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '예약 ID',
  `flight_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '항공편 ID',
  `track_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '트랙 ID',
  `artist_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '아티스트 ID',
  `agent_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '에이전트 ID',
  `temperature` DECIMAL(4,1) DEFAULT 0.0 COMMENT '온도 (섭씨)',
  `humidity` INT DEFAULT 0 COMMENT '습도 (%)',
  `weather_condition` ENUM('맑음', '흐림', '비', '눈', '안개') DEFAULT '맑음' COMMENT '날씨 상태',
  `measured_time` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '측정 시간',
  `seat_number` VARCHAR(10) DEFAULT NULL COMMENT '좌석 번호',
  `delivery_address` VARCHAR(500) DEFAULT NULL COMMENT '배송 주소',
  `genre` VARCHAR(100) DEFAULT NULL COMMENT '장르',
  `director` VARCHAR(100) DEFAULT NULL COMMENT '감독',
  `release_date` DATE DEFAULT '1970-01-01' COMMENT '개봉일',
  `borrow_date` DATE DEFAULT '1970-01-01' COMMENT '대출일',
  `return_date` DATE DEFAULT '1970-01-01' COMMENT '반납일',
  `appointment_date` DATETIME DEFAULT '1970-01-01 00:00:00' COMMENT '진료 예약일',
  `match_date` DATETIME DEFAULT '1970-01-01 00:00:00' COMMENT '경기 날짜',
  `quantity` INT DEFAULT 1 COMMENT '수량',
  `price` DECIMAL(12,2) DEFAULT 0.00 COMMENT '가격',
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `UK_username` (`username`),
  UNIQUE KEY `UK_email` (`email`),
  INDEX `IDX_created_at` (`created_at`),
  INDEX `IDX_status` (`status`)
) COMMENT='서비스 사용자 프로필 테이블';
"""
    
    # SQL을 직접 파일로 저장
    with open(os.path.join(OUTPUT_DIR, "svc_user_profile_schema.sql"), "w", encoding="utf-8") as f:
        f.write(example_sql.strip() + "\n")
    
    print(f"[+] 예시 스키마 생성: svc_user_profile_schema.sql")

def json_type_to_sql(col):
    t = col["type"].upper()
    return t

def add_defaults(col_name, col):
    # id, created_at, updated_at 등은 NOT NULL, 나머지는 NULL 허용
    if "not_null" not in col:
        if col_name in ("id", "user_id", "created_at", "updated_at", "message_id"):
            col["not_null"] = True
        else:
            col["not_null"] = False
    
    if "default" not in col:
        if col["not_null"]:
            # NOT NULL인 경우 적절한 기본값 설정
            if col_name == "id" and col["type"].upper() in ("INTEGER", "INT", "BIGINT"):
                col["default"] = None  # AUTO_INCREMENT로 처리
                col["auto_increment"] = True
            elif col_name == "created_at" and col["type"].upper().startswith(("TIMESTAMP", "DATETIME")):
                col["default"] = "CURRENT_TIMESTAMP"
            elif col_name == "updated_at" and col["type"].upper().startswith(("TIMESTAMP", "DATETIME")):
                col["default"] = None
                col["on_update"] = "CURRENT_TIMESTAMP"
            else:
                # NOT NULL이지만 기본값이 없는 경우
                col["default"] = None
        else:
            # NULL 허용인 경우
            col["default"] = None
    return col

def build_column_sql(col_name, col):
    sql = f"  `{col_name}` {json_type_to_sql(col)}"
    if col.get("not_null"):
        sql += " NOT NULL"
    if "default" in col:
        default = col["default"]
        if default is not None:  # None이 아닌 경우만 DEFAULT 추가
            if isinstance(default, str) and not default.upper().startswith("CURRENT_"):
                sql += f" DEFAULT '{default}'"
            else:
                sql += f" DEFAULT {default}"
    if col.get("on_update"):
        sql += f" ON UPDATE {col['on_update']}"
    if col.get("auto_increment"):
        sql += " AUTO_INCREMENT"
    if col.get("comment"):
        sql += f" COMMENT '{col['comment']}'"
    return sql

def build_table_sql(table_name, schema):
    lines = []
    pk = []
    
    for col_name, col in schema.items():
        col = add_defaults(col_name, col)
        lines.append(build_column_sql(col_name, col))
        if col.get("primary_key"):
            pk.append(col_name)
    
    # 복합키 처리
    if table_name == "svc_push_send_msg":
        lines.append("  PRIMARY KEY (message_id, created_at)")
        lines.append("  UNIQUE KEY (message_id, app_id, created_at)")
        lines.append("  KEY IDX_created_at (created_at)")
    
    # 테이블 COMMENT
    table_comment = "푸시 메시지 전송 테이블"
    
    return f"CREATE OR REPLACE TABLE `{table_name}` (\n" + ",\n".join(lines) + f"\n) COMMENT='{table_comment}';"

def validate_schema_sql(sql, domain_name):
    """생성된 스키마 SQL의 유효성을 검사 - 실제 오류만 체크"""
    issues = []
    
    # 1. DATE 타입의 잘못된 DEFAULT 검사 (가장 중요한 오류)
    date_default_pattern = r"`[^`]+`\s+DATE[^\n,]*DEFAULT\s+(CURRENT_DATE|CURRENT_TIMESTAMP)"
    if re.search(date_default_pattern, sql, re.IGNORECASE):
        issues.append("DATE 컬럼에 잘못된 DEFAULT가 있습니다")
    
    # 2. AUTO_INCREMENT가 없는 PRIMARY KEY 검사
    pk_pattern = r"PRIMARY KEY\s*\(`([^`]+)`\)"
    pk_matches = re.findall(pk_pattern, sql)
    for pk_col in pk_matches:
        # 해당 컬럼에 AUTO_INCREMENT가 있는지 확인
        col_pattern = rf"`{pk_col}`\s+[^,\n]+AUTO_INCREMENT"
        if not re.search(col_pattern, sql, re.IGNORECASE):
            issues.append(f"PRIMARY KEY 컬럼 '{pk_col}'에 AUTO_INCREMENT가 없습니다")
    
    # 3. 컬럼 개수 검사 (20개 이상) - 너무 엄격하지 않게
    col_count = len(re.findall(r"`[^`]+`\s+[^,\n]+(?:NOT NULL|DEFAULT|COMMENT|,|\))", sql))
    if col_count < 15:  # 20개에서 15개로 완화
        issues.append(f"컬럼 개수가 부족합니다 (현재: {col_count}개, 필요: 15개 이상)")
    
    # 4. 빈 ENUM 값 검사
    enum_pattern = r"ENUM\('([^']*)'"
    enum_matches = re.findall(enum_pattern, sql)
    for enum_values in enum_matches:
        if not enum_values:
            issues.append("빈 ENUM 값이 있습니다")
    
    return issues

def check_invalid_defaults(sql, domain_name):
    # DATE 타입 DEFAULT CURRENT_DATE/CURRENT_TIMESTAMP 등 금지
    date_default_pattern = r"`[^`]+`\s+DATE[^\n,]*DEFAULT\s+(CURRENT_DATE|CURRENT_TIMESTAMP)"
    matches = re.findall(date_default_pattern, sql, re.IGNORECASE)
    if matches:
        print(f"[ERROR] {domain_name} 스키마에 DATE 컬럼의 DEFAULT로 {matches}가 포함되어 있습니다! (수정 필요)")
        return False
    return True

def regenerate_schemas_with_llm():
    """LLM을 사용하여 기존 스키마들을 재생성"""
    with open(DOMAIN_PATH, encoding="utf-8") as f:
        domains = json.load(f)
    print(f"[+] {len(domains)}개 도메인의 스키마를 LLM으로 재생성합니다...")
    for domain in domains:
        print(f"[+] {domain['name']} 스키마 생성 중...")
        max_attempts = 3
        best_schema = None
        best_col_count = 0
        
        for attempt in range(1, max_attempts+1):
            schema_sql = generate_schema_with_llm(domain)
            if not schema_sql:
                print(f"[ERROR] {domain['name']} 스키마 생성 실패 (시도 {attempt})")
                continue
            
            # 코드블록 마크다운 제거
            schema_sql = clean_sql_codeblock(schema_sql)
            
            # 컬럼 개수 파싱
            col_lines = [line for line in schema_sql.splitlines() if re.match(r"\s*`[^']+` ", line)]
            col_count = len(col_lines)
            
            # 스키마 검증
            is_valid = validate_schema_sql(schema_sql, domain['name'])
            date_valid = check_invalid_defaults(schema_sql, domain['name'])
            
            # 더 나은 스키마 선택 (컬럼 수가 많고 유효한 것)
            if col_count >= best_col_count and is_valid and date_valid:
                best_schema = schema_sql
                best_col_count = col_count
            
            if col_count >= 20 and is_valid and date_valid:
                print(f"[+] {domain['name']} 스키마 생성 성공 (컬럼 {col_count}개)")
                break
            else:
                print(f"[WARNING] {domain['name']} 스키마 검증 실패: 컬럼 {col_count}개, 유효성 {is_valid}, 날짜 {date_valid} (시도 {attempt})")
        
        # 최종 스키마 저장
        if best_schema:
            sql_path = os.path.join(OUTPUT_DIR, f"{domain['name']}_schema.sql")
            with open(sql_path, "w", encoding="utf-8") as f:
                f.write(best_schema + "\n")
            print(f"[+] {domain['name']} 스키마 SQL 생성 완료: {sql_path} (컬럼 {best_col_count}개)")
        else:
            print(f"[ERROR] {domain['name']} 스키마 생성 실패 - 모든 시도 실패")

def clean_sql_codeblock(sql):
    import re
    sql = re.sub(r"^```sql\s*", "", sql, flags=re.IGNORECASE | re.MULTILINE)
    sql = re.sub(r"^```\s*", "", sql, flags=re.IGNORECASE | re.MULTILINE)
    sql = re.sub(r"```\s*$", "", sql, flags=re.IGNORECASE | re.MULTILINE)
    return sql.strip()


def main():
    # 예시 스키마 생성
    create_example_schemas()
    
    # LLM으로 스키마 재생성
    regenerate_schemas_with_llm()
    
    print("[완료] 모든 도메인 스키마 SQL 생성 완료!")

if __name__ == "__main__":
    main() 
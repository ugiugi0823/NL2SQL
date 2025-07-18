CREATE TABLE `음악_스트리밍` (
  `music_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '음악 고유 ID',
  `title` VARCHAR(200) NOT NULL COMMENT '음악 제목',
  `artist` VARCHAR(100) NOT NULL COMMENT '아티스트 이름',
  `album` VARCHAR(100) NOT NULL COMMENT '앨범 이름',
  `release_date` DATE DEFAULT '1970-01-01' COMMENT '발매 날짜',
  `genre` ENUM('팝', '락', '힙합', '재즈', '클래식', '기타') DEFAULT '기타' COMMENT '음악 장르',
  `duration` INT NOT NULL DEFAULT 0 COMMENT '음악 길이 (초 단위)',
  `play_count` INT UNSIGNED DEFAULT 0 COMMENT '재생 횟수',
  `is_active` BOOLEAN NOT NULL DEFAULT TRUE COMMENT '음악 활성 여부',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '음악 추가 시각',
  `updated_at` TIMESTAMP NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP COMMENT '마지막 수정 시각',
  `description` TEXT COMMENT '음악 설명',
  `user_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '사용자 고유 ID (외래키)',
  `playlist_id` BIGINT UNSIGNED DEFAULT NULL COMMENT '재생목록 고유 ID (외래키)',
  `status` ENUM('활성', '비활성', '완료', '취소', '대기') DEFAULT '활성' COMMENT '음악 상태',
  `payment_status` ENUM('완료', '대기', '취소', '실패') DEFAULT '대기' COMMENT '결제 상태',
  `order_status` ENUM('주문완료', '배송중', '배송완료', '취소') DEFAULT '주문완료' COMMENT '주문 상태',
  `album_cover` BLOB COMMENT '앨범 커버 이미지 (바이너리 데이터)',
  `rating` DECIMAL(5,2) DEFAULT 0.00 COMMENT '음악 평점 (예: 4.75)',
  `language` ENUM('한국어', '영어', '일본어', '기타') DEFAULT '기타' COMMENT '음악 언어',
  `label` VARCHAR(100) DEFAULT NULL COMMENT '레코드 레이블',
  PRIMARY KEY (`music_id`),
  UNIQUE KEY `UK_title_artist` (`title`, `artist`),
  INDEX `IDX_created_at` (`created_at`),
  INDEX `IDX_artist` (`artist`),
  INDEX `IDX_genre` (`genre`)
) COMMENT='음악 스트리밍 서비스 정보 관리 테이블';

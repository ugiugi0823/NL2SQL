CREATE TABLE `음식_배달` (
  `order_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '주문 ID',
  `user_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '사용자 ID',
  `restaurant_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '레스토랑 ID',
  `delivery_address` VARCHAR(500) DEFAULT NULL COMMENT '배송 주소',
  `order_status` ENUM('주문완료', '배송중', '배송완료', '취소') DEFAULT '주문완료' COMMENT '주문 상태',
  `payment_status` ENUM('완료', '대기', '취소', '실패') DEFAULT '대기' COMMENT '결제 상태',
  `total_price` DECIMAL(12,2) NOT NULL DEFAULT 0.00 COMMENT '총 가격',
  `delivery_fee` DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '배달 비용',
  `order_date` DATETIME DEFAULT '1970-01-01 00:00:00' COMMENT '주문 날짜',
  `delivery_time` DATETIME DEFAULT '1970-01-01 00:00:00' COMMENT '배송 시간',
  `is_active` BOOLEAN NOT NULL DEFAULT TRUE COMMENT '주문 활성 여부',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '주문 생성 시각',
  `updated_at` TIMESTAMP NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP COMMENT '마지막 수정 시각',
  `quantity` INT NOT NULL DEFAULT 1 COMMENT '주문 수량',
  `menu_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '메뉴 ID',
  `delivery_person_id` BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '배달원 ID',
  `feedback` TEXT COMMENT '사용자 피드백',
  `rating` DECIMAL(2,1) DEFAULT NULL COMMENT '평점',
  `restaurant_name` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '레스토랑 이름',
  `customer_name` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '고객 이름',
  `phone` CHAR(11) DEFAULT NULL COMMENT '고객 전화번호 (숫자만)',
  `status` ENUM('활성', '비활성', '완료', '취소', '대기') DEFAULT '활성' COMMENT '주문 상태',
  PRIMARY KEY (`order_id`),
  UNIQUE KEY `UK_order_user` (`user_id`, `order_date`),
  INDEX `IDX_restaurant_id` (`restaurant_id`),
  INDEX `IDX_user_id` (`user_id`)
) COMMENT='음식 배달 주문 관리 테이블';

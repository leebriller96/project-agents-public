package com.shop.order;

import java.util.Map;

/* 주문 서비스 계약 — 상위 타입(인터페이스)은 클래스 통째 */
public interface OrderService {

    int insertOrder(Map<String, Object> row);

    int approveOrder(String orderNo);

    Map<String, Object> getOrder(String orderNo);
}

package com.shop.order;

/* 업무 안 공용 유틸 — 메서드 단위 배정 대상이 아니다(클래스 통째) */
public class OrderUtil {

    public static boolean isBlank(String s) {
        return s == null || s.trim().isEmpty();
    }

    public static String today() {
        return "20260101";
    }
}

package com.legacy.common.util;

/* 레거시 공통 문자열 유틸: 모듈·범위별로 쓰는 메서드가 다르다 */
public class StrUtil {

    public static String trimAll(String s) {
        if (s == null) { return ""; }
        return s.replace(" ", "").replace("\t", "");
    }

    public static String formatPhone(String raw) {
        String d = raw.replace("-", "");
        return d.substring(0, 3) + "-" + d.substring(3, 7) + "-" + d.substring(7);
    }

    public static boolean checkAuth(String role) {
        return role != null && (role.startsWith("ROLE_") || role.equals("ADMIN"));
    }

    public static String batchOnly(String s) {
        return "[BATCH]" + s;
    }

    public static String legacyJoin(String id) {
        return "JOIN-" + id;
    }

    public static String dead() {
        return "dead";
    }
}

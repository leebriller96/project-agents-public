package com.legacy.common.util;

import java.text.SimpleDateFormat;

/* 레거시 공통 유틸: 업무마다 쓰는 메서드가 다르다 */
public class CommonUtil {

    public static String formatDate(String yyyymmdd) {
        return padLeft(yyyymmdd, 8) + "-";
    }

    public static String padLeft(String s, int len) {
        String r = s;
        while (r.length() < len) { r = "0" + r; }
        return r;
    }

    public static String maskName(String name) {
        if (name == null) { return ""; }
        return name.substring(0, 1) + "*";
    }

    public static long calcInterest(long amount, double rate) {
        return Math.round(amount * rate / 100.0);
    }

    public static long calcInterest(long amount, double rate, int days) {
        return Math.round(amount * rate / 100.0 * days / 365.0);
    }

    public static String unusedLegacy() {
        return "legacy";
    }
}

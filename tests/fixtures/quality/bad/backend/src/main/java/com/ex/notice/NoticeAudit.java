package com.ex.notice;

import lombok.extern.slf4j.Slf4j;

/**
 * 감사 로그 기록기.
 */
@Slf4j
public class NoticeAudit {

    /**
     * 기록한다.
     *
     * @param userId 사용자
     * @param token 토큰
     */
    public void write(String userId, String token) {
        log.info("감사 기록 user=" + userId);
        log.info("토큰 발급 user={} token={}",
                userId, token);
    }
}

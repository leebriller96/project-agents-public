package com.ex.notice;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 공지사항 업무 서비스. (slice: notice)
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class NoticeService {

    private final NoticeMapper noticeMapper;

    /**
     * 공지사항을 등록한다.
     *
     * @param title 제목
     * @param password 작성자 확인 비밀번호 (로그에 남기지 않는다)
     * @return 생성된 공지 ID
     */
    @Transactional
    public long register(String title, String password) {
        long id = noticeMapper.insertNotice(title);
        log.info("공지 등록 완료 id={}", id);
        return id;
    }

    /**
     * 조회수를 1 증가시킨다. REQ-011
     *
     * @param id 공지 ID
     */
    @Transactional
    public void increaseViewCount(
            long id) {
        try {
            noticeMapper.increaseViewCount(id);
        } catch (IllegalStateException e) {
            // 조회수 증가 실패는 본 조회를 막지 않는다 (REQ-011 비기능 요구)
        }
    }

    private void helper() {
        log.debug("내부 처리");
    }
}

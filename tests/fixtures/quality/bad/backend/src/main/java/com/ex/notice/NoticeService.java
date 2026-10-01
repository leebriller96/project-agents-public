package com.ex.notice;

import org.springframework.stereotype.Service;

@Service
public class NoticeService {

    private final NoticeMapper noticeMapper = null;

    public long register(String title, String password) {
        long id = noticeMapper.insertNotice(title);
        System.out.println("등록: " + id);
        return id;
    }

    /**
     * 로그인 처리.
     *
     * @param userId 사용자 ID
     * @param password 비밀번호
     */
    public void login(String userId, String password) {
        try {
            noticeMapper.insertNotice(userId);
        } catch (RuntimeException e) {
        }
    }
}

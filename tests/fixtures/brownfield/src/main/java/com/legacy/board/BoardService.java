package com.legacy.board;

import com.legacy.common.util.StrUtil;

/* 게시판(사용자 앱) 업무 서비스 */
public class BoardService {

    public String title(String raw, String role) {
        if (!StrUtil.checkAuth(role)) {
            return "";
        }
        return StrUtil.trimAll(raw);
    }
}

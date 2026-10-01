package com.legacy.admin;

import com.legacy.common.util.StrUtil;
import java.util.List;
import org.apache.ibatis.session.SqlSession;

/* 회원 관리(관리자 앱) 업무 서비스 */
public class AdminMemberService {

    private SqlSession sqlSession;

    public String phone(String raw, String role) {
        if (!StrUtil.checkAuth(role)) {
            return "";
        }
        List<Object> codes = sqlSession.selectList("common.selectCode", "ADMIN");
        return StrUtil.formatPhone(raw) + codes.size();
    }
}

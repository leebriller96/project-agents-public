package com.legacy.member;

import com.legacy.common.util.StrUtil;
import com.legacy.join.JoinService;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.session.SqlSession;

/* 회원(사용자 앱) 업무 서비스 */
public class MemberService {

    private SqlSession sqlSession;
    private MemberDAO memberDAO;
    private JoinService joinService;

    public Map<String, Object> detail(String id, String role, String phone) {
        if (!StrUtil.checkAuth(role)) {
            return null;
        }
        if (!joinService.isJoined(StrUtil.trimAll(id))) {
            return null;
        }
        List<Object> codes = sqlSession.selectList("common.selectCode", "MEMBER");
        Map<String, Object> row = memberDAO.selectMember(id);
        row.put("phone", StrUtil.formatPhone(phone));
        row.put("codes", codes);
        return row;
    }
}

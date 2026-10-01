package com.legacy.member;

import java.util.Map;
import org.apache.ibatis.session.SqlSession;

/* 회원 DAO: purgeAll 은 아무도 부르지 않는다 */
public class MemberDAO {

    private SqlSession sqlSession;

    public Map<String, Object> selectMember(String id) {
        return sqlSession.selectOne("member.selectMember", id);
    }

    public int purgeAll() {
        return sqlSession.delete("member.deleteAll");
    }
}

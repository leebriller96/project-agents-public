package com.legacy.join;

import com.legacy.common.util.StrUtil;
import org.apache.ibatis.session.SqlSession;

/* 회원 가입: 이전 차수에서 이미 이관된 영역 */
public class JoinService {

    private SqlSession sqlSession;

    public boolean isJoined(String id) {
        Object row = sqlSession.selectOne("join.selectJoin", StrUtil.legacyJoin(id));
        return row != null;
    }
}

package com.ins.claim;

import java.util.List;
import org.apache.ibatis.session.SqlSession;

/* 구비서류 도우미 — 접수와 심사가 모두 쓴다 */
public class ClaimDocHelper {

    private SqlSession sqlSession;

    public List<Object> requiredDocs(String claimType) {
        return sqlSession.selectList("claim.selectRequiredDocs", claimType);
    }
}

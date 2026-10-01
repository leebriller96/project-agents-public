package com.ins.claim;

import java.util.List;
import org.apache.ibatis.session.SqlSession;

/* 심사 규칙 — 심사 단계만 쓴다 */
public class ReviewRuleUtil {

    private SqlSession sqlSession;

    public boolean checkDocs(String claimNo) {
        List<Object> docs = sqlSession.selectList("claim.selectReviewDocs", claimNo);
        return !docs.isEmpty();
    }
}

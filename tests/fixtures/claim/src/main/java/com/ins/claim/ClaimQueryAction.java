package com.ins.claim;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.session.SqlSession;

/* 청구 조회 */
public class ClaimQueryAction {

    private SqlSession sqlSession;
    private ClaimService claimService;

    public List<Object> list(Map<String, Object> cond) {
        return sqlSession.selectList("claim.selectClaimList", cond);
    }

    public Map<String, Object> detail(String claimNo) {
        return claimService.getClaim(claimNo);
    }
}

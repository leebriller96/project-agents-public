package com.ins.claim;

import java.util.Map;
import org.apache.ibatis.session.SqlSession;

/* 보험금 지급 */
public class ClaimPayAction {

    private SqlSession sqlSession;
    private ClaimService claimService;

    public int pay(String claimNo) {
        Map<String, Object> claim = claimService.getClaim(claimNo);
        sqlSession.insert("claim.insertPayment", claim);
        return claimService.changeStatus(claimNo, "PAID");
    }
}

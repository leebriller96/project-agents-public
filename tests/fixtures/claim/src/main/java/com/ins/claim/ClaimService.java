package com.ins.claim;

import com.ins.common.CommonUtil;
import java.util.Map;
import org.apache.ibatis.session.SqlSession;

/* 청구 공용 서비스 — 심사·지급·조회가 함께 쓴다(slice 내부 공통) */
public class ClaimService {

    private SqlSession sqlSession;

    public Map<String, Object> getClaim(String claimNo) {
        return sqlSession.selectOne("claim.selectClaim", claimNo);
    }

    public int changeStatus(String claimNo, String status) {
        String at = CommonUtil.today();
        return sqlSession.update("claim.updateStatus", claimNo + status + at);
    }

    public boolean validateReceipt(Map<String, Object> dto) {
        Object dup = sqlSession.selectOne("claim.selectDupReceipt", dto);
        return dup == null;
    }
}

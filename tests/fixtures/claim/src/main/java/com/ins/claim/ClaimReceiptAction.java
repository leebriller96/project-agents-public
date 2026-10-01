package com.ins.claim;

import java.util.Map;
import org.apache.ibatis.session.SqlSession;

/* 청구 접수 */
public class ClaimReceiptAction {

    private SqlSession sqlSession;
    private ClaimService claimService;
    private ClaimDocHelper claimDocHelper;

    public int receive(Map<String, Object> dto) {
        if (!claimService.validateReceipt(dto)) {
            return 0;
        }
        claimDocHelper.requiredDocs("ACC");
        return sqlSession.insert("claim.insertClaim", dto);
    }
}

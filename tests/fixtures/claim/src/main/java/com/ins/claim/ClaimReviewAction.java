package com.ins.claim;

import java.util.Map;

/* 청구 심사 */
public class ClaimReviewAction {

    private ClaimService claimService;
    private ClaimDocHelper claimDocHelper;
    private ReviewRuleUtil reviewRuleUtil;

    public int review(String claimNo) {
        Map<String, Object> claim = claimService.getClaim(claimNo);
        claimDocHelper.requiredDocs("ACC");
        boolean ok = reviewRuleUtil.checkDocs(claimNo);
        return claimService.changeStatus(claimNo, ok ? "REVIEWED" : "HOLD") + (claim == null ? 0 : 1);
    }
}

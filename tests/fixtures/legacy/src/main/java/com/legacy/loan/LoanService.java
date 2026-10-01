package com.legacy.loan;

import com.legacy.common.base.BaseService;
import com.legacy.common.util.CommonUtil;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.session.SqlSession;

/* 대출 업무 서비스 */
public class LoanService extends BaseService {

    private SqlSession sqlSession;

    public List<Map<String, Object>> list(Map<String, Object> session, int page) {
        String user = getLoginUserId(session);
        int offset = calcOffset(page, 10);
        writeAudit("LOAN_LIST " + user + offset);
        List<Map<String, Object>> codes = commonDAO.selectCode("LOAN_TYPE");
        return sqlSession.selectList("loan.selectLoanList", codes);
    }

    public long interest(long amount, double rate) {
        String today = CommonUtil.formatDate("20260101");
        Object rateRow = sqlSession.selectOne("deposit.selectBaseRate", today);
        return CommonUtil.calcInterest(amount, rate) + (rateRow == null ? 0 : 1);
    }
}

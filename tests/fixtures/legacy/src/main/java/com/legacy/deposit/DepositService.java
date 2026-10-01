package com.legacy.deposit;

import com.legacy.common.base.BaseService;
import com.legacy.common.util.CommonUtil;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.session.SqlSession;

/* 예금 업무 서비스 */
public class DepositService extends BaseService {

    private SqlSession sqlSession;

    public List<Map<String, Object>> list(int page, String ymd) {
        if (this.isHoliday(ymd)) {
            return null;
        }
        int offset = super.calcOffset(page, 20);
        return sqlSession.selectList("deposit.selectDepositList", offset);
    }

    public String owner(String name, long amount) {
        return CommonUtil.maskName(name) + CommonUtil.calcInterest(amount, 1.5, 30);
    }
}

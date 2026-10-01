package com.shop.order;

import java.util.Map;
import org.apache.ibatis.session.SqlSession;
import org.springframework.stereotype.Service;

/* 업무 서비스 구현체 — 메서드 단위 배정 대상 */
@Service
public class OrderServiceImpl implements OrderService {

    private SqlSession sqlSession;

    /* 접수 전용 */
    public int insertOrder(Map<String, Object> row) {
        if (getOrder(String.valueOf(row.get("orderNo"))) != null) {
            return 0;
        }
        int n = sqlSession.insert("order.insertOrder", row);
        writeHistory(String.valueOf(row.get("orderNo")));
        return n;
    }

    /* 승인 전용 */
    public int approveOrder(String orderNo) {
        Map<String, Object> order = getOrder(orderNo);
        int n = sqlSession.update("order.updateApprove", order);
        writeHistory(orderNo + OrderUtil.today());
        return n;
    }

    /* 접수·승인 공용 조회 */
    public Map<String, Object> getOrder(String orderNo) {
        return sqlSession.selectOne("order.selectOrder", orderNo);
    }

    /* 접수·승인 공용 이력 기록 — private 헬퍼 */
    private void writeHistory(String orderNo) {
        sqlSession.insert("order.insertHistory", orderNo);
    }
}

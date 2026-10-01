package com.legacy.common.base;

import com.legacy.common.dao.CommonDAO;
import java.util.List;
import java.util.Map;

/* 모든 업무 서비스의 상위 클래스 */
public abstract class BaseService {

    protected CommonDAO commonDAO;

    protected String getLoginUserId(Map<String, Object> session) {
        return (String) session.get("USER_ID");
    }

    protected void writeAudit(String action) {
        commonDAO.insertAudit(action);
    }

    protected int calcOffset(int page, int size) {
        return (page - 1) * size;
    }

    protected boolean isHoliday(String ymd) {
        List<Map<String, Object>> list = commonDAO.selectHoliday(ymd);
        return !list.isEmpty();
    }
}

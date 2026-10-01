package com.legacy.common.dao;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.session.SqlSession;

/* 공통 DAO: SqlSession 직접 호출 */
public class CommonDAO {

    private SqlSession sqlSession;

    public List<Map<String, Object>> selectCode(String groupCd) {
        return sqlSession.selectList("common.selectCode", groupCd);
    }

    public List<Map<String, Object>> selectHoliday(String ymd) {
        return sqlSession.selectList("common.selectHoliday", ymd);
    }

    public int insertAudit(String action) {
        return sqlSession.insert("common.insertAudit", action);
    }

    public Object selectDynamic(String queryId) {
        return sqlSession.selectOne(queryId);
    }
}

package com.ins.event;

import java.util.List;
import org.apache.ibatis.session.SqlSession;

/* 이벤트 목록 */
public class EventAction {

    private SqlSession sqlSession;

    public List<Object> list() {
        return sqlSession.selectList("event.selectEventList", null);
    }
}

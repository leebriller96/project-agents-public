package com.legacy.batch;

import com.legacy.common.util.StrUtil;
import java.util.List;
import org.apache.ibatis.session.SqlSession;

/* 야간 배치: 이번 차수 범위 외 */
public class NightBatch {

    private SqlSession sqlSession;

    public void run() {
        List<Object> targets = sqlSession.selectList("batch.selectTargets");
        for (Object t : targets) {
            StrUtil.batchOnly(String.valueOf(t));
        }
    }
}

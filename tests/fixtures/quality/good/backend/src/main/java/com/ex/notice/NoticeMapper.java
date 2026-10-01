package com.ex.notice;

import org.apache.ibatis.annotations.Mapper;

/**
 * 공지사항 Mapper. SQL 은 mapper/NoticeMapper.xml 참조.
 */
@Mapper
public interface NoticeMapper {

    /**
     * 공지 1건을 등록한다.
     *
     * @param title 제목
     * @return 생성된 ID
     */
    long insertNotice(String title);

    /**
     * 조회수를 1 증가시킨다.
     *
     * @param id 공지 ID
     * @return 갱신 행 수
     */
    int increaseViewCount(long id);
}

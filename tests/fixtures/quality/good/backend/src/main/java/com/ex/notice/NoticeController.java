package com.ex.notice;

import io.swagger.v3.oas.annotations.Operation;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 공지사항 API. (계약: docs/api/notice.yaml)
 */
@RestController
@RequiredArgsConstructor
public class NoticeController {

    private final NoticeService noticeService;

    /**
     * 공지를 등록한다.
     *
     * @param title 제목
     * @return 생성된 ID
     */
    @Operation(
            operationId = "createNotice",
            summary = "공지 등록")
    @PostMapping("/api/v1/notices")
    public long create(String title) {
        return noticeService.register(title, "");
    }
}

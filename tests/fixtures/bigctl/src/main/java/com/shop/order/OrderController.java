package com.shop.order;

import java.util.HashMap;
import java.util.Map;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;

/* 거대 컨트롤러 — 접수·승인 단계의 진입 메서드가 한 클래스에 몰려 있다(메서드 단위 배정 대상) */
@Controller
@RequestMapping("/order")
public class OrderController {

    private OrderService orderService;

    /* 주문 접수 — 접수 unit 전용이고 길다 */
    @RequestMapping(value = "/insert.do", method = RequestMethod.POST)
    public String insert(Map<String, Object> dto) {
        checkParam(dto);
        Map<String, Object> row = new HashMap<String, Object>();
        row.put("f01", dto.get("f01"));
        row.put("f02", dto.get("f02"));
        row.put("f03", dto.get("f03"));
        row.put("f04", dto.get("f04"));
        row.put("f05", dto.get("f05"));
        row.put("f06", dto.get("f06"));
        row.put("f07", dto.get("f07"));
        row.put("f08", dto.get("f08"));
        row.put("f09", dto.get("f09"));
        row.put("f10", dto.get("f10"));
        row.put("f11", dto.get("f11"));
        row.put("f12", dto.get("f12"));
        row.put("f13", dto.get("f13"));
        row.put("f14", dto.get("f14"));
        row.put("f15", dto.get("f15"));
        row.put("f16", dto.get("f16"));
        row.put("f17", dto.get("f17"));
        row.put("f18", dto.get("f18"));
        row.put("f19", dto.get("f19"));
        row.put("f20", dto.get("f20"));
        row.put("f21", dto.get("f21"));
        row.put("f22", dto.get("f22"));
        row.put("f23", dto.get("f23"));
        row.put("f24", dto.get("f24"));
        row.put("f25", dto.get("f25"));
        row.put("f26", dto.get("f26"));
        row.put("f27", dto.get("f27"));
        row.put("f28", dto.get("f28"));
        row.put("f29", dto.get("f29"));
        row.put("f30", dto.get("f30"));
        orderService.insertOrder(row);
        return "order/insertResult";
    }

    /* 주문 승인 — 승인 unit 전용 */
    @PostMapping("/approve.do")
    public String approve(String orderNo) {
        Map<String, Object> dto = new HashMap<String, Object>();
        dto.put("orderNo", orderNo);
        checkParam(dto);
        orderService.approveOrder(orderNo);
        return "order/approveResult";
    }

    /* 승인 취소 — API 경로가 없어 asis.methods 로 승인 unit 에 선언한다 */
    @RequestMapping("/cancel.do")
    public String cancel(String orderNo) {
        orderService.approveOrder(orderNo);
        return "order/cancelResult";
    }

    /* 과거 출력 — 쓰지 않는다(폐기) */
    @GetMapping("/legacyPrint.do")
    public String legacyPrint() {
        return "order/print";
    }

    /* 입력 점검 — 접수·승인이 함께 쓰는 private 헬퍼 */
    private void checkParam(Map<String, Object> dto) {
        if (OrderUtil.isBlank(String.valueOf(dto.get("orderNo")))) {
            dto.put("orderNo", "NEW");
        }
    }
}

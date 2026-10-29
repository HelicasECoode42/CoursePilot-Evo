package com.coursepilot.verifier.web;

import com.coursepilot.verifier.application.CareerDirectionAssembler;
import com.coursepilot.verifier.web.dto.CareerDirectionDtos;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 契约端点：listCareerDirections（contracts/java.openapi.json，/api/v1/career-directions）。
 *
 * 契约只声明了 subjectTag 查询参数，没有 limit 和 cursor，所以这里不加分页。
 * 与教师评价端点一致：参数格式在这里校验（不合法 400 INVALID_QUERY），
 * 归属由 X-Subject-Id 经 SubjectGuard 确认，服务密钥由 ServiceKeyFilter 确认。
 */
@RestController
@RequestMapping("/api/v1")
public class CareerDirectionController {

    /** 契约 subjectTag：minLength 1，maxLength 80。 */
    private static final int SUBJECT_TAG_MAX_LENGTH = 80;

    private final CareerDirectionAssembler assembler;
    private final SubjectGuard subjects;

    public CareerDirectionController(CareerDirectionAssembler assembler, SubjectGuard subjects) {
        this.assembler = assembler;
        this.subjects = subjects;
    }

    @GetMapping("/career-directions")
    public Envelope<CareerDirectionDtos.CareerDirectionList> listCareerDirections(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId,
        @RequestParam(required = false) String subjectTag) {
        subjects.require(subjectId);

        if (subjectTag != null && (subjectTag.isEmpty() || subjectTag.length() > SUBJECT_TAG_MAX_LENGTH)) {
            throw new InvalidQuery("subjectTag",
                "subjectTag 长度须在 1 到 " + SUBJECT_TAG_MAX_LENGTH + " 之间");
        }

        return Envelope.ok(requestId, assembler.list(subjectTag));
    }
}

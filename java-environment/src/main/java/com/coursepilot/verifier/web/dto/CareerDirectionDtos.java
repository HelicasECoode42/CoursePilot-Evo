package com.coursepilot.verifier.web.dto;

import java.util.List;

/**
 * 契约形状的职业方向 DTO。字段名与必填项逐条对照 contracts/schemas/domain.schema.json 的 CareerDirection，
 * 以及 contracts/java.openapi.json 的 listCareerDirections 的 data 形状（只有 items，没有其它字段）。
 *
 * 不得把 JPA 实体直接返回，必须经 CareerDirectionAssembler 映射到这里。
 */
public final class CareerDirectionDtos {

    private CareerDirectionDtos() {}

    /** contracts: CareerDirection。 */
    public record CareerDirection(
        String directionId,
        List<String> subjectTags,
        String title,
        String description,
        List<String> courseCodes,
        List<String> sourceRefIds) {}

    /** listCareerDirections 的 data。空结果是 items 为空数组，不是错误。 */
    public record CareerDirectionList(List<CareerDirection> items) {}
}

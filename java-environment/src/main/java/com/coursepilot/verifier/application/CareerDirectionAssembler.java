package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.CareerDirection;
import com.coursepilot.verifier.persistence.repo.CareerDirectionRepository;
import com.coursepilot.verifier.web.dto.CareerDirectionDtos;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * 读取职业方向并映射成契约形状。subjectTag 为 null 表示不过滤。
 *
 * 过滤在内存里做：方向条目很少，且 subjectTags 是元素集合，逐条比对更直接。
 * 没有匹配时返回空列表，这是正常的业务状态。
 */
@Service
public class CareerDirectionAssembler {

    private final CareerDirectionRepository repo;

    public CareerDirectionAssembler(CareerDirectionRepository repo) {
        this.repo = repo;
    }

    @Transactional(readOnly = true)
    public CareerDirectionDtos.CareerDirectionList list(String subjectTag) {
        List<CareerDirectionDtos.CareerDirection> items = repo.findAllByOrderByDirectionIdAsc().stream()
            .filter(d -> subjectTag == null || d.getSubjectTags().contains(subjectTag))
            .map(CareerDirectionAssembler::toDto)
            .toList();
        return new CareerDirectionDtos.CareerDirectionList(items);
    }

    private static CareerDirectionDtos.CareerDirection toDto(CareerDirection d) {
        return new CareerDirectionDtos.CareerDirection(
            d.getDirectionId(),
            List.copyOf(d.getSubjectTags()),
            d.getTitle(),
            d.getDescription(),
            List.copyOf(d.getCourseCodes()),
            List.copyOf(d.getSourceRefIds()));
    }
}

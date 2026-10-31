package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.CurriculumUnmodeledRule;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface CurriculumUnmodeledRuleRepository extends JpaRepository<CurriculumUnmodeledRule, Long> {

    /** 按工作簿行号排序，便于追溯到原表位置。 */
    List<CurriculumUnmodeledRule> findBySnapshot_SnapshotIdAndDispositionOrderBySourceRowAsc(
        String snapshotId, CurriculumUnmodeledRule.Disposition disposition);
}

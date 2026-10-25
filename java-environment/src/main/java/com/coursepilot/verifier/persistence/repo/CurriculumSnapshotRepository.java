package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import org.springframework.data.domain.Limit;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface CurriculumSnapshotRepository extends JpaRepository<CurriculumSnapshot, String> {

    /** 按种类取，最新在前。契约 items 上限 200，由调用方传 Limit 挡住。 */
    List<CurriculumSnapshot> findByKind(CurriculumSnapshot.Kind kind, Sort sort, Limit limit);

    /** 按种类与状态取，最新在前。listCurricula 只用它取 PUBLISHED，见契约 operation summary。 */
    List<CurriculumSnapshot> findByKindAndState(CurriculumSnapshot.Kind kind, CurriculumSnapshot.State state,
                                                Sort sort, Limit limit);
}

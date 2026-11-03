package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.CourseOffering;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Collection;
import java.util.List;

public interface CourseOfferingRepository extends JpaRepository<CourseOffering, String> {
    List<CourseOffering> findByCourseCode(String courseCode);

    /** 按开课快照取班次；调用方传 Pageable 挡住上限。 */
    List<CourseOffering> findBySnapshotId(String snapshotId, Pageable pageable);

    /** 按开课快照与课程号取班次；调用方传 Pageable 挡住上限。 */
    List<CourseOffering> findBySnapshotIdAndCourseCode(String snapshotId, String courseCode, Pageable pageable);

    /**
     * 按开课快照与一组课程号取全部班次（不分页）。调用方传入的课程号来自培养快照的课程表，
     * 数量受培养方案约束，因此不需要 Pageable 上限。
     */
    List<CourseOffering> findBySnapshotIdAndCourseCodeIn(String snapshotId, Collection<String> courseCodes);
}

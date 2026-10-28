package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.CurriculumCourse;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CurriculumCourseRepository extends JpaRepository<CurriculumCourse, Long> {

    @EntityGraph(attributePaths = {"course", "sourceReference"})
    @Query(value = """
        select cc from CurriculumCourse cc
        where cc.snapshot.snapshotId = :snapshotId
          and (:query is null
            or lower(cc.course.courseCode) like lower(concat('%', :query, '%'))
            or lower(cc.name) like lower(concat('%', :query, '%')))
        order by cc.course.courseCode
        """,
        countQuery = """
        select count(cc) from CurriculumCourse cc
        where cc.snapshot.snapshotId = :snapshotId
          and (:query is null
            or lower(cc.course.courseCode) like lower(concat('%', :query, '%'))
            or lower(cc.name) like lower(concat('%', :query, '%')))
        """)
    Page<CurriculumCourse> findCourses(@Param("snapshotId") String snapshotId,
                                       @Param("query") String query,
                                       Pageable pageable);

    boolean existsBySnapshot_SnapshotIdAndCourse_CourseCode(String snapshotId, String courseCode);

    @EntityGraph(attributePaths = {"course", "sourceReference"})
    java.util.Optional<CurriculumCourse> findBySnapshot_SnapshotIdAndCourse_CourseCode(
        String snapshotId, String courseCode);

    @EntityGraph(attributePaths = {"course", "sourceReference"})
    java.util.List<CurriculumCourse> findBySnapshot_SnapshotIdAndCourse_CourseCodeIn(
        String snapshotId, java.util.Collection<String> courseCodes);
}

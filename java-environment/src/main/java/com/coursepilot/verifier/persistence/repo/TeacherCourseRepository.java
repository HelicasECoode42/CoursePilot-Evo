package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.TeacherCourse;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface TeacherCourseRepository extends JpaRepository<TeacherCourse, String> {

    List<TeacherCourse> findByCurriculumSnapshotIdOrderByCourseCodeAscTeacherKeyAsc(String curriculumSnapshotId);

    boolean existsByCourseCodeAndTeacherKey(String courseCode, String teacherKey);
}

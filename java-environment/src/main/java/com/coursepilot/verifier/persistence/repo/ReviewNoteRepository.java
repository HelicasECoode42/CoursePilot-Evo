package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.ReviewNote;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ReviewNoteRepository extends JpaRepository<ReviewNote, String> {

    List<ReviewNote> findByCourseCodeOrderByReviewNoteIdAsc(String courseCode);

    List<ReviewNote> findByCourseCodeAndTeacherKeyOrderByReviewNoteIdAsc(String courseCode, String teacherKey);
}

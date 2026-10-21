package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.Course;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface CourseRepository extends JpaRepository<Course, String> {
    List<Course> findByCategory(String category);
}

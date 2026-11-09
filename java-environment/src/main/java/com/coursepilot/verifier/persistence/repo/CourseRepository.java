package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.Course;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CourseRepository extends JpaRepository<Course, String> {
}

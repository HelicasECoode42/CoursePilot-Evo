package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.CourseOffering;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface CourseOfferingRepository extends JpaRepository<CourseOffering, String> {
    List<CourseOffering> findByCourseCode(String courseCode);
}

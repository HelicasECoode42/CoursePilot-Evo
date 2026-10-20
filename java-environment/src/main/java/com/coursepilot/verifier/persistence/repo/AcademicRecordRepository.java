package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.AcademicRecord;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface AcademicRecordRepository extends JpaRepository<AcademicRecord, Long> {
    List<AcademicRecord> findByStudentId(String studentId);
}

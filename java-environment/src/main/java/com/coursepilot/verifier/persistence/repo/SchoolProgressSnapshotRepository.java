package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.SchoolProgressSnapshot;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface SchoolProgressSnapshotRepository extends JpaRepository<SchoolProgressSnapshot, String> {
    long countBySubjectId(String subjectId);
    Optional<SchoolProgressSnapshot> findBySubjectIdAndContentHash(String subjectId, String contentHash);
    Optional<SchoolProgressSnapshot> findFirstBySubjectIdOrderByImportedAtDesc(String subjectId);
}

package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.Transcript;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface TranscriptRepository extends JpaRepository<Transcript, String> {
    Optional<Transcript> findByStudentId(String studentId);
}

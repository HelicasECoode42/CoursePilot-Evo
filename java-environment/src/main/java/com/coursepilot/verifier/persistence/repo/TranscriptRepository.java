package com.coursepilot.verifier.persistence.repo;
import com.coursepilot.verifier.persistence.entity.Transcript;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TranscriptRepository extends JpaRepository<Transcript, String> {
    Transcript findByStudentId(String studentId);
}

package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.OfferingVerificationAudit;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OfferingVerificationAuditRepository
    extends JpaRepository<OfferingVerificationAudit, String> {
    List<OfferingVerificationAudit> findBySnapshotIdOrderByVerifiedAtAsc(String snapshotId);
}

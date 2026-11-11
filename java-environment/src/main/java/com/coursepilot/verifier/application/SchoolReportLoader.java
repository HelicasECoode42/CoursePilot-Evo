package com.coursepilot.verifier.application;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.coursepilot.verifier.persistence.repo.SchoolProgressSnapshotRepository;
import com.coursepilot.verifier.web.dto.RecordDtos;
import com.coursepilot.verifier.web.dto.SchoolProgressDtos;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 读取某主体最近一次导入的学校报告；没有导入则返回 SchoolReport.NONE。 */
@Service
public class SchoolReportLoader {

    private final SchoolProgressSnapshotRepository snapshots;
    private final ObjectMapper mapper;

    public SchoolReportLoader(SchoolProgressSnapshotRepository snapshots, ObjectMapper mapper) {
        this.snapshots = snapshots;
        this.mapper = mapper;
    }

    @Transactional(readOnly = true)
    SchoolReport latest(String subjectId, String curriculumSnapshotId) {
        return snapshots.findFirstBySubjectIdOrderByImportedAtDesc(subjectId)
            .map(entity -> {
                try {
                    RecordDtos.AcademicRecord record = mapper.readValue(entity.getAcademicRecordJson(),
                        RecordDtos.AcademicRecord.class);
                    if (!curriculumSnapshotId.equals(record.curriculumSnapshotId())) {
                        return SchoolReport.NONE;
                    }
                    return SchoolReport.from(mapper.readValue(entity.getSnapshotJson(),
                        SchoolProgressDtos.Snapshot.class));
                } catch (JsonProcessingException e) {
                    throw new IllegalStateException("已保存的学校报告无法读取", e);
                }
            })
            .orElse(SchoolReport.NONE);
    }
}

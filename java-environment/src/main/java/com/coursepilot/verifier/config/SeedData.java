package com.coursepilot.verifier.config;

import com.coursepilot.verifier.persistence.entity.*;
import com.coursepilot.verifier.persistence.repo.*;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Instant;

@Configuration
public class SeedData {

    @Bean
    CommandLineRunner init(CourseRepository courseRepo,
                           RequirementRepository reqRepo,
                           AcademicRecordRepository recordRepo,
                           CourseOfferingRepository offeringRepo,
                           CurriculumSnapshotRepository snapshotRepo) {
        return args -> {
            if (courseRepo.count() > 0) return;

            // 演示种子一律 SYNTHETIC/SYNTHETIC：这些不是真实教学计划，
            // 不能标成 CURRICULUM_FILE 或 VERIFIED（AGENTS.md：REAL 不能用 synthetic）。
            snapshotRepo.save(new CurriculumSnapshot("PLAN_CS_2025",
                CurriculumSnapshot.Kind.CURRICULUM, CurriculumSnapshot.State.PUBLISHED,
                CurriculumSnapshot.SourceKind.SYNTHETIC,
                CurriculumSnapshot.SourceValidation.SYNTHETIC, null,
                Instant.parse("2025-09-01T00:00:00Z")));
            // 自称来自浏览器快照但尚未核验，用来说明 sourceKind 不决定
            // sourceValidation：上传者给的标签不能让它自动变 VERIFIED。
            snapshotRepo.save(new CurriculumSnapshot("PLAN_CS_2024",
                CurriculumSnapshot.Kind.CURRICULUM, CurriculumSnapshot.State.PUBLISHED,
                CurriculumSnapshot.SourceKind.BROWSER_SNAPSHOT,
                CurriculumSnapshot.SourceValidation.UNVERIFIED, null,
                Instant.parse("2024-09-01T00:00:00Z")));
            // 开课快照同表不同 kind，listCurricula 不应把它列出来。
            snapshotRepo.save(new CurriculumSnapshot("OFFER_2025_FALL",
                CurriculumSnapshot.Kind.OFFERING, CurriculumSnapshot.State.PUBLISHED,
                CurriculumSnapshot.SourceKind.SYNTHETIC,
                CurriculumSnapshot.SourceValidation.SYNTHETIC, "2025-FALL",
                Instant.parse("2025-08-15T00:00:00Z")));

            courseRepo.save(new Course("CS101", "Java 程序设计", 3.0, "必修"));
            courseRepo.save(new Course("CS102", "数据结构", 4.0, "必修"));
            courseRepo.save(new Course("GE101", "通识写作", 2.0, "通识"));
            courseRepo.save(new Course("CS103", "操作系统", null, "必修")); // 学分未知

            reqRepo.save(new Requirement("PLAN_CS_2025", "必修", 10.0));
            reqRepo.save(new Requirement("PLAN_CS_2025", "通识", 4.0));

            recordRepo.save(new AcademicRecord("S001", "CS101", true, 3.0, 1));
            recordRepo.save(new AcademicRecord("S001", "CS101", true, 3.0, 2)); // 重修，应去重
            recordRepo.save(new AcademicRecord("S001", "CS102", true, 4.0, 1));
            recordRepo.save(new AcademicRecord("S001", "GE101", true, 2.0, 1));

            offeringRepo.save(new CourseOffering("O_CS101_01", "CS101", "张老师",
                "周一第1-2节{第1-16周}", "SYNTHETIC"));
            offeringRepo.save(new CourseOffering("O_CS102_01", "CS102", "李老师",
                "周一第2-3节{第1-16周}", "SYNTHETIC"));
            offeringRepo.save(new CourseOffering("O_CS103_01", "CS103", "王老师",
                "时间待定", "SYNTHETIC")); // 时间未知
        };
    }
}

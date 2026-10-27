package com.coursepilot.verifier.config;

import com.coursepilot.verifier.persistence.entity.*;
import com.coursepilot.verifier.persistence.repo.*;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

@Configuration
public class SeedData {

    @Bean
    CommandLineRunner init(CourseRepository courseRepo,
                           RequirementRepository reqRepo,
                           CourseOfferingRepository offeringRepo,
                           TranscriptRepository transcriptRepo,
                           ReviewNoteRepository reviewRepo) {
        return args -> {
            // 如果已经有课程数据，说明不是第一次启动，直接跳过
            if (courseRepo.count() > 0) return;

            // 1. 插入课程库 (原样保留)
            courseRepo.save(new Course("CS101", "Java 程序设计", new BigDecimal("3.0"), "必修"));
            courseRepo.save(new Course("CS102", "数据结构", new BigDecimal("4.0"), "必修"));
            courseRepo.save(new Course("GE101", "通识写作", new BigDecimal("2.0"), "通识"));
            courseRepo.save(new Course("CS103", "操作系统", null, "必修")); // 故意留个学分未知的

            // 2. 插入培养要求 (原样保留)
            reqRepo.save(new Requirement("PLAN_CS_2025", "必修", new BigDecimal("10.0")));
            reqRepo.save(new Requirement("PLAN_CS_2025", "通识", new BigDecimal("4.0")));

            // 3. 插入班次 (原样保留)
            offeringRepo.save(new CourseOffering("O_CS101_01", "CS101", "张老师", "周一第1-2节{第1-16周}", "SYNTHETIC"));
            offeringRepo.save(new CourseOffering("O_CS102_01", "CS102", "李老师", "周一第2-3节{第1-16周}", "SYNTHETIC"));
            offeringRepo.save(new CourseOffering("O_CS103_01", "CS103", "王老师", "时间待定", "SYNTHETIC"));

            // ==========================================
            // 4. Issue #32: 插入学业记录聚合实体 (替代旧版 AcademicRecord)
            // ==========================================
            Transcript transcript = new Transcript();
            transcript.setAcademicRecordId("REC-2026-001"); // 记录ID
            transcript.setStudentId("S001");                // 学生ID
            transcript.setCurriculumSnapshotId("SNAP-2025");// 快照ID
            transcript.setTranscriptComplete(true);         // 是否完整
            transcript.setSourceKind("SYNTHETIC");          // 来源
            transcript.setRevision(1);                      // 版本号
            transcript.setCreatedAt(LocalDateTime.now());   // 创建时间

            // 创建子表里的已修课程
            CompletedCourse c1 = new CompletedCourse();
            c1.setCourseCode("CS101"); c1.setCourseName("Java 程序设计"); c1.setCredits(new BigDecimal("3.0")); c1.setPassed(true);

            CompletedCourse c2 = new CompletedCourse();
            c2.setCourseCode("CS102"); c2.setCourseName("数据结构"); c2.setCredits(new BigDecimal("4.0")); c2.setPassed(true);

            // 把课程塞给记录，并保存
            transcript.setCompletedCourses(List.of(c1, c2));
            transcriptRepo.save(transcript);


            // ==========================================
            // 5. Issue #31: 插入教师评价实体 (独立维度)
            // ==========================================
            ReviewNote r1 = new ReviewNote();
            r1.setCourseCode("CS101");
            r1.setTeacherName("张老师");
            r1.setSemester("2025-Fall");
            r1.setGpaImpact(4.5);               // 高绩点影响
            r1.setAttendance("随机签到");         // 签到维度
            r1.setWorkload("代码量大");           // 工作量维度
            r1.setTeachingQuality("清晰幽默");     // 授课评价维度
            r1.setContent("老师人很好，但是作业有点多，注意平时分。");
            r1.setSourceId("REVIEW-001");
            r1.setIdentityRole("匿名学生");

            reviewRepo.save(r1);
        };
    }
}

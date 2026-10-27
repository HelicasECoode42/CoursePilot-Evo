CREATE TABLE course (
                      course_code VARCHAR(32) PRIMARY KEY,
                      name VARCHAR(128) NOT NULL,
                      credits DECIMAL(10,2),
                      category VARCHAR(32)
);
-- 补充其他表

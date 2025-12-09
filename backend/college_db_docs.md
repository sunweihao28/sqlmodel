# 数据库文档说明

## 1. 数据库整体概述

本数据库是一个完整的大学教务管理系统数据库，主要用于管理大学的教学资源、课程安排、学生信息、教师信息等。数据库包含11个表，46个字段，涵盖了从基础设施（教室）到教学管理（课程、选课）再到学术管理（导师指导）等多个方面的数据。

主要用途：
- 管理学校各类教学资源
- 记录学生选课和成绩信息
- 管理教师授课安排
- 维护课程和先修课程关系
- 跟踪导师指导关系

## 2. 表业务含义和用途说明

| 表名 | 业务含义 | 用途说明 |
|------|----------|----------|
| advisor | 导师指导关系 | 记录学生与导师的指导关系 |
| classroom | 教室信息 | 记录学校所有教室的位置和容量信息 |
| course | 课程信息 | 记录学校开设的所有课程信息 |
| department | 院系信息 | 记录学校的各个院系及其预算信息 |
| instructor | 教师信息 | 记录所有在职教师的基本信息 |
| prereq | 先修课程 | 记录课程之间的先修关系 |
| section | 课程开课信息 | 记录课程的具体开课安排 |
| student | 学生信息 | 记录所有在校学生的基本信息 |
| takes | 学生选课 | 记录学生的选课和成绩信息 |
| teaches | 教师授课 | 记录教师的授课安排 |
| time_slot | 时间安排 | 记录课程的时间段安排 |

## 3. 表关联关系分析

数据库表之间存在以下主要关联关系：
1. **院系与教师/学生**：
   - department.dept_name → instructor.dept_name
   - department.dept_name → student.dept_name

2. **课程与院系**：
   - department.dept_name → course.dept_name

3. **课程与先修课程**：
   - course.course_id → prereq.course_id
   - course.course_id → prereq.prereq_id

4. **课程与开课**：
   - course.course_id → section.course_id

5. **教室与开课**：
   - classroom.(building, room_number) → section.(building, room_number)

6. **学生与选课**：
   - student.ID → takes.ID
   - section.(course_id, sec_id, semester, year) → takes.(course_id, sec_id, semester, year)

7. **教师与授课**：
   - instructor.ID → teaches.ID
   - section.(course_id, sec_id, semester, year) → teaches.(course_id, sec_id, semester, year)

8. **导师指导**：
   - student.ID → advisor.s_ID
   - instructor.ID → advisor.i_ID

## 4. 重要字段业务含义说明

- **department.budget**：院系年度预算，用于财务管理
- **instructor.salary**：教师薪资，用于人事管理
- **student.tot_cred**：学生已获得的总学分，用于毕业审核
- **course.credits**：课程学分，用于计算学生总学分
- **section.time_slot_id**：课程时间段，需与time_slot表关联获取具体时间
- **takes.grade**：学生课程成绩，用于成绩管理和学分计算
- **classroom.capacity**：教室容量，用于课程安排时的教室分配
- **prereq.prereq_id**：先修课程ID，用于课程选修资格验证

## 5. 数据约束和完整性说明

1. **主键约束**：
   - 每个表都有明确的主键设置，确保数据唯一性
   - 复合主键：classroom、section、takes、teaches、time_slot使用复合主键

2. **外键约束**：
   - 所有标注的外键关系都确保了数据的引用完整性
   - 删除或修改主表数据时，需要考虑关联表中的数据

3. **非空约束**：
   - 关键字段如ID、name等设置为NOT NULL，确保数据完整性

4. **数据类型约束**：
   - 合理设置了各字段的数据类型和长度限制
   - 如decimal类型用于金融和数值计算相关字段

## 6. 使用建议和注意事项

1. **数据操作建议**：
   - 新增课程时需同时考虑prereq表中的先修课程关系
   - 分配教室时需检查classroom.capacity是否满足需求
   - 学生选课需验证是否满足先修课程要求

2. **性能建议**：
   - 学生选课(takes)数据量较大(30,000行)，查询时需考虑优化
   - 导师关系(advisor)表关联学生和教师，高频查询可考虑建立索引

3. **数据维护建议**：
   - 定期检查外键约束的完整性
   - 学期开始时需要更新section表的新学期开课信息
   - 学年结束时需要归档历史数据

4. **注意事项**：
   - 删除院系前需确保没有关联的教师、学生和课程
   - 修改课程ID时需同步更新相关表的关联字段
   - 时间安排(time_slot)与开课(section)的关联需保持一致性

本数据库设计合理，表结构清晰，能够满足大学教务管理的基本需求。使用时应遵循上述建议，确保数据的一致性和完整性。
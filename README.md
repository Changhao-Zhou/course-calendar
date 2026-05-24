# 大学课表 ICS 日历

这个仓库用于生成一个可以被苹果日历订阅的 `schedule.ics`。推荐发布方式是 GitHub Pages：

```text
https://你的用户名.github.io/仓库名/schedule.ics
```

## 文件说明

- `calendar_config.json`：日历名称、时区、学期第一周周一日期、默认提醒时间。
- `courses.csv`：基础课表。
- `changes.csv`：停课、调课、补课、临时修改。
- `generate_ics.py`：生成 `schedule.ics` 的脚本。
- `schedule.ics`：苹果日历订阅的目标文件，由脚本生成。

## 基础课表

编辑 `courses.csv`。字段如下：

```text
course_id,title,weekday,start_time,end_time,start_week,end_week,week_type,location,teacher,notes,alarm_minutes
```

- `course_id`：课程唯一 ID，例如 `math101`。后续调课要用它定位原课程。
- `weekday`：1-7 或 `周一` 到 `周日`。
- `week_type`：`all`、`odd`、`even`，分别代表每周、单周、双周。
- `alarm_minutes`：上课前几分钟提醒；留空则使用默认提醒；写 `none` 表示不提醒。

可以参考 `courses.example.csv`。

## 从一维课表 Excel 导入

如果新课表还是“星期、周次、节次、上课地点、课程名称、任课教师”这种一维表，可以直接导入：

```powershell
python .\import_timetable.py --input "E:\OneDrive\01_本科课程\一维课表.xlsx" --sheet "一维课表"
python .\generate_ics.py
```

节次对应时间写在 `period_times.json`，当前采用教务处〔2025〕83 号通知里的“春明湖校区作息时间安排”。如果学校调整作息时间，改这个文件后重新运行 `generate_ics.py` 即可。

## 调课、停课、补课

编辑 `changes.csv`。字段如下：

```text
action,course_id,original_date,new_date,new_start_time,new_end_time,new_title,new_location,new_teacher,notes,alarm_minutes
```

支持的 `action`：

- `cancel`：停课，需要 `course_id` 和 `original_date`。
- `reschedule`：调课，需要 `course_id`、`original_date`、`new_date`，时间和地点可按需填写。
- `update`：修改某一次课，例如换教室。
- `extra`：新增补课，需要 `new_date`、`new_start_time`、`new_end_time`、`new_title`。

可以参考 `changes.example.csv`。

## 生成

```powershell
python .\generate_ics.py
```

脚本会生成或覆盖 `schedule.ics`。

为提高苹果日历订阅兼容性，`schedule.ics` 中的事件时间会写成 UTC `Z` 时间；在中国大陆、香港等 UTC+8 时区查看时，会自动显示为课表里的本地上课时间。

## 发布到 GitHub Pages

1. 在 GitHub 新建一个公开仓库，例如 `course-calendar`。
2. 把本目录推送到仓库。
3. 在 GitHub 仓库页面打开 `Settings -> Pages`。
4. `Build and deployment` 选择 `Deploy from a branch`。
5. Branch 选择 `main`，目录选择 `/root`，保存。
6. 等待 Pages 部署完成。
7. 在苹果日历订阅：

```text
https://你的用户名.github.io/course-calendar/schedule.ics
```

以后更新课表时，只需要修改 `courses.csv` 或 `changes.csv`，运行脚本，提交并推送。订阅地址保持不变。

如果订阅成功但日历里暂时看不到课程，可以先订阅 `test.ics` 排查链路：

```text
https://你的用户名.github.io/course-calendar/test.ics
```

这个文件只有一条测试事件，能显示则说明客户端订阅正常。

## 隐私提醒

GitHub Pages 免费公开发布时，知道地址的人可以访问你的课表。如果课程、教室、老师信息不适合公开，不建议使用公开仓库。

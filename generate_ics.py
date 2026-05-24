from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "calendar_config.json"
COURSES_PATH = ROOT / "courses.csv"
CHANGES_PATH = ROOT / "changes.csv"
OUTPUT_PATH = ROOT / "schedule.ics"
UID_DOMAIN = "course-calendar.local"

WEEKDAYS = {
    "1": 0,
    "mon": 0,
    "monday": 0,
    "周一": 0,
    "星期一": 0,
    "2": 1,
    "tue": 1,
    "tuesday": 1,
    "周二": 1,
    "星期二": 1,
    "3": 2,
    "wed": 2,
    "wednesday": 2,
    "周三": 2,
    "星期三": 2,
    "4": 3,
    "thu": 3,
    "thursday": 3,
    "周四": 3,
    "星期四": 3,
    "5": 4,
    "fri": 4,
    "friday": 4,
    "周五": 4,
    "星期五": 4,
    "6": 5,
    "sat": 5,
    "saturday": 5,
    "周六": 5,
    "星期六": 5,
    "7": 6,
    "sun": 6,
    "sunday": 6,
    "周日": 6,
    "周天": 6,
    "星期日": 6,
    "星期天": 6,
}

CANCEL_ACTIONS = {"cancel", "cancelled", "canceled", "停课", "取消"}
RESCHEDULE_ACTIONS = {"reschedule", "move", "调课", "改期"}
EXTRA_ACTIONS = {"extra", "add", "补课", "新增"}
UPDATE_ACTIONS = {"update", "change", "修改", "变更"}


@dataclass(frozen=True)
class Event:
    uid_source: str
    course_id: str
    title: str
    start: datetime
    end: datetime
    location: str = ""
    teacher: str = ""
    notes: str = ""
    alarm_minutes: int | None = None


def clean(value: str | None) -> str:
    return (value or "").strip()


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            return []
        rows = []
        for row in reader:
            normalized = {key: clean(value) for key, value in row.items() if key is not None}
            if any(normalized.values()):
                rows.append(normalized)
        return rows


def parse_date(value: str, field_name: str) -> date:
    value = clean(value)
    if not value:
        raise ValueError(f"{field_name} is required")
    return date.fromisoformat(value)


def parse_time(value: str, field_name: str) -> time:
    value = clean(value)
    if not value:
        raise ValueError(f"{field_name} is required")
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            pass
    raise ValueError(f"{field_name} must use HH:MM, got {value!r}")


def parse_int(value: str, field_name: str) -> int:
    value = clean(value)
    if not value:
        raise ValueError(f"{field_name} is required")
    return int(value)


def parse_alarm(value: str, default_alarm: int | None) -> int | None:
    value = clean(value)
    if value == "":
        return default_alarm
    if value.lower() in {"none", "off", "no", "false", "不提醒", "无"}:
        return None
    return int(value)


def parse_weekday(value: str) -> int:
    key = clean(value).lower()
    if key not in WEEKDAYS:
        raise ValueError(f"weekday must be 1-7, 周一-周日, or English weekday, got {value!r}")
    return WEEKDAYS[key]


def matches_week_type(week: int, week_type: str) -> bool:
    key = clean(week_type).lower()
    if key in {"", "all", "every", "weekly", "每周", "全周"}:
        return True
    if key in {"odd", "single", "单", "单周"}:
        return week % 2 == 1
    if key in {"even", "double", "双", "双周"}:
        return week % 2 == 0
    raise ValueError(f"week_type must be all/odd/even, got {week_type!r}")


def combine_local(day: date, clock: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, clock).replace(tzinfo=tz)


def event_key(course_id: str, original_date: date) -> str:
    return f"{course_id}:{original_date.isoformat()}"


def uid_from(source: str) -> str:
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:16]
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", source).strip("-")[:40] or "event"
    return f"{safe}-{digest}@{UID_DOMAIN}"


def build_description(event: Event) -> str:
    parts = []
    if event.teacher:
        parts.append(f"教师: {event.teacher}")
    if event.notes:
        parts.append(event.notes)
    return "\n".join(parts)


def expand_courses(rows: list[dict[str, str]], term_start: date, tz: ZoneInfo, default_alarm: int | None) -> dict[str, Event]:
    events: dict[str, Event] = {}
    for line_number, row in enumerate(rows, start=2):
        course_id = clean(row.get("course_id"))
        if not course_id:
            raise ValueError(f"courses.csv line {line_number}: course_id is required")

        title = clean(row.get("title"))
        if not title:
            raise ValueError(f"courses.csv line {line_number}: title is required")

        weekday = parse_weekday(row.get("weekday", ""))
        start_time = parse_time(row.get("start_time", ""), "start_time")
        end_time = parse_time(row.get("end_time", ""), "end_time")
        start_week = parse_int(row.get("start_week", ""), "start_week")
        end_week = parse_int(row.get("end_week", ""), "end_week")
        if end_week < start_week:
            raise ValueError(f"courses.csv line {line_number}: end_week must be >= start_week")

        week_type = row.get("week_type", "all")
        alarm = parse_alarm(row.get("alarm_minutes", ""), default_alarm)

        for week in range(start_week, end_week + 1):
            if not matches_week_type(week, week_type):
                continue
            day = term_start + timedelta(days=(week - 1) * 7 + weekday)
            start = combine_local(day, start_time, tz)
            end = combine_local(day, end_time, tz)
            if end <= start:
                end += timedelta(days=1)

            key = event_key(course_id, day)
            if key in events:
                raise ValueError(f"duplicate event for {key}")

            events[key] = Event(
                uid_source=key,
                course_id=course_id,
                title=title,
                start=start,
                end=end,
                location=clean(row.get("location")),
                teacher=clean(row.get("teacher")),
                notes=clean(row.get("notes")),
                alarm_minutes=alarm,
            )
    return events


def apply_changes(
    events: dict[str, Event],
    rows: list[dict[str, str]],
    tz: ZoneInfo,
    default_alarm: int | None,
) -> dict[str, Event]:
    updated = dict(events)
    for line_number, row in enumerate(rows, start=2):
        action = clean(row.get("action")).lower()
        if not action:
            continue

        course_id = clean(row.get("course_id"))
        original_date_text = clean(row.get("original_date"))
        target_key = ""
        original_event: Event | None = None
        if course_id and original_date_text:
            original_date = parse_date(original_date_text, "original_date")
            target_key = event_key(course_id, original_date)
            original_event = updated.get(target_key)

        if action in CANCEL_ACTIONS:
            if not target_key:
                raise ValueError(f"changes.csv line {line_number}: cancel needs course_id and original_date")
            updated.pop(target_key, None)
            continue

        if action in RESCHEDULE_ACTIONS or action in UPDATE_ACTIONS:
            if not target_key:
                raise ValueError(f"changes.csv line {line_number}: {action} needs course_id and original_date")
            if original_event is None:
                raise ValueError(f"changes.csv line {line_number}: cannot find original event {target_key}")

            new_date = parse_date(row.get("new_date") or original_event.start.date().isoformat(), "new_date")
            new_start_time = parse_time(row.get("new_start_time") or original_event.start.strftime("%H:%M"), "new_start_time")
            new_end_time = parse_time(row.get("new_end_time") or original_event.end.strftime("%H:%M"), "new_end_time")
            start = combine_local(new_date, new_start_time, tz)
            end = combine_local(new_date, new_end_time, tz)
            if end <= start:
                end += timedelta(days=1)

            title = clean(row.get("new_title")) or original_event.title
            location = clean(row.get("new_location")) or original_event.location
            teacher = clean(row.get("new_teacher")) or original_event.teacher
            notes = clean(row.get("notes"))
            if action in RESCHEDULE_ACTIONS:
                change_note = f"调课: 原日期 {original_event.start.date().isoformat()}"
                notes = f"{change_note}\n{notes}".strip()
                updated.pop(target_key, None)

            updated[target_key] = replace(
                original_event,
                title=title,
                start=start,
                end=end,
                location=location,
                teacher=teacher,
                notes=notes or original_event.notes,
                alarm_minutes=parse_alarm(row.get("alarm_minutes", ""), original_event.alarm_minutes),
            )
            continue

        if action in EXTRA_ACTIONS:
            new_date = parse_date(row.get("new_date", ""), "new_date")
            new_start_time = parse_time(row.get("new_start_time", ""), "new_start_time")
            new_end_time = parse_time(row.get("new_end_time", ""), "new_end_time")
            title = clean(row.get("new_title"))
            if not title:
                raise ValueError(f"changes.csv line {line_number}: extra needs new_title")
            start = combine_local(new_date, new_start_time, tz)
            end = combine_local(new_date, new_end_time, tz)
            if end <= start:
                end += timedelta(days=1)

            source = f"extra:{line_number}:{title}:{start.isoformat()}"
            updated[source] = Event(
                uid_source=source,
                course_id=course_id,
                title=title,
                start=start,
                end=end,
                location=clean(row.get("new_location")),
                teacher=clean(row.get("new_teacher")),
                notes=clean(row.get("notes")),
                alarm_minutes=parse_alarm(row.get("alarm_minutes", ""), default_alarm),
            )
            continue

        raise ValueError(f"changes.csv line {line_number}: unknown action {action!r}")

    return updated


def escape_ical_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def format_dt(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


def format_dt_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fold_ical_line(line: str) -> list[str]:
    remaining = line.encode("utf-8")
    lines = []
    first = True
    while remaining:
        limit = 75 if first else 74
        chunk_size = min(limit, len(remaining))
        while chunk_size > 0:
            try:
                chunk = remaining[:chunk_size].decode("utf-8")
                break
            except UnicodeDecodeError:
                chunk_size -= 1
        else:
            raise UnicodeDecodeError("utf-8", remaining, 0, 1, "cannot fold line")
        lines.append(chunk if first else f" {chunk}")
        remaining = remaining[chunk_size:]
        first = False
    return lines or [""]


def add_prop(lines: list[str], name: str, value: str) -> None:
    lines.extend(fold_ical_line(f"{name}:{value}"))


def format_offset(offset: timedelta) -> str:
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"{sign}{hours:02d}{minutes:02d}"


def build_timezone_lines(tzid: str, tz: ZoneInfo, sample_date: date) -> list[str]:
    sample = datetime.combine(sample_date, time(12, 0)).replace(tzinfo=tz)
    offset = sample.utcoffset() or timedelta(hours=8)
    tzname = sample.tzname() or tzid
    return [
        "BEGIN:VTIMEZONE",
        f"TZID:{tzid}",
        f"X-LIC-LOCATION:{tzid}",
        "BEGIN:STANDARD",
        f"TZOFFSETFROM:{format_offset(offset)}",
        f"TZOFFSETTO:{format_offset(offset)}",
        f"TZNAME:{tzname}",
        "DTSTART:19700101T000000",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]


def build_ics(events: list[Event], calendar_name: str, tzid: str, tz: ZoneInfo, term_start: date) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Changhao-Zhou//Course Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    add_prop(lines, "X-WR-CALNAME", escape_ical_text(calendar_name))

    for event in sorted(events, key=lambda item: (item.start, item.title)):
        lines.append("BEGIN:VEVENT")
        add_prop(lines, "UID", uid_from(event.uid_source))
        add_prop(lines, "DTSTAMP", now)
        add_prop(lines, "DTSTART", format_dt_utc(event.start))
        add_prop(lines, "DTEND", format_dt_utc(event.end))
        add_prop(lines, "SUMMARY", escape_ical_text(event.title))
        if event.location:
            add_prop(lines, "LOCATION", escape_ical_text(event.location))
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main() -> int:
    config = load_json(CONFIG_PATH)
    calendar_name = clean(config.get("calendar_name")) or "大学课表"
    tzid = clean(config.get("timezone")) or "Asia/Hong_Kong"
    term_start = parse_date(config.get("term_start_date", ""), "term_start_date")
    default_alarm = config.get("default_alarm_minutes", 15)
    default_alarm = None if default_alarm is None else int(default_alarm)

    tz = ZoneInfo(tzid)
    events = expand_courses(read_rows(COURSES_PATH), term_start, tz, default_alarm)
    events = apply_changes(events, read_rows(CHANGES_PATH), tz, default_alarm)

    OUTPUT_PATH.write_text(
        build_ics(list(events.values()), calendar_name, tzid, tz, term_start),
        encoding="utf-8",
        newline="",
    )
    print(f"Generated {OUTPUT_PATH.name} with {len(events)} events.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)

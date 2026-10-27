"""Business contact SLA deadline calculator based on working hours."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def calculate_contact_deadline(
    now: datetime.datetime | None = None,
    *,
    start_hour: int = 8,
    end_hour: int = 21,
    commit_hours: float = 4.0,
) -> tuple[datetime.datetime, str]:
    """Calculate the promised contact deadline and format a natural Vietnamese string.

    Working hours: default 08:00 to 21:00 (Vietnam time).
    Outside working hours or near closing, deadline rolls over to the next business morning.
    Rounded up to the nearest 30 minutes (e.g., 'trước 12h trưa nay', 'trước 16h30 chiều nay').
    """
    if now is None:
        now = datetime.datetime.now(VN_TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=VN_TZ)
    else:
        now = now.astimezone(VN_TZ)

    current = now
    remaining_minutes = commit_hours * 60.0

    for _ in range(30):  # safety bounded search
        day_open = current.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        day_close = current.replace(hour=end_hour, minute=0, second=0, microsecond=0)

        if current < day_open:
            current = day_open
        elif current >= day_close:
            current = (current + datetime.timedelta(days=1)).replace(
                hour=start_hour, minute=0, second=0, microsecond=0
            )
            continue

        available_minutes = (day_close - current).total_seconds() / 60.0
        if remaining_minutes <= available_minutes:
            target = current + datetime.timedelta(minutes=remaining_minutes)
            # Round up to 30 min boundary
            rem = target.minute % 30
            if rem > 0:
                target += datetime.timedelta(minutes=(30 - rem))
            target = target.replace(second=0, microsecond=0)
            target = min(target, day_close)
            return target, format_deadline_text(target, now)

        remaining_minutes -= available_minutes
        current = (current + datetime.timedelta(days=1)).replace(
            hour=start_hour, minute=0, second=0, microsecond=0
        )

    return current, format_deadline_text(current, now)


def format_deadline_text(target: datetime.datetime, now: datetime.datetime) -> str:
    target_date = target.date()
    now_date = now.date()
    h = target.hour
    m = f"{target.minute:02d}" if target.minute else ""
    time_str = f"{h}h{m}"

    if h < 11:
        session = "sáng"
    elif h < 13:
        session = "trưa"
    elif h < 18:
        session = "chiều"
    else:
        session = "tối"

    if target_date == now_date:
        return f"trước {time_str} {session} nay"
    elif target_date == now_date + datetime.timedelta(days=1):
        return f"trước {time_str} {session} mai"
    else:
        days = ["Chủ nhật", "thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy"]
        day_name = days[target.isoweekday() % 7]
        return f"trước {time_str} {day_name} ngày {target.day}/{target.month}"

import os
from datetime import date, timedelta
from html import escape

from flask import current_app
from sqlalchemy import func

from models import (
    db,
    Elder,
    MealRecord,
    MedRecord,
    VitalRecord,
    WaterRecord,
    BowelRecord,
    Photo,
    get_setting,
)

SLOT_ZH = {"morning": "早上", "noon": "中午", "evening": "晚上", "bedtime": "睡前"}
INTAKE_ZH = {"all": "全部吃完", "half": "吃一半", "little": "吃很少", "none": "沒有吃"}
VITAL_FIELDS = (
    ("weight", "體重", "kg"),
    ("systolic", "收縮壓", "mmHg"),
    ("diastolic", "舒張壓", "mmHg"),
    ("pulse", "脈搏", "次/分"),
    ("spo2", "血氧", "%"),
)


def _display_number(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.1f}"
    return str(value)


def _fmt(value, unit=""):
    if value is None:
        return "—"
    suffix = f" {unit}" if unit else ""
    return f"{_display_number(value)}{suffix}"


def _when(value):
    return value.strftime("%m/%d %H:%M") if value else ""


def _series_stats(vitals, attr):
    points = [
        (getattr(vital, attr), vital.recorded_at)
        for vital in vitals
        if getattr(vital, attr) is not None
    ]
    if not points:
        return {
            "avg": None,
            "min": None,
            "max": None,
            "min_at": None,
            "max_at": None,
            "count": 0,
        }
    minimum = min(points, key=lambda item: item[0])
    maximum = max(points, key=lambda item: item[0])
    return {
        "avg": round(sum(item[0] for item in points) / len(points), 1),
        "min": minimum[0],
        "max": maximum[0],
        "min_at": minimum[1],
        "max_at": maximum[1],
        "count": len(points),
    }


def collect_period(elder, start, end):
    """Aggregate one elder's data for the inclusive period [start, end]."""

    def query(model):
        return model.query.filter(
            model.elder_id == elder.id,
            model.record_date >= start,
            model.record_date <= end,
        )

    data = {"elder": elder, "start": start, "end": end}

    meals = query(MealRecord).order_by(MealRecord.record_date).all()
    data["meals"] = meals
    data["meal_summary"] = {
        key: sum(1 for meal in meals if meal.intake == key) for key in INTAKE_ZH
    }
    data["sup_count"] = sum(1 for meal in meals if meal.supplement)
    data["sup_cc"] = sum(meal.supplement_cc or 0 for meal in meals if meal.supplement)

    meds = query(MedRecord).order_by(MedRecord.record_date).all()
    given = sum(1 for med in meds if med.given)
    data["meds"] = meds
    data["med_total"] = len(meds)
    data["med_given"] = given
    data["med_rate"] = round(given * 100 / len(meds)) if meds else None
    data["med_missed"] = [med for med in meds if not med.given]

    vitals = query(VitalRecord).order_by(VitalRecord.recorded_at).all()
    data["vitals"] = vitals
    data["vital_stats"] = {
        attr: _series_stats(vitals, attr) for attr, _label, _unit in VITAL_FIELDS
    }
    # Retain the old key for third-party extensions that used collect_period().
    data["avg"] = {
        attr: data["vital_stats"][attr]["avg"] for attr, _label, _unit in VITAL_FIELDS
    }

    water_rows = (
        db.session.query(WaterRecord.record_date, func.sum(WaterRecord.amount))
        .filter(
            WaterRecord.elder_id == elder.id,
            WaterRecord.record_date >= start,
            WaterRecord.record_date <= end,
        )
        .group_by(WaterRecord.record_date)
        .order_by(WaterRecord.record_date)
        .all()
    )
    water_by_date = {row_date: int(amount or 0) for row_date, amount in water_rows}
    period_days = (end - start).days + 1
    water_daily = [
        (start + timedelta(days=offset), water_by_date.get(start + timedelta(days=offset), 0))
        for offset in range(period_days)
    ]
    recorded_water = [(row_date, amount) for row_date, amount in water_by_date.items()]
    if recorded_water:
        water_min_date, water_min = min(recorded_water, key=lambda item: item[1])
        water_max_date, water_max = max(recorded_water, key=lambda item: item[1])
        water_avg = round(sum(amount for _row_date, amount in recorded_water) / len(recorded_water))
    else:
        water_min_date = water_max_date = None
        water_min = water_max = water_avg = None
    total_water = sum(water_by_date.values())
    data["water_daily"] = water_daily
    data["water_recorded_days"] = len(water_rows)
    data["period_days"] = period_days
    data["water_avg"] = water_avg
    data["water_period_avg"] = round(total_water / period_days) if period_days else None
    data["water_min"] = water_min
    data["water_min_date"] = water_min_date
    data["water_max"] = water_max
    data["water_max_date"] = water_max_date

    bowels = query(BowelRecord).order_by(BowelRecord.recorded_at).all()
    data["bowels"] = bowels

    data["photo_count"] = Photo.query.filter(
        Photo.elder_id == elder.id,
        Photo.deleted_at.is_(None),
        Photo.record_date >= start,
        Photo.record_date <= end,
    ).count()
    return data


def _vital_html_rows(data, css_td):
    rows = []
    for attr, label, unit in VITAL_FIELDS:
        stat = data["vital_stats"][attr]
        minimum = _fmt(stat["min"], unit)
        maximum = _fmt(stat["max"], unit)
        if stat["min_at"]:
            minimum += (
                f"<br><span style='font-size:11px;color:#6b7a76;'>"
                f"{_when(stat['min_at'])}</span>"
            )
        if stat["max_at"]:
            maximum += (
                f"<br><span style='font-size:11px;color:#6b7a76;'>"
                f"{_when(stat['max_at'])}</span>"
            )
        rows.append(
            f"<tr><td style='{css_td}'><b>{label}</b></td>"
            f"<td style='{css_td}'>{_fmt(stat['avg'], unit)}</td>"
            f"<td style='{css_td}'>{minimum}</td>"
            f"<td style='{css_td}'>{maximum}</td>"
            f"<td style='{css_td}'>{stat['count']}</td></tr>"
        )
    return "".join(rows)


def build_html(all_data, period_label, items=None):
    items = items if items is not None else (get_setting("report_items") or {})
    css_td = "padding:6px 10px;border-bottom:1px solid #e3ebe7;font-size:14px;"
    css_th = css_td + "background:#eef5f2;text-align:left;color:#245b4f;"
    parts = [
        f"""
    <div style="font-family:'Noto Sans TC',sans-serif;max-width:760px;margin:auto;color:#1f2b2a;">
    <div style="background:#2F7E6D;color:#fff;padding:16px 20px;border-radius:12px 12px 0 0;">
      <div style="font-size:18px;font-weight:700;">居家照顧健康回報 — {escape(period_label)}</div>
    </div>
    <div style="border:1px solid #dfe8e4;border-top:none;padding:20px;border-radius:0 0 12px 12px;">"""
    ]

    for data in all_data:
        elder = data["elder"]
        parts.append(
            f"<h2 style='font-size:16px;color:#2F7E6D;margin:18px 0 8px;'>👤 {escape(elder.name)}"
            f"<span style='font-weight:400;color:#6b7a76;font-size:13px;'>"
            f"（{data['start']} ~ {data['end']}）</span></h2>"
        )

        if items.get("vitals", True):
            rows = _vital_html_rows(data, css_td)
            parts.append(
                f"""<table style="border-collapse:collapse;width:100%;margin:6px 0;">
                  <tr><th style="{css_th}">健康項目</th><th style="{css_th}">平均</th>
                      <th style="{css_th}">最低</th><th style="{css_th}">最高</th>
                      <th style="{css_th}">次數</th></tr>{rows}</table>"""
            )

        if items.get("meds", True):
            rate = f"{data['med_rate']}%" if data["med_rate"] is not None else "—"
            parts.append(
                f"<p style='margin:10px 0 4px;font-size:14px;'>💊 <b>用藥完成率：{rate}</b>"
                f"（已填報 {data['med_total']} 項、已給 {data['med_given']} 項）</p>"
            )
            if data["med_missed"]:
                rows = "".join(
                    f"<tr><td style='{css_td}'>{med.record_date}</td>"
                    f"<td style='{css_td}'>{escape(med.plan.name if med.plan else '')}"
                    f"（{SLOT_ZH.get(med.plan.timeslot, '') if med.plan else ''}）</td>"
                    f"<td style='{css_td}'>{escape(med.reason or '未填原因')}</td></tr>"
                    for med in data["med_missed"]
                )
                parts.append(
                    f"<table style='border-collapse:collapse;width:100%;'>"
                    f"<tr><th style='{css_th}'>日期</th><th style='{css_th}'>未給藥項目</th>"
                    f"<th style='{css_th}'>原因</th></tr>{rows}</table>"
                )

        if items.get("meals", True):
            summary = data["meal_summary"]
            meal_text = "、".join(
                f"{INTAKE_ZH[key]} {count} 餐" for key, count in summary.items() if count
            )
            if data["meals"]:
                meal_text = f"{meal_text}（共 {len(data['meals'])} 餐）"
            else:
                meal_text = "本期間無紀錄"
            parts.append(
                f"<p style='margin:10px 0 4px;font-size:14px;'>🍚 <b>餐飲：</b>{meal_text}</p>"
            )
            if data["sup_count"]:
                parts.append(
                    f"<p style='margin:4px 0;font-size:14px;'>🥤 <b>營養品：</b>"
                    f"{data['sup_count']} 次、共 {data['sup_cc']} cc</p>"
                )

        if items.get("water", True):
            if data["water_recorded_days"]:
                water_detail = (
                    f"有紀錄日平均 {data['water_avg']} ml；"
                    f"最低 {data['water_min']} ml（{data['water_min_date']}）；"
                    f"最高 {data['water_max']} ml（{data['water_max_date']}）；"
                    f"全期間日均 {data['water_period_avg']} ml。"
                )
            else:
                water_detail = "本期間無喝水紀錄。"
            parts.append(
                f"<p style='margin:10px 0 4px;font-size:14px;'>💧 <b>喝水：</b>"
                f"{water_detail}目標 {elder.water_goal} ml。"
                f"<span style='color:#6b7a76;'>有紀錄 {data['water_recorded_days']} / "
                f"{data['period_days']} 天。</span></p>"
            )

        if items.get("bowel", True):
            abnormal = sum(
                1 for bowel in data["bowels"] if bowel.bristol_type in (1, 2, 6, 7)
            )
            parts.append(
                f"<p style='margin:10px 0 4px;font-size:14px;'>🚽 <b>排便：</b>"
                f"共 {len(data['bowels'])} 次，偏硬／偏稀 {abnormal} 次</p>"
            )

        parts.append(
            f"<p style='margin:10px 0;font-size:13px;color:#6b7a76;'>"
            f"📷 佐證照片 {data['photo_count']} 張（可登入系統檢視）</p>"
            f"<hr style='border:none;border-top:1px solid #e3ebe7;'>"
        )

    parts.append(
        "<p style='font-size:12px;color:#9aa7a3;'>本郵件由居家照顧回報系統自動產生。"
        "本報表供照顧溝通參考，不取代專業醫療判斷。</p></div></div>"
    )
    return "".join(parts)


def _usable_font(font_path):
    """Convert a variable font to a static wght=400 instance for fpdf2."""
    try:
        from fontTools.ttLib import TTFont

        probe = TTFont(font_path, lazy=True)
        is_variable = "fvar" in probe
        probe.close()
        if not is_variable:
            return font_path
        cache = font_path + ".static.ttf"
        if not os.path.exists(cache):
            from fontTools.varLib.instancer import instantiateVariableFont

            variable_font = TTFont(font_path)
            static_font = instantiateVariableFont(variable_font, {"wght": 400})
            try:
                static_font.save(cache)
            except OSError:
                import tempfile

                cache = os.path.join(tempfile.gettempdir(), "carelog-noto-static.ttf")
                if not os.path.exists(cache):
                    static_font.save(cache)
        return cache
    except Exception:
        return font_path


def _vital_pdf_line(data, attr, label, unit):
    stat = data["vital_stats"][attr]
    if not stat["count"]:
        return f"{label}：無紀錄"
    return (
        f"{label}：平均 {_fmt(stat['avg'], unit)}｜"
        f"最低 {_fmt(stat['min'], unit)}（{_when(stat['min_at'])}）｜"
        f"最高 {_fmt(stat['max'], unit)}（{_when(stat['max_at'])}）｜"
        f"量測 {stat['count']} 次"
    )


def build_pdf(all_data, period_label, items=None):
    """Return PDF bytes, or None when the configured CJK font is unavailable."""
    font_path = current_app.config["FONT_PATH"]
    if not os.path.exists(font_path):
        return None
    try:
        from fpdf import FPDF
    except ImportError:
        return None

    items = items if items is not None else (get_setting("report_items") or {})
    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.add_font("noto", "", _usable_font(font_path))
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("noto", size=16)
    pdf.set_text_color(47, 126, 109)
    pdf.cell(
        0,
        12,
        f"居家照顧健康回報 — {period_label}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_text_color(31, 43, 42)

    for data in all_data:
        elder = data["elder"]
        pdf.set_font("noto", size=13)
        pdf.cell(
            0,
            10,
            f"{elder.name}（{data['start']} ~ {data['end']}）",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_font("noto", size=10.5)
        lines = []
        if items.get("vitals", True):
            lines.extend(
                _vital_pdf_line(data, attr, label, unit)
                for attr, label, unit in VITAL_FIELDS
            )
        if items.get("meds", True):
            rate = f"{data['med_rate']}%" if data["med_rate"] is not None else "—"
            lines.append(
                f"用藥完成率 {rate}（已填報 {data['med_total']}、已給 {data['med_given']}）"
            )
        if items.get("meals", True):
            lines.append(
                "餐飲："
                + (
                    "、".join(
                        f"{INTAKE_ZH[key]} {count} 餐"
                        for key, count in data["meal_summary"].items()
                        if count
                    )
                    or "無紀錄"
                )
            )
            lines.append(
                f"營養品：{data['sup_count']} 次、共 {data['sup_cc']} cc"
                if data["sup_count"]
                else "營養品：無"
            )
        if items.get("water", True):
            if data["water_recorded_days"]:
                lines.append(
                    f"喝水：有紀錄日平均 {data['water_avg']} ml｜"
                    f"最低 {data['water_min']} ml（{data['water_min_date']}）｜"
                    f"最高 {data['water_max']} ml（{data['water_max_date']}）｜"
                    f"全期間日均 {data['water_period_avg']} ml｜"
                    f"目標 {elder.water_goal} ml｜有紀錄 {data['water_recorded_days']} / "
                    f"{data['period_days']} 天"
                )
            else:
                lines.append(
                    f"喝水：本期間無紀錄｜目標 {elder.water_goal} ml｜"
                    f"有紀錄 0 / {data['period_days']} 天"
                )
        if items.get("bowel", True):
            abnormal = sum(
                1 for bowel in data["bowels"] if bowel.bristol_type in (1, 2, 6, 7)
            )
            lines.append(f"排便：共 {len(data['bowels'])} 次，偏硬／偏稀 {abnormal} 次")
        lines.append(f"佐證照片：{data['photo_count']} 張")

        for line in lines:
            pdf.multi_cell(0, 7, line, new_x="LMARGIN", new_y="NEXT")
        if items.get("meds", True) and data["med_missed"]:
            pdf.multi_cell(
                0,
                7,
                "未給藥明細："
                + "；".join(
                    f"{med.record_date} {med.plan.name if med.plan else ''}"
                    f"（{med.reason or '未填原因'}）"
                    for med in data["med_missed"]
                ),
                new_x="LMARGIN",
                new_y="NEXT",
            )
        pdf.cell(0, 6, "", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def build_report(period):
    """Build a daily, weekly, or rolling 30-day report."""
    today = date.today()
    if period == "daily":
        start = end = today
        label = f"每日報表 {today}"
    elif period == "weekly":
        start, end = today - timedelta(days=6), today
        label = f"每週報表 {start} ~ {end}"
    else:
        start, end = today - timedelta(days=29), today
        label = f"每月報表 {start} ~ {end}"

    elders = Elder.query.filter_by(active=True).all()
    all_data = [collect_period(elder, start, end) for elder in elders]
    items = get_setting("report_items") or {}
    html = build_html(all_data, label, items=items)
    pdf = None
    if get_setting("pdf_attach"):
        try:
            pdf = build_pdf(all_data, label, items=items)
        except Exception:
            current_app.logger.exception("PDF generation failed; sending HTML only")
            pdf = None
    return f"【照顧回報】{label}", html, pdf

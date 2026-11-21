#app.py
# =============================================================================
# >>> SECTION A1 START: IMPORTS & DYNAMIC THEME STATE SETUP <<<
# =============================================================================
import flet as ft
import asyncio
import sys
import base64
from datetime import datetime, timedelta
import calendar
from backend import (
    init_db,
    get_db_connection,
    fetch_tasks_for_date,
    get_completions_for_date,
    mark_complete_db,
    remove_completion_db,
    add_task_db,
    update_task_db,
    remove_task_db,
    fetch_backlog_tasks,
    schedule_backlog_task_db,
    fetch_all_tasks,
    batch_remove_tasks_db,
    get_distinct_categories,
    get_distinct_habits,
    get_unified_heatmap_data,
    get_streak_and_stats,
    get_habit_unit_logs,
    get_habit_goals,
    update_habit_goals,
    get_habit_trend_data,
    get_habit_date_bounds,
    format_ui_date,
    parse_ui_date_to_iso,
    is_habit_daily,
    add_habit_goal_db,
    delete_habit_goal_db,
    get_habit_goals_list,
    get_all_settings,
    save_setting,
)

def main(page: ft.Page):
    init_db()

    # --- Live Dynamic Theme Registry ---
    # Default Pine Theme: #092328 (Bg), #0D2E34 (Surface), #12544F (Card), #0F3840 (Box/Shelf), #8BBB92 (Accent)
    saved_settings = get_all_settings()
    theme_state = {
        "bg": saved_settings.get("theme_bg", "#092328"),
        "surface": saved_settings.get("theme_surface", "#0D2E34"),
        "surface_card": saved_settings.get("theme_surface_card", saved_settings.get("theme_card", "#12544F")),
        "box": saved_settings.get("theme_box", "#0F3840"),
        "accent": saved_settings.get("theme_accent", "#8BBB92"),
        "accent_dim": saved_settings.get("theme_accent_dim", "#2A835F"),
    }

    def hex_to_rgb(hex_str: str):
        hex_clean = hex_str.lstrip("#")
        if len(hex_clean) == 3:
            hex_clean = "".join([c * 2 for c in hex_clean])
        if len(hex_clean) != 6:
            return (139, 187, 146)
        try:
            return tuple(int(hex_clean[i : i + 2], 16) for i in (0, 2, 4))
        except Exception:
            return (139, 187, 146)

    def rgb_to_hex(r: int, g: int, b: int) -> str:
        return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"

    def get_luminance(hex_str: str) -> float:
        r, g, b = hex_to_rgb(hex_str)
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0

    def get_text_color(hex_bg: str) -> str:
        return "#092328" if get_luminance(hex_bg) > 0.55 else "#FFFFFF"

    def get_subtext_color(hex_bg: str) -> str:
        return "#244A4F" if get_luminance(hex_bg) > 0.55 else "#94A3B8"

    def get_border_color(hex_bg: str) -> str:
        return "#19444B" if get_luminance(hex_bg) <= 0.55 else "#CBD5E1"

    def apply_page_theme():
        page.bgcolor = theme_state["bg"]
        page.theme_mode = ft.ThemeMode.LIGHT if get_luminance(theme_state["bg"]) > 0.55 else ft.ThemeMode.DARK
        page.theme = ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=theme_state["accent"],
                surface=theme_state["surface"],
            )
        )

    page.title = "Habit & Task Tracker"
    page.window.title_bar_hidden = True
    page.window.title_bar_buttons_hidden = True
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.padding = 20
    apply_page_theme()

    current_selected_date = datetime.now()
    current_view_mode = "day"
    is_typing = False
    selected_task_idx = 0
    current_day_tasks = []

    def set_typing(state: bool):
        nonlocal is_typing
        is_typing = state

    def make_border(width: float, color: str = None):
        c = color or get_border_color(theme_state["bg"])
        side = ft.BorderSide(width, c)
        return ft.Border(top=side, bottom=side, left=side, right=side)

    def get_scroll_direction(e) -> int:
        dy = getattr(e, "scroll_delta_y", None)
        if dy is None:
            sd = getattr(e, "scroll_delta", None)
            if sd is not None:
                dy = getattr(sd, "y", 0)
        if dy is None:
            dy = getattr(e, "delta_y", 0)
        try:
            val = float(dy)
            if val > 0:
                return 1
            elif val < 0:
                return -1
        except Exception:
            pass
        return 0
# =============================================================================
# >>> SECTION A1 END: IMPORTS & DYNAMIC THEME STATE SETUP <<<
# =============================================================================

# =============================================================================
# >>> SECTION A2 START: SHARED UI HELPERS & INTERACTIVE SVG CHART GENERATOR <<<
# =============================================================================
    import math as _math

    def build_shelf(title: str, subtitle: str, body_control: ft.Control):
        t_col = theme_state["accent"]
        sub_col = get_subtext_color(theme_state["box"])
        header_col = ft.Column(
            [
                ft.Text(title, size=15, weight=ft.FontWeight.BOLD, color=t_col),
                ft.Text(subtitle, size=11, color=sub_col),
            ],
            spacing=2,
            tight=True,
        )
        return ft.Container(
            padding=16,
            bgcolor=theme_state["box"],
            border_radius=10,
            border=make_border(1.5, get_border_color(theme_state["box"])),
            content=ft.Column(
                [header_col, ft.Divider(color=get_border_color(theme_state["box"]), height=10), body_control],
                spacing=10,
                tight=True,
            ),
        )

    def _build_chart_series(unit_logs: list, time_bucket: str = "daily", weekly_agg_mode: str = "avg") -> list:
        """Return chronological list of (label_str, dt_obj, float_val) for either Daily or Weekly view."""
        if not unit_logs:
            return []

        if time_bucket == "weekly":
            iso_week_groups = {}
            for d_str, val in unit_logs:
                try:
                    dt = datetime.strptime(d_str, "%Y-%m-%d")
                    iso_yr, iso_wk, _ = dt.isocalendar()
                    wk_monday = dt - timedelta(days=dt.weekday())
                    wk_key = f"{iso_yr}-W{iso_wk:02d}"
                except Exception:
                    wk_key = d_str
                    wk_monday = datetime.now()
                iso_week_groups.setdefault(wk_key, {"dt": wk_monday, "vals": []})["vals"].append(float(val))

            series = []
            for wk_key in sorted(iso_week_groups.keys()):
                entry = iso_week_groups[wk_key]
                w_vals = entry["vals"]
                agg_v = sum(w_vals) if weekly_agg_mode == "sum" else (sum(w_vals) / len(w_vals))
                short_wk = wk_key.split("-")[1] if "-" in wk_key else wk_key
                series.append((short_wk, entry["dt"], agg_v))
            return series
        else:
            by_day = {}
            for d_str, val in unit_logs:
                try:
                    dt = datetime.strptime(d_str, "%Y-%m-%d")
                    by_day.setdefault(d_str, {"dt": dt, "vals": []})["vals"].append(float(val))
                except Exception:
                    continue
            return [
                (d_str, by_day[d_str]["dt"], max(by_day[d_str]["vals"]))
                for d_str in sorted(by_day.keys())
            ]

    def _damped_project_value(base_val: float, slope_per_week: float, days_ahead: float, phi: float = 0.97) -> float:
        """Project value `days_ahead` using Holt's gently damped growth factor (phi per week)."""
        if days_ahead <= 0 or abs(slope_per_week) < 1e-9:
            return max(0.0, base_val)
        weeks = days_ahead / 7.0
        eff_weeks = (1.0 - (phi ** weeks)) / (1.0 - phi)
        return max(0.0, base_val + slope_per_week * eff_weeks)

    def _filter_visible_chart_goals(
        goals_list: list,
        time_bucket: str = "daily",
        weekly_agg_mode: str = "avg",
        show_trend: bool = False,
    ) -> list:
        """Always show active goals on the graph regardless of which chart mode is active."""
        visible = []
        for g in (goals_list or []):
            if g.get("target_value") is None:
                continue
            gt = g.get("goal_type", "max")
            if not g.get("achieved", False) or gt in ("weekly_avg", "all_time_avg"):
                visible.append(g)
        return visible

    def compute_unit_pace_and_forecast(
        unit_logs: list,
        goals_list: list = None,
        time_bucket: str = "daily",
        weekly_agg_mode: str = "avg",
        lookback_days: int = None,
    ) -> dict:
        """Compute outlier-resistant recency-weighted Theil-Sen pace and damped goal ETA."""
        full_series = _build_chart_series(unit_logs, time_bucket=time_bucket, weekly_agg_mode=weekly_agg_mode)
        if not full_series:
            return {
                "has_pace": False,
                "slope_per_day": 0.0,
                "slope_per_week": 0.0,
                "first_val": 0.0,
                "last_dt": datetime.now(),
                "last_val": 0.0,
                "cur_avg": 0.0,
                "target_goal": None,
                "target_goal_type": "max",
                "days_to_goal": None,
                "eta_date_str": None,
                "points_used": 0,
            }

        last_dt = full_series[-1][1]
        last_val = full_series[-1][2]
        cur_avg = sum(pt[2] for pt in full_series) / len(full_series)

        if lookback_days is not None:
            cutoff_dt = last_dt - timedelta(days=lookback_days)
            window_series = [pt for pt in full_series if pt[1] >= cutoff_dt]
            if len(window_series) < 2 and len(full_series) >= 2:
                window_series = full_series[-2:]
        else:
            window_series = full_series

        first_val = window_series[0][2]

        if len(window_series) < 2:
            return {
                "has_pace": False,
                "slope_per_day": 0.0,
                "slope_per_week": 0.0,
                "first_val": first_val,
                "last_dt": last_dt,
                "last_val": last_val,
                "cur_avg": cur_avg,
                "target_goal": None,
                "target_goal_type": "max",
                "days_to_goal": None,
                "eta_date_str": None,
                "points_used": len(window_series),
            }

        n_w = len(window_series)
        weighted_slopes = []
        for i in range(n_w):
            dt_i, val_i = window_series[i][1], window_series[i][2]
            for j in range(i + 1, n_w):
                dt_j, val_j = window_series[j][1], window_series[j][2]
                delta_days = max(1.0, float((dt_j - dt_i).days))
                s_ij = (val_j - val_i) / delta_days
                w_ij = _math.sqrt(delta_days) * (1.0 + (j / float(n_w)))
                weighted_slopes.append((s_ij, w_ij))

        weighted_slopes.sort(key=lambda pair: pair[0])
        total_w = sum(w for _, w in weighted_slopes)
        half_w = total_w * 0.5
        cum_w = 0.0
        slope_per_day = weighted_slopes[-1][0]
        for s_val, w_val in weighted_slopes:
            cum_w += w_val
            if cum_w >= half_w:
                slope_per_day = s_val
                break

        slope_per_week = slope_per_day * 7.0

        unachieved_goals = [
            g for g in (goals_list or [])
            if not g.get("achieved", False) and g.get("target_value") is not None
        ]

        target_goal = None
        target_goal_type = "max"
        if unachieved_goals:
            above = [g for g in unachieved_goals if float(g["target_value"]) > last_val]
            chosen_g = min(above, key=lambda x: float(x["target_value"])) if above else min(
                unachieved_goals, key=lambda x: float(x["target_value"])
            )
            target_goal = float(chosen_g["target_value"])
            target_goal_type = chosen_g.get("goal_type", "max")

        days_to_goal = None
        eta_date_str = None
        phi = 0.97
        if target_goal is not None and slope_per_week > 1e-5:
            if target_goal_type == "all_time_avg" and cur_avg < target_goal:
                n_hist_pts = len(full_series)
                hist_sum = sum(pt[2] for pt in full_series)
                step_days = 7.0 if time_bucket == "weekly" else max(
                    1.0, float((last_dt - window_series[0][1]).days) / max(1, n_w - 1)
                )
                for step_k in range(1, 200):
                    d_ahead = step_k * step_days
                    proj_v = _damped_project_value(last_val, slope_per_week, d_ahead, phi=phi)
                    hist_sum += proj_v
                    new_avg = hist_sum / (n_hist_pts + step_k)
                    if new_avg >= target_goal:
                        days_to_goal = max(1, int(round(d_ahead)))
                        eta_dt = max(last_dt, datetime.now()) + timedelta(days=days_to_goal)
                        eta_date_str = eta_dt.strftime("%Y-%m-%d")
                        break
            elif last_val < target_goal:
                needed_gain = target_goal - last_val
                eff_weeks_needed = needed_gain / slope_per_week
                inner = 1.0 - eff_weeks_needed * (1.0 - phi)
                if inner > 0.05:
                    w_needed = _math.log(inner) / _math.log(phi)
                    est_days = int(round(w_needed * 7.0))
                    if 1 <= est_days <= 730:
                        days_to_goal = est_days
                        eta_dt = max(last_dt, datetime.now()) + timedelta(days=est_days)
                        eta_date_str = eta_dt.strftime("%Y-%m-%d")

        return {
            "has_pace": True,
            "slope_per_day": slope_per_day,
            "slope_per_week": slope_per_week,
            "first_val": first_val,
            "last_dt": last_dt,
            "last_val": last_val,
            "cur_avg": cur_avg,
            "target_goal": target_goal,
            "target_goal_type": target_goal_type,
            "days_to_goal": days_to_goal,
            "eta_date_str": eta_date_str,
            "points_used": n_w,
        }

    def build_area_line_chart_image(
        unit_name: str,
        unit_logs: list,
        chart_style: str = "line",
        show_trend: bool = False,
        time_bucket: str = "daily",
        weekly_agg_mode: str = "avg",
        goals_list: list = None,
        show_forecast: bool = False,
        forecast_horizon_days: int = 30,
        forecast_to_goal: bool = False,
        lookback_days: int = None,
        custom_width: int = None,
        custom_height: int = None,
    ) -> ft.Control:
        import base64

        processed_logs = _build_chart_series(unit_logs, time_bucket=time_bucket, weekly_agg_mode=weekly_agg_mode)
        if not processed_logs:
            processed_logs = [("2026-01-01", datetime.now(), 0.0)]

        n_hist = len(processed_logs)
        # Always render as pillars when there are only 1-3 data points
        effective_style = "pillars" if n_hist <= 3 else chart_style

        dates = [x[0] for x in processed_logs]
        vals = [float(x[2]) for x in processed_logs]

        forecast_pts_data = []
        pace_info = compute_unit_pace_and_forecast(
            unit_logs,
            goals_list=goals_list,
            time_bucket=time_bucket,
            weekly_agg_mode=weekly_agg_mode,
            lookback_days=lookback_days,
        )
        if show_forecast and pace_info["has_pace"]:
            slope_wk = pace_info["slope_per_week"]
            last_dt = pace_info["last_dt"]
            base_v = pace_info["last_val"]

            if forecast_to_goal and pace_info["days_to_goal"] is not None:
                horizon_days = min(365, max(14, pace_info["days_to_goal"]))
            else:
                horizon_days = max(7, int(forecast_horizon_days or 30))

            if time_bucket == "weekly":
                n_future_steps = max(2, min(12, int(round(horizon_days / 7.0))))
                for step_i in range(1, n_future_steps + 1):
                    d_off = step_i * 7
                    f_dt = last_dt + timedelta(days=d_off)
                    proj_v = _damped_project_value(base_v, slope_wk, d_off)
                    _, f_wk, _ = f_dt.isocalendar()
                    forecast_pts_data.append((f"W{f_wk:02d}", proj_v))
            else:
                n_future_steps = max(3, min(8, horizon_days // 7 if horizon_days >= 21 else horizon_days // 3))
                for step_i in range(1, n_future_steps + 1):
                    d_off = int(round((horizon_days * step_i) / n_future_steps))
                    f_dt = last_dt + timedelta(days=d_off)
                    proj_v = _damped_project_value(base_v, slope_wk, d_off)
                    forecast_pts_data.append((f_dt.strftime("%Y-%m-%d"), proj_v))

        all_dates = dates + [f[0] for f in forecast_pts_data]
        n_total = len(all_dates)

        raw_win_w = getattr(getattr(page, "window", None), "width", None) or getattr(page, "width", None) or 1200
        if custom_width is not None:
            width = int(custom_width)
        else:
            width = max(640, min(1360, int(raw_win_w - 96)))
        height = int(custom_height) if custom_height is not None else 270
        pad_l, pad_r, pad_t, pad_b = 46, 28, 32, 34
        plot_w = width - pad_l - pad_r
        plot_h = height - pad_t - pad_b

        running_avgs = []
        curr_sum = 0.0
        for idx, v in enumerate(vals):
            curr_sum += v
            running_avgs.append(curr_sum / (idx + 1))

        projected_avgs = []
        if forecast_pts_data and running_avgs:
            fut_sum = curr_sum
            for j, (_, f_val) in enumerate(forecast_pts_data):
                fut_sum += f_val
                projected_avgs.append(fut_sum / (n_hist + j + 1))

        visible_goals = _filter_visible_chart_goals(
            goals_list,
            time_bucket=time_bucket,
            weekly_agg_mode=weekly_agg_mode,
            show_trend=show_trend,
        )
        active_goal_vals = [float(g["target_value"]) for g in visible_goals]
        forecast_vals = [f[1] for f in forecast_pts_data]

        all_numeric = vals + active_goal_vals + forecast_vals + projected_avgs
        raw_max = max(all_numeric + [1.0])
        raw_min = min(vals) if len(vals) > 1 else 0.0
        min_v = 0.0 if raw_min < raw_max * 0.45 else max(0.0, raw_min * 0.85)
        max_v = raw_max + max(1.0, (raw_max - min_v) * 0.16)

        def val_to_y(v: float) -> float:
            if max_v <= min_v:
                return pad_t + plot_h / 2
            return pad_t + plot_h - ((v - min_v) / (max_v - min_v)) * plot_h

        hist_span_px = (plot_w * 0.64) if forecast_pts_data else plot_w
        fut_span_px = (plot_w * 0.36) if forecast_pts_data else 0.0

        def idx_to_x(i: int) -> float:
            if i < n_hist:
                if effective_style == "pillars":
                    slot_w = hist_span_px / max(1, n_hist)
                    return pad_l + slot_w * (i + 0.5)
                if n_hist <= 1:
                    return pad_l + hist_span_px * 0.5
                return pad_l + (i / (n_hist - 1)) * hist_span_px
            else:
                j = i - n_hist + 1
                n_fut = max(1, len(forecast_pts_data))
                return pad_l + hist_span_px + (j / n_fut) * fut_span_px

        accent_hex = theme_state["accent"]
        bg_base_hex = theme_state["bg"]
        grid_hex = get_border_color(bg_base_hex)
        sub_hex = get_subtext_color(bg_base_hex)
        is_dark_bg = (get_text_color(bg_base_hex) == "#FFFFFF")
        avg_line_hex = "#F1F5F9" if is_dark_bg else "#0F172A"
        proj_line_hex = accent_hex

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            f'<rect width="100%" height="100%" fill="{bg_base_hex}" rx="8"/>',
        ]

        # 1. Theme-Synced Shaded Forecast Zone
        if forecast_pts_data and n_hist >= 1:
            split_x = pad_l + hist_span_px
            right_edge = width - pad_r
            if right_edge > split_x:
                svg_parts.append(
                    f'<rect x="{split_x:.1f}" y="{pad_t}" width="{right_edge - split_x:.1f}" height="{plot_h}" fill="{proj_line_hex}" fill-opacity="0.08"/>'
                )
                svg_parts.append(
                    f'<line x1="{split_x:.1f}" y1="{pad_t}" x2="{split_x:.1f}" y2="{height - pad_b}" stroke="{proj_line_hex}" stroke-width="1.2" stroke-dasharray="3,3" stroke-opacity="0.75"/>'
                )

        # 2. Horizontal Grid
        for step in range(3):
            gv = min_v + (max_v - min_v) * (step / 2.0)
            gy = val_to_y(gv)
            svg_parts.append(
                f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" stroke="{grid_hex}" stroke-width="1"/>'
            )
            gv_str = f"{gv:.1f}".rstrip("0").rstrip(".")
            svg_parts.append(
                f'<text x="{pad_l - 8}" y="{gy + 4:.1f}" fill="{sub_hex}" font-size="10" font-family="sans-serif" text-anchor="end">{gv_str}</text>'
            )

        # 3. Goal Benchmark Lines — Always Black & White Striped regardless of theme
        goal_short_names = {
            "max": "Peak Goal",
            "weekly_avg": "Weekly Avg Goal",
            "all_time_avg": "Overall Avg Goal",
        }
        placed_goal_label_ys = []
        for g in sorted(visible_goals, key=lambda item: float(item["target_value"]), reverse=True):
            gv = float(g["target_value"])
            gy = val_to_y(gv)
            gv_str = f"{gv:.1f}".rstrip("0").rstrip(".")
            g_lbl = f"{goal_short_names.get(g.get('goal_type', 'max'), 'Goal')}: {gv_str} {unit_name}"

            # Pure white base line + crisp black dashes so it is always high-contrast black-and-white striped
            svg_parts.append(
                f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" stroke="#FFFFFF" stroke-width="2.4"/>'
            )
            svg_parts.append(
                f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" stroke="#000000" stroke-width="2.4" stroke-dasharray="6,6"/>'
            )

            lbl_y = max(pad_t + 11, gy - 6)
            for prev_y in placed_goal_label_ys:
                if abs(lbl_y - prev_y) < 16:
                    lbl_y = prev_y + 16
            placed_goal_label_ys.append(lbl_y)

            pill_w = max(72.0, len(g_lbl) * 5.7 + 10.0)
            svg_parts.append(
                f'<rect x="{pad_l + 4}" y="{lbl_y - 10:.1f}" width="{pill_w:.1f}" height="14" rx="3" fill="#000000" fill-opacity="0.82" stroke="#FFFFFF" stroke-width="0.8"/>'
            )
            svg_parts.append(
                f'<text x="{pad_l + 9}" y="{lbl_y:.1f}" fill="#FFFFFF" font-size="9.5" font-weight="bold" font-family="sans-serif" text-anchor="start">{g_lbl}</text>'
            )

        # 4. Primary Historical Series — Show ALL labels until points are physically closer than 26px
        pts = [(idx_to_x(i), val_to_y(v)) for i, v in enumerate(vals)]
        peak_idx = vals.index(max(vals)) if vals else 0
        px_per_item = hist_span_px / max(1, n_hist)
        if px_per_item >= 26.0:
            labeled_indices = set(range(n_hist))
        else:
            step_lbl = max(2, int(_math.ceil(26.0 / max(1.0, px_per_item))))
            labeled_indices = {i for i in range(0, n_hist, step_lbl)} | {0, n_hist - 1, peak_idx}

        bar_w = 24.0
        if effective_style == "pillars":
            slot_w = hist_span_px / max(1, n_hist)
            bar_w = max(8.0, min(42.0, slot_w * 0.56))
            base_y = val_to_y(min_v)
            for i, (px, py) in enumerate(pts):
                bh = max(4.0, base_y - py)
                bx = px - bar_w / 2
                val_str = f"{vals[i]:.1f}".rstrip("0").rstrip(".")
                svg_parts.append(
                    f'<rect x="{bx:.1f}" y="{py:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" fill="{accent_hex}" fill-opacity="0.88" rx="4"/>'
                )
                if i in labeled_indices:
                    svg_parts.append(
                        f'<text x="{px:.1f}" y="{py - 6:.1f}" fill="{accent_hex}" font-size="10" font-weight="bold" font-family="sans-serif" text-anchor="middle">{val_str}</text>'
                    )
        else:
            if len(pts) > 1:
                poly_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                area_pts = f"{pts[0][0]:.1f},{val_to_y(min_v):.1f} " + poly_pts + f" {pts[-1][0]:.1f},{val_to_y(min_v):.1f}"
                svg_parts.append(f'<polygon points="{area_pts}" fill="{accent_hex}" fill-opacity="0.14"/>')
                svg_parts.append(
                    f'<polyline points="{poly_pts}" fill="none" stroke="{accent_hex}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
                )
            dot_r = 4.2 if px_per_item >= 18.0 else 2.8
            for i, (px, py) in enumerate(pts):
                val_str = f"{vals[i]:.1f}".rstrip("0").rstrip(".")
                svg_parts.append(
                    f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{dot_r}" fill="{accent_hex}" stroke="{bg_base_hex}" stroke-width="1.2"/>'
                )
                if i in labeled_indices:
                    svg_parts.append(
                        f'<text x="{px:.1f}" y="{py - 7:.1f}" fill="{accent_hex}" font-size="9.5" font-weight="bold" font-family="sans-serif" text-anchor="middle">{val_str}</text>'
                    )

        # 5. Optional Running Average Line + Projected Future Average Line
        avg_pts = []
        avg_f_coords = []
        if show_trend and len(vals) >= 1:
            avg_pts = [(idx_to_x(i), val_to_y(av)) for i, av in enumerate(running_avgs)]
            if len(avg_pts) > 1:
                avg_poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in avg_pts)
                svg_parts.append(
                    f'<polyline points="{avg_poly}" fill="none" stroke="{avg_line_hex}" stroke-width="1.9" stroke-opacity="0.90" stroke-linecap="round"/>'
                )
            if px_per_item >= 14.0:
                for ax, ay in avg_pts:
                    svg_parts.append(
                        f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="3.0" fill="{avg_line_hex}" stroke="{bg_base_hex}" stroke-width="1.0"/>'
                    )

            if projected_avgs and avg_pts:
                avg_f_coords = [avg_pts[-1]] + [
                    (idx_to_x(n_hist + j), val_to_y(pav))
                    for j, pav in enumerate(projected_avgs)
                ]
                avg_f_poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in avg_f_coords)
                svg_parts.append(
                    f'<polyline points="{avg_f_poly}" fill="none" stroke="{avg_line_hex}" stroke-width="1.9" stroke-dasharray="4,4" stroke-opacity="0.85" stroke-linecap="round"/>'
                )
                for afx, afy in avg_f_coords[1:]:
                    svg_parts.append(
                        f'<circle cx="{afx:.1f}" cy="{afy:.1f}" r="3.2" fill="{avg_line_hex}" stroke="{bg_base_hex}" stroke-width="1.0"/>'
                    )
                last_afx, last_afy = avg_f_coords[-1]
                last_pav = projected_avgs[-1]
                pav_str = f"{last_pav:.1f}".rstrip("0").rstrip(".")
                svg_parts.append(
                    f'<text x="{last_afx:.1f}" y="{last_afy + 13:.1f}" fill="{avg_line_hex}" font-size="9" font-weight="bold" font-family="sans-serif" text-anchor="middle">Avg: {pav_str}</text>'
                )

        # 6. Optional Future Projection Line
        f_coords = []
        if forecast_pts_data and pts:
            f_coords = [pts[-1]] + [
                (idx_to_x(n_hist + j), val_to_y(f_val))
                for j, (_, f_val) in enumerate(forecast_pts_data)
            ]
            f_poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in f_coords)
            svg_parts.append(
                f'<polyline points="{f_poly}" fill="none" stroke="{proj_line_hex}" stroke-width="2.2" stroke-dasharray="5,4" stroke-linecap="round"/>'
            )
            for j, (fx, fy) in enumerate(f_coords[1:]):
                _, f_val = forecast_pts_data[j]
                f_str = f"{f_val:.1f}".rstrip("0").rstrip(".")
                is_last_pt = (j == len(forecast_pts_data) - 1)
                r_dot = 4.2 if is_last_pt else 3.0
                svg_parts.append(
                    f'<circle cx="{fx:.1f}" cy="{fy:.1f}" r="{r_dot}" fill="{proj_line_hex}" stroke="{bg_base_hex}" stroke-width="1.2"/>'
                )
                if is_last_pt or len(forecast_pts_data) <= 5:
                    svg_parts.append(
                        f'<text x="{fx:.1f}" y="{fy - 7:.1f}" fill="{proj_line_hex}" font-size="9.5" font-weight="bold" font-family="sans-serif" text-anchor="middle">{f_str}</text>'
                    )

        # 7. X-Axis Labels
        max_x_labels = max(6, int(plot_w // 85))
        step_x = max(1, (n_total - 1) // max_x_labels) if n_total > max_x_labels else 1
        for i, d_str in enumerate(all_dates):
            if i % step_x == 0 or i == n_total - 1:
                if i != n_total - 1 and (n_total - 1 - i) < max(1, step_x // 2):
                    continue
                px = idx_to_x(i)
                lbl = d_str if time_bucket == "weekly" else format_ui_date(d_str, "day_month")
                lbl_col = proj_line_hex if i >= n_hist else sub_hex
                svg_parts.append(
                    f'<text x="{px:.1f}" y="{height - 10}" fill="{lbl_col}" font-size="10" font-family="sans-serif" text-anchor="middle">{lbl}</text>'
                )

        svg_parts.append("</svg>")
        svg_str = "".join(svg_parts)
        b64 = base64.b64encode(svg_str.encode("utf-8")).decode("utf-8")
        base_img = ft.Image(src=f"data:image/svg+xml;base64,{b64}", width=width, height=height, fit=ft.BoxFit.CONTAIN)

        # --- Clean Hover Layer (Zero Native Tooltips — Instant Readout Pill Only) ---
        hover_readout_txt = ft.Text(
            "Hover any point, bar, or average node to inspect",
            size=11,
            weight=ft.FontWeight.W_600,
            color=get_subtext_color(theme_state["surface_card"]),
        )
        hover_readout_pill = ft.Container(
            top=6,
            right=32,
            padding=ft.Padding(left=10, right=10, top=4, bottom=4),
            border_radius=6,
            bgcolor=theme_state["surface_card"],
            border=make_border(1.5, get_border_color(theme_state["surface_card"])),
            content=hover_readout_txt,
        )

        overlay_controls = [base_img, hover_readout_pill]
        base_floor_y = val_to_y(min_v)

        def make_hover_hitbox(
            cx: float,
            cy: float,
            date_disp: str,
            val_num: float,
            prefix_tag: str = "",
            is_bar: bool = False,
            ring_color: str = None,
        ):
            v_str = f"{val_num:.2f}".rstrip("0").rstrip(".")
            readout_str = f"{prefix_tag}{date_disp}: {v_str} {unit_name}"
            active_ring = ring_color or theme_state["accent"]

            if is_bar:
                hit_w = max(14.0, bar_w + 2.0)
                hit_h = max(18.0, (base_floor_y - cy) + 6.0)
                hit_left = max(0.0, cx - hit_w / 2.0)
                hit_top = max(0.0, cy - 6.0)
                hit_radius = 4
            else:
                hit_w = 18.0
                hit_h = 18.0
                hit_left = max(0.0, cx - 9.0)
                hit_top = max(0.0, cy - 9.0)
                hit_radius = 9

            box_ctrl = ft.Container(
                left=hit_left,
                top=hit_top,
                width=hit_w,
                height=hit_h,
                border_radius=hit_radius,
                bgcolor=ft.Colors.TRANSPARENT,
            )

            def on_pt_hover(e, c=box_ctrl, lbl_s=readout_str, r_col=active_ring):
                hovered = (str(e.data).lower() == "true")
                if hovered:
                    c.border = make_border(2, r_col)
                    c.bgcolor = "#22FFFFFF" if get_text_color(bg_base_hex) == "#FFFFFF" else "#22000000"
                    hover_readout_txt.value = lbl_s
                    hover_readout_txt.color = r_col
                    hover_readout_pill.border = make_border(1.5, r_col)
                else:
                    c.border = None
                    c.bgcolor = ft.Colors.TRANSPARENT
                    hover_readout_txt.value = "Hover any point, bar, or average node to inspect"
                    hover_readout_txt.color = get_subtext_color(theme_state["surface_card"])
                    hover_readout_pill.border = make_border(1.5, get_border_color(theme_state["surface_card"]))
                try:
                    c.update()
                    hover_readout_pill.update()
                except Exception:
                    pass

            box_ctrl.on_hover = on_pt_hover
            return box_ctrl

        for i, (px, py) in enumerate(pts):
            nice_d = dates[i] if time_bucket == "weekly" else format_ui_date(dates[i], "short_text")
            overlay_controls.append(
                make_hover_hitbox(
                    px,
                    py,
                    nice_d,
                    vals[i],
                    prefix_tag="",
                    is_bar=(effective_style == "pillars"),
                    ring_color=theme_state["accent"],
                )
            )

        if forecast_pts_data and len(f_coords) > 1:
            for j, (fx, fy) in enumerate(f_coords[1:]):
                f_raw_d, f_val = forecast_pts_data[j]
                nice_fd = f_raw_d if time_bucket == "weekly" else format_ui_date(f_raw_d, "short_text")
                overlay_controls.append(
                    make_hover_hitbox(
                        fx,
                        fy,
                        nice_fd,
                        f_val,
                        prefix_tag="Projected • ",
                        is_bar=False,
                        ring_color=proj_line_hex,
                    )
                )

        if show_trend and avg_pts:
            avg_prefix = "Weekly Avg • " if time_bucket == "weekly" else "Running Avg • "
            for i, (ax, ay) in enumerate(avg_pts):
                nice_d = dates[i] if time_bucket == "weekly" else format_ui_date(dates[i], "short_text")
                overlay_controls.append(
                    make_hover_hitbox(
                        ax,
                        ay,
                        nice_d,
                        running_avgs[i],
                        prefix_tag=avg_prefix,
                        is_bar=False,
                        ring_color=avg_line_hex,
                    )
                )
            if len(avg_f_coords) > 1 and projected_avgs:
                for j, (afx, afy) in enumerate(avg_f_coords[1:]):
                    f_raw_d, _ = forecast_pts_data[j]
                    nice_fd = f_raw_d if time_bucket == "weekly" else format_ui_date(f_raw_d, "short_text")
                    overlay_controls.append(
                        make_hover_hitbox(
                            afx,
                            afy,
                            nice_fd,
                            projected_avgs[j],
                            prefix_tag="Projected Avg • ",
                            is_bar=False,
                            ring_color=avg_line_hex,
                        )
                    )

        return ft.Container(
            width=width,
            height=height,
            content=ft.Stack(overlay_controls, width=width, height=height),
        )
# =============================================================================
# >>> SECTION A2 END: SHARED UI HELPERS & INTERACTIVE SVG CHART GENERATOR <<<
# =============================================================================

# =============================================================================
# >>> SECTION A3 START: TOP NAVIGATION, POPUP MODALS & SETTINGS ENGINE <<<
# =============================================================================
    import os
    import wave
    import math
    import struct
    import tempfile
    import platform
    import subprocess

    schedule_body_container = ft.Container(expand=True)
    add_task_view = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=14)
    backlog_view = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=12)
    habits_view = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=14)
    all_tasks_view = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=10)

    current_view_index = 0
    content_area = ft.Container(expand=True)
    top_nav_row = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=24)

    def show_message(msg: str):
        page.snack_bar = ft.SnackBar(ft.Text(msg))
        page.snack_bar.open = True
        page.update()

    # Time Format Preference ("24h" or "12h") & Notification Chime State
    current_time_format = saved_settings.get("time_format", "24h")
    notif_sound_enabled = (saved_settings.get("notif_sound", "on") == "on")

    def _render_bell_wav(wav_path: str, note_events: list, master_gain: float = 0.22):
        """Synthesize warm, overlapping marimba/bell tones with soft overtones."""
        if os.path.exists(wav_path):
            return wav_path
        sample_rate = 44100
        total_dur = max(start_t + dur_t for _, start_t, dur_t in note_events) + 0.05
        total_samples = int(sample_rate * total_dur)
        mix_buf = [0.0] * total_samples

        for freq, start_t, dur_t in note_events:
            start_idx = int(start_t * sample_rate)
            note_samples = int(dur_t * sample_rate)
            for i in range(note_samples):
                idx = start_idx + i
                if idx >= total_samples:
                    break
                t = i / sample_rate
                # Smooth 8ms attack + natural exponential bell decay
                attack = min(1.0, t / 0.008)
                env = attack * math.exp(-5.2 * t)
                # Fundamental + gentle octave overtone + subtle 3rd harmonic for warmth
                tone = (
                    1.00 * math.sin(2.0 * math.pi * freq * t)
                    + 0.24 * math.sin(2.0 * math.pi * (freq * 2.0) * t) * math.exp(-3.0 * t)
                    + 0.06 * math.sin(2.0 * math.pi * (freq * 3.0) * t) * math.exp(-6.0 * t)
                )
                mix_buf[idx] += master_gain * env * tone

        frames = bytearray()
        for s in mix_buf:
            clamped = max(-0.95, min(0.95, s))
            frames.extend(struct.pack("<h", int(clamped * 32767)))

        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(bytes(frames))
        return wav_path

    def _ensure_sound_wav(kind: str = "notification") -> str:
        tmp_dir = tempfile.gettempdir()
        if kind == "celebration":
            # Uplifting ascending F-major triad + octave sparkle (F5 -> A5 -> C6 -> F6)
            path = os.path.join(tmp_dir, "habit_reward_chime_v2.wav")
            events = [
                (698.46, 0.00, 0.36),   # F5
                (880.00, 0.075, 0.38),  # A5
                (1046.50, 0.15, 0.42),  # C6
                (1396.91, 0.23, 0.55),  # F6
            ]
            return _render_bell_wav(path, events, master_gain=0.20)
        else:
            # Calm, pleasant two-note fifth interval (G5 -> D6)
            path = os.path.join(tmp_dir, "habit_notif_chime_v2.wav")
            events = [
                (783.99, 0.00, 0.32),   # G5
                (1174.66, 0.11, 0.45),  # D6
            ]
            return _render_bell_wav(path, events, master_gain=0.19)

    def play_notification_sound(kind: str = "notification"):
        if not notif_sound_enabled:
            return
        try:
            chime_path = _ensure_sound_wav(kind)
            sys_name = platform.system()
            if sys_name == "Windows":
                import winsound
                winsound.PlaySound(chime_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif sys_name == "Darwin":
                subprocess.Popen(["afplay", chime_path])
            elif sys_name == "Linux":
                for player in ("paplay", "aplay"):
                    try:
                        subprocess.Popen([player, chime_path])
                        break
                    except FileNotFoundError:
                        continue
        except Exception:
            pass

    # --- Non-Intrusive Floating Dopamine Celebration Toast (Top-Center Overlay) ---
    _celebration_seq = 0
    celeb_icon = ft.Icon(ft.Icons.EMOJI_EVENTS_ROUNDED, size=22, color=get_text_color(theme_state["accent"]))
    celeb_icon_badge = ft.Container(
        width=36,
        height=36,
        border_radius=18,
        bgcolor=theme_state["accent"],
        alignment=ft.Alignment(0, 0),
        content=celeb_icon,
    )
    celeb_headline_txt = ft.Text(size=13, weight=ft.FontWeight.BOLD, color=theme_state["accent"])
    celeb_sub_txt = ft.Text(size=11, color=get_text_color(theme_state["surface_card"]))

    def dismiss_celebration_toast(e=None):
        celebration_toast_card.opacity = 0.0
        celebration_toast_card.offset = ft.Offset(0, -0.5)
        celebration_toast_card.visible = False
        try:
            celebration_toast_host.update()
        except Exception:
            page.update()

    celebration_toast_card = ft.Container(
        visible=False,
        opacity=0.0,
        offset=ft.Offset(0, -0.5),
        animate_opacity=ft.Animation(240, ft.AnimationCurve.EASE_OUT),
        animate_offset=ft.Animation(280, ft.AnimationCurve.EASE_OUT_CUBIC),
        padding=ft.Padding(left=14, right=10, top=10, bottom=10),
        width=480,
        bgcolor=theme_state["surface_card"],
        border_radius=12,
        border=make_border(1.5, theme_state["accent"]),
        shadow=[
            ft.BoxShadow(
                spread_radius=2,
                blur_radius=22,
                color="#AA000000",
                offset=ft.Offset(0, 6),
            )
        ],
        content=ft.Row(
            [
                celeb_icon_badge,
                ft.Column(
                    [celeb_headline_txt, celeb_sub_txt],
                    spacing=2,
                    expand=True,
                ),
                ft.IconButton(
                    icon=ft.Icons.CLOSE_ROUNDED,
                    icon_size=16,
                    tooltip="Dismiss",
                    on_click=dismiss_celebration_toast,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    celebration_toast_host = ft.Container(
        top=62,
        left=0,
        right=0,
        alignment=ft.Alignment(0, -1),
        content=celebration_toast_card,
    )

    async def _run_celebration_toast_lifecycle(seq_id: int):
        await asyncio.sleep(0.02)
        if _celebration_seq != seq_id:
            return
        celebration_toast_card.opacity = 1.0
        celebration_toast_card.offset = ft.Offset(0, 0)
        try:
            celebration_toast_host.update()
        except Exception:
            pass
        await asyncio.sleep(4.2)
        if _celebration_seq != seq_id:
            return
        celebration_toast_card.opacity = 0.0
        celebration_toast_card.offset = ft.Offset(0, -0.5)
        try:
            celebration_toast_host.update()
        except Exception:
            pass
        await asyncio.sleep(0.26)
        if _celebration_seq == seq_id:
            celebration_toast_card.visible = False
            try:
                celebration_toast_host.update()
            except Exception:
                pass

    def trigger_celebration_popup(headline: str, subtext: str, is_streak: bool = False):
        """Show a non-blocking, auto-dismissing top celebration banner with reward chime."""
        nonlocal _celebration_seq
        _celebration_seq += 1
        cur_seq = _celebration_seq

        play_notification_sound("celebration")

        acc = theme_state["accent"]
        card_bg = theme_state["surface_card"]
        celebration_toast_card.bgcolor = card_bg
        celebration_toast_card.border = make_border(1.5, acc)
        celeb_icon_badge.bgcolor = acc
        celeb_icon.icon = ft.Icons.BOLT_ROUNDED if is_streak else ft.Icons.EMOJI_EVENTS_ROUNDED
        celeb_icon.color = get_text_color(acc)
        celeb_headline_txt.value = headline
        celeb_headline_txt.color = acc
        celeb_sub_txt.value = subtext
        celeb_sub_txt.color = get_text_color(card_bg)

        if celebration_toast_host not in page.overlay:
            page.overlay.append(celebration_toast_host)

        celebration_toast_card.opacity = 0.0
        celebration_toast_card.offset = ft.Offset(0, -0.5)
        celebration_toast_card.visible = True
        page.update()

        try:
            page.run_task(_run_celebration_toast_lifecycle, cur_seq)
        except Exception:
            celebration_toast_card.opacity = 1.0
            celebration_toast_card.offset = ft.Offset(0, 0)
            page.update()

    def format_time_display(time_str: str) -> str:
        if not time_str:
            return ""
        formatted_alerts = []
        for entry in time_str.split(";;"):
            parts_pipe = entry.strip().split("|")
            base_t = parts_pipe[0]
            offset_code = parts_pipe[1] if len(parts_pipe) > 1 else ""
            try:
                hm = base_t.split(":")
                h, m = int(hm[0]), int(hm[1])
                if current_time_format == "12h":
                    suffix = "AM" if h < 12 else "PM"
                    h_12 = h % 12 or 12
                    t_disp = f"{h_12}:{m:02d} {suffix}"
                else:
                    t_disp = f"{h:02d}:{m:02d}"
            except Exception:
                t_disp = base_t

            if offset_code.startswith("-") and offset_code.endswith("d") and offset_code[1:-1].isdigit():
                d_num = int(offset_code[1:-1])
                day_word = "day" if d_num == 1 else "days"
                formatted_alerts.append(f"{t_disp} ({d_num} {day_word} before)")
            elif offset_code == "-1w":
                formatted_alerts.append(f"{t_disp} (7 days before)")
            else:
                formatted_alerts.append(t_disp)
        return " + ".join(formatted_alerts)

    # --- Live Settings / Staged Color Studio Modal ---
    cur_edit_target = "accent"
    staged_theme = dict(theme_state)

    preview_box_title = ft.Text("Sample Habit Title", size=12, weight=ft.FontWeight.BOLD)
    preview_box_sub = ft.Text("Category • Daily • Ends 15 Dec", size=10)
    preview_chk_icon = ft.Icon(ft.Icons.CHECK_ROUNDED, size=14)
    preview_sample_btn = ft.Container(
        padding=ft.Padding(left=8, right=8, top=4, bottom=4),
        border_radius=5,
        content=ft.Row([preview_chk_icon, ft.Text("Done", size=10, weight=ft.FontWeight.BOLD)], spacing=4, tight=True),
    )

    mini_task_card = ft.Container(
        padding=10,
        border_radius=6,
        content=ft.Row(
            [
                ft.Column([preview_box_title, preview_box_sub], spacing=2, expand=True),
                preview_sample_btn,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    mini_shelf_box = ft.Container(
        padding=10,
        border_radius=8,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Shelf / Box Layer", size=11, weight=ft.FontWeight.BOLD),
                        ft.Text("Card Surface Layer ↓", size=10, italic=True),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                mini_task_card,
            ],
            spacing=6,
        ),
    )

    mini_preview_frame = ft.Container(
        padding=12,
        border_radius=10,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Live Preview:", size=11, weight=ft.FontWeight.BOLD),
                        ft.Container(expand=True),
                        ft.Text("(Click 'Apply Theme' to commit)", size=10, italic=True),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                mini_shelf_box,
            ],
            spacing=6,
        ),
    )

    hex_input = ft.TextField(
        label="Hex Code",
        value=staged_theme["accent"],
        width=110,
        text_size=12,
        on_focus=lambda _: set_typing(True),
        on_blur=lambda _: set_typing(False),
    )

    r_slider = ft.Slider(min=0, max=255, value=128, label="{value}", expand=True)
    g_slider = ft.Slider(min=0, max=255, value=128, label="{value}", expand=True)
    b_slider = ft.Slider(min=0, max=255, value=128, label="{value}", expand=True)

    def refresh_mini_preview():
        bg_col = staged_theme["bg"]
        box_col = staged_theme["box"]
        card_col = staged_theme["surface_card"]
        acc_col = staged_theme["accent"]

        mini_preview_frame.bgcolor = bg_col
        mini_preview_frame.border = make_border(1.5, get_border_color(bg_col))
        mini_preview_frame.content.controls[0].controls[0].color = get_text_color(bg_col)
        mini_preview_frame.content.controls[0].controls[2].color = get_subtext_color(bg_col)

        mini_shelf_box.bgcolor = box_col
        mini_shelf_box.border = make_border(1.5, get_border_color(box_col))
        mini_shelf_box.content.controls[0].controls[0].color = acc_col
        mini_shelf_box.content.controls[0].controls[1].color = get_subtext_color(box_col)

        mini_task_card.bgcolor = card_col
        mini_task_card.border = make_border(1.5, get_border_color(card_col))
        preview_box_title.color = get_text_color(card_col)
        preview_box_sub.color = get_subtext_color(card_col)

        preview_sample_btn.bgcolor = acc_col
        preview_chk_icon.color = get_text_color(acc_col)
        preview_sample_btn.content.controls[1].color = get_text_color(acc_col)

        active_hex = staged_theme[cur_edit_target]
        hex_input.value = active_hex
        r, g, b = hex_to_rgb(active_hex)
        r_slider.value = r
        g_slider.value = g
        b_slider.value = b

        for btn, k in [
            (target_accent_btn, "accent"),
            (target_bg_btn, "bg"),
            (target_surface_btn, "surface_card"),
            (target_box_btn, "box"),
        ]:
            is_sel = cur_edit_target == k
            btn.bgcolor = staged_theme["accent"] if is_sel else staged_theme["box"]
            btn.border = make_border(1.5, staged_theme["accent"])
            btn.content.color = get_text_color(staged_theme["accent"]) if is_sel else get_subtext_color(staged_theme["box"])

    def on_staged_color_change(new_hex: str):
        staged_theme[cur_edit_target] = new_hex
        refresh_mini_preview()
        page.update()

    def on_hex_submit(e):
        val = hex_input.value.strip()
        if not val.startswith("#"):
            val = "#" + val
        if len(val) in (4, 7):
            on_staged_color_change(val)

    hex_input.on_submit = on_hex_submit

    def on_slider_change(e):
        new_hex = rgb_to_hex(int(r_slider.value), int(g_slider.value), int(b_slider.value))
        on_staged_color_change(new_hex)

    r_slider.on_change = on_slider_change
    g_slider.on_change = on_slider_change
    b_slider.on_change = on_slider_change

    def select_edit_target(target_name: str):
        nonlocal cur_edit_target
        cur_edit_target = target_name
        refresh_mini_preview()
        page.update()

    def make_target_btn(label: str, target_key: str):
        return ft.Container(
            padding=ft.Padding(left=10, right=10, top=5, bottom=5),
            border_radius=6,
            on_click=lambda _, tk=target_key: select_edit_target(tk),
            content=ft.Text(label, size=11, weight=ft.FontWeight.BOLD),
        )

    target_accent_btn = make_target_btn("Accent", "accent")
    target_bg_btn = make_target_btn("Background", "bg")
    target_surface_btn = make_target_btn("Card Surface", "surface_card")
    target_box_btn = make_target_btn("Box / Shelf", "box")

    theme_presets = [
        ("Nordic Pine (Default)", "#092328", "#0D2E34", "#12544F", "#0F3840", "#8BBB92", "#2A835F"),
        ("Anki Classic", "#121212", "#181818", "#1E1E1E", "#222222", "#39D353", "#0E4429"),
        ("Cyber Sky", "#0A121E", "#111C2D", "#172A42", "#132338", "#38BDF8", "#0284C7"),
        ("Electric Violet", "#140D1E", "#1E132B", "#2B1B3D", "#231633", "#C084FC", "#9333EA"),
        ("Pitch OLED", "#000000", "#101010", "#161616", "#121212", "#10B981", "#059669"),
        ("Solar Amber", "#1C140D", "#291D13", "#38281B", "#2D2015", "#FBBF24", "#D97706"),
        ("Y2K Brushed Chrome", "#8E99A4", "#10171E", "#AAB4BE", "#1A2632", "#00E5FF", "#008394"),
    ]

    def stage_preset(p_tuple):
        _, bg_val, surf_val, card_val, box_val, acc_val, dim_val = p_tuple
        staged_theme["bg"] = bg_val
        staged_theme["surface"] = surf_val
        staged_theme["surface_card"] = card_val
        staged_theme["box"] = box_val
        staged_theme["accent"] = acc_val
        staged_theme["accent_dim"] = dim_val
        refresh_mini_preview()
        page.update()

    def make_preset_pill(p_tuple):
        p_name, _, _, card_val, _, acc_val, _ = p_tuple
        return ft.Container(
            padding=ft.Padding(left=10, right=10, top=5, bottom=5),
            bgcolor=card_val,
            border_radius=14,
            border=make_border(1.5, acc_val),
            on_click=lambda _, pr=p_tuple: stage_preset(pr),
            content=ft.Row(
                [
                    ft.Container(width=8, height=8, border_radius=4, bgcolor=acc_val),
                    ft.Text(p_name, size=11, color="#FFFFFF", weight=ft.FontWeight.W_500),
                ],
                spacing=6,
                tight=True,
            ),
        )

    preset_chips_row = ft.Row([make_preset_pill(p) for p in theme_presets], wrap=True, spacing=6)

    def set_time_format(fmt: str):
        nonlocal current_time_format
        current_time_format = fmt
        save_setting("time_format", fmt)
        time_24_btn.bgcolor = theme_state["accent"] if fmt == "24h" else theme_state["box"]
        time_24_btn.content.color = get_text_color(theme_state["accent"]) if fmt == "24h" else get_subtext_color(theme_state["box"])
        time_12_btn.bgcolor = theme_state["accent"] if fmt == "12h" else theme_state["box"]
        time_12_btn.content.color = get_text_color(theme_state["accent"]) if fmt == "12h" else get_subtext_color(theme_state["box"])
        switch_view(current_view_index)
        page.update()

    time_24_btn = ft.Container(
        padding=ft.Padding(left=12, right=12, top=6, bottom=6),
        bgcolor=theme_state["accent"] if current_time_format == "24h" else theme_state["box"],
        border_radius=6,
        border=make_border(1.5, theme_state["accent"]),
        on_click=lambda _: set_time_format("24h"),
        content=ft.Text(
            "24-Hour (14:30)",
            size=11,
            weight=ft.FontWeight.BOLD,
            color=get_text_color(theme_state["accent"]) if current_time_format == "24h" else get_subtext_color(theme_state["box"]),
        ),
    )

    time_12_btn = ft.Container(
        padding=ft.Padding(left=12, right=12, top=6, bottom=6),
        bgcolor=theme_state["accent"] if current_time_format == "12h" else theme_state["box"],
        border_radius=6,
        border=make_border(1.5, theme_state["accent"]),
        on_click=lambda _: set_time_format("12h"),
        content=ft.Text(
            "12-Hour AM/PM (2:30 PM)",
            size=11,
            weight=ft.FontWeight.BOLD,
            color=get_text_color(theme_state["accent"]) if current_time_format == "12h" else get_subtext_color(theme_state["box"]),
        ),
    )

    sound_toggle_btn = ft.OutlinedButton(
        content=ft.Text("Sound: On" if notif_sound_enabled else "Sound: Off", size=11, weight=ft.FontWeight.BOLD),
        icon=ft.Icons.VOLUME_UP_ROUNDED if notif_sound_enabled else ft.Icons.VOLUME_OFF_ROUNDED,
    )

    def toggle_notif_sound(e=None):
        nonlocal notif_sound_enabled
        notif_sound_enabled = not notif_sound_enabled
        save_setting("notif_sound", "on" if notif_sound_enabled else "off")
        sound_toggle_btn.content.value = "Sound: On" if notif_sound_enabled else "Sound: Off"
        sound_toggle_btn.icon = ft.Icons.VOLUME_UP_ROUNDED if notif_sound_enabled else ft.Icons.VOLUME_OFF_ROUNDED
        if notif_sound_enabled:
            play_notification_sound("notification")
        page.update()

    sound_toggle_btn.on_click = toggle_notif_sound

    def commit_staged_theme(e=None):
        for k, v in staged_theme.items():
            theme_state[k] = v
            save_setting(f"theme_{k}", v)

        apply_page_theme()
        rebuild_top_nav()
        if "settings_gear_btn" in locals() or "settings_gear_btn" in globals():
            try:
                settings_gear_btn.icon_color = theme_state["accent"]
            except Exception:
                pass

        sync_unit_popup_theme()
        close_settings_modal()
        switch_view(current_view_index)
        show_message("🎨 New theme applied & saved!")
        page.update()

    settings_modal_content = ft.Container(
        padding=16,
        width=480,
        bgcolor=theme_state["surface"],
        border_radius=10,
        border=make_border(1.5, theme_state["accent"]),
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SETTINGS_ROUNDED, color=theme_state["accent"], size=20),
                        ft.Text("Settings & Customization", weight=ft.FontWeight.BOLD, size=15),
                        ft.Container(expand=True),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE_ROUNDED,
                            icon_size=16,
                            on_click=lambda _: close_settings_modal(),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(color=get_border_color(theme_state["surface"]), height=4),
                ft.Text("Time Format & Alerts:", size=11, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                ft.Row(
                    [
                        time_24_btn,
                        time_12_btn,
                        sound_toggle_btn,
                        ft.OutlinedButton(
                            content=ft.Text("Test Alert", size=11, weight=ft.FontWeight.BOLD),
                            icon=ft.Icons.NOTIFICATIONS_ACTIVE_OUTLINED,
                            on_click=lambda _: page.run_task(
                                dispatch_immediate_notification,
                                "🔔 Habit & Task Tracker",
                                "Notification banner and chime are working!",
                            ),
                        ),
                    ],
                    spacing=8,
                    wrap=True,
                ),
                ft.Divider(color=get_border_color(theme_state["surface"]), height=4),
                mini_preview_frame,
                ft.Divider(color=get_border_color(theme_state["surface"]), height=4),
                ft.Text("Curated Presets:", size=11, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                preset_chips_row,
                ft.Divider(color=get_border_color(theme_state["surface"]), height=4),
                ft.Text("Custom Color Sliders:", size=11, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                ft.Row([target_accent_btn, target_bg_btn, target_surface_btn, target_box_btn], spacing=6, wrap=True),
                ft.Row([hex_input], alignment=ft.MainAxisAlignment.START),
                ft.Row([ft.Text("R", size=11, color="#EF4444", weight=ft.FontWeight.BOLD), r_slider]),
                ft.Row([ft.Text("G", size=11, color="#22C55E", weight=ft.FontWeight.BOLD), g_slider]),
                ft.Row([ft.Text("B", size=11, color="#3B82F6", weight=ft.FontWeight.BOLD), b_slider]),
                ft.Divider(color=get_border_color(theme_state["surface"]), height=6),
                ft.Row(
                    [
                        ft.FilledButton(
                            content=ft.Text("Apply Theme", weight=ft.FontWeight.BOLD),
                            icon=ft.Icons.CHECK_CIRCLE_ROUNDED,
                            on_click=commit_staged_theme,
                        ),
                        ft.TextButton(
                            content=ft.Text("Cancel"),
                            on_click=lambda _: close_settings_modal(),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=10,
                ),
            ],
            spacing=8,
            tight=True,
            scroll=ft.ScrollMode.AUTO,
        ),
    )

    settings_dialog = ft.AlertDialog(
        content=settings_modal_content,
        bgcolor=theme_state["surface"],
        shape=ft.RoundedRectangleBorder(radius=10),
    )

    def close_settings_modal():
        set_typing(False)
        if hasattr(page, "close"):
            page.close(settings_dialog)
        else:
            settings_dialog.open = False
            page.update()

    def open_settings_modal(e):
        nonlocal staged_theme
        staged_theme = dict(theme_state)
        settings_modal_content.bgcolor = theme_state["surface"]
        settings_dialog.bgcolor = theme_state["surface"]
        select_edit_target("accent")
        refresh_mini_preview()
        if settings_dialog not in page.overlay:
            page.overlay.append(settings_dialog)
        if hasattr(page, "open"):
            page.open(settings_dialog)
        else:
            page.dialog = settings_dialog
            settings_dialog.open = True
            page.update()

    popup_task_id = None
    popup_date_str = None
    popup_task_name = ""
    popup_unit_str = ""

    popup_bolt_icon = ft.Icon(ft.Icons.BOLT_ROUNDED, color=theme_state["accent"])
    popup_title_text = ft.Text(size=14, weight=ft.FontWeight.BOLD, color=theme_state["accent"])
    popup_amount_field = ft.TextField(
        label="Value",
        width=190,
        dense=True,
        autofocus=True,
        on_focus=lambda _: set_typing(True),
        on_blur=lambda _: set_typing(False),
    )

    async def _animate_log_banner_in():
        await asyncio.sleep(0.016)
        unit_popup_banner.opacity = 1.0
        unit_popup_banner.offset = ft.Offset(0, 0)
        try:
            unit_popup_banner.update()
        except Exception:
            pass

    async def _animate_log_banner_out():
        unit_popup_banner.opacity = 0.0
        unit_popup_banner.offset = ft.Offset(0, -0.35)
        try:
            unit_popup_banner.update()
        except Exception:
            pass
        await asyncio.sleep(0.16)
        unit_popup_banner.visible = False
        refresh_schedule_view()

    def show_unit_popup_animated():
        unit_popup_banner.opacity = 0.0
        unit_popup_banner.offset = ft.Offset(0, -0.35)
        unit_popup_banner.visible = True
        refresh_schedule_view()
        try:
            page.run_task(_animate_log_banner_in)
        except Exception:
            unit_popup_banner.opacity = 1.0
            unit_popup_banner.offset = ft.Offset(0, 0)
            page.update()

    def close_unit_popup(e=None):
        set_typing(False)
        if not unit_popup_banner.visible:
            return
        try:
            page.run_task(_animate_log_banner_out)
        except Exception:
            unit_popup_banner.visible = False
            refresh_schedule_view()

    def save_unit_popup(e=None):
        if popup_task_id is None or not popup_date_str:
            return
        raw_val = (popup_amount_field.value or "").strip().replace(",", ".")
        amt_val = None
        if raw_val:
            try:
                parsed = float(raw_val)
                amt_val = int(parsed) if parsed.is_integer() else round(parsed, 2)
            except ValueError:
                show_message("Please enter a valid number (e.g. 12.5 or 12,5)")
                return
        mark_complete_db(popup_task_id, completed_dt=f"{popup_date_str} 12:00:00", amount=amt_val)
        check_and_celebrate_habit_milestones(popup_task_name)
        set_typing(False)
        show_message(
            f"✓ {popup_task_name}" + (f": {amt_val:g} {popup_unit_str}" if amt_val is not None else "")
        )
        close_unit_popup()

    popup_amount_field.on_submit = save_unit_popup

    popup_log_btn_text = ft.Text("Log (Enter)", color=get_text_color(theme_state["accent"]), weight=ft.FontWeight.BOLD)
    popup_log_btn = ft.FilledButton(
        content=popup_log_btn_text,
        icon=ft.Icons.CHECK,
        icon_color=get_text_color(theme_state["accent"]),
        bgcolor=theme_state["accent"],
        on_click=save_unit_popup,
    )
    popup_cancel_btn_text = ft.Text("Cancel", color=get_subtext_color(theme_state["surface_card"]))

    unit_popup_banner = ft.Container(
        visible=False,
        opacity=0.0,
        offset=ft.Offset(0, -0.35),
        animate_opacity=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        animate_offset=ft.Animation(220, ft.AnimationCurve.EASE_OUT_CUBIC),
        padding=ft.Padding(left=16, right=16, top=10, bottom=10),
        bgcolor=theme_state["surface_card"],
        border_radius=10,
        border=make_border(1.5, theme_state["accent"]),
        shadow=[
            ft.BoxShadow(
                spread_radius=1,
                blur_radius=18,
                color="#99000000",
                offset=ft.Offset(0, 6),
            )
        ],
        content=ft.Row(
            [
                popup_bolt_icon,
                popup_title_text,
                popup_amount_field,
                popup_log_btn,
                ft.TextButton(content=popup_cancel_btn_text, on_click=close_unit_popup),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
            tight=True,
            wrap=True,
        ),
    )

    def sync_unit_popup_theme():
        acc = theme_state["accent"]
        card_c = theme_state["surface_card"]
        unit_popup_banner.bgcolor = card_c
        unit_popup_banner.border = make_border(1.5, acc)
        popup_bolt_icon.color = acc
        popup_title_text.color = acc
        popup_amount_field.border_color = acc
        popup_amount_field.focused_border_color = acc
        popup_amount_field.cursor_color = acc
        popup_log_btn.bgcolor = acc
        popup_log_btn.icon_color = get_text_color(acc)
        popup_log_btn_text.color = get_text_color(acc)
        popup_cancel_btn_text.color = get_subtext_color(card_c)

    nav_items = [
        (0, ft.Icons.CALENDAR_TODAY_ROUNDED, "1: Schedule & Today"),
        (1, ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED, "2: Add Task / Habit"),
        (2, ft.Icons.INBOX_ROUNDED, "3: Backlog Queue"),
        (3, ft.Icons.GRID_VIEW_ROUNDED, "4: Habits & Heatmap"),
        (4, ft.Icons.LIST_ALT_ROUNDED, "5: All Database Tasks"),
    ]

    def rebuild_top_nav():
        top_nav_row.controls.clear()
        for idx, icon_data, tip in nav_items:
            is_active = (idx == current_view_index)

            nav_btn = ft.IconButton(
                icon=icon_data,
                icon_size=23,
                icon_color=theme_state["accent"] if is_active else get_subtext_color(theme_state["bg"]),
                tooltip=tip,
                style=ft.ButtonStyle(
                    color={
                        ft.ControlState.HOVERED: theme_state["accent"],
                        ft.ControlState.DEFAULT: theme_state["accent"] if is_active else get_subtext_color(theme_state["bg"]),
                    },
                    bgcolor={
                        ft.ControlState.HOVERED: theme_state["surface"],
                        ft.ControlState.PRESSED: theme_state["box"],
                        ft.ControlState.DEFAULT: theme_state["surface_card"] if is_active else ft.Colors.TRANSPARENT,
                    },
                    shape=ft.RoundedRectangleBorder(radius=8),
                    padding=ft.Padding(12, 8, 12, 8),
                ),
                on_click=lambda _, i=idx: switch_view(i),
            )

            top_nav_row.controls.append(nav_btn)

    def switch_view(index):
        nonlocal current_view_index, is_typing
        is_typing = False
        unit_popup_banner.visible = False
        current_view_index = index
        rebuild_top_nav()
        if index == 0:
            content_area.content = build_schedule_layout()
            refresh_schedule_view()
        elif index == 1:
            content_area.content = add_task_view
            load_add_task_form()
        elif index == 2:
            content_area.content = backlog_view
            load_backlog_view()
        elif index == 3:
            content_area.content = habits_view
            load_habits_dashboard()
        elif index == 4:
            content_area.content = all_tasks_view
            load_all_tasks_view()
        page.update()
# =============================================================================
# >>> SECTION A3 END: TOP NAVIGATION, POPUP MODALS & SETTINGS ENGINE <<<
# =============================================================================

# =============================================================================
# >>> SECTION A4 START: VIEW 1 - SCHEDULE & TODAY (DAY / WEEK / MONTH) <<<
# =============================================================================
    date_header_text = ft.Text(size=16, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER, no_wrap=True)
    mode_rocker_row = ft.Row(spacing=4, tight=True)
    expanded_edit_task_id = None
    delete_confirm_task_id = None
    selected_task_idx = -1
    just_opened_edit_id = None
    active_edit_drawer_ctrl = None
    DRAWER_OPEN_H = 475
    progress_state = {"day": None, "week": None, "month": None}

    def get_saturated_progress_color(pct: float) -> str:
        """Keep the active theme's hue while scaling saturation from muted (0%) to full vivid accent (100%)."""
        p = max(0.0, min(1.0, float(pct)))
        hex_col = theme_state["accent"].lstrip("#")
        if len(hex_col) != 6:
            return theme_state["accent"]
        r = int(hex_col[0:2], 16) / 255.0
        g = int(hex_col[2:4], 16) / 255.0
        b = int(hex_col[4:6], 16) / 255.0

        max_c = max(r, g, b)
        min_c = min(r, g, b)
        l = (max_c + min_c) / 2.0
        if max_c == min_c:
            h = s = 0.0
        else:
            d = max_c - min_c
            s = d / (2.0 - max_c - min_c) if l > 0.5 else d / (max_c + min_c)
            if max_c == r:
                h = (g - b) / d + (6.0 if g < b else 0.0)
            elif max_c == g:
                h = (b - r) / d + 2.0
            else:
                h = (r - g) / d + 4.0
            h /= 6.0

        # Scale saturation smoothly from 20% of target at 0% progress up to 100% saturation when full
        scaled_s = s * (0.20 + 0.80 * p)

        def hue_to_rgb(p1, p2, t):
            if t < 0.0:
                t += 1.0
            if t > 1.0:
                t -= 1.0
            if t < 1.0 / 6.0:
                return p1 + (p2 - p1) * 6.0 * t
            if t < 0.5:
                return p2
            if t < 2.0 / 3.0:
                return p1 + (p2 - p1) * (2.0 / 3.0 - t) * 6.0
            return p1

        if scaled_s == 0.0:
            nr = ng = nb = l
        else:
            q = l * (1.0 + scaled_s) if l < 0.5 else l + scaled_s - l * scaled_s
            p_val = 2.0 * l - q
            nr = hue_to_rgb(p_val, q, h + 1.0 / 3.0)
            ng = hue_to_rgb(p_val, q, h)
            nb = hue_to_rgb(p_val, q, h - 1.0 / 3.0)

        return f"#{int(round(nr * 255)):02x}{int(round(ng * 255)):02x}{int(round(nb * 255)):02x}"

    async def _animate_progress_bar(pb: ft.ProgressBar, start_p: float, end_p: float):
        steps = 22
        for step in range(1, steps + 1):
            await asyncio.sleep(0.016)
            t = step / steps
            eased = 1.0 - pow(1.0 - t, 3)  # ease-out-cubic
            cur_p = start_p + (end_p - start_p) * eased
            pb.value = cur_p
            pb.color = get_saturated_progress_color(cur_p)
            try:
                pb.update()
            except Exception:
                break

    # In-place Day view unit input state
    inline_unit_task_id = None
    inline_unit_date_str = None
    inline_unit_name = ""
    inline_unit_label = ""
    just_opened_unit_id = None
    active_unit_pill_ctrl = None
    active_unit_inner_ctrl = None

    def format_amt(val) -> str:
        if val is None:
            return ""
        try:
            f_val = float(val)
            return f"{f_val:g}"
        except Exception:
            return str(val)

    def is_current_day_today() -> bool:
        return current_selected_date.strftime("%Y-%m-%d") == datetime.now().strftime("%Y-%m-%d")

    def update_date_header():
        date_header_text.color = theme_state["accent"] if is_current_day_today() else get_text_color(theme_state["bg"])
        if current_view_mode == "day":
            date_str = current_selected_date.strftime("%a, %d %b %Y")
            _, iso_week, _ = current_selected_date.isocalendar()
            date_header_text.value = f"{date_str} • W{iso_week}"
        elif current_view_mode == "week":
            start_w = current_selected_date - timedelta(days=current_selected_date.weekday())
            end_w = start_w + timedelta(days=6)
            _, iso_week, _ = current_selected_date.isocalendar()
            date_header_text.value = f"W{iso_week}: {start_w.strftime('%d %b')} – {end_w.strftime('%d %b %Y')}"
        elif current_view_mode == "month":
            date_header_text.value = current_selected_date.strftime("%B %Y")

    def jump_to_habit_analytics(habit_name: str):
        nonlocal active_heatmap_scope, active_heatmap_identifier
        active_heatmap_scope = "habit"
        active_heatmap_identifier = habit_name
        scope_dropdown.value = "habit"
        habit_analytics_state["start"] = None
        habit_analytics_state["end"] = None
        switch_view(3)

    def open_inline_unit_editor(
        tid: int,
        tname: str,
        date_str: str,
        unit_str: str,
        existing_amt=None,
    ):
        nonlocal inline_unit_task_id, inline_unit_date_str, inline_unit_name, inline_unit_label, just_opened_unit_id
        unit_popup_banner.visible = False
        inline_unit_task_id = tid
        inline_unit_date_str = date_str
        inline_unit_name = tname
        inline_unit_label = unit_str
        just_opened_unit_id = tid
        set_typing(True)
        refresh_schedule_view()

    def trigger_task_completion(
        tid: int,
        tname: str,
        date_str: str,
        unit_str: str = None,
        recurrence: str = "once",
        existing_amt=None,
    ):
        nonlocal popup_task_id, popup_date_str, popup_task_name, popup_unit_str
        nonlocal inline_unit_task_id, inline_unit_date_str, inline_unit_name, inline_unit_label, just_opened_unit_id
        has_unit = bool(unit_str and unit_str != "None" and recurrence != "once")
        if has_unit:
            mark_complete_db(tid, completed_dt=f"{date_str} 12:00:00", amount=existing_amt)
            if current_view_index == 0 and current_view_mode == "day":
                unit_popup_banner.visible = False
                inline_unit_task_id = tid
                inline_unit_date_str = date_str
                inline_unit_name = tname
                inline_unit_label = unit_str
                just_opened_unit_id = tid
                set_typing(True)
                refresh_schedule_view()
            else:
                inline_unit_task_id = None
                popup_task_id = tid
                popup_date_str = date_str
                popup_task_name = tname
                popup_unit_str = unit_str
                sync_unit_popup_theme()
                popup_title_text.value = f"Log {tname} ({unit_str}):"
                popup_amount_field.label = f"Amount ({unit_str})"
                popup_amount_field.value = format_amt(existing_amt)
                set_typing(True)
                show_unit_popup_animated()
                try:
                    popup_amount_field.focus()
                except Exception:
                    pass
        else:
            mark_complete_db(tid, completed_dt=f"{date_str} 12:00:00")
            check_and_celebrate_habit_milestones(tname)
            show_message(f"✓ {tname}")
            refresh_schedule_view()

# >>> SUB-SECTION A4b START: DAY TASKS LIST <<<
    async def _reveal_drawer_smoothly(drawer_box: ft.Container):
        await asyncio.sleep(0.016)
        drawer_box.height = DRAWER_OPEN_H
        drawer_box.opacity = 1.0
        try:
            drawer_box.update()
        except Exception:
            pass

    async def _expand_unit_pill_smoothly(
        pill_box: ft.Container,
        inner_box: ft.Container,
        tf_box: ft.TextField,
        target_w: int,
    ):
        await asyncio.sleep(0.025)
        pill_box.width = target_w
        try:
            pill_box.update()
        except Exception:
            return
        # Wait for the pill to finish opening before fading in the controls
        await asyncio.sleep(0.18)
        inner_box.opacity = 1.0
        try:
            inner_box.update()
        except Exception:
            pass
        await asyncio.sleep(0.04)
        try:
            tf_box.focus()
        except Exception:
            pass

    def build_day_tasks_view():
        nonlocal current_day_tasks, selected_task_idx, just_opened_edit_id, active_edit_drawer_ctrl
        nonlocal inline_unit_task_id, just_opened_unit_id, active_unit_pill_ctrl, active_unit_inner_ctrl
        target_date_str = current_selected_date.strftime("%Y-%m-%d")
        raw_tasks = fetch_tasks_for_date(target_date_str)
        comp_map = get_completions_for_date(target_date_str)

        # Keep incomplete tasks at top; move completed tasks to the bottom
        tasks = sorted(raw_tasks, key=lambda t: 1 if t[0] in comp_map else 0)
        current_day_tasks = tasks

        if selected_task_idx >= len(tasks):
            selected_task_idx = -1

        day_col = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=8)

        total_cnt = len(tasks)
        done_cnt = len([t for t in tasks if t[0] in comp_map])
        pct = (done_cnt / total_cnt) if total_cnt > 0 else 0.0

        day_pb_to_animate = None
        if total_cnt > 0:
            prev_day_pct = progress_state["day"] if progress_state["day"] is not None else 0.0
            progress_state["day"] = pct
            day_pb = ft.ProgressBar(
                value=prev_day_pct,
                color=get_saturated_progress_color(prev_day_pct),
                bgcolor=theme_state["surface"],
                height=7,
                border_radius=4,
            )
            if abs(pct - prev_day_pct) > 0.001:
                day_pb_to_animate = (day_pb, prev_day_pct, pct)

            status_text = (
                f"Mastered {done_cnt}/{total_cnt} ({int(pct * 100)}%)"
                if pct < 1.0
                else "★ All Daily Tasks Completed!"
            )
            day_progress_header = ft.Container(
                padding=12,
                bgcolor=theme_state["surface_card"] if pct == 1.0 else theme_state["box"],
                border_radius=8,
                border=make_border(
                    1.5,
                    theme_state["accent"] if pct == 1.0 else get_border_color(theme_state["box"]),
                ),
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(status_text, size=12, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                                ft.Text(f"{done_cnt} of {total_cnt}", size=11, color=get_subtext_color(theme_state["box"])),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        day_pb,
                    ],
                    spacing=6,
                ),
            )
            day_col.controls.append(day_progress_header)
        else:
            progress_state["day"] = 0.0

        if not tasks:
            empty_card = ft.Container(
                padding=24,
                bgcolor=theme_state["box"],
                border_radius=8,
                border=make_border(1.5, get_border_color(theme_state["box"])),
                alignment=ft.Alignment(0, 0),
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.AUTO_AWESOME_OUTLINED, color=theme_state["accent"], size=30),
                        ft.Text("Clear Day", size=15, weight=ft.FontWeight.BOLD, color=get_text_color(theme_state["box"])),
                        ft.Text(
                            "Nothing scheduled. Enjoy the downtime or tap '+ Add' above to plan a task or start a habit.",
                            size=11,
                            color=get_subtext_color(theme_state["box"]),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6,
                ),
            )
            day_col.controls.append(empty_card)
            return day_col

        drawer_to_animate = None
        unit_pill_to_animate = None

        for idx, t in enumerate(tasks):
            task_id, name, category, _, _, recurrence, _, _, _, note, unit = t[:11]
            custom_days = t[11] if len(t) > 11 else None
            t_rem = t[13] if len(t) > 13 else None
            is_done = task_id in comp_map
            logged_amt = comp_map[task_id]["amount"] if is_done else None
            is_focused = (selected_task_idx >= 0 and idx == selected_task_idx)
            is_expanded = (expanded_edit_task_id == task_id)
            is_habit = bool(recurrence and recurrence != "once")
            has_unit = bool(unit and unit != "None" and is_habit)
            is_logging_inline = (has_unit and inline_unit_task_id == task_id)

            def toggle_task(
                e, tid=task_id, tname=name, u_str=unit, rec_str=recurrence, cur_amt=logged_amt
            ):
                nonlocal inline_unit_task_id
                currently_done = tid in get_completions_for_date(target_date_str)
                if not currently_done:
                    trigger_task_completion(tid, tname, target_date_str, u_str, rec_str, cur_amt)
                else:
                    remove_completion_db(tid, target_date_str)
                    if inline_unit_task_id == tid:
                        inline_unit_task_id = None
                        set_typing(False)
                    unit_popup_banner.visible = False
                    show_message(f"↩ {tname}")
                    refresh_schedule_view()

            card_bg = theme_state["surface_card"] if (is_expanded or is_done) else theme_state["box"]
            is_highlighted = (is_focused or is_expanded or is_done)
            border_color = theme_state["accent"] if is_highlighted else get_border_color(theme_state["box"])
            card_border = ft.Border(
                top=ft.BorderSide(1.5, border_color),
                bottom=ft.BorderSide(1.5, border_color),
                left=ft.BorderSide(3.5, border_color),
                right=ft.BorderSide(1.5, border_color),
            )

            tag_parts = [category or "General"]
            if is_habit:
                if recurrence == "weekly" and custom_days:
                    tag_parts.append(f"weekly ({custom_days})")
                else:
                    tag_parts.append(recurrence)
            if unit and unit != "None":
                tag_parts.append(f"unit: {unit}")
                end_date_val = t[7] if len(t) > 7 else None
                if end_date_val:
                    tag_parts.append(f"ends {format_ui_date(end_date_val, 'short_text')}")
            if t_rem:
                tag_parts.append(f"🔔 {format_time_display(t_rem)}")

            tag_text = " • ".join(tag_parts)

            chk_control = ft.Checkbox(
                label=name,
                value=is_done,
                on_change=toggle_task,
                label_style=ft.TextStyle(
                    size=14,
                    weight=ft.FontWeight.W_600,
                    color=theme_state["accent"] if is_done else get_text_color(card_bg),
                ),
                fill_color={
                    ft.ControlState.SELECTED: theme_state["accent"],
                    ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT,
                },
                check_color=get_text_color(theme_state["accent"]),
            )
            left_col_items = [chk_control]
            if note:
                left_col_items.append(
                    ft.Container(
                        padding=ft.Padding(left=32, top=0, right=0, bottom=2),
                        content=ft.Text(f"📝 {note}", size=11, italic=True, color=get_subtext_color(card_bg)),
                    )
                )

            right_items = []
            if has_unit:
                has_logged_val = (is_done and logged_amt is not None)
                val_label = format_amt(logged_amt) if has_logged_val else "+"
                rest_pill_w = 38 if len(val_label) <= 1 else max(46, len(val_label) * 9 + 22)
                open_pill_w = 122

                unit_text_ctrl = ft.Text(
                    unit,
                    size=15,
                    weight=ft.FontWeight.BOLD,
                    color=theme_state["accent"],
                    no_wrap=True,
                )

                if is_logging_inline:
                    animate_pill = (just_opened_unit_id == task_id)
                    input_state = {"val": format_amt(logged_amt)}

                    inline_tf = ft.TextField(
                        value=input_state["val"],
                        hint_text="0",
                        width=46,
                        dense=True,
                        text_size=14,
                        text_align=ft.TextAlign.CENTER,
                        text_style=ft.TextStyle(
                            size=14,
                            height=1.0,
                            weight=ft.FontWeight.BOLD,
                            color=get_text_color(theme_state["surface_card"]),
                        ),
                        hint_style=ft.TextStyle(
                            size=14,
                            height=1.0,
                            color=get_subtext_color(theme_state["surface_card"]),
                        ),
                        border=ft.InputBorder.NONE,
                        filled=False,
                        bgcolor=ft.Colors.TRANSPARENT,
                        fill_color=ft.Colors.TRANSPARENT,
                        hover_color=ft.Colors.TRANSPARENT,
                        focus_color=ft.Colors.TRANSPARENT,
                        content_padding=ft.Padding(left=2, right=2, top=8, bottom=8),
                        cursor_color=theme_state["accent"],
                        on_change=lambda e, st=input_state: st.update({"val": e.control.value}),
                        on_focus=lambda _: set_typing(True),
                        on_blur=lambda _: set_typing(False),
                    )

                    input_well = ft.Container(
                        width=50,
                        height=30,
                        border_radius=15,
                        bgcolor=theme_state["surface_card"],
                        alignment=ft.Alignment(0, 0),
                        content=inline_tf,
                    )

                    async def _collapse_pill_and_refresh(
                        pill_ref: ft.Container,
                        inner_ref: ft.Container,
                        collapse_to_w: int,
                    ):
                        nonlocal inline_unit_task_id, active_unit_pill_ctrl, active_unit_inner_ctrl
                        # Fade inner controls out first, then shrink the pill smoothly
                        inner_ref.animate_opacity = ft.Animation(100, ft.AnimationCurve.EASE_IN)
                        inner_ref.opacity = 0.0
                        try:
                            inner_ref.update()
                        except Exception:
                            pass
                        await asyncio.sleep(0.10)
                        pill_ref.animate = ft.Animation(180, ft.AnimationCurve.EASE_IN_OUT_CUBIC)
                        pill_ref.width = collapse_to_w
                        try:
                            pill_ref.update()
                        except Exception:
                            pass
                        await asyncio.sleep(0.19)
                        inline_unit_task_id = None
                        active_unit_pill_ctrl = None
                        active_unit_inner_ctrl = None
                        refresh_schedule_view()

                    def submit_inline_unit(
                        e=None,
                        tid=task_id,
                        tname=name,
                        u_str=unit,
                        tf_ref=inline_tf,
                        st=input_state,
                    ):
                        nonlocal inline_unit_task_id
                        raw_v = (st["val"] if st["val"] is not None else (tf_ref.value or "")).strip().replace(",", ".")
                        amt_v = None
                        if raw_v:
                            try:
                                parsed = float(raw_v)
                                amt_v = int(parsed) if parsed.is_integer() else round(parsed, 2)
                            except ValueError:
                                show_message("Enter a valid number (e.g. 12.5 or 12,5)")
                                return
                        mark_complete_db(tid, completed_dt=f"{target_date_str} 12:00:00", amount=amt_v)
                        check_and_celebrate_habit_milestones(tname)
                        set_typing(False)
                        show_message(f"✓ {tname}" + (f": {amt_v:g} {u_str}" if amt_v is not None else ""))
                        next_lbl = format_amt(amt_v) if amt_v is not None else "+"
                        next_w = 38 if len(next_lbl) <= 1 else max(46, len(next_lbl) * 9 + 22)
                        if active_unit_pill_ctrl is not None and active_unit_inner_ctrl is not None:
                            try:
                                page.run_task(
                                    _collapse_pill_and_refresh,
                                    active_unit_pill_ctrl,
                                    active_unit_inner_ctrl,
                                    next_w,
                                )
                                return
                            except Exception:
                                pass
                        inline_unit_task_id = None
                        refresh_schedule_view()

                    def cancel_inline_unit(e=None, cw=rest_pill_w):
                        nonlocal inline_unit_task_id
                        set_typing(False)
                        if active_unit_pill_ctrl is not None and active_unit_inner_ctrl is not None:
                            try:
                                page.run_task(
                                    _collapse_pill_and_refresh,
                                    active_unit_pill_ctrl,
                                    active_unit_inner_ctrl,
                                    cw,
                                )
                                return
                            except Exception:
                                pass
                        inline_unit_task_id = None
                        refresh_schedule_view()

                    inline_tf.on_submit = submit_inline_unit

                    save_dot_btn = ft.Container(
                        width=28,
                        height=28,
                        border_radius=14,
                        bgcolor=theme_state["accent"],
                        alignment=ft.Alignment(0, 0),
                        on_click=submit_inline_unit,
                        tooltip="Save (Enter)",
                        content=ft.Icon(
                            ft.Icons.CHECK_ROUNDED,
                            size=16,
                            color=get_text_color(theme_state["accent"]),
                        ),
                    )

                    cancel_dot_btn = ft.Container(
                        width=28,
                        height=28,
                        border_radius=14,
                        bgcolor=theme_state["surface_card"],
                        alignment=ft.Alignment(0, 0),
                        on_click=cancel_inline_unit,
                        tooltip="Cancel (Esc)",
                        content=ft.Icon(
                            ft.Icons.CLOSE_ROUNDED,
                            size=15,
                            color=get_subtext_color(theme_state["surface_card"]),
                        ),
                    )

                    pill_controls_box = ft.Container(
                        opacity=0.0 if animate_pill else 1.0,
                        animate_opacity=ft.Animation(140, ft.AnimationCurve.EASE_OUT),
                        content=ft.Row(
                            [
                                save_dot_btn,
                                cancel_dot_btn,
                                input_well,
                            ],
                            spacing=4,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            tight=True,
                        ),
                    )

                    input_anim_pill = ft.Container(
                        width=rest_pill_w if animate_pill else open_pill_w,
                        height=38,
                        border_radius=19,
                        padding=ft.Padding(left=4, right=4, top=0, bottom=0),
                        alignment=ft.Alignment(1, 0),
                        bgcolor=theme_state["surface"],
                        border=make_border(1.5, theme_state["accent"]),
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                        animate=ft.Animation(190, ft.AnimationCurve.EASE_OUT_CUBIC),
                        content=pill_controls_box,
                    )
                    active_unit_pill_ctrl = input_anim_pill
                    active_unit_inner_ctrl = pill_controls_box
                    if animate_pill:
                        unit_pill_to_animate = (input_anim_pill, pill_controls_box, inline_tf, open_pill_w)
                        just_opened_unit_id = None
                else:
                    # Bold (W_800, size=15) number/plus centered cleanly inside the resting circle
                    input_anim_pill = ft.Container(
                        width=rest_pill_w,
                        height=38,
                        border_radius=19,
                        bgcolor=theme_state["accent"] if has_logged_val else theme_state["surface"],
                        border=make_border(
                            1.5,
                            theme_state["accent"] if has_logged_val else get_border_color(card_bg),
                        ),
                        alignment=ft.Alignment(0, 0),
                        tooltip="Click to log or edit value",
                        on_click=lambda _, tid=task_id, tn=name, us=unit, ca=logged_amt: open_inline_unit_editor(
                            tid, tn, target_date_str, us, ca
                        ),
                        content=ft.Text(
                            val_label,
                            size=15,
                            weight=ft.FontWeight.W_800,
                            color=get_text_color(theme_state["accent"]) if has_logged_val else theme_state["accent"],
                            text_align=ft.TextAlign.CENTER,
                            no_wrap=True,
                        ),
                    )

                unit_cluster = ft.Row(
                    [
                        input_anim_pill,
                        unit_text_ctrl,
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    tight=True,
                )
                right_items.append(unit_cluster)

            right_items.append(ft.Text(tag_text, size=12, color=get_subtext_color(card_bg)))

            if is_habit:
                habit_stats_btn = ft.Container(
                    width=36,
                    height=36,
                    alignment=ft.Alignment(0, 0),
                    border_radius=8,
                    bgcolor=theme_state["surface"],
                    on_click=lambda _, hname=name: jump_to_habit_analytics(hname),
                    tooltip=f"Open '{name}' Streak & Analytics",
                    content=ft.Icon(
                        ft.Icons.INSIGHTS_ROUNDED,
                        size=20,
                        color=theme_state["accent"] if is_done else get_subtext_color(card_bg),
                    ),
                )
                right_items.append(habit_stats_btn)

            edit_btn = ft.Container(
                width=36,
                height=36,
                alignment=ft.Alignment(0, 0),
                border_radius=8,
                bgcolor=theme_state["surface_card"] if is_expanded else theme_state["surface"],
                on_click=lambda _, tid=task_id: toggle_inline_edit(tid),
                tooltip="Collapse Edit" if is_expanded else "Edit or Delete Task",
                content=ft.Icon(
                    ft.Icons.EXPAND_LESS_ROUNDED if is_expanded else ft.Icons.EDIT_OUTLINED,
                    size=20,
                    color=theme_state["accent"] if is_expanded else get_subtext_color(card_bg),
                ),
            )
            right_items.append(edit_btn)

            card_children = [
                ft.Row(
                    [
                        ft.Column(left_col_items, spacing=2, expand=True),
                        ft.Row(
                            right_items,
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            tight=True,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            ]

            if is_expanded:
                animate_now = (just_opened_edit_id == task_id)
                drawer_wrapper = ft.Container(
                    height=0 if animate_now else DRAWER_OPEN_H,
                    opacity=0.0 if animate_now else 1.0,
                    padding=ft.Padding(top=10, left=0, right=0, bottom=0),
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    animate=ft.Animation(240, ft.AnimationCurve.EASE_OUT_CUBIC),
                    animate_opacity=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
                    content=build_inline_edit_drawer(task_id),
                )
                active_edit_drawer_ctrl = drawer_wrapper
                if animate_now:
                    drawer_to_animate = drawer_wrapper
                    just_opened_edit_id = None
                card_children.append(drawer_wrapper)

            day_col.controls.append(
                ft.Container(
                    content=ft.Column(card_children, spacing=0, tight=True),
                    padding=12,
                    bgcolor=card_bg,
                    border_radius=8,
                    border=card_border,
                )
            )

        if drawer_to_animate is not None:
            try:
                page.run_task(_reveal_drawer_smoothly, drawer_to_animate)
            except Exception:
                drawer_to_animate.height = DRAWER_OPEN_H
                drawer_to_animate.opacity = 1.0

        if unit_pill_to_animate is not None:
            p_box, in_box, t_box, tgt_w = unit_pill_to_animate
            try:
                page.run_task(_expand_unit_pill_smoothly, p_box, in_box, t_box, tgt_w)
            except Exception:
                p_box.width = tgt_w
                in_box.opacity = 1.0

        if day_pb_to_animate is not None:
            pb_ctrl, s_p, e_p = day_pb_to_animate
            try:
                page.run_task(_animate_progress_bar, pb_ctrl, s_p, e_p)
            except Exception:
                pb_ctrl.value = e_p
                pb_ctrl.color = get_saturated_progress_color(e_p)

        return day_col
# >>> SUB-SECTION A4b END: DAY TASKS LIST <<<

# >>> SUB-SECTION A4c START: VERTICAL WEEK VIEW, MONTH VIEW & SCHEDULE LAYOUT <<<
    def build_week_day_row(day_dt: datetime, today_str: str) -> ft.Control:
        d_str = day_dt.strftime("%Y-%m-%d")
        is_today = d_str == today_str
        is_selected = d_str == current_selected_date.strftime("%Y-%m-%d")

        day_tasks = fetch_tasks_for_date(d_str)
        comp_map = get_completions_for_date(d_str)

        total_cnt = len(day_tasks)
        done_cnt = len([t for t in day_tasks if t[0] in comp_map])
        is_fully_done = (total_cnt > 0 and done_cnt == total_cnt)

        row_bg = theme_state["surface_card"] if is_today else theme_state["box"]

        date_badge = ft.Container(
            width=76,
            on_click=lambda _, dt=day_dt: jump_to_specific_day(dt),
            tooltip=f"Open {day_dt.strftime('%A, %d %b')}",
            content=ft.Row(
                [
                    ft.Text(
                        day_dt.strftime("%a").upper(),
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=theme_state["accent"] if is_today else get_subtext_color(row_bg),
                    ),
                    ft.Text(
                        day_dt.strftime("%d"),
                        size=15,
                        weight=ft.FontWeight.BOLD,
                        color=theme_state["accent"] if (is_today or is_selected) else get_text_color(row_bg),
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        pct_badge = ft.Container(
            padding=ft.Padding(left=8, right=8, top=3, bottom=3),
            border_radius=5,
            bgcolor=theme_state["accent"] if is_fully_done else theme_state["surface"],
            content=ft.Text(
                "✓ 100%" if is_fully_done else (f"{done_cnt}/{total_cnt}" if total_cnt > 0 else "Clear"),
                size=10,
                weight=ft.FontWeight.BOLD,
                color=get_text_color(theme_state["accent"]) if is_fully_done else get_subtext_color(row_bg),
            ),
        )

        quick_day_add = ft.Container(
            padding=5,
            border_radius=6,
            bgcolor=theme_state["surface"],
            border=make_border(1, get_border_color(row_bg)),
            tooltip=f"Add task for {day_dt.strftime('%a, %d %b')}",
            on_click=lambda _, ds=d_str: (switch_view(1), load_add_task_form(default_date=ds)),
            content=ft.Icon(ft.Icons.ADD_ROUNDED, size=15, color=theme_state["accent"]),
        )

        if not day_tasks:
            middle_content = ft.Container(
                expand=True,
                on_click=lambda _, dt=day_dt: jump_to_specific_day(dt),
                content=ft.Text("—", size=12, color=get_subtext_color(row_bg)),
            )
        else:
            task_pills = []
            for t in day_tasks:
                tid, tname, _, _, _, trec, _, _, _, _, tunit = t[:11]
                t_rem = t[13] if len(t) > 13 else None
                done = tid in comp_map
                logged_amt = comp_map[tid]["amount"] if done else None

                def toggle_w_task(
                    e=None,
                    task_id=tid,
                    name_s=tname,
                    date_s=d_str,
                    u_s=tunit,
                    r_s=trec,
                    amt_s=logged_amt,
                    is_d=done,
                ):
                    if not is_d:
                        trigger_task_completion(task_id, name_s, date_s, u_s, r_s, amt_s)
                    else:
                        remove_completion_db(task_id, date_s)
                        unit_popup_banner.visible = False
                        refresh_schedule_view()

                rem_suffix = f" 🔔{format_time_display(t_rem)}" if t_rem else ""
                label_display = (
                    f"{tname} ({format_amt(logged_amt)}{tunit}){rem_suffix}"
                    if (done and logged_amt is not None and tunit)
                    else f"{tname}{rem_suffix}"
                )

                task_pills.append(
                    ft.Container(
                        padding=ft.Padding(left=8, right=10, top=5, bottom=5),
                        border_radius=6,
                        bgcolor=theme_state["surface_card"] if done else theme_state["surface"],
                        border=make_border(1, theme_state["accent"] if done else get_border_color(row_bg)),
                        on_click=toggle_w_task,
                        content=ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.CHECK_CIRCLE_ROUNDED if done else ft.Icons.RADIO_BUTTON_UNCHECKED_ROUNDED,
                                    size=15,
                                    color=theme_state["accent"] if done else get_subtext_color(row_bg),
                                ),
                                ft.Text(
                                    label_display,
                                    size=12,
                                    weight=ft.FontWeight.W_500 if done else ft.FontWeight.NORMAL,
                                    color=theme_state["accent"] if done else get_text_color(row_bg),
                                ),
                            ],
                            spacing=6,
                            tight=True,
                        ),
                    )
                )

            middle_content = ft.Row(task_pills, wrap=True, spacing=6, run_spacing=6, expand=True)

        border_col = (
            theme_state["accent"]
            if is_today
            else (theme_state["accent_dim"] if is_selected else get_border_color(row_bg))
        )

        return ft.Container(
            padding=12,
            bgcolor=row_bg,
            border_radius=8,
            border=make_border(1.5, border_col),
            content=ft.Row(
                [
                    date_badge,
                    ft.VerticalDivider(color=get_border_color(row_bg), width=1),
                    middle_content,
                    pct_badge,
                    quick_day_add,
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def build_week_tasks_view():
        start_w = current_selected_date - timedelta(days=current_selected_date.weekday())
        today_str = datetime.now().strftime("%Y-%m-%d")
        all_7_days = [start_w + timedelta(days=i) for i in range(7)]

        week_total_tasks = 0
        week_done_tasks = 0
        for d in all_7_days:
            d_s = d.strftime("%Y-%m-%d")
            tasks = fetch_tasks_for_date(d_s)
            comp = get_completions_for_date(d_s)
            week_total_tasks += len(tasks)
            week_done_tasks += len([t for t in tasks if t[0] in comp])

        week_pct = (week_done_tasks / week_total_tasks) if week_total_tasks > 0 else 0.0

        week_pb_to_animate = None
        prev_week_pct = progress_state["week"] if progress_state["week"] is not None else 0.0
        progress_state["week"] = week_pct
        week_pb = ft.ProgressBar(
            value=prev_week_pct,
            color=get_saturated_progress_color(prev_week_pct),
            bgcolor=theme_state["surface"],
            height=7,
            border_radius=4,
        )
        if abs(week_pct - prev_week_pct) > 0.001:
            week_pb_to_animate = (week_pb, prev_week_pct, week_pct)

        weekly_summary_shelf = ft.Container(
            padding=12,
            bgcolor=theme_state["surface_card"] if week_pct == 1.0 else theme_state["box"],
            border_radius=8,
            border=make_border(
                1.5,
                theme_state["accent"] if week_pct == 1.0 else get_border_color(theme_state["box"]),
            ),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.INSIGHTS_ROUNDED, size=16, color=theme_state["accent"]),
                                    ft.Text("Weekly Mastery", size=12, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                                ],
                                spacing=6,
                            ),
                            ft.Text(
                                f"★ 100% Habit Week! ({week_done_tasks}/{week_total_tasks})"
                                if week_pct == 1.0
                                else f"{week_done_tasks} of {week_total_tasks} completed ({int(week_pct * 100)}%)",
                                size=11,
                                weight=ft.FontWeight.BOLD if week_pct == 1.0 else ft.FontWeight.NORMAL,
                                color=theme_state["accent"] if week_pct == 1.0 else get_subtext_color(theme_state["box"]),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    week_pb,
                ],
                spacing=6,
            ),
        )

        if week_pb_to_animate is not None:
            pb_ctrl, s_p, e_p = week_pb_to_animate
            try:
                page.run_task(_animate_progress_bar, pb_ctrl, s_p, e_p)
            except Exception:
                pb_ctrl.value = e_p
                pb_ctrl.color = get_saturated_progress_color(e_p)

        return ft.Column(
            [weekly_summary_shelf] + [build_week_day_row(d, today_str) for d in all_7_days],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def build_month_tasks_view():
        year = current_selected_date.year
        month = current_selected_date.month
        cal = calendar.Calendar(firstweekday=0)
        month_weeks = cal.monthdatescalendar(year, month)
        today_str = datetime.now().strftime("%Y-%m-%d")

        month_total_tasks = 0
        month_done_tasks = 0
        for week in month_weeks:
            for d_date in week:
                if d_date.month == month:
                    d_s = d_date.strftime("%Y-%m-%d")
                    t_list = fetch_tasks_for_date(d_s)
                    c_map = get_completions_for_date(d_s)
                    month_total_tasks += len(t_list)
                    month_done_tasks += len([t for t in t_list if t[0] in c_map])

        month_pct = (month_done_tasks / month_total_tasks) if month_total_tasks > 0 else 0.0

        grid_col = ft.Column(spacing=6, expand=True)

        month_pb_to_animate = None
        if month_total_tasks > 0:
            prev_month_pct = progress_state["month"] if progress_state["month"] is not None else 0.0
            progress_state["month"] = month_pct
            month_pb = ft.ProgressBar(
                value=prev_month_pct,
                color=get_saturated_progress_color(prev_month_pct),
                bgcolor=theme_state["surface"],
                height=7,
                border_radius=4,
            )
            if abs(month_pct - prev_month_pct) > 0.001:
                month_pb_to_animate = (month_pb, prev_month_pct, month_pct)

            monthly_summary_shelf = ft.Container(
                padding=10,
                bgcolor=theme_state["surface_card"] if month_pct == 1.0 else theme_state["box"],
                border_radius=8,
                border=make_border(
                    1.5,
                    theme_state["accent"] if month_pct == 1.0 else get_border_color(theme_state["box"]),
                ),
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    "★ 100% Habit Month!" if month_pct == 1.0 else "Monthly Mastery",
                                    size=12,
                                    weight=ft.FontWeight.BOLD,
                                    color=theme_state["accent"],
                                ),
                                ft.Text(
                                    f"{month_done_tasks} of {month_total_tasks} completed ({int(month_pct * 100)}%)",
                                    size=11,
                                    color=get_subtext_color(theme_state["box"]),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        month_pb,
                    ],
                    spacing=5,
                ),
            )
            grid_col.controls.append(monthly_summary_shelf)
        else:
            progress_state["month"] = 0.0

        header_row = ft.Row(
            [
                ft.Container(
                    width=42,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Text("Wk", weight=ft.FontWeight.BOLD, size=11, color=get_subtext_color(theme_state["bg"])),
                )
            ]
            + [
                ft.Container(
                    expand=1,
                    alignment=ft.Alignment(-1, 0),
                    content=ft.Text(day_name, weight=ft.FontWeight.BOLD, size=12, color=get_subtext_color(theme_state["bg"])),
                )
                for day_name in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            ],
            spacing=6,
        )
        grid_col.controls.append(header_row)

        for week in month_weeks:
            _, iso_wk_num, _ = week[3].isocalendar()
            week_start_dt = datetime(week[0].year, week[0].month, week[0].day)
            is_cur_week = any(d.strftime("%Y-%m-%d") == today_str for d in week)

            week_badge = ft.GestureDetector(
                on_double_tap=lambda _, wdt=week_start_dt: jump_to_specific_week(wdt),
                content=ft.Container(
                    width=42,
                    border_radius=6,
                    bgcolor=theme_state["surface_card"] if is_cur_week else theme_state["box"],
                    border=make_border(
                        1.5,
                        theme_state["accent"] if is_cur_week else get_border_color(theme_state["box"]),
                    ),
                    alignment=ft.Alignment(0, 0),
                    tooltip=f"Double-click (or double-tap) to inspect Week {iso_wk_num}",
                    content=ft.Text(
                        f"W{iso_wk_num}",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=theme_state["accent"] if is_cur_week else get_subtext_color(theme_state["box"]),
                    ),
                ),
            )

            w_row = ft.Row([week_badge], spacing=6, expand=1)
            for day_date in week:
                d_str = day_date.strftime("%Y-%m-%d")
                in_month = day_date.month == month
                is_today = d_str == today_str
                day_dt = datetime(day_date.year, day_date.month, day_date.day)

                tasks = fetch_tasks_for_date(d_str) if in_month else []
                comp_map = get_completions_for_date(d_str) if in_month else {}

                cell_add_btn = ft.Container(
                    padding=2,
                    border_radius=4,
                    tooltip=f"Add task on {day_date.strftime('%d %b %Y')}",
                    on_click=lambda _, ds=d_str: (switch_view(1), load_add_task_form(default_date=ds)),
                    content=ft.Icon(ft.Icons.ADD_ROUNDED, size=14, color=get_subtext_color(theme_state["box"])),
                )

                day_num_trigger = ft.Container(
                    on_click=lambda _, dt=day_dt: jump_to_specific_day(dt),
                    tooltip=f"Open {day_date.strftime('%d %b %Y')}",
                    content=ft.Text(
                        str(day_date.day),
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=theme_state["accent"]
                        if is_today
                        else (get_text_color(theme_state["box"]) if in_month else get_subtext_color(theme_state["bg"])),
                    ),
                )

                cell_header = ft.Row(
                    [
                        day_num_trigger,
                        ft.Row(
                            [
                                ft.Text(
                                    f"{len(comp_map)}/{len(tasks)}" if tasks else "",
                                    size=10,
                                    color=theme_state["accent"],
                                ),
                                cell_add_btn,
                            ],
                            spacing=4,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            tight=True,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )

                task_entries_col = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, expand=True)

                for t in tasks:
                    tid, tname, _, _, _, trec, _, _, _, _, tunit = t[:11]
                    done = tid in comp_map
                    logged_amt = comp_map[tid]["amount"] if done else None

                    def toggle_m_task(
                        e,
                        task_id=tid,
                        name_s=tname,
                        date_s=d_str,
                        u_s=tunit,
                        r_s=trec,
                        amt_s=logged_amt,
                        is_d=done,
                    ):
                        if not is_d:
                            trigger_task_completion(task_id, name_s, date_s, u_s, r_s, amt_s)
                        else:
                            remove_completion_db(task_id, date_s)
                            unit_popup_banner.visible = False
                            refresh_schedule_view()

                    txt_label = f"{'✓ ' if done else '• '}{tname}" + (
                        f" ({format_amt(logged_amt)}{tunit})" if (done and logged_amt is not None and tunit) else ""
                    )
                    task_entries_col.controls.append(
                        ft.Container(
                            on_click=toggle_m_task,
                            tooltip="Click to complete / log unit (stays in Month view)",
                            content=ft.Text(
                                txt_label,
                                size=10,
                                color=theme_state["accent"] if done else get_subtext_color(theme_state["box"]),
                                no_wrap=True,
                            ),
                        )
                    )

                empty_day_filler = ft.Container(expand=True)
                task_entries_col.controls.append(empty_day_filler)

                border_col = theme_state["accent"] if is_today else get_border_color(theme_state["box"])
                day_box = ft.Container(
                    padding=6,
                    bgcolor=theme_state["box"] if in_month else theme_state["surface"],
                    border_radius=6,
                    border=make_border(1.5, border_col),
                    tooltip=f"Double-click (or double-tap) to inspect {day_date.strftime('%a, %d %b %Y')}",
                    content=ft.Column([cell_header, task_entries_col], spacing=3, expand=True),
                )

                w_row.controls.append(
                    ft.GestureDetector(
                        expand=1,
                        on_double_tap=lambda _, dt=day_dt: jump_to_specific_day(dt),
                        content=day_box,
                    )
                )
            grid_col.controls.append(w_row)

        if month_pb_to_animate is not None:
            pb_ctrl, s_p, e_p = month_pb_to_animate
            try:
                page.run_task(_animate_progress_bar, pb_ctrl, s_p, e_p)
            except Exception:
                pb_ctrl.value = e_p
                pb_ctrl.color = get_saturated_progress_color(e_p)

        return grid_col

    def jump_to_specific_day(dt: datetime):
        nonlocal current_selected_date, current_view_mode, selected_task_idx, inline_unit_task_id
        current_selected_date = dt
        current_view_mode = "day"
        selected_task_idx = -1
        inline_unit_task_id = None
        progress_state["day"] = None
        progress_state["week"] = None
        progress_state["month"] = None
        refresh_schedule_view()
    
    def jump_to_specific_week(dt: datetime):
        nonlocal current_selected_date, current_view_mode, selected_task_idx, inline_unit_task_id
        current_selected_date = dt
        current_view_mode = "week"
        selected_task_idx = -1
        inline_unit_task_id = None
        progress_state["day"] = None
        progress_state["week"] = None
        progress_state["month"] = None
        refresh_schedule_view()

    def set_mode(mode: str):
        nonlocal current_view_mode, selected_task_idx, inline_unit_task_id
        current_view_mode = mode
        selected_task_idx = -1
        inline_unit_task_id = None
        unit_popup_banner.visible = False
        progress_state["day"] = None
        progress_state["week"] = None
        progress_state["month"] = None
        refresh_schedule_view()

    def cycle_view_mode(delta: int):
        if delta == 0:
            return
        modes = ["day", "week", "month"]
        cur_idx = modes.index(current_view_mode)
        new_idx = max(0, min(len(modes) - 1, cur_idx + delta))
        if new_idx != cur_idx:
            set_mode(modes[new_idx])

    def update_mode_rocker():
        mode_rocker_row.controls.clear()
        for label, m_val in [("Day", "day"), ("Week", "week"), ("Month", "month")]:
            active = current_view_mode == m_val
            btn = ft.Container(
                padding=ft.Padding(left=12, right=12, top=6, bottom=6),
                border_radius=6,
                bgcolor=theme_state["surface_card"] if active else theme_state["box"],
                border=make_border(
                    1.5,
                    theme_state["accent"] if active else get_border_color(theme_state["box"]),
                ),
                on_click=lambda _, mv=m_val: set_mode(mv),
                tooltip=f"Switch to {label} view (Shortcut: {label[0]})",
                content=ft.Text(
                    label,
                    size=12,
                    weight=ft.FontWeight.BOLD if active else ft.FontWeight.W_500,
                    color=theme_state["accent"] if active else get_subtext_color(theme_state["box"]),
                ),
            )
            mode_rocker_row.controls.append(btn)

    def refresh_schedule_view():
        update_date_header()
        update_mode_rocker()

        is_today = is_current_day_today()
        today_btn_pill.bgcolor = theme_state["surface"] if is_today else theme_state["surface_card"]
        today_btn_pill.border = make_border(
            1.5,
            theme_state["accent"] if not is_today else get_border_color(theme_state["surface"]),
        )
        today_btn_text.color = theme_state["accent"] if not is_today else get_subtext_color(theme_state["surface"])
        today_btn_icon.color = theme_state["accent"] if not is_today else get_subtext_color(theme_state["surface"])

        quick_add_pill.bgcolor = theme_state["surface_card"]
        quick_add_pill.border = make_border(1.5, get_border_color(theme_state["box"]))
        quick_add_text.color = theme_state["accent"]
        quick_add_icon.color = theme_state["accent"]

        if current_view_mode == "day":
            schedule_body_container.content = build_day_tasks_view()
        elif current_view_mode == "week":
            schedule_body_container.content = build_week_tasks_view()
        elif current_view_mode == "month":
            schedule_body_container.content = build_month_tasks_view()
        page.update()

    def shift_date(delta_steps):
        if delta_steps == 0:
            return
        nonlocal current_selected_date, selected_task_idx, inline_unit_task_id
        selected_task_idx = -1
        inline_unit_task_id = None
        if current_view_mode == "day":
            current_selected_date += timedelta(days=delta_steps)
        elif current_view_mode == "week":
            current_selected_date += timedelta(weeks=delta_steps)
        elif current_view_mode == "month":
            month = current_selected_date.month + delta_steps
            year = current_selected_date.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            current_selected_date = current_selected_date.replace(year=year, month=month, day=1)
        progress_state["day"] = None
        progress_state["week"] = None
        progress_state["month"] = None
        refresh_schedule_view()

    def snap_to_today(e=None):
        nonlocal current_selected_date, selected_task_idx, inline_unit_task_id
        current_selected_date = datetime.now()
        selected_task_idx = -1
        inline_unit_task_id = None
        progress_state["day"] = None
        progress_state["week"] = None
        progress_state["month"] = None
        refresh_schedule_view()

    def open_quick_add_for_date(e=None):
        date_str = current_selected_date.strftime("%Y-%m-%d")
        switch_view(1)
        load_add_task_form(default_date=date_str)

    today_btn_text = ft.Text("Today", size=12, weight=ft.FontWeight.BOLD)
    today_btn_icon = ft.Icon(ft.Icons.CALENDAR_TODAY_ROUNDED, size=14)
    today_btn_pill = ft.Container(
        padding=ft.Padding(left=12, right=12, top=6, bottom=6),
        border_radius=6,
        on_click=snap_to_today,
        tooltip="Jump back to Today (Shortcut: T)",
        content=ft.Row([today_btn_icon, today_btn_text], spacing=6, tight=True),
    )

    quick_add_text = ft.Text("Add", size=12, weight=ft.FontWeight.BOLD)
    quick_add_icon = ft.Icon(ft.Icons.ADD_ROUNDED, size=15)
    quick_add_pill = ft.Container(
        padding=ft.Padding(left=12, right=12, top=6, bottom=6),
        border_radius=6,
        on_click=open_quick_add_for_date,
        tooltip="Add task for this specific day",
        content=ft.Row([quick_add_icon, quick_add_text], spacing=5, tight=True),
    )

    def build_schedule_layout():
        update_date_header()
        update_mode_rocker()

        is_today = is_current_day_today()
        today_btn_pill.bgcolor = theme_state["surface"] if is_today else theme_state["surface_card"]
        today_btn_pill.border = make_border(
            1.5,
            theme_state["accent"] if not is_today else get_border_color(theme_state["surface"]),
        )
        today_btn_text.color = theme_state["accent"] if not is_today else get_subtext_color(theme_state["surface"])
        today_btn_icon.color = theme_state["accent"] if not is_today else get_subtext_color(theme_state["surface"])

        quick_add_pill.bgcolor = theme_state["surface_card"]
        quick_add_pill.border = make_border(1.5, get_border_color(theme_state["box"]))
        quick_add_text.color = theme_state["accent"]
        quick_add_icon.color = theme_state["accent"]

        date_nav_cluster = ft.GestureDetector(
            on_scroll=lambda e: shift_date(get_scroll_direction(e)),
            content=ft.Row(
                [
                    ft.IconButton(
                        icon=ft.Icons.CHEVRON_LEFT_ROUNDED,
                        icon_size=22,
                        icon_color=theme_state["accent"],
                        tooltip="Previous (← or Scroll / Swipe)",
                        on_click=lambda _: shift_date(-1),
                    ),
                    ft.Container(
                        padding=ft.Padding(left=8, right=8, top=4, bottom=4),
                        content=date_header_text,
                        tooltip="Scroll wheel or swipe horizontally to travel in time",
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CHEVRON_RIGHT_ROUNDED,
                        icon_size=22,
                        icon_color=theme_state["accent"],
                        tooltip="Next (→ or Scroll / Swipe)",
                        on_click=lambda _: shift_date(1),
                    ),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
        )

        mode_scroll_zone = ft.GestureDetector(
            on_scroll=lambda e: cycle_view_mode(get_scroll_direction(e)),
            content=ft.Container(
                padding=ft.Padding(left=4, right=0, top=2, bottom=2),
                content=mode_rocker_row,
            ),
        )

        def make_edge_nav_strip(icon_data, delta: int, tip: str):
            strip = ft.Container(
                width=24,
                alignment=ft.Alignment(0, 0),
                border_radius=6,
                bgcolor=ft.Colors.TRANSPARENT,
                tooltip=tip,
                on_click=lambda _: shift_date(delta),
                content=ft.Icon(icon_data, size=18, color=get_border_color(theme_state["bg"])),
            )

            def on_edge_hover(e):
                if e.data == "true":
                    strip.bgcolor = theme_state["surface"]
                    strip.content.color = theme_state["accent"]
                else:
                    strip.bgcolor = ft.Colors.TRANSPARENT
                    strip.content.color = get_border_color(theme_state["bg"])
                strip.update()

            strip.on_hover = on_edge_hover
            return strip

        left_edge_cue = make_edge_nav_strip(ft.Icons.CHEVRON_LEFT_ROUNDED, -1, "Previous (or Scroll / Swipe)")
        right_edge_cue = make_edge_nav_strip(ft.Icons.CHEVRON_RIGHT_ROUNDED, 1, "Next (or Scroll / Swipe)")

        swipeable_body_wrapper = ft.GestureDetector(
            expand=True,
            on_horizontal_drag_end=lambda e: shift_date(
                -1 if (e.primary_velocity or 0) > 250 else (1 if (e.primary_velocity or 0) < -250 else 0)
            ),
            content=ft.Row(
                [
                    left_edge_cue,
                    schedule_body_container,
                    right_edge_cue,
                ],
                expand=True,
                spacing=4,
            ),
        )

        # Top-center floating overlay used on Week & Month views (Day uses in-place card input)
        body_with_floating_log = ft.Stack(
            [
                swipeable_body_wrapper,
                ft.Container(
                    left=0,
                    right=0,
                    top=8,
                    content=ft.Row(
                        [unit_popup_banner],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ),
            ],
            expand=True,
        )

        sub_header_bar = ft.Row(
            [
                ft.Container(
                    width=190,
                    alignment=ft.Alignment(-1, 0),
                    content=ft.Row(
                        [today_btn_pill, quick_add_pill],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        tight=True,
                    ),
                ),
                ft.Container(
                    expand=True,
                    alignment=ft.Alignment(0, 0),
                    content=date_nav_cluster,
                ),
                ft.Container(
                    width=190,
                    alignment=ft.Alignment(1, 0),
                    content=mode_scroll_zone,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        return ft.Column(
            [
                sub_header_bar,
                ft.Divider(color=get_border_color(theme_state["bg"]), height=1),
                body_with_floating_log,
            ],
            expand=True,
            spacing=8,
        )
# >>> SUB-SECTION A4c END: VERTICAL WEEK VIEW, MONTH VIEW & SCHEDULE LAYOUT <<<
# =============================================================================
# >>> SECTION A4 END: VIEW 1 - SCHEDULE & TODAY (DAY / WEEK / MONTH) <<<
# =============================================================================

# =============================================================================
# >>> SECTION A5 START: VIEW 2 - ADD TASK & EDIT TASK MODAL FORM <<<
# =============================================================================
# >>> SUB-SECTION A5a START: UNIFIED ADD TASK / HABIT FORM <<<
    UNIFORM_BORDER_W = 1.5

    selected_target_date = datetime.now()
    calendar_Browse_date = datetime.now()
    calendar_popup_open = False
    is_backlog_mode = False
    is_recurring_habit = False
    recurrence_freq = "weekly"
    has_note = False
    has_reminder = False
    has_second_reminder = False
    has_end_date = False
    initial_consistency_pct = 85

    def format_form_date_label(dt_val: datetime) -> str:
        today_s = datetime.now().strftime("%Y-%m-%d")
        if dt_val.strftime("%Y-%m-%d") == today_s:
            return f"Today • {dt_val.strftime('%d %b %Y')}"
        return dt_val.strftime("%a, %d %b %Y")

    def style_uniform_input(ctrl, surface_bg: str):
        ctrl.border_width = UNIFORM_BORDER_W
        ctrl.focused_border_width = UNIFORM_BORDER_W
        ctrl.border_color = get_border_color(surface_bg)
        ctrl.focused_border_color = theme_state["accent"]

    name_field = ft.TextField(
        label="Task or Habit Name",
        expand=True,
        border_width=UNIFORM_BORDER_W,
        focused_border_width=UNIFORM_BORDER_W,
        on_focus=lambda _: set_typing(True),
        on_blur=lambda _: set_typing(False),
    )

    linked_habit_badge = ft.Container(
        visible=False,
        padding=ft.Padding(left=10, right=10, top=6, bottom=6),
        bgcolor=theme_state["surface"],
        border_radius=6,
        border=make_border(UNIFORM_BORDER_W, get_border_color(theme_state["surface"])),
    )

    def check_live_linked_habit(e=None, do_update: bool = True):
        if is_backlog_mode or not is_recurring_habit:
            linked_habit_badge.visible = False
            if do_update:
                page.update()
            return

        linked_habit_badge.visible = True
        val = (name_field.value or "").strip().lower()
        existing = [h.lower() for h in get_distinct_habits()]
        is_coupled = bool(val and val in existing)

        if is_coupled:
            linked_habit_badge.bgcolor = theme_state["surface_card"]
            linked_habit_badge.border = make_border(UNIFORM_BORDER_W, theme_state["accent"])
            linked_habit_badge.content = ft.Row(
                [
                    ft.Icon(ft.Icons.LINK_ROUNDED, size=15, color=theme_state["accent"]),
                    ft.Text(
                        "Coupled with existing habit — streaks, heatmap & unit charts will merge on Page 4.",
                        size=11,
                        weight=ft.FontWeight.W_600,
                        color=theme_state["accent"],
                    ),
                ],
                spacing=6,
                tight=True,
            )
        else:
            linked_habit_badge.bgcolor = theme_state["surface"]
            linked_habit_badge.border = make_border(UNIFORM_BORDER_W, get_border_color(theme_state["surface"]))
            linked_habit_badge.content = ft.Row(
                [
                    ft.Icon(
                        ft.Icons.INFO_OUTLINED,
                        size=14,
                        color=get_subtext_color(theme_state["surface"]),
                    ),
                    ft.Text(
                        "Tip: Naming a habit the exact same as an existing one couples their history & unit stats on Page 4.",
                        size=11,
                        color=get_subtext_color(theme_state["surface"]),
                    ),
                ],
                spacing=6,
                tight=True,
            )

        if do_update:
            page.update()

    name_field.on_change = lambda e: check_live_linked_habit(e, do_update=True)

    # --- Unified Category Field + True Floating Overlay Dropdown ---
    category_field = ft.TextField(
        label="Category",
        hint_text="Write new or select existing",
        width=240,
        border_width=UNIFORM_BORDER_W,
        focused_border_width=UNIFORM_BORDER_W,
        on_focus=lambda _: set_typing(True),
        on_blur=lambda _: set_typing(False),
    )

    cat_arrow_icon = ft.Icon(ft.Icons.ARROW_DROP_DOWN, color=theme_state["accent"], size=22)
    cat_arrow_box = ft.Container(
        width=42,
        height=48,
        bgcolor=theme_state["surface_card"],
        border_radius=8,
        border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
        alignment=ft.Alignment(0, 0),
        content=cat_arrow_icon,
    )

    category_popup_btn = ft.PopupMenuButton(
        content=cat_arrow_box,
        bgcolor=theme_state["surface_card"],
        shape=ft.RoundedRectangleBorder(radius=8),
        menu_position=ft.PopupMenuPosition.UNDER,
        tooltip="Select existing category",
        items=[],
    )

    def rebuild_category_popup_items():
        cats = get_distinct_categories()
        if "General" not in cats:
            cats.insert(0, "General")
        cur_val = (category_field.value or "").strip().lower()
        category_popup_btn.bgcolor = theme_state["surface_card"]

        def pick_cat(chosen: str):
            category_field.value = chosen
            rebuild_category_popup_items()
            set_typing(False)
            page.update()

        menu_items = []
        for c_name in cats:
            is_sel = (c_name.lower() == cur_val)
            menu_items.append(
                ft.PopupMenuItem(
                    on_click=lambda _, ch=c_name: pick_cat(ch),
                    content=ft.Row(
                        [
                            ft.Text(
                                c_name,
                                size=13,
                                weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.W_500,
                                color=theme_state["accent"]
                                if is_sel
                                else get_text_color(theme_state["surface_card"]),
                            ),
                            ft.Icon(
                                ft.Icons.CHECK_ROUNDED,
                                size=15,
                                color=theme_state["accent"],
                                visible=is_sel,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        width=210,
                    ),
                )
            )
        category_popup_btn.items = menu_items

    category_field.on_change = lambda _: rebuild_category_popup_items()

    category_trigger_row = ft.Row(
        [category_field, category_popup_btn],
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        tight=True,
    )

    restart_habit_dropdown = ft.Dropdown(
        label="↻ Load Habit Template",
        hint_text="Pre-fill & continue an existing habit",
        width=270,
        border_width=UNIFORM_BORDER_W,
        focused_border_width=UNIFORM_BORDER_W,
    )

    # --- Time Wheel Picker (Automatically Adapts to 24h vs 12h AM/PM Setting) ---
    def build_time_wheel_picker(initial_time="09:00", on_time_changed=None):
        h_val, m_val = 9, 0
        if initial_time and ":" in initial_time:
            try:
                clean_t = initial_time.split(";;")[0].split("|")[0]
                parts = clean_t.split(":")
                h_val, m_val = int(parts[0]) % 24, int(parts[1]) % 60
            except Exception:
                pass

        hour_text = ft.Text(size=20, weight=ft.FontWeight.BOLD, color=theme_state["accent"])
        min_text = ft.Text(size=20, weight=ft.FontWeight.BOLD, color=theme_state["accent"])
        ampm_text = ft.Text(size=13, weight=ft.FontWeight.BOLD, color=theme_state["accent"])

        def toggle_ampm(e=None):
            nonlocal h_val
            h_val = (h_val + 12) % 24
            sync_wheel_display()
            if on_time_changed:
                on_time_changed()
            page.update()

        ampm_pill = ft.Container(
            width=46,
            height=42,
            bgcolor=theme_state["surface_card"],
            border_radius=8,
            border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
            alignment=ft.Alignment(0, 0),
            on_click=toggle_ampm,
            tooltip="Click to toggle AM / PM",
            content=ampm_text,
        )

        presets_row = ft.Row(spacing=2, wrap=True, alignment=ft.MainAxisAlignment.CENTER)

        def sync_wheel_display():
            is_12h = (current_time_format == "12h")
            if is_12h:
                disp_h = h_val % 12 or 12
                hour_text.value = f"{disp_h}"
                ampm_text.value = "AM" if h_val < 12 else "PM"
                ampm_text.color = theme_state["accent"]
                ampm_pill.visible = True
                ampm_pill.bgcolor = theme_state["surface_card"]
                ampm_pill.border = make_border(UNIFORM_BORDER_W, theme_state["accent"])
            else:
                hour_text.value = f"{h_val:02d}"
                ampm_pill.visible = False

            min_text.value = f"{m_val:02d}"
            hour_text.color = theme_state["accent"]
            min_text.color = theme_state["accent"]

            presets_row.controls.clear()
            preset_defs = [
                ("8:00 AM" if is_12h else "08:00", 8, 0),
                ("12:00 PM" if is_12h else "12:00", 12, 0),
                ("5:00 PM" if is_12h else "17:00", 17, 0),
                ("8:00 PM" if is_12h else "20:00", 20, 0),
            ]
            for p_lbl, ph, pm in preset_defs:
                presets_row.controls.append(
                    ft.TextButton(
                        content=ft.Text(p_lbl, size=11, color=theme_state["accent"]),
                        on_click=lambda _, hh=ph, mm=pm: set_preset_time(hh, mm, notify_ui=True),
                    )
                )

        def step_hour(delta):
            nonlocal h_val
            h_val = (h_val + delta) % 24
            sync_wheel_display()
            if on_time_changed:
                on_time_changed()
            page.update()

        def step_min(delta):
            nonlocal m_val
            m_val = (m_val + delta) % 60
            sync_wheel_display()
            if on_time_changed:
                on_time_changed()
            page.update()

        def get_time_string():
            return f"{h_val:02d}:{m_val:02d}"

        def set_preset_time(h, m, notify_ui: bool = False):
            nonlocal h_val, m_val
            h_val, m_val = h % 24, m % 60
            sync_wheel_display()
            if on_time_changed:
                on_time_changed()
            if notify_ui:
                page.update()

        sync_wheel_display()

        h_col = ft.Column(
            [
                ft.IconButton(icon=ft.Icons.KEYBOARD_ARROW_UP_ROUNDED, icon_size=18, on_click=lambda _: step_hour(1)),
                ft.Container(
                    width=50,
                    height=42,
                    bgcolor=theme_state["surface_card"],
                    border_radius=8,
                    alignment=ft.Alignment(0, 0),
                    border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
                    content=hour_text,
                ),
                ft.IconButton(icon=ft.Icons.KEYBOARD_ARROW_DOWN_ROUNDED, icon_size=18, on_click=lambda _: step_hour(-1)),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        )

        m_col = ft.Column(
            [
                ft.IconButton(icon=ft.Icons.KEYBOARD_ARROW_UP_ROUNDED, icon_size=18, on_click=lambda _: step_min(5)),
                ft.Container(
                    width=50,
                    height=42,
                    bgcolor=theme_state["surface_card"],
                    border_radius=8,
                    alignment=ft.Alignment(0, 0),
                    border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
                    content=min_text,
                ),
                ft.IconButton(icon=ft.Icons.KEYBOARD_ARROW_DOWN_ROUNDED, icon_size=18, on_click=lambda _: step_min(-5)),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        )

        wheel_container = ft.Container(
            padding=8,
            bgcolor=theme_state["box"],
            border_radius=8,
            border=make_border(UNIFORM_BORDER_W, get_border_color(theme_state["box"])),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            h_col,
                            ft.Text(":", size=22, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                            m_col,
                            ampm_pill,
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                    presets_row,
                ],
                spacing=4,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        return wheel_container, get_time_string, set_preset_time

    # --- Date Picker Controls (Row 1 Anchor, defaults to Today) ---
    date_cal_icon = ft.Icon(ft.Icons.CALENDAR_MONTH_ROUNDED, color=theme_state["accent"], size=18)
    date_btn_label = ft.Text(
        format_form_date_label(selected_target_date),
        color=theme_state["accent"],
        weight=ft.FontWeight.BOLD,
        size=13,
    )
    date_arrow_icon = ft.Icon(ft.Icons.ARROW_DROP_DOWN, color=theme_state["accent"], size=18)

    calendar_popup_container = ft.Container(
        visible=False,
        padding=14,
        bgcolor=theme_state["surface"],
        border_radius=10,
        border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
        width=340,
    )

    def rebuild_calendar_popup():
        yr = calendar_Browse_date.year
        mo = calendar_Browse_date.month
        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdatescalendar(yr, mo)
        today_str = datetime.now().strftime("%Y-%m-%d")
        sel_str = selected_target_date.strftime("%Y-%m-%d")

        def shift_cal_month(delta):
            nonlocal calendar_Browse_date
            new_m = calendar_Browse_date.month + delta
            new_y = calendar_Browse_date.year + (new_m - 1) // 12
            new_m = (new_m - 1) % 12 + 1
            calendar_Browse_date = calendar_Browse_date.replace(year=new_y, month=new_m, day=1)
            rebuild_calendar_popup()
            page.update()

        def pick_cal_day(dt_val: datetime):
            nonlocal selected_target_date, calendar_popup_open
            selected_target_date = dt_val
            date_btn_label.value = format_form_date_label(selected_target_date)
            calendar_popup_open = False
            calendar_popup_container.visible = False
            if is_recurring_habit:
                rebuild_recurrence_visuals()
            page.update()

        cal_rows = [
            ft.Row(
                [
                    ft.IconButton(
                        icon=ft.Icons.CHEVRON_LEFT,
                        icon_size=18,
                        on_click=lambda _: shift_cal_month(-1),
                    ),
                    ft.Text(
                        calendar_Browse_date.strftime("%B %Y"),
                        weight=ft.FontWeight.BOLD,
                        size=14,
                        color=theme_state["accent"],
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CHEVRON_RIGHT,
                        icon_size=18,
                        on_click=lambda _: shift_cal_month(1),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Row(
                [
                    ft.Container(
                        width=36,
                        alignment=ft.Alignment(0, 0),
                        content=ft.Text(
                            d,
                            size=11,
                            color=get_subtext_color(theme_state["surface"]),
                            weight=ft.FontWeight.BOLD,
                        ),
                    )
                    for d in ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=6,
            ),
        ]

        for wk in weeks:
            r_controls = []
            for d_obj in wk:
                d_s = d_obj.strftime("%Y-%m-%d")
                in_m = d_obj.month == mo
                is_sel = d_s == sel_str
                is_tod = d_s == today_str
                dt_full = datetime(d_obj.year, d_obj.month, d_obj.day)

                bg = theme_state["accent"] if is_sel else (theme_state["box"] if in_m else theme_state["surface"])
                fg = (
                    get_text_color(theme_state["accent"])
                    if is_sel
                    else (get_text_color(theme_state["box"]) if in_m else get_subtext_color(theme_state["surface"]))
                )
                bdr = make_border(UNIFORM_BORDER_W, theme_state["accent"]) if (is_tod and not is_sel) else None

                r_controls.append(
                    ft.Container(
                        width=36,
                        height=34,
                        bgcolor=bg,
                        border_radius=6,
                        border=bdr,
                        alignment=ft.Alignment(0, 0),
                        on_click=lambda _, d_pick=dt_full: pick_cal_day(d_pick),
                        content=ft.Text(
                            str(d_obj.day),
                            size=12,
                            weight=ft.FontWeight.BOLD if (is_sel or is_tod) else ft.FontWeight.NORMAL,
                            color=fg,
                        ),
                    )
                )
            cal_rows.append(
                ft.Row(r_controls, alignment=ft.MainAxisAlignment.CENTER, spacing=6)
            )

        cal_rows.append(
            ft.Row(
                [
                    ft.TextButton(
                        content=ft.Text("Today", size=12, color=theme_state["accent"]),
                        on_click=lambda _: pick_cal_day(datetime.now()),
                    ),
                    ft.TextButton(
                        content=ft.Text("Close", size=12, color=get_subtext_color(theme_state["surface"])),
                        on_click=lambda _: toggle_calendar_popup(None),
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
            )
        )
        calendar_popup_container.content = ft.Column(cal_rows, spacing=6)

    def toggle_calendar_popup(e):
        nonlocal calendar_popup_open, calendar_Browse_date
        calendar_popup_open = not calendar_popup_open
        if calendar_popup_open:
            calendar_Browse_date = selected_target_date.replace(day=1)
            rebuild_calendar_popup()
        calendar_popup_container.visible = calendar_popup_open
        page.update()

    date_selector_button = ft.Container(
        padding=ft.Padding(left=14, right=14, top=9, bottom=9),
        bgcolor=theme_state["surface_card"],
        border_radius=8,
        border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
        on_click=toggle_calendar_popup,
        tooltip="Click to choose target / start date",
        content=ft.Row(
            [date_cal_icon, date_btn_label, date_arrow_icon],
            spacing=8,
            tight=True,
        ),
    )

    # --- Habit Recurrence, Units & Initial Goal Controls ---
    week_days_list = [
        ("Mon", "M"),
        ("Tue", "T"),
        ("Wed", "W"),
        ("Thu", "T"),
        ("Fri", "F"),
        ("Sat", "S"),
        ("Sun", "S"),
    ]
    month_names_list = [
        (1, "Jan"), (2, "Feb"), (3, "Mar"), (4, "Apr"), (5, "May"), (6, "Jun"),
        (7, "Jul"), (8, "Aug"), (9, "Sep"), (10, "Oct"), (11, "Nov"), (12, "Dec"),
    ]

    active_weekly_days = set()
    active_monthly_months = set(range(1, 13))
    single_month_mode = False

    interval_days_field = ft.TextField(
        label="Repeat Every X Days",
        value="2",
        width=160,
        border_width=UNIFORM_BORDER_W,
        focused_border_width=UNIFORM_BORDER_W,
        on_focus=lambda _: set_typing(True),
        on_blur=lambda _: set_typing(False),
    )

    common_units = ["None", "kg", "lb", "km", "sets", "reps", "mins", "hours", "pages", "+ Custom Unit"]
    unit_dropdown = ft.Dropdown(
        label="Habit Unit (Optional)",
        width=190,
        border_width=UNIFORM_BORDER_W,
        focused_border_width=UNIFORM_BORDER_W,
        options=[ft.dropdown.Option(key=u, text=u) for u in common_units],
        value="None",
    )

    custom_unit_field = ft.TextField(
        label="Custom Unit",
        width=150,
        visible=False,
        border_width=UNIFORM_BORDER_W,
        focused_border_width=UNIFORM_BORDER_W,
        on_focus=lambda _: set_typing(True),
        on_blur=lambda _: set_typing(False),
    )

    initial_goal_type_dd = ft.Dropdown(
        label="Unit Goal Type",
        width=175,
        visible=False,
        border_width=UNIFORM_BORDER_W,
        focused_border_width=UNIFORM_BORDER_W,
        value="max",
        options=[
            ft.dropdown.Option(key="max", text="Max / Peak Value"),
            ft.dropdown.Option(key="weekly_avg", text="Weekly Average"),
            ft.dropdown.Option(key="all_time_avg", text="Overall Average"),
        ],
    )

    initial_goal_val_field = ft.TextField(
        label="Target Goal (Optional)",
        hint_text="e.g. 90",
        width=165,
        visible=False,
        border_width=UNIFORM_BORDER_W,
        focused_border_width=UNIFORM_BORDER_W,
        on_focus=lambda _: set_typing(True),
        on_blur=lambda _: set_typing(False),
    )

    consistency_chips_row = ft.Row(spacing=6, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def rebuild_initial_consistency_chips():
        consistency_chips_row.controls.clear()
        consistency_chips_row.controls.append(
            ft.Text(
                "Consistency Goal:",
                size=11,
                weight=ft.FontWeight.BOLD,
                color=get_subtext_color(theme_state["surface"]),
            )
        )
        for pct_opt, lbl_opt in [
            (80, "80%"),
            (85, "85% (Recommended)"),
            (90, "90%"),
            (95, "95%"),
        ]:
            is_sel_c = (initial_consistency_pct == pct_opt)

            def pick_init_cons(e, pv=pct_opt):
                nonlocal initial_consistency_pct
                initial_consistency_pct = pv
                rebuild_initial_consistency_chips()
                page.update()

            consistency_chips_row.controls.append(
                ft.Container(
                    padding=ft.Padding(left=10, right=10, top=5, bottom=5),
                    border_radius=6,
                    bgcolor=theme_state["accent"] if is_sel_c else theme_state["box"],
                    border=make_border(
                        UNIFORM_BORDER_W,
                        theme_state["accent"] if is_sel_c else get_border_color(theme_state["box"]),
                    ),
                    on_click=pick_init_cons,
                    content=ft.Text(
                        lbl_opt,
                        size=11,
                        weight=ft.FontWeight.BOLD if is_sel_c else ft.FontWeight.W_500,
                        color=get_text_color(theme_state["accent"])
                        if is_sel_c
                        else get_subtext_color(theme_state["box"]),
                    ),
                )
            )

    def handle_unit_select(e):
        u_val = unit_dropdown.value
        has_u = bool(u_val and u_val != "None")
        custom_unit_field.visible = (u_val == "+ Custom Unit")
        initial_goal_type_dd.visible = has_u
        initial_goal_val_field.visible = has_u
        if has_u:
            u_lbl = (custom_unit_field.value or "").strip() if u_val == "+ Custom Unit" else u_val
            initial_goal_val_field.label = f"Target ({u_lbl or 'unit'})"
        page.update()

    unit_dropdown.on_select = handle_unit_select
    unit_dropdown.on_change = handle_unit_select
    custom_unit_field.on_change = lambda _: (
        setattr(initial_goal_val_field, "label", f"Target ({(custom_unit_field.value or '').strip() or 'unit'})"),
        page.update(),
    )

    recurrence_visual_container = ft.Column(spacing=10)
    habit_section_wrapper = ft.Container(
        visible=False,
        padding=12,
        bgcolor=theme_state["surface"],
        border_radius=8,
        border=make_border(UNIFORM_BORDER_W, get_border_color(theme_state["surface"])),
    )

    def set_recurrence_freq(freq_val: str):
        nonlocal recurrence_freq
        recurrence_freq = freq_val
        rebuild_recurrence_visuals()
        page.update()

    def toggle_daily_all_days(e=None):
        if len(active_weekly_days) == 7:
            active_weekly_days.clear()
        else:
            for d_k, _ in week_days_list:
                active_weekly_days.add(d_k)
        rebuild_recurrence_visuals()
        page.update()

    def set_single_month_mode(only_one: bool):
        nonlocal single_month_mode
        single_month_mode = only_one
        active_monthly_months.clear()
        if only_one:
            active_monthly_months.add(selected_target_date.month)
        else:
            active_monthly_months.update(range(1, 13))
        rebuild_recurrence_visuals()
        page.update()

    def rebuild_recurrence_visuals():
        recurrence_visual_container.controls.clear()
        if not is_recurring_habit or is_backlog_mode:
            return

        is_all_7_days = len(active_weekly_days) == 7

        def freq_pill(label: str, f_val: str):
            active = recurrence_freq == f_val
            return ft.Container(
                padding=ft.Padding(left=14, right=14, top=7, bottom=7),
                bgcolor=theme_state["surface_card"] if active else theme_state["box"],
                border_radius=6,
                border=make_border(UNIFORM_BORDER_W, theme_state["accent"] if active else get_border_color(theme_state["box"])),
                on_click=lambda _: set_recurrence_freq(f_val),
                content=ft.Text(
                    label,
                    size=12,
                    weight=ft.FontWeight.BOLD if active else ft.FontWeight.NORMAL,
                    color=theme_state["accent"] if active else get_subtext_color(theme_state["box"]),
                ),
            )

        freq_row = ft.Row(
            [
                freq_pill("Weekly / Daily", "weekly"),
                freq_pill("Monthly / Yearly", "monthly"),
                freq_pill("Every X Days", "custom_interval"),
            ],
            spacing=8,
            wrap=True,
        )
        recurrence_visual_container.controls.append(freq_row)

        if recurrence_freq == "weekly":
            balls_row = ft.Row(spacing=8, wrap=True)
            for d_key, d_init in week_days_list:
                ball_lit = d_key in active_weekly_days

                def click_day_ball(e, day_code=d_key):
                    if day_code in active_weekly_days:
                        active_weekly_days.remove(day_code)
                    else:
                        active_weekly_days.add(day_code)
                    rebuild_recurrence_visuals()
                    page.update()

                balls_row.controls.append(
                    ft.Container(
                        width=38,
                        height=38,
                        border_radius=19,
                        bgcolor=theme_state["accent"] if ball_lit else theme_state["box"],
                        border=make_border(UNIFORM_BORDER_W, theme_state["accent"] if ball_lit else get_border_color(theme_state["box"])),
                        alignment=ft.Alignment(0, 0),
                        on_click=click_day_ball,
                        tooltip=f"Click to toggle {d_key}",
                        content=ft.Text(
                            d_init,
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color=get_text_color(theme_state["accent"]) if ball_lit else get_subtext_color(theme_state["box"]),
                        ),
                    )
                )

            daily_toggle_btn = ft.Container(
                padding=ft.Padding(left=12, right=12, top=6, bottom=6),
                bgcolor=theme_state["accent"] if is_all_7_days else theme_state["box"],
                border_radius=19,
                border=make_border(UNIFORM_BORDER_W, theme_state["accent"] if is_all_7_days else get_border_color(theme_state["box"])),
                on_click=toggle_daily_all_days,
                tooltip="Toggle all 7 days on or off",
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE if is_all_7_days else ft.Icons.CIRCLE_OUTLINED,
                            size=15,
                            color=get_text_color(theme_state["accent"]) if is_all_7_days else get_subtext_color(theme_state["box"]),
                        ),
                        ft.Text(
                            "Daily (All 7)",
                            size=12,
                            weight=ft.FontWeight.BOLD,
                            color=get_text_color(theme_state["accent"]) if is_all_7_days else get_text_color(theme_state["box"]),
                        ),
                    ],
                    spacing=6,
                    tight=True,
                ),
            )

            status_hint = (
                "Every day of the week is active (Daily)!"
                if is_all_7_days
                else (
                    "Select which days of the week (or tap Daily):"
                    if len(active_weekly_days) == 0
                    else f"Repeating {len(active_weekly_days)} day(s) per week:"
                )
            )

            recurrence_visual_container.controls.append(
                ft.Column(
                    [
                        ft.Text(
                            status_hint,
                            size=11,
                            color=theme_state["accent"] if is_all_7_days else get_subtext_color(theme_state["surface"]),
                        ),
                        ft.Row(
                            [balls_row, daily_toggle_btn],
                            spacing=14,
                            wrap=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=6,
                )
            )

        elif recurrence_freq == "monthly":
            m_grid_rows = []
            for row_i in range(2):
                m_row_controls = []
                for col_i in range(6):
                    m_idx = row_i * 6 + col_i
                    m_num, m_label = month_names_list[m_idx]
                    has_dot = m_num in active_monthly_months

                    def click_month_box(e, month_val=m_num):
                        if single_month_mode:
                            active_monthly_months.clear()
                            active_monthly_months.add(month_val)
                        else:
                            if month_val in active_monthly_months and len(active_monthly_months) > 1:
                                active_monthly_months.remove(month_val)
                            else:
                                active_monthly_months.add(month_val)
                        rebuild_recurrence_visuals()
                        page.update()

                    dot_circle = ft.Container(
                        width=10,
                        height=10,
                        border_radius=5,
                        bgcolor=theme_state["accent"] if has_dot else theme_state["box"],
                        border=make_border(UNIFORM_BORDER_W, theme_state["accent"] if has_dot else get_border_color(theme_state["box"])),
                    )
                    m_row_controls.append(
                        ft.Container(
                            width=54,
                            height=48,
                            bgcolor=theme_state["surface_card"] if has_dot else theme_state["box"],
                            border_radius=6,
                            border=make_border(
                                UNIFORM_BORDER_W,
                                theme_state["accent"] if has_dot else get_border_color(theme_state["box"]),
                            ),
                            alignment=ft.Alignment(0, 0),
                            on_click=click_month_box,
                            tooltip=f"Click to select {m_label}",
                            content=ft.Column(
                                [
                                    ft.Text(
                                        m_label,
                                        size=11,
                                        weight=ft.FontWeight.BOLD,
                                        color=get_text_color(theme_state["surface_card"])
                                        if has_dot
                                        else get_subtext_color(theme_state["box"]),
                                    ),
                                    dot_circle,
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=4,
                            ),
                        )
                    )
                m_grid_rows.append(ft.Row(m_row_controls, spacing=6, wrap=True))

            def small_chip(txt: str, active: bool, fn):
                return ft.Container(
                    padding=ft.Padding(left=10, right=10, top=5, bottom=5),
                    bgcolor=theme_state["surface_card"] if active else theme_state["box"],
                    border_radius=6,
                    border=make_border(UNIFORM_BORDER_W, theme_state["accent"] if active else get_border_color(theme_state["box"])),
                    on_click=fn,
                    content=ft.Text(
                        txt,
                        size=11,
                        weight=ft.FontWeight.BOLD if active else ft.FontWeight.NORMAL,
                        color=theme_state["accent"] if active else get_subtext_color(theme_state["box"]),
                    ),
                )

            month_mode_toggle = ft.Row(
                [
                    small_chip(
                        "Every Month (All 12)",
                        (not single_month_mode and len(active_monthly_months) == 12),
                        lambda _: set_single_month_mode(False),
                    ),
                    small_chip(
                        "Only 1 Month (Yearly)",
                        single_month_mode,
                        lambda _: set_single_month_mode(True),
                    ),
                ],
                spacing=8,
                wrap=True,
            )

            recurrence_visual_container.controls.append(
                ft.Column(
                    [
                        ft.Text(
                            f"Repeats on day #{selected_target_date.day} of the selected month(s):",
                            size=11,
                            color=get_subtext_color(theme_state["surface"]),
                        ),
                        month_mode_toggle,
                        ft.Column(m_grid_rows, spacing=6),
                    ],
                    spacing=6,
                )
            )

        elif recurrence_freq == "custom_interval":
            recurrence_visual_container.controls.append(
                ft.Row(
                    [
                        interval_days_field,
                        ft.Text(
                            f"Starts on {selected_target_date.strftime('%d %b %Y')}",
                            size=12,
                            color=get_subtext_color(theme_state["surface"]),
                        ),
                    ],
                    spacing=14,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

    # --- Optional Toggles Row: Add Note | Set Reminder | Set End Date ---
    note_field = ft.TextField(
        label="Note",
        hint_text="Add extra details or context...",
        border_width=UNIFORM_BORDER_W,
        focused_border_width=UNIFORM_BORDER_W,
        on_focus=lambda _: set_typing(True),
        on_blur=lambda _: set_typing(False),
    )

    note_section_container = ft.Container(
        visible=False,
        padding=10,
        bgcolor=theme_state["surface"],
        border_radius=8,
        border=make_border(UNIFORM_BORDER_W, get_border_color(theme_state["surface"])),
        content=note_field,
    )

    alert_1_days_before = 0
    alert_2_days_before = 1

    alert_1_timing_row = ft.Row(spacing=6, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    alert_2_timing_row = ft.Row(spacing=6, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    alert_1_summary_txt = ft.Text(size=11, italic=True)
    alert_2_summary_txt = ft.Text(size=11, italic=True)

    def update_alert_summaries():
        t1_disp = format_time_display(get_add_time())
        if alert_1_days_before == 0:
            alert_1_summary_txt.value = f"Notifies on the scheduled day at {t1_disp}"
        else:
            d_w = "day" if alert_1_days_before == 1 else "days"
            alert_1_summary_txt.value = f"Notifies {alert_1_days_before} {d_w} before the task date at {t1_disp}"
        alert_1_summary_txt.color = get_subtext_color(theme_state["surface"])

        t2_disp = format_time_display(get_add_time_2())
        if alert_2_days_before == 0:
            alert_2_summary_txt.value = f"Notifies on the scheduled day at {t2_disp}"
        else:
            d_w2 = "day" if alert_2_days_before == 1 else "days"
            alert_2_summary_txt.value = f"Notifies {alert_2_days_before} {d_w2} before the task date at {t2_disp}"
        alert_2_summary_txt.color = get_subtext_color(theme_state["surface"])

    add_time_picker, get_add_time, set_add_time = build_time_wheel_picker(
        "09:00", on_time_changed=update_alert_summaries
    )
    add_time_picker_2, get_add_time_2, set_add_time_2 = build_time_wheel_picker(
        "09:00", on_time_changed=update_alert_summaries
    )

    alert_2_card = ft.Container(visible=False)
    second_alert_toggle_btn = ft.Container()

    def build_day_offset_controls(target_row: ft.Row, current_days: int, set_days_fn):
        target_row.controls.clear()
        on_day_active = (current_days == 0)
        before_active = (current_days > 0)

        target_row.controls.append(
            ft.Container(
                padding=ft.Padding(left=10, right=10, top=6, bottom=6),
                border_radius=6,
                bgcolor=theme_state["accent"] if on_day_active else theme_state["box"],
                border=make_border(UNIFORM_BORDER_W, theme_state["accent"] if on_day_active else get_border_color(theme_state["box"])),
                on_click=lambda _: set_days_fn(0),
                content=ft.Text(
                    "On the day",
                    size=11,
                    weight=ft.FontWeight.BOLD if on_day_active else ft.FontWeight.W_500,
                    color=get_text_color(theme_state["accent"]) if on_day_active else get_subtext_color(theme_state["box"]),
                ),
            )
        )

        if not before_active:
            target_row.controls.append(
                ft.Container(
                    padding=ft.Padding(left=10, right=10, top=6, bottom=6),
                    border_radius=6,
                    bgcolor=theme_state["box"],
                    border=make_border(UNIFORM_BORDER_W, get_border_color(theme_state["box"])),
                    on_click=lambda _: set_days_fn(1),
                    content=ft.Text(
                        "Days before...",
                        size=11,
                        weight=ft.FontWeight.W_500,
                        color=get_subtext_color(theme_state["box"]),
                    ),
                )
            )
        else:
            d_label = "1 day before" if current_days == 1 else f"{current_days} days before"
            target_row.controls.append(
                ft.Container(
                    padding=ft.Padding(left=4, right=4, top=2, bottom=2),
                    border_radius=6,
                    bgcolor=theme_state["surface_card"],
                    border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
                    content=ft.Row(
                        [
                            ft.Container(
                                width=24,
                                height=24,
                                border_radius=4,
                                bgcolor=theme_state["box"],
                                alignment=ft.Alignment(0, 0),
                                on_click=lambda _: set_days_fn(max(1, current_days - 1)),
                                content=ft.Icon(ft.Icons.REMOVE_ROUNDED, size=14, color=theme_state["accent"]),
                            ),
                            ft.Text(
                                d_label,
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color=theme_state["accent"],
                            ),
                            ft.Container(
                                width=24,
                                height=24,
                                border_radius=4,
                                bgcolor=theme_state["box"],
                                alignment=ft.Alignment(0, 0),
                                on_click=lambda _: set_days_fn(min(14, current_days + 1)),
                                content=ft.Icon(ft.Icons.ADD_ROUNDED, size=14, color=theme_state["accent"]),
                            ),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        tight=True,
                    ),
                )
            )

    def rebuild_alert_ui():
        def set_a1_days(val: int):
            nonlocal alert_1_days_before
            alert_1_days_before = val
            rebuild_alert_ui()
            page.update()

        def set_a2_days(val: int):
            nonlocal alert_2_days_before
            alert_2_days_before = val
            rebuild_alert_ui()
            page.update()

        build_day_offset_controls(alert_1_timing_row, alert_1_days_before, set_a1_days)
        build_day_offset_controls(alert_2_timing_row, alert_2_days_before, set_a2_days)
        update_alert_summaries()

        def toggle_second_alert(e=None):
            nonlocal has_second_reminder
            has_second_reminder = not has_second_reminder
            rebuild_alert_ui()
            page.update()

        second_alert_toggle_btn.content = ft.Container(
            padding=ft.Padding(left=10, right=10, top=5, bottom=5),
            border_radius=6,
            bgcolor=theme_state["surface_card"],
            border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
            on_click=toggle_second_alert,
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.CLOSE_ROUNDED if has_second_reminder else ft.Icons.ADD_ROUNDED,
                        size=14,
                        color=theme_state["accent"],
                    ),
                    ft.Text(
                        "Remove 2nd Alert" if has_second_reminder else "Add 2nd Alert",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=theme_state["accent"],
                    ),
                ],
                spacing=4,
                tight=True,
            ),
        )

        alert_2_card.visible = has_second_reminder
        if has_second_reminder:
            alert_2_card.width = 320
            alert_2_card.padding = 10
            alert_2_card.bgcolor = theme_state["box"]
            alert_2_card.border_radius = 8
            alert_2_card.border = make_border(UNIFORM_BORDER_W, get_border_color(theme_state["box"]))
            alert_2_card.content = ft.Column(
                [
                    ft.Text("Second Alert", size=12, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                    alert_2_timing_row,
                    add_time_picker_2,
                    alert_2_summary_txt,
                ],
                spacing=6,
            )

    alert_1_card = ft.Container(
        width=320,
        padding=10,
        bgcolor=theme_state["box"],
        border_radius=8,
        border=make_border(UNIFORM_BORDER_W, get_border_color(theme_state["box"])),
        content=ft.Column(
            [
                ft.Text("Primary Alert", size=12, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                alert_1_timing_row,
                add_time_picker,
                alert_1_summary_txt,
            ],
            spacing=6,
        ),
    )

    reminder_section_container = ft.Container(
        visible=False,
        padding=12,
        bgcolor=theme_state["surface"],
        border_radius=8,
        border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.ALARM_ROUNDED, size=16, color=theme_state["accent"]),
                                ft.Text("Reminder Alerts", size=12, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                            ],
                            spacing=6,
                        ),
                        second_alert_toggle_btn,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [alert_1_card, alert_2_card],
                    spacing=12,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ],
            spacing=8,
        ),
    )

    end_target_date = datetime.now() + timedelta(days=30)
    end_calendar_open = False
    end_calendar_browse = datetime.now()

    end_date_btn_label = ft.Text(
        end_target_date.strftime("%d %b %Y"),
        color=theme_state["accent"],
        weight=ft.FontWeight.BOLD,
        size=12,
    )

    end_calendar_container = ft.Container(
        visible=False,
        padding=12,
        bgcolor=theme_state["surface_card"],
        border_radius=10,
        border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
        width=320,
    )

    def set_duration_offset(days_delta: int, months_delta: int = 0):
        nonlocal end_target_date
        if months_delta > 0:
            new_m = selected_target_date.month + months_delta
            new_y = selected_target_date.year + (new_m - 1) // 12
            new_m = (new_m - 1) % 12 + 1
            end_target_date = selected_target_date.replace(
                year=new_y,
                month=new_m,
                day=min(selected_target_date.day, calendar.monthrange(new_y, new_m)[1]),
            )
        else:
            end_target_date = selected_target_date + timedelta(days=days_delta)
        end_date_btn_label.value = end_target_date.strftime("%d %b %Y")
        page.update()

    duration_chips_row = ft.Row(
        [
            ft.TextButton(content=ft.Text("2 Weeks", size=11), on_click=lambda _: set_duration_offset(14)),
            ft.TextButton(content=ft.Text("1 Month", size=11), on_click=lambda _: set_duration_offset(0, 1)),
            ft.TextButton(content=ft.Text("3 Months", size=11), on_click=lambda _: set_duration_offset(0, 3)),
            ft.TextButton(content=ft.Text("1 Year", size=11), on_click=lambda _: set_duration_offset(0, 12)),
        ],
        spacing=4,
        wrap=True,
    )

    def toggle_end_cal_popup(e):
        nonlocal end_calendar_open, end_calendar_browse
        end_calendar_open = not end_calendar_open
        if end_calendar_open:
            end_calendar_browse = end_target_date.replace(day=1)
            rebuild_end_cal_popup()
        end_calendar_container.visible = end_calendar_open
        page.update()

    def rebuild_end_cal_popup():
        yr = end_calendar_browse.year
        mo = end_calendar_browse.month
        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdatescalendar(yr, mo)
        sel_str = end_target_date.strftime("%Y-%m-%d")

        def shift_end_m(delta):
            nonlocal end_calendar_browse
            nm = end_calendar_browse.month + delta
            ny = end_calendar_browse.year + (nm - 1) // 12
            nm = (nm - 1) % 12 + 1
            end_calendar_browse = end_calendar_browse.replace(year=ny, month=nm, day=1)
            rebuild_end_cal_popup()
            page.update()

        def pick_end_d(dt_val: datetime):
            nonlocal end_target_date, end_calendar_open
            end_target_date = dt_val
            end_date_btn_label.value = end_target_date.strftime("%d %b %Y")
            end_calendar_open = False
            end_calendar_container.visible = False
            page.update()

        c_rows = [
            ft.Row(
                [
                    ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, icon_size=16, on_click=lambda _: shift_end_m(-1)),
                    ft.Text(end_calendar_browse.strftime("%B %Y"), weight=ft.FontWeight.BOLD, size=13, color=theme_state["accent"]),
                    ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_size=16, on_click=lambda _: shift_end_m(1)),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
        ]
        for wk in weeks:
            r_c = []
            for d_o in wk:
                ds = d_o.strftime("%Y-%m-%d")
                in_m = d_o.month == mo
                is_s = ds == sel_str
                dt_f = datetime(d_o.year, d_o.month, d_o.day)
                r_c.append(
                    ft.Container(
                        width=34,
                        height=30,
                        bgcolor=theme_state["accent"] if is_s else (theme_state["box"] if in_m else theme_state["surface"]),
                        border_radius=6,
                        alignment=ft.Alignment(0, 0),
                        on_click=lambda _, dp=dt_f: pick_end_d(dp),
                        content=ft.Text(
                            str(d_o.day),
                            size=11,
                            color=get_text_color(theme_state["accent"])
                            if is_s
                            else (get_text_color(theme_state["box"]) if in_m else get_subtext_color(theme_state["surface"])),
                        ),
                    )
                )
            c_rows.append(ft.Row(r_c, alignment=ft.MainAxisAlignment.CENTER, spacing=4))
        end_calendar_container.content = ft.Column(c_rows, spacing=4)

    end_date_selector_btn = ft.Container(
        padding=ft.Padding(left=12, right=12, top=8, bottom=8),
        bgcolor=theme_state["surface_card"],
        border_radius=8,
        border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
        on_click=toggle_end_cal_popup,
        content=ft.Row(
            [
                ft.Icon(ft.Icons.EVENT_BUSY_ROUNDED, color=theme_state["accent"], size=16),
                end_date_btn_label,
            ],
            spacing=6,
            tight=True,
        ),
    )

    end_date_section = ft.Container(
        visible=False,
        padding=10,
        bgcolor=theme_state["surface"],
        border_radius=8,
        border=make_border(UNIFORM_BORDER_W, get_border_color(theme_state["surface"])),
        content=ft.Column(
            [
                ft.Text("Stop Habit After (End Date or Quick Duration):", size=11, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                ft.Row(
                    [end_date_selector_btn, duration_chips_row],
                    spacing=10,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                end_calendar_container,
            ],
            spacing=6,
        ),
    )

    # --- 3-Option Mode Selector: [ Task ]  [ Habit ]  [ Backlog ] ---
    task_mode_pill = ft.Container(
        padding=ft.Padding(left=16, right=16, top=8, bottom=8),
        border_radius=8,
    )
    habit_mode_pill = ft.Container(
        padding=ft.Padding(left=16, right=16, top=8, bottom=8),
        border_radius=8,
    )
    backlog_pill_btn = ft.Container(
        padding=ft.Padding(left=14, right=14, top=8, bottom=8),
        border_radius=8,
        tooltip="Stash in Backlog without a scheduled date",
    )
    mode_selector_row = ft.Row([task_mode_pill, habit_mode_pill, backlog_pill_btn], spacing=8, tight=True)

    note_toggle_pill = ft.Container(
        padding=ft.Padding(left=12, right=12, top=7, bottom=7),
        border_radius=8,
    )
    reminder_toggle_pill = ft.Container(
        padding=ft.Padding(left=12, right=12, top=7, bottom=7),
        border_radius=8,
    )
    end_date_toggle_pill = ft.Container(
        padding=ft.Padding(left=12, right=12, top=7, bottom=7),
        border_radius=8,
    )

    save_btn_label = ft.Text("Save Task", weight=ft.FontWeight.BOLD)
    save_primary_btn = ft.FilledButton(
        content=save_btn_label,
        icon=ft.Icons.CHECK_ROUNDED,
    )

    def sync_form_visual_state():
        date_selector_button.visible = not is_backlog_mode
        date_btn_label.value = format_form_date_label(selected_target_date)
        date_btn_label.color = theme_state["accent"]
        date_cal_icon.color = theme_state["accent"]
        date_arrow_icon.color = theme_state["accent"]
        date_selector_button.bgcolor = theme_state["surface_card"]
        date_selector_button.border = make_border(UNIFORM_BORDER_W, theme_state["accent"])

        cat_arrow_box.bgcolor = theme_state["surface_card"]
        cat_arrow_box.border = make_border(UNIFORM_BORDER_W, theme_state["accent"])
        cat_arrow_icon.color = theme_state["accent"]
        category_popup_btn.bgcolor = theme_state["surface_card"]

        task_active = (not is_backlog_mode) and (not is_recurring_habit)
        habit_active = (not is_backlog_mode) and is_recurring_habit
        backlog_active = is_backlog_mode

        task_mode_pill.bgcolor = theme_state["accent"] if task_active else theme_state["surface"]
        task_mode_pill.border = make_border(
            UNIFORM_BORDER_W,
            theme_state["accent"] if task_active else get_border_color(theme_state["surface"]),
        )
        task_mode_pill.content = ft.Text(
            "Task",
            size=13,
            weight=ft.FontWeight.BOLD,
            color=get_text_color(theme_state["accent"]) if task_active else get_subtext_color(theme_state["surface"]),
        )

        habit_mode_pill.bgcolor = theme_state["accent"] if habit_active else theme_state["surface"]
        habit_mode_pill.border = make_border(
            UNIFORM_BORDER_W,
            theme_state["accent"] if habit_active else get_border_color(theme_state["surface"]),
        )
        habit_mode_pill.content = ft.Text(
            "Habit",
            size=13,
            weight=ft.FontWeight.BOLD,
            color=get_text_color(theme_state["accent"]) if habit_active else get_subtext_color(theme_state["surface"]),
        )

        backlog_pill_btn.bgcolor = theme_state["accent"] if backlog_active else theme_state["surface"]
        backlog_pill_btn.border = make_border(
            UNIFORM_BORDER_W,
            theme_state["accent"] if backlog_active else get_border_color(theme_state["surface"]),
        )
        backlog_pill_btn.content = ft.Row(
            [
                ft.Icon(
                    ft.Icons.INBOX_ROUNDED,
                    size=15,
                    color=get_text_color(theme_state["accent"]) if backlog_active else get_subtext_color(theme_state["surface"]),
                ),
                ft.Text(
                    "Backlog",
                    size=13,
                    weight=ft.FontWeight.BOLD,
                    color=get_text_color(theme_state["accent"]) if backlog_active else get_subtext_color(theme_state["surface"]),
                ),
            ],
            spacing=6,
            tight=True,
        )

        show_habit_block = is_recurring_habit and (not is_backlog_mode)
        habit_section_wrapper.visible = show_habit_block
        if show_habit_block:
            rebuild_recurrence_visuals()
            rebuild_initial_consistency_chips()
        check_live_linked_habit(do_update=False)

        def style_option_pill(pill: ft.Container, icon_data, label: str, active: bool):
            pill.bgcolor = theme_state["surface_card"] if active else theme_state["surface"]
            pill.border = make_border(
                UNIFORM_BORDER_W,
                theme_state["accent"] if active else get_border_color(theme_state["surface"]),
            )
            pill.content = ft.Row(
                [
                    ft.Icon(
                        icon_data,
                        size=15,
                        color=theme_state["accent"] if active else get_subtext_color(theme_state["surface"]),
                    ),
                    ft.Text(
                        label,
                        size=12,
                        weight=ft.FontWeight.BOLD if active else ft.FontWeight.W_500,
                        color=theme_state["accent"] if active else get_subtext_color(theme_state["surface"]),
                    ),
                ],
                spacing=6,
                tight=True,
            )

        style_option_pill(note_toggle_pill, ft.Icons.EDIT_OUTLINED, "Add Note", has_note)
        note_section_container.visible = has_note

        reminder_toggle_pill.visible = not is_backlog_mode
        style_option_pill(reminder_toggle_pill, ft.Icons.ALARM_ROUNDED, "Set Reminder", has_reminder)
        reminder_section_container.visible = has_reminder and (not is_backlog_mode)
        if reminder_section_container.visible:
            alert_1_card.bgcolor = theme_state["box"]
            alert_1_card.border = make_border(UNIFORM_BORDER_W, get_border_color(theme_state["box"]))
            rebuild_alert_ui()

        end_date_toggle_pill.visible = show_habit_block
        style_option_pill(end_date_toggle_pill, ft.Icons.EVENT_BUSY_ROUNDED, "Set End Date", has_end_date)
        end_date_section.visible = has_end_date and show_habit_block

        if is_backlog_mode:
            save_btn_label.value = "Send to Backlog"
            save_primary_btn.icon = ft.Icons.INBOX_ROUNDED
        elif is_recurring_habit:
            save_btn_label.value = "Save Habit"
            save_primary_btn.icon = ft.Icons.EVENT_REPEAT_ROUNDED
        else:
            save_btn_label.value = "Save Task"
            save_primary_btn.icon = ft.Icons.CHECK_ROUNDED
        save_btn_label.color = get_text_color(theme_state["accent"])
        save_primary_btn.bgcolor = theme_state["accent"]
        save_primary_btn.icon_color = get_text_color(theme_state["accent"])

    def select_task_mode(e=None):
        nonlocal is_backlog_mode, is_recurring_habit
        is_backlog_mode = False
        is_recurring_habit = False
        sync_form_visual_state()
        page.update()

    def select_habit_mode(e=None):
        nonlocal is_backlog_mode, is_recurring_habit, recurrence_freq
        was_habit = is_recurring_habit and (not is_backlog_mode)
        is_backlog_mode = False
        is_recurring_habit = True
        if not was_habit:
            recurrence_freq = "weekly"
            active_weekly_days.clear()
        sync_form_visual_state()
        page.update()

    def select_backlog_mode(e=None):
        nonlocal is_backlog_mode, is_recurring_habit, calendar_popup_open
        is_backlog_mode = True
        is_recurring_habit = False
        calendar_popup_open = False
        calendar_popup_container.visible = False
        sync_form_visual_state()
        page.update()

    def toggle_note_option(e=None):
        nonlocal has_note
        has_note = not has_note
        sync_form_visual_state()
        page.update()

    def toggle_reminder_option(e=None):
        nonlocal has_reminder
        has_reminder = not has_reminder
        sync_form_visual_state()
        page.update()

    def toggle_end_date_option(e=None):
        nonlocal has_end_date
        has_end_date = not has_end_date
        sync_form_visual_state()
        page.update()

    task_mode_pill.on_click = select_task_mode
    habit_mode_pill.on_click = select_habit_mode
    backlog_pill_btn.on_click = select_backlog_mode
    note_toggle_pill.on_click = toggle_note_option
    reminder_toggle_pill.on_click = toggle_reminder_option
    end_date_toggle_pill.on_click = toggle_end_date_option

    def reset_add_task_form(notify: bool = True):
        nonlocal selected_target_date, calendar_popup_open, end_calendar_open
        nonlocal is_backlog_mode, is_recurring_habit, recurrence_freq
        nonlocal has_note, has_reminder, has_second_reminder, has_end_date, single_month_mode, end_target_date
        nonlocal alert_1_days_before, alert_2_days_before, initial_consistency_pct

        name_field.value = ""
        category_field.value = ""
        note_field.value = ""
        linked_habit_badge.visible = False
        rebuild_category_popup_items()

        selected_target_date = datetime.now()
        end_target_date = datetime.now() + timedelta(days=30)
        end_date_btn_label.value = end_target_date.strftime("%d %b %Y")

        is_backlog_mode = False
        is_recurring_habit = False
        recurrence_freq = "weekly"
        active_weekly_days.clear()
        active_monthly_months.clear()
        active_monthly_months.update(range(1, 13))
        single_month_mode = False
        interval_days_field.value = "2"

        unit_dropdown.value = "None"
        custom_unit_field.value = ""
        custom_unit_field.visible = False
        initial_goal_type_dd.value = "max"
        initial_goal_type_dd.visible = False
        initial_goal_val_field.value = ""
        initial_goal_val_field.visible = False
        initial_consistency_pct = 85

        has_note = False
        has_reminder = False
        has_second_reminder = False
        alert_1_days_before = 0
        alert_2_days_before = 1
        set_add_time(9, 0)
        set_add_time_2(9, 0)

        has_end_date = False
        calendar_popup_open = False
        calendar_popup_container.visible = False
        end_calendar_open = False
        end_calendar_container.visible = False
        restart_habit_dropdown.value = None

        set_typing(False)
        sync_form_visual_state()
        if notify:
            show_message("Form cleared")
        page.update()

    def parse_days_before_code(code_str: str) -> int:
        if not code_str:
            return 0
        if code_str.startswith("-") and code_str.endswith("d") and code_str[1:-1].isdigit():
            return int(code_str[1:-1])
        if code_str == "-1w":
            return 7
        return 0

    def on_restart_habit_selected(e):
        h_name = restart_habit_dropdown.value
        if not h_name:
            return
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT category, recurrence_type, interval_days, note, unit, custom_days, custom_months, reminder_time
            FROM tasks
            WHERE LOWER(name) = LOWER(?) AND recurrence_type != 'once'
            ORDER BY id DESC LIMIT 1
            """,
            (h_name,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            cat_db, rec_db, int_db, note_db, unit_db, cdays_db, cmonths_db, rem_db = row
            name_field.value = h_name
            category_field.value = cat_db or ""
            rebuild_category_popup_items()

            nonlocal has_note, has_reminder, has_second_reminder, is_backlog_mode, is_recurring_habit, selected_target_date
            nonlocal alert_1_days_before, alert_2_days_before, initial_consistency_pct
            is_backlog_mode = False
            initial_consistency_pct = get_habit_consistency_target(h_name)

            if note_db:
                has_note = True
                note_field.value = note_db
            else:
                has_note = False
                note_field.value = ""

            if unit_db and unit_db != "None":
                if unit_db in common_units:
                    unit_dropdown.value = unit_db
                    custom_unit_field.visible = False
                else:
                    unit_dropdown.value = "+ Custom Unit"
                    custom_unit_field.value = unit_db
                    custom_unit_field.visible = True
                initial_goal_type_dd.visible = True
                initial_goal_val_field.visible = True
                initial_goal_val_field.label = f"Target ({unit_db})"
            else:
                unit_dropdown.value = "None"
                custom_unit_field.visible = False
                initial_goal_type_dd.visible = False
                initial_goal_val_field.visible = False

            if rem_db:
                has_reminder = True
                alerts_parts = rem_db.split(";;")
                p1 = alerts_parts[0].split("|")
                alert_1_days_before = parse_days_before_code(p1[1] if len(p1) > 1 else "")
                try:
                    rh, rm = int(p1[0].split(":")[0]), int(p1[0].split(":")[1])
                    set_add_time(rh, rm)
                except Exception:
                    pass
                if len(alerts_parts) > 1:
                    has_second_reminder = True
                    p2 = alerts_parts[1].split("|")
                    alert_2_days_before = parse_days_before_code(p2[1] if len(p2) > 1 else "-1d")
                    try:
                        rh2, rm2 = int(p2[0].split(":")[0]), int(p2[0].split(":")[1])
                        set_add_time_2(rh2, rm2)
                    except Exception:
                        pass
                else:
                    has_second_reminder = False
            else:
                has_reminder = False
                has_second_reminder = False

            is_rec = bool(rec_db and rec_db != "once")
            is_recurring_habit = is_rec
            active_weekly_days.clear()
            if is_rec:
                if rec_db in ["daily", "weekly"]:
                    set_recurrence_freq("weekly")
                    if rec_db == "daily":
                        active_weekly_days.update([d for d, _ in week_days_list])
                    elif cdays_db:
                        active_weekly_days.update([d.strip() for d in cdays_db.split(",") if d.strip()])
                elif rec_db in ["monthly", "yearly"]:
                    set_recurrence_freq("monthly")
                    if rec_db == "yearly":
                        set_single_month_mode(True)
                    if cmonths_db:
                        active_monthly_months.clear()
                        active_monthly_months.update([int(m.strip()) for m in cmonths_db.split(",") if m.strip().isdigit()])
                elif rec_db == "custom_interval":
                    set_recurrence_freq("custom_interval")
                    interval_days_field.value = str(int_db or 2)

            selected_target_date = datetime.now()
            sync_form_visual_state()
            show_message(f"↻ Loaded template for '{h_name}' — customize and save!")
            page.update()

    restart_habit_dropdown.on_select = on_restart_habit_selected
    restart_habit_dropdown.on_change = on_restart_habit_selected

    def build_serialized_reminder() -> str:
        if not has_reminder or is_backlog_mode:
            return None
        t1 = get_add_time()
        entry1 = f"{t1}|-{alert_1_days_before}d" if alert_1_days_before > 0 else t1
        if has_second_reminder:
            t2 = get_add_time_2()
            entry2 = f"{t2}|-{alert_2_days_before}d" if alert_2_days_before > 0 else t2
            return f"{entry1};;{entry2}"
        return entry1

    def handle_save_task(e):
        if not name_field.value or not name_field.value.strip():
            show_message("Task or habit name cannot be empty!")
            return

        if (not is_backlog_mode) and is_recurring_habit and recurrence_freq == "weekly" and len(active_weekly_days) == 0:
            show_message("Pick at least one weekday circle (or tap Daily)!")
            return

        clean_name = name_field.value.strip()
        final_category = (category_field.value or "").strip() or "General"
        note_val = (note_field.value or "").strip() if has_note else ""
        note_val = note_val if note_val else None

        if is_backlog_mode or not is_recurring_habit:
            rec_val = "once"
        elif recurrence_freq == "weekly":
            rec_val = "daily" if len(active_weekly_days) == 7 else "weekly"
        elif recurrence_freq == "monthly":
            rec_val = "yearly" if (single_month_mode and len(active_monthly_months) == 1) else "monthly"
        else:
            rec_val = "custom_interval"

        final_unit = None
        if rec_val != "once" and not is_backlog_mode:
            u_choice = unit_dropdown.value
            if u_choice == "+ Custom Unit":
                final_unit = (custom_unit_field.value or "").strip() or None
            elif u_choice and u_choice != "None":
                final_unit = u_choice

        # Parse optional initial unit goal if provided
        parsed_init_goal = None
        if final_unit and initial_goal_val_field.visible:
            raw_g = (initial_goal_val_field.value or "").strip().replace(",", ".")
            if raw_g:
                try:
                    parsed_init_goal = float(raw_g)
                except ValueError:
                    show_message("Enter a valid number for your Target Goal (or leave it blank)!")
                    return

        ordered_days = [d for d, _ in week_days_list if d in active_weekly_days]
        custom_days_str = ",".join(ordered_days) if rec_val == "weekly" else None
        custom_months_str = (
            ",".join([str(m) for m in sorted(active_monthly_months)])
            if rec_val in ["monthly", "yearly"]
            else None
        )

        final_end_date = (
            end_target_date.strftime("%Y-%m-%d")
            if (is_recurring_habit and has_end_date and not is_backlog_mode)
            else None
        )
        final_reminder = build_serialized_reminder()

        if is_backlog_mode:
            add_task_db(
                name=clean_name,
                category=final_category,
                time_frame="custom",
                target_date=None,
                recurrence_type="once",
                interval_days=0,
                end_date=None,
                custom_list="Backlog",
                note=note_val,
                unit=None,
                custom_days=None,
                custom_months=None,
                reminder_time=None,
            )
            reset_add_task_form(notify=False)
            show_message(f"📥 Saved to Backlog ({final_category})")
            switch_view(2)
        else:
            t_date = selected_target_date.strftime("%Y-%m-%d")
            int_days = 0
            if rec_val == "daily":
                int_days = 1
            elif rec_val == "weekly":
                int_days = 7
            elif rec_val == "custom_interval":
                int_days = (
                    int(interval_days_field.value)
                    if (interval_days_field.value and interval_days_field.value.isdigit())
                    else 2
                )

            add_task_db(
                name=clean_name,
                category=final_category,
                time_frame="day",
                target_date=t_date,
                recurrence_type=rec_val,
                interval_days=int_days,
                end_date=final_end_date,
                custom_list=None,
                note=note_val,
                unit=final_unit,
                custom_days=custom_days_str,
                custom_months=custom_months_str,
                reminder_time=final_reminder,
            )

            # Save Consistency Goal & Optional Unit Goal immediately upon Habit creation
            if rec_val != "once":
                set_habit_consistency_target(clean_name, initial_consistency_pct)
                if parsed_init_goal is not None:
                    add_habit_goal_db(
                        habit_name=clean_name,
                        goal_type=initial_goal_type_dd.value or "max",
                        target_value=parsed_init_goal,
                        start_date=t_date,
                        end_date=final_end_date,
                    )

            reset_add_task_form(notify=False)
            goal_msg = (
                f" + 🎯 Goal: {parsed_init_goal:g} {final_unit}"
                if parsed_init_goal is not None
                else (f" + 🎯 {initial_consistency_pct}% consistency goal" if rec_val != "once" else "")
            )
            show_message(f"✅ Saved '{clean_name}'{goal_msg}!")
            switch_view(0)

    save_primary_btn.on_click = handle_save_task

    clear_form_btn = ft.OutlinedButton(
        content=ft.Text("Clear", weight=ft.FontWeight.W_600),
        icon=ft.Icons.CLOSE_ROUNDED,
        on_click=lambda _: reset_add_task_form(notify=True),
    )

    def load_add_task_form(default_date=None):
        nonlocal selected_target_date, calendar_popup_open, is_backlog_mode
        distinct_habs = get_distinct_habits()
        if distinct_habs:
            restart_habit_dropdown.options = [ft.dropdown.Option(key=h, text=h) for h in distinct_habs]
            restart_habit_dropdown.visible = True
            restart_habit_dropdown.value = None
        else:
            restart_habit_dropdown.visible = False

        if default_date:
            selected_target_date = datetime.strptime(default_date, "%Y-%m-%d")
            is_backlog_mode = False
        else:
            selected_target_date = datetime.now()

        if single_month_mode:
            active_monthly_months.clear()
            active_monthly_months.add(selected_target_date.month)

        cur_h1, cur_m1 = map(int, get_add_time().split(":"))
        set_add_time(cur_h1, cur_m1)
        cur_h2, cur_m2 = map(int, get_add_time_2().split(":"))
        set_add_time_2(cur_h2, cur_m2)

        style_uniform_input(name_field, theme_state["box"])
        style_uniform_input(category_field, theme_state["box"])
        style_uniform_input(restart_habit_dropdown, theme_state["bg"])
        style_uniform_input(unit_dropdown, theme_state["surface"])
        style_uniform_input(custom_unit_field, theme_state["surface"])
        style_uniform_input(initial_goal_type_dd, theme_state["surface"])
        style_uniform_input(initial_goal_val_field, theme_state["surface"])
        style_uniform_input(interval_days_field, theme_state["surface"])
        style_uniform_input(note_field, theme_state["surface"])

        clear_form_btn.style = ft.ButtonStyle(
            side=ft.BorderSide(UNIFORM_BORDER_W, get_border_color(theme_state["box"])),
            shape=ft.RoundedRectangleBorder(radius=8),
        )

        rebuild_category_popup_items()
        rebuild_initial_consistency_chips()

        calendar_popup_open = False
        calendar_popup_container.visible = False
        calendar_popup_container.bgcolor = theme_state["surface"]
        calendar_popup_container.border = make_border(UNIFORM_BORDER_W, theme_state["accent"])

        habit_section_wrapper.bgcolor = theme_state["surface"]
        habit_section_wrapper.border = make_border(UNIFORM_BORDER_W, get_border_color(theme_state["surface"]))
        habit_section_wrapper.content = ft.Column(
            [
                ft.Text(
                    "Habit Schedule, Units & Goal",
                    size=12,
                    weight=ft.FontWeight.BOLD,
                    color=theme_state["accent"],
                ),
                recurrence_visual_container,
                ft.Divider(color=get_border_color(theme_state["surface"]), height=6),
                consistency_chips_row,
                ft.Row(
                    [unit_dropdown, custom_unit_field, initial_goal_type_dd, initial_goal_val_field],
                    spacing=10,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=8,
        )

        note_section_container.bgcolor = theme_state["surface"]
        note_section_container.border = make_border(UNIFORM_BORDER_W, get_border_color(theme_state["surface"]))
        reminder_section_container.bgcolor = theme_state["surface"]
        reminder_section_container.border = make_border(UNIFORM_BORDER_W, theme_state["accent"])
        end_date_section.bgcolor = theme_state["surface"]
        end_date_section.border = make_border(UNIFORM_BORDER_W, get_border_color(theme_state["surface"]))
        end_date_selector_btn.bgcolor = theme_state["surface_card"]
        end_date_selector_btn.border = make_border(UNIFORM_BORDER_W, theme_state["accent"])
        end_date_btn_label.color = theme_state["accent"]

        sync_form_visual_state()

        unified_form_card = ft.Container(
            padding=16,
            bgcolor=theme_state["box"],
            border_radius=10,
            border=make_border(UNIFORM_BORDER_W, get_border_color(theme_state["box"])),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            date_selector_button,
                            mode_selector_row,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        wrap=True,
                        spacing=10,
                    ),
                    calendar_popup_container,
                    ft.Divider(color=get_border_color(theme_state["box"]), height=6),
                    ft.Row(
                        [name_field, category_trigger_row],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    linked_habit_badge,
                    habit_section_wrapper,
                    ft.Row(
                        [note_toggle_pill, reminder_toggle_pill, end_date_toggle_pill],
                        spacing=10,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    note_section_container,
                    reminder_section_container,
                    end_date_section,
                    ft.Divider(color=get_border_color(theme_state["box"]), height=8),
                    ft.Row(
                        [save_primary_btn, clear_form_btn],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=12,
            ),
        )

        add_task_view.controls.clear()
        add_task_view.controls.extend(
            [
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(
                                    "Create Task or Habit",
                                    size=20,
                                    weight=ft.FontWeight.BOLD,
                                    color=theme_state["accent"],
                                ),
                                ft.Text(
                                    "Schedule a quick task or build a recurring habit with goals.",
                                    size=12,
                                    color=get_subtext_color(theme_state["bg"]),
                                ),
                            ],
                            spacing=2,
                        ),
                        restart_habit_dropdown if restart_habit_dropdown.visible else ft.Container(),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True,
                ),
                unified_form_card,
            ]
        )
        page.update()
# >>> SUB-SECTION A5a END: UNIFIED ADD TASK / HABIT FORM <<<

# >>> SUB-SECTION A5b START: EDIT TASK & HABIT MODAL <<<
    edit_modal_container = ft.Container(
        padding=16,
        width=620,
        bgcolor=theme_state["surface"],
        border_radius=10,
        border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
    )

    edit_task_dialog = ft.AlertDialog(
        content=edit_modal_container,
        bgcolor=theme_state["surface"],
        shape=ft.RoundedRectangleBorder(radius=10),
    )

    def close_edit_modal(e=None):
        nonlocal expanded_edit_task_id, delete_confirm_task_id, just_opened_edit_id, active_edit_drawer_ctrl
        expanded_edit_task_id = None
        delete_confirm_task_id = None
        just_opened_edit_id = None
        active_edit_drawer_ctrl = None
        set_typing(False)
        if hasattr(page, "close"):
            page.close(edit_task_dialog)
        else:
            edit_task_dialog.open = False
            page.update()

    def build_inline_edit_drawer(task_id: int) -> ft.Control:
        return ft.Container()

    def toggle_inline_edit(task_id: int):
        open_edit_task_modal(task_id)

    def open_edit_task_modal(task_id: int):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, category, time_frame, target_date, recurrence_type,
                   interval_days, end_date, note, unit, custom_days, custom_months, reminder_time
            FROM tasks WHERE id = ?
            """,
            (task_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            show_message("Task not found.")
            return

        tid, t_name, t_cat, t_tf, t_tdate, t_rec, t_int, t_end_date, t_note, t_unit, t_cdays, t_cmonths, t_rem = row
        is_backlog_item = (t_tf == "custom")

        edit_name_f = ft.TextField(
            label="Task or Habit Name",
            value=t_name or "",
            expand=True,
            border_width=UNIFORM_BORDER_W,
            focused_border_width=UNIFORM_BORDER_W,
            border_color=get_border_color(theme_state["surface"]),
            focused_border_color=theme_state["accent"],
            on_focus=lambda _: set_typing(True),
            on_blur=lambda _: set_typing(False),
        )

        # Unified Category Input + True Floating Overlay Dropdown
        edit_cat_f = ft.TextField(
            label="Category",
            hint_text="Write new or select",
            value=t_cat or "General",
            width=202,
            border_width=UNIFORM_BORDER_W,
            focused_border_width=UNIFORM_BORDER_W,
            border_color=get_border_color(theme_state["surface"]),
            focused_border_color=theme_state["accent"],
            on_focus=lambda _: set_typing(True),
            on_blur=lambda _: set_typing(False),
        )

        edit_cat_arrow = ft.Icon(ft.Icons.ARROW_DROP_DOWN, color=theme_state["accent"], size=22)
        edit_cat_btn_box = ft.Container(
            width=42,
            height=48,
            bgcolor=theme_state["surface_card"],
            border_radius=8,
            border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
            alignment=ft.Alignment(0, 0),
            content=edit_cat_arrow,
        )

        edit_cat_popup_btn = ft.PopupMenuButton(
            content=edit_cat_btn_box,
            bgcolor=theme_state["surface_card"],
            shape=ft.RoundedRectangleBorder(radius=8),
            menu_position=ft.PopupMenuPosition.UNDER,
            tooltip="Select existing category",
            items=[],
        )

        def rebuild_edit_cat_popup():
            cats = get_distinct_categories()
            if "General" not in cats:
                cats.insert(0, "General")
            cur_v = (edit_cat_f.value or "").strip().lower()

            def pick_ecat(chosen: str):
                edit_cat_f.value = chosen
                rebuild_edit_cat_popup()
                page.update()

            items_list = []
            for c_name in cats:
                is_sel = (c_name.lower() == cur_v)
                items_list.append(
                    ft.PopupMenuItem(
                        on_click=lambda _, ch=c_name: pick_ecat(ch),
                        content=ft.Row(
                            [
                                ft.Text(
                                    c_name,
                                    size=12,
                                    weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.W_500,
                                    color=theme_state["accent"]
                                    if is_sel
                                    else get_text_color(theme_state["surface_card"]),
                                ),
                                ft.Icon(
                                    ft.Icons.CHECK_ROUNDED,
                                    size=14,
                                    color=theme_state["accent"],
                                    visible=is_sel,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            width=190,
                        ),
                    )
                )
            edit_cat_popup_btn.items = items_list

        edit_cat_f.on_change = lambda _: rebuild_edit_cat_popup()
        rebuild_edit_cat_popup()

        edit_cat_trigger_row = ft.Row(
            [edit_cat_f, edit_cat_popup_btn],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        )

        # Date & Task/Habit Mode Controls
        edit_dt = datetime.strptime(t_tdate, "%Y-%m-%d") if t_tdate else datetime.now()
        edit_cal_browse = edit_dt.replace(day=1)
        edit_cal_open = False

        edit_date_text = ft.Text(
            format_form_date_label(edit_dt),
            color=theme_state["accent"],
            weight=ft.FontWeight.BOLD,
            size=13,
        )
        edit_cal_box = ft.Container(
            visible=False,
            padding=12,
            bgcolor=theme_state["box"],
            border_radius=10,
            border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
            width=340,
        )

        edit_is_recurring = (not is_backlog_item) and (t_rec is not None and t_rec != "once")
        if t_rec in ["weekly", "daily"]:
            edit_freq = "weekly"
        elif t_rec in ["monthly", "yearly"]:
            edit_freq = "monthly"
        elif t_rec == "custom_interval":
            edit_freq = "custom_interval"
        else:
            edit_freq = "weekly"

        if t_rec == "daily":
            edit_days = {d for d, _ in week_days_list}
        elif t_cdays:
            edit_days = {d.strip() for d in t_cdays.split(",") if d.strip()}
        else:
            edit_days = set()

        if t_cmonths:
            edit_months = {int(m.strip()) for m in t_cmonths.split(",") if m.strip().isdigit()}
        else:
            edit_months = {edit_dt.month} if t_rec == "yearly" else set(range(1, 13))

        edit_single_month = (t_rec == "yearly")
        edit_int_f = ft.TextField(
            label="Repeat Every X Days",
            value=str(t_int if (t_int and t_int > 0) else 2),
            width=160,
            border_width=UNIFORM_BORDER_W,
            focused_border_width=UNIFORM_BORDER_W,
            border_color=get_border_color(theme_state["surface"]),
            focused_border_color=theme_state["accent"],
            on_focus=lambda _: set_typing(True),
            on_blur=lambda _: set_typing(False),
        )

        # Unit Selector
        clean_unit_init = t_unit if (t_unit and t_unit != "None") else "None"
        init_is_custom_u = (clean_unit_init != "None" and clean_unit_init not in common_units)
        edit_unit_dd = ft.Dropdown(
            label="Habit Unit (Optional)",
            width=190,
            border_width=UNIFORM_BORDER_W,
            focused_border_width=UNIFORM_BORDER_W,
            border_color=get_border_color(theme_state["box"]),
            focused_border_color=theme_state["accent"],
            options=[ft.dropdown.Option(key=u, text=u) for u in common_units],
            value="+ Custom Unit" if init_is_custom_u else clean_unit_init,
        )
        edit_custom_unit_f = ft.TextField(
            label="Custom Unit",
            value=clean_unit_init if init_is_custom_u else "",
            width=160,
            visible=init_is_custom_u,
            border_width=UNIFORM_BORDER_W,
            focused_border_width=UNIFORM_BORDER_W,
            border_color=get_border_color(theme_state["box"]),
            focused_border_color=theme_state["accent"],
            on_focus=lambda _: set_typing(True),
            on_blur=lambda _: set_typing(False),
        )

        def on_edit_unit_change(e):
            edit_custom_unit_f.visible = (edit_unit_dd.value == "+ Custom Unit")
            page.update()

        edit_unit_dd.on_select = on_edit_unit_change
        edit_unit_dd.on_change = on_edit_unit_change

        edit_habit_box = ft.Container(
            visible=edit_is_recurring,
            padding=12,
            bgcolor=theme_state["box"],
            border_radius=8,
            border=make_border(UNIFORM_BORDER_W, get_border_color(theme_state["box"])),
        )
        edit_rec_visuals = ft.Column(spacing=10)

        def rebuild_edit_cal():
            yr, mo = edit_cal_browse.year, edit_cal_browse.month
            cal = calendar.Calendar(firstweekday=0)
            weeks = cal.monthdatescalendar(yr, mo)
            sel_s = edit_dt.strftime("%Y-%m-%d")

            def shift_m(delta):
                nonlocal edit_cal_browse
                nm = edit_cal_browse.month + delta
                ny = edit_cal_browse.year + (nm - 1) // 12
                nm = (nm - 1) % 12 + 1
                edit_cal_browse = edit_cal_browse.replace(year=ny, month=nm, day=1)
                rebuild_edit_cal()
                page.update()

            def pick_d(d_val: datetime):
                nonlocal edit_dt, edit_cal_open
                edit_dt = d_val
                edit_date_text.value = format_form_date_label(edit_dt)
                edit_cal_open = False
                edit_cal_box.visible = False
                rebuild_edit_rec()
                page.update()

            c_rows = [
                ft.Row(
                    [
                        ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, icon_size=18, on_click=lambda _: shift_m(-1)),
                        ft.Text(edit_cal_browse.strftime("%B %Y"), weight=ft.FontWeight.BOLD, size=13, color=theme_state["accent"]),
                        ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_size=18, on_click=lambda _: shift_m(1)),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            ]
            for wk in weeks:
                r_c = []
                for d_o in wk:
                    ds = d_o.strftime("%Y-%m-%d")
                    in_m = d_o.month == mo
                    is_s = ds == sel_s
                    dt_f = datetime(d_o.year, d_o.month, d_o.day)
                    r_c.append(
                        ft.Container(
                            width=36,
                            height=32,
                            bgcolor=theme_state["accent"] if is_s else (theme_state["surface_card"] if in_m else theme_state["surface"]),
                            border_radius=6,
                            alignment=ft.Alignment(0, 0),
                            on_click=lambda _, dp=dt_f: pick_d(dp),
                            content=ft.Text(
                                str(d_o.day),
                                size=11,
                                color=get_text_color(theme_state["accent"])
                                if is_s
                                else (get_text_color(theme_state["surface_card"]) if in_m else get_subtext_color(theme_state["surface"])),
                            ),
                        )
                    )
                c_rows.append(ft.Row(r_c, alignment=ft.MainAxisAlignment.CENTER, spacing=6))
            edit_cal_box.content = ft.Column(c_rows, spacing=4)

        def toggle_edit_cal(e=None):
            nonlocal edit_cal_open, edit_cal_browse
            edit_cal_open = not edit_cal_open
            if edit_cal_open:
                edit_cal_browse = edit_dt.replace(day=1)
                rebuild_edit_cal()
            edit_cal_box.visible = edit_cal_open
            page.update()

        def rebuild_edit_rec():
            edit_rec_visuals.controls.clear()
            if not edit_is_recurring:
                return

            def f_pill(label: str, active: bool, fn):
                return ft.Container(
                    padding=ft.Padding(left=12, right=12, top=6, bottom=6),
                    bgcolor=theme_state["surface_card"] if active else theme_state["surface"],
                    border_radius=6,
                    border=make_border(UNIFORM_BORDER_W, theme_state["accent"] if active else get_border_color(theme_state["surface"])),
                    on_click=fn,
                    content=ft.Text(
                        label,
                        size=12,
                        weight=ft.FontWeight.BOLD if active else ft.FontWeight.NORMAL,
                        color=theme_state["accent"] if active else get_subtext_color(theme_state["surface"]),
                    ),
                )

            def set_e_freq(fv: str):
                nonlocal edit_freq
                edit_freq = fv
                rebuild_edit_rec()
                page.update()

            edit_rec_visuals.controls.append(
                ft.Row(
                    [
                        f_pill("Weekly / Daily", edit_freq == "weekly", lambda _: set_e_freq("weekly")),
                        f_pill("Monthly / Yearly", edit_freq == "monthly", lambda _: set_e_freq("monthly")),
                        f_pill("Every X Days", edit_freq == "custom_interval", lambda _: set_e_freq("custom_interval")),
                    ],
                    spacing=8,
                    wrap=True,
                )
            )

            if edit_freq == "weekly":
                all_7 = len(edit_days) == 7
                b_row = ft.Row(spacing=8, wrap=True)
                for dk, di in week_days_list:
                    lit = dk in edit_days

                    def click_eb(e, d_code=dk):
                        if d_code in edit_days:
                            edit_days.remove(d_code)
                        else:
                            edit_days.add(d_code)
                        rebuild_edit_rec()
                        page.update()

                    b_row.controls.append(
                        ft.Container(
                            width=36,
                            height=36,
                            border_radius=18,
                            bgcolor=theme_state["accent"] if lit else theme_state["surface"],
                            border=make_border(UNIFORM_BORDER_W, theme_state["accent"] if lit else get_border_color(theme_state["surface"])),
                            alignment=ft.Alignment(0, 0),
                            on_click=click_eb,
                            content=ft.Text(
                                di,
                                size=13,
                                weight=ft.FontWeight.BOLD,
                                color=get_text_color(theme_state["accent"]) if lit else get_subtext_color(theme_state["surface"]),
                            ),
                        )
                    )

                def toggle_e_daily(e):
                    if len(edit_days) == 7:
                        edit_days.clear()
                    else:
                        for d_k, _ in week_days_list:
                            edit_days.add(d_k)
                    rebuild_edit_rec()
                    page.update()

                edit_rec_visuals.controls.append(
                    ft.Row(
                        [b_row, f_pill("Daily (All 7)", all_7, toggle_e_daily)],
                        spacing=12,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                )

            elif edit_freq == "monthly":
                m_rows = []
                for r_i in range(2):
                    m_c = []
                    for c_i in range(6):
                        m_num, m_lbl = month_names_list[r_i * 6 + c_i]
                        has_m = m_num in edit_months

                        def click_em(e, mv=m_num):
                            if edit_single_month:
                                edit_months.clear()
                                edit_months.add(mv)
                            else:
                                if mv in edit_months and len(edit_months) > 1:
                                    edit_months.remove(mv)
                                else:
                                    edit_months.add(mv)
                            rebuild_edit_rec()
                            page.update()

                        m_c.append(
                            ft.Container(
                                width=48,
                                height=40,
                                bgcolor=theme_state["surface_card"] if has_m else theme_state["surface"],
                                border_radius=6,
                                border=make_border(UNIFORM_BORDER_W, theme_state["accent"] if has_m else get_border_color(theme_state["surface"])),
                                alignment=ft.Alignment(0, 0),
                                on_click=click_em,
                                content=ft.Text(
                                    m_lbl,
                                    size=11,
                                    weight=ft.FontWeight.BOLD,
                                    color=get_text_color(theme_state["surface_card"]) if has_m else get_subtext_color(theme_state["surface"]),
                                ),
                            )
                        )
                    m_rows.append(ft.Row(m_c, spacing=6, wrap=True))
                edit_rec_visuals.controls.append(ft.Column(m_rows, spacing=6))

            elif edit_freq == "custom_interval":
                edit_rec_visuals.controls.append(edit_int_f)

        edit_habit_box.content = ft.Column(
            [
                ft.Text("Habit Schedule & Unit", size=12, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                edit_rec_visuals,
                ft.Divider(color=get_border_color(theme_state["box"]), height=6),
                ft.Row([edit_unit_dd, edit_custom_unit_f], spacing=10, wrap=True),
            ],
            spacing=8,
        )

        # Optional Note, Reminder (Primary + 2nd Alert), and End Date
        has_edit_note = bool(t_note and t_note.strip())
        edit_note_f = ft.TextField(
            label="Note",
            value=t_note or "",
            border_width=UNIFORM_BORDER_W,
            focused_border_width=UNIFORM_BORDER_W,
            border_color=get_border_color(theme_state["box"]),
            focused_border_color=theme_state["accent"],
            on_focus=lambda _: set_typing(True),
            on_blur=lambda _: set_typing(False),
        )
        edit_note_box = ft.Container(
            visible=has_edit_note,
            padding=10,
            bgcolor=theme_state["box"],
            border_radius=8,
            border=make_border(UNIFORM_BORDER_W, get_border_color(theme_state["box"])),
            content=edit_note_f,
        )

        has_edit_rem = bool(t_rem) and (not is_backlog_item)
        has_edit_rem_2 = False
        e_a1_days = 0
        e_a2_days = 1
        e_t1_init = "09:00"
        e_t2_init = "09:00"
        if t_rem:
            rem_parts = t_rem.split(";;")
            p1 = rem_parts[0].split("|")
            e_t1_init = p1[0] or "09:00"
            e_a1_days = parse_days_before_code(p1[1] if len(p1) > 1 else "")
            if len(rem_parts) > 1:
                has_edit_rem_2 = True
                p2 = rem_parts[1].split("|")
                e_t2_init = p2[0] or "09:00"
                e_a2_days = parse_days_before_code(p2[1] if len(p2) > 1 else "-1d")

        e_a1_row = ft.Row(spacing=6, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        e_a2_row = ft.Row(spacing=6, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        e_a1_sum = ft.Text(size=11, italic=True)
        e_a2_sum = ft.Text(size=11, italic=True)

        def update_edit_alert_sums():
            t1_d = format_time_display(get_e_time_1())
            e_a1_sum.value = (
                f"Notifies on the scheduled day at {t1_d}"
                if e_a1_days == 0
                else f"Notifies {e_a1_days} {'day' if e_a1_days == 1 else 'days'} before at {t1_d}"
            )
            e_a1_sum.color = get_subtext_color(theme_state["box"])

            t2_d = format_time_display(get_e_time_2())
            e_a2_sum.value = (
                f"Notifies on the scheduled day at {t2_d}"
                if e_a2_days == 0
                else f"Notifies {e_a2_days} {'day' if e_a2_days == 1 else 'days'} before at {t2_d}"
            )
            e_a2_sum.color = get_subtext_color(theme_state["box"])

        e_wheel_1, get_e_time_1, _ = build_time_wheel_picker(e_t1_init, on_time_changed=update_edit_alert_sums)
        e_wheel_2, get_e_time_2, _ = build_time_wheel_picker(e_t2_init, on_time_changed=update_edit_alert_sums)
        e_alert_2_card = ft.Container(visible=False)
        e_sec_btn = ft.Container()

        def rebuild_edit_alerts():
            def set_ea1(v: int):
                nonlocal e_a1_days
                e_a1_days = v
                rebuild_edit_alerts()
                page.update()

            def set_ea2(v: int):
                nonlocal e_a2_days
                e_a2_days = v
                rebuild_edit_alerts()
                page.update()

            build_day_offset_controls(e_a1_row, e_a1_days, set_ea1)
            build_day_offset_controls(e_a2_row, e_a2_days, set_ea2)
            update_edit_alert_sums()

            def toggle_e_sec(e=None):
                nonlocal has_edit_rem_2
                has_edit_rem_2 = not has_edit_rem_2
                rebuild_edit_alerts()
                page.update()

            e_sec_btn.content = ft.Container(
                padding=ft.Padding(left=10, right=10, top=5, bottom=5),
                border_radius=6,
                bgcolor=theme_state["surface_card"],
                border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
                on_click=toggle_e_sec,
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.CLOSE_ROUNDED if has_edit_rem_2 else ft.Icons.ADD_ROUNDED, size=14, color=theme_state["accent"]),
                        ft.Text(
                            "Remove 2nd Alert" if has_edit_rem_2 else "Add 2nd Alert",
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color=theme_state["accent"],
                        ),
                    ],
                    spacing=4,
                    tight=True,
                ),
            )

            e_alert_2_card.visible = has_edit_rem_2
            if has_edit_rem_2:
                e_alert_2_card.width = 275
                e_alert_2_card.padding = 10
                e_alert_2_card.bgcolor = theme_state["surface"]
                e_alert_2_card.border_radius = 8
                e_alert_2_card.border = make_border(UNIFORM_BORDER_W, get_border_color(theme_state["surface"]))
                e_alert_2_card.content = ft.Column(
                    [
                        ft.Text("Second Alert", size=12, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                        e_a2_row,
                        e_wheel_2,
                        e_a2_sum,
                    ],
                    spacing=6,
                )

        e_alert_1_card = ft.Container(
            width=275,
            padding=10,
            bgcolor=theme_state["surface"],
            border_radius=8,
            border=make_border(UNIFORM_BORDER_W, get_border_color(theme_state["surface"])),
            content=ft.Column(
                [
                    ft.Text("Primary Alert", size=12, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                    e_a1_row,
                    e_wheel_1,
                    e_a1_sum,
                ],
                spacing=6,
            ),
        )

        edit_rem_box = ft.Container(
            visible=has_edit_rem,
            padding=12,
            bgcolor=theme_state["box"],
            border_radius=8,
            border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.ALARM_ROUNDED, size=16, color=theme_state["accent"]),
                                    ft.Text("Reminder Alerts", size=12, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                                ],
                                spacing=6,
                            ),
                            e_sec_btn,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Row([e_alert_1_card, e_alert_2_card], spacing=10, wrap=True, vertical_alignment=ft.CrossAxisAlignment.START),
                ],
                spacing=8,
            ),
        )

        # End Date Controls
        has_edit_end = bool(t_end_date) and edit_is_recurring
        edit_end_dt = datetime.strptime(t_end_date, "%Y-%m-%d") if t_end_date else (edit_dt + timedelta(days=30))
        edit_end_browse = edit_end_dt.replace(day=1)
        edit_end_cal_open = False

        edit_end_date_text = ft.Text(
            edit_end_dt.strftime("%d %b %Y"),
            color=theme_state["accent"],
            weight=ft.FontWeight.BOLD,
            size=12,
        )
        edit_end_cal_box = ft.Container(
            visible=False,
            padding=12,
            bgcolor=theme_state["surface_card"],
            border_radius=10,
            border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
            width=320,
        )

        def set_edit_dur(days_delta: int, months_delta: int = 0):
            nonlocal edit_end_dt
            if months_delta > 0:
                nm = edit_dt.month + months_delta
                ny = edit_dt.year + (nm - 1) // 12
                nm = (nm - 1) % 12 + 1
                edit_end_dt = edit_dt.replace(year=ny, month=nm, day=min(edit_dt.day, calendar.monthrange(ny, nm)[1]))
            else:
                edit_end_dt = edit_dt + timedelta(days=days_delta)
            edit_end_date_text.value = edit_end_dt.strftime("%d %b %Y")
            page.update()

        def rebuild_edit_end_cal():
            yr, mo = edit_end_browse.year, edit_end_browse.month
            cal = calendar.Calendar(firstweekday=0)
            weeks = cal.monthdatescalendar(yr, mo)
            sel_s = edit_end_dt.strftime("%Y-%m-%d")

            def shift_em(delta):
                nonlocal edit_end_browse
                nm = edit_end_browse.month + delta
                ny = edit_end_browse.year + (nm - 1) // 12
                nm = (nm - 1) % 12 + 1
                edit_end_browse = edit_end_browse.replace(year=ny, month=nm, day=1)
                rebuild_edit_end_cal()
                page.update()

            def pick_ed(dt_v: datetime):
                nonlocal edit_end_dt, edit_end_cal_open
                edit_end_dt = dt_v
                edit_end_date_text.value = edit_end_dt.strftime("%d %b %Y")
                edit_end_cal_open = False
                edit_end_cal_box.visible = False
                page.update()

            c_rows = [
                ft.Row(
                    [
                        ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, icon_size=16, on_click=lambda _: shift_em(-1)),
                        ft.Text(edit_end_browse.strftime("%B %Y"), weight=ft.FontWeight.BOLD, size=13, color=theme_state["accent"]),
                        ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_size=16, on_click=lambda _: shift_em(1)),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            ]
            for wk in weeks:
                r_c = []
                for d_o in wk:
                    ds = d_o.strftime("%Y-%m-%d")
                    in_m = d_o.month == mo
                    is_s = ds == sel_s
                    dt_f = datetime(d_o.year, d_o.month, d_o.day)
                    r_c.append(
                        ft.Container(
                            width=34,
                            height=30,
                            bgcolor=theme_state["accent"] if is_s else (theme_state["box"] if in_m else theme_state["surface"]),
                            border_radius=6,
                            alignment=ft.Alignment(0, 0),
                            on_click=lambda _, dp=dt_f: pick_ed(dp),
                            content=ft.Text(
                                str(d_o.day),
                                size=11,
                                color=get_text_color(theme_state["accent"])
                                if is_s
                                else (get_text_color(theme_state["box"]) if in_m else get_subtext_color(theme_state["surface"])),
                            ),
                        )
                    )
                c_rows.append(ft.Row(r_c, alignment=ft.MainAxisAlignment.CENTER, spacing=4))
            edit_end_cal_box.content = ft.Column(c_rows, spacing=4)

        def toggle_edit_end_cal(e=None):
            nonlocal edit_end_cal_open, edit_end_browse
            edit_end_cal_open = not edit_end_cal_open
            if edit_end_cal_open:
                edit_end_browse = edit_end_dt.replace(day=1)
                rebuild_edit_end_cal()
            edit_end_cal_box.visible = edit_end_cal_open
            page.update()

        edit_end_section = ft.Container(
            visible=has_edit_end,
            padding=10,
            bgcolor=theme_state["box"],
            border_radius=8,
            border=make_border(UNIFORM_BORDER_W, get_border_color(theme_state["box"])),
            content=ft.Column(
                [
                    ft.Text("Stop Habit After:", size=11, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                    ft.Row(
                        [
                            ft.Container(
                                padding=ft.Padding(left=12, right=12, top=8, bottom=8),
                                bgcolor=theme_state["surface_card"],
                                border_radius=8,
                                border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
                                on_click=toggle_edit_end_cal,
                                content=ft.Row(
                                    [ft.Icon(ft.Icons.EVENT_BUSY_ROUNDED, color=theme_state["accent"], size=16), edit_end_date_text],
                                    spacing=6,
                                    tight=True,
                                ),
                            ),
                            ft.Row(
                                [
                                    ft.TextButton(content=ft.Text("2 Weeks", size=11), on_click=lambda _: set_edit_dur(14)),
                                    ft.TextButton(content=ft.Text("1 Month", size=11), on_click=lambda _: set_edit_dur(0, 1)),
                                    ft.TextButton(content=ft.Text("3 Months", size=11), on_click=lambda _: set_edit_dur(0, 3)),
                                    ft.TextButton(content=ft.Text("1 Year", size=11), on_click=lambda _: set_edit_dur(0, 12)),
                                ],
                                spacing=2,
                                wrap=True,
                            ),
                        ],
                        spacing=10,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    edit_end_cal_box,
                ],
                spacing=6,
            ),
        )

        # Mode & Option Pills
        e_task_pill = ft.Container(padding=ft.Padding(left=14, right=14, top=7, bottom=7), border_radius=8)
        e_habit_pill = ft.Container(padding=ft.Padding(left=14, right=14, top=7, bottom=7), border_radius=8)
        e_note_pill = ft.Container(padding=ft.Padding(left=12, right=12, top=7, bottom=7), border_radius=8)
        e_rem_pill = ft.Container(padding=ft.Padding(left=12, right=12, top=7, bottom=7), border_radius=8)
        e_end_pill = ft.Container(padding=ft.Padding(left=12, right=12, top=7, bottom=7), border_radius=8)

        def sync_edit_modal_state():
            e_task_pill.bgcolor = theme_state["accent"] if not edit_is_recurring else theme_state["box"]
            e_task_pill.border = make_border(UNIFORM_BORDER_W, theme_state["accent"] if not edit_is_recurring else get_border_color(theme_state["box"]))
            e_task_pill.content = ft.Text(
                "Task",
                size=12,
                weight=ft.FontWeight.BOLD,
                color=get_text_color(theme_state["accent"]) if not edit_is_recurring else get_subtext_color(theme_state["box"]),
            )

            e_habit_pill.bgcolor = theme_state["accent"] if edit_is_recurring else theme_state["box"]
            e_habit_pill.border = make_border(UNIFORM_BORDER_W, theme_state["accent"] if edit_is_recurring else get_border_color(theme_state["box"]))
            e_habit_pill.content = ft.Text(
                "Habit",
                size=12,
                weight=ft.FontWeight.BOLD,
                color=get_text_color(theme_state["accent"]) if edit_is_recurring else get_subtext_color(theme_state["box"]),
            )

            edit_habit_box.visible = edit_is_recurring
            if edit_is_recurring:
                rebuild_edit_rec()

            def style_epill(pill: ft.Container, ic, lbl: str, act: bool):
                pill.bgcolor = theme_state["surface_card"] if act else theme_state["box"]
                pill.border = make_border(UNIFORM_BORDER_W, theme_state["accent"] if act else get_border_color(theme_state["box"]))
                pill.content = ft.Row(
                    [
                        ft.Icon(ic, size=15, color=theme_state["accent"] if act else get_subtext_color(theme_state["box"])),
                        ft.Text(
                            lbl,
                            size=12,
                            weight=ft.FontWeight.BOLD if act else ft.FontWeight.W_500,
                            color=theme_state["accent"] if act else get_subtext_color(theme_state["box"]),
                        ),
                    ],
                    spacing=6,
                    tight=True,
                )

            style_epill(e_note_pill, ft.Icons.EDIT_OUTLINED, "Add Note", has_edit_note)
            edit_note_box.visible = has_edit_note

            e_rem_pill.visible = not is_backlog_item
            style_epill(e_rem_pill, ft.Icons.ALARM_ROUNDED, "Set Reminder", has_edit_rem)
            edit_rem_box.visible = has_edit_rem and (not is_backlog_item)
            if edit_rem_box.visible:
                rebuild_edit_alerts()

            e_end_pill.visible = edit_is_recurring
            style_epill(e_end_pill, ft.Icons.EVENT_BUSY_ROUNDED, "Set End Date", has_edit_end)
            edit_end_section.visible = has_edit_end and edit_is_recurring

        def set_e_mode(rec_flag: bool):
            nonlocal edit_is_recurring
            edit_is_recurring = rec_flag
            sync_edit_modal_state()
            page.update()

        def toggle_e_note(e=None):
            nonlocal has_edit_note
            has_edit_note = not has_edit_note
            sync_edit_modal_state()
            page.update()

        def toggle_e_rem_pill(e=None):
            nonlocal has_edit_rem
            has_edit_rem = not has_edit_rem
            sync_edit_modal_state()
            page.update()

        def toggle_e_end_pill(e=None):
            nonlocal has_edit_end
            has_edit_end = not has_edit_end
            sync_edit_modal_state()
            page.update()

        e_task_pill.on_click = lambda _: set_e_mode(False)
        e_habit_pill.on_click = lambda _: set_e_mode(True)
        e_note_pill.on_click = toggle_e_note
        e_rem_pill.on_click = toggle_e_rem_pill
        e_end_pill.on_click = toggle_e_end_pill

        # Delete Safeguard
        def execute_confirmed_delete(e):
            close_edit_modal()
            remove_task_db(tid)
            show_message(f"🗑️ Deleted '{t_name}'")
            if current_view_index == 0:
                refresh_schedule_view()
            elif current_view_index == 2:
                load_backlog_view()
            elif current_view_index == 4:
                load_all_tasks_view()

        delete_confirm_row = ft.Container(
            visible=False,
            padding=10,
            bgcolor=theme_state["surface_card"],
            border_radius=8,
            border=make_border(UNIFORM_BORDER_W, ft.Colors.RED_400),
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.RED_400, size=18),
                    ft.Text(
                        f"Permanently delete '{t_name}'?",
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color=get_text_color(theme_state["surface_card"]),
                        expand=True,
                    ),
                    ft.TextButton(
                        content=ft.Text("Yes, Delete", color=ft.Colors.RED_400, weight=ft.FontWeight.BOLD, size=12),
                        on_click=execute_confirmed_delete,
                    ),
                    ft.TextButton(
                        content=ft.Text("Cancel", color=get_subtext_color(theme_state["surface_card"]), size=12),
                        on_click=lambda _: (setattr(delete_confirm_row, "visible", False), page.update()),
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        def save_task_changes(e):
            if not edit_name_f.value or not edit_name_f.value.strip():
                show_message("Task or habit name cannot be empty!")
                return

            if edit_is_recurring and edit_freq == "weekly" and len(edit_days) == 0:
                show_message("Pick at least one weekday circle (or tap Daily)!")
                return

            if not edit_is_recurring:
                final_rec = "once"
            elif edit_freq == "weekly":
                final_rec = "daily" if len(edit_days) == 7 else "weekly"
            elif edit_freq == "monthly":
                final_rec = "yearly" if (edit_single_month and len(edit_months) == 1) else "monthly"
            else:
                final_rec = "custom_interval"

            ord_days = ",".join([d for d, _ in week_days_list if d in edit_days]) if final_rec == "weekly" else None
            ord_months = ",".join([str(m) for m in sorted(edit_months)]) if final_rec in ["monthly", "yearly"] else None
            int_val = int(edit_int_f.value) if (edit_int_f.value and edit_int_f.value.isdigit()) else 1

            u_val = None
            if edit_is_recurring:
                u_choice = edit_unit_dd.value
                if u_choice == "+ Custom Unit":
                    u_val = (edit_custom_unit_f.value or "").strip() or None
                elif u_choice and u_choice != "None":
                    u_val = u_choice

            final_end_date = edit_end_dt.strftime("%Y-%m-%d") if (edit_is_recurring and has_edit_end) else None

            final_edit_rem = None
            if has_edit_rem and (not is_backlog_item):
                t1 = get_e_time_1()
                ent1 = f"{t1}|-{e_a1_days}d" if e_a1_days > 0 else t1
                if has_edit_rem_2:
                    t2 = get_e_time_2()
                    ent2 = f"{t2}|-{e_a2_days}d" if e_a2_days > 0 else t2
                    final_edit_rem = f"{ent1};;{ent2}"
                else:
                    final_edit_rem = ent1

            update_task_db(
                task_id=tid,
                name=edit_name_f.value.strip(),
                category=(edit_cat_f.value or "").strip() or "General",
                time_frame=t_tf,
                target_date=edit_dt.strftime("%Y-%m-%d") if t_tf == "day" else None,
                recurrence_type=final_rec,
                interval_days=int_val,
                end_date=final_end_date,
                note=(edit_note_f.value or "").strip() if (has_edit_note and edit_note_f.value and edit_note_f.value.strip()) else None,
                unit=u_val,
                custom_days=ord_days,
                custom_months=ord_months,
                reminder_time=final_edit_rem,
            )

            if is_backlog_item:
                try:
                    c_bg = get_db_connection()
                    c_bg.execute("UPDATE tasks SET custom_list = 'Backlog' WHERE id = ?", (tid,))
                    c_bg.commit()
                    c_bg.close()
                except Exception:
                    pass

            close_edit_modal()
            show_message("✏️ Changes saved!")
            if current_view_index == 0:
                refresh_schedule_view()
            elif current_view_index == 2:
                load_backlog_view()
            elif current_view_index == 4:
                load_all_tasks_view()

        sync_edit_modal_state()

        win_h = getattr(page, "height", None) or 760
        modal_h = min(640, max(420, int(win_h * 0.80)))

        top_bar_controls = [
            ft.Row(
                [
                    ft.Icon(ft.Icons.EDIT_OUTLINED, color=theme_state["accent"], size=20),
                    ft.Text(
                        "Edit Backlog Task" if is_backlog_item else "Edit Task / Habit",
                        size=16,
                        weight=ft.FontWeight.BOLD,
                        color=theme_state["accent"],
                    ),
                ],
                spacing=8,
            ),
            ft.Row(
                [
                    ft.OutlinedButton(
                        content=ft.Text("Delete", color=ft.Colors.RED_400, size=12, weight=ft.FontWeight.BOLD),
                        icon=ft.Icons.DELETE_FOREVER_ROUNDED,
                        icon_color=ft.Colors.RED_400,
                        style=ft.ButtonStyle(
                            side=ft.BorderSide(UNIFORM_BORDER_W, ft.Colors.RED_400),
                            shape=ft.RoundedRectangleBorder(radius=8),
                        ),
                        on_click=lambda _: (setattr(delete_confirm_row, "visible", True), page.update()),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE_ROUNDED,
                        icon_size=18,
                        tooltip="Close",
                        on_click=close_edit_modal,
                    ),
                ],
                spacing=4,
            ),
        ]

        when_type_row = ft.Row(
            [
                ft.Container(
                    visible=not is_backlog_item,
                    padding=ft.Padding(left=12, right=12, top=8, bottom=8),
                    bgcolor=theme_state["surface_card"],
                    border_radius=8,
                    border=make_border(UNIFORM_BORDER_W, theme_state["accent"]),
                    on_click=toggle_edit_cal,
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.CALENDAR_MONTH_ROUNDED, color=theme_state["accent"], size=16),
                            edit_date_text,
                            ft.Icon(ft.Icons.ARROW_DROP_DOWN, color=theme_state["accent"], size=18),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                ),
                ft.Row([e_task_pill, e_habit_pill], spacing=8, tight=True, visible=not is_backlog_item),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
        )

        scrollable_middle = ft.Column(
            [
                delete_confirm_row,
                when_type_row if not is_backlog_item else ft.Container(),
                edit_cal_box,
                ft.Row(
                    [edit_name_f, edit_cat_trigger_row],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                edit_habit_box,
                ft.Row(
                    [e_note_pill, e_rem_pill, e_end_pill],
                    spacing=8,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                edit_note_box,
                edit_rem_box,
                edit_end_section,
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            spacing=10,
        )

        edit_modal_container.height = modal_h
        edit_modal_container.bgcolor = theme_state["surface"]
        edit_modal_container.border = make_border(UNIFORM_BORDER_W, theme_state["accent"])
        edit_task_dialog.bgcolor = theme_state["surface"]

        edit_modal_container.content = ft.Column(
            [
                ft.Row(top_bar_controls, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(color=get_border_color(theme_state["surface"]), height=4),
                scrollable_middle,
                ft.Divider(color=get_border_color(theme_state["surface"]), height=4),
                ft.Row(
                    [
                        ft.OutlinedButton(
                            content=ft.Text("Cancel", weight=ft.FontWeight.W_600),
                            style=ft.ButtonStyle(
                                side=ft.BorderSide(UNIFORM_BORDER_W, get_border_color(theme_state["surface"])),
                                shape=ft.RoundedRectangleBorder(radius=8),
                            ),
                            on_click=close_edit_modal,
                        ),
                        ft.FilledButton(
                            content=ft.Text(
                                "Save Changes",
                                color=get_text_color(theme_state["accent"]),
                                weight=ft.FontWeight.BOLD,
                            ),
                            icon=ft.Icons.CHECK_ROUNDED,
                            icon_color=get_text_color(theme_state["accent"]),
                            bgcolor=theme_state["accent"],
                            on_click=save_task_changes,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=10,
                ),
            ],
            spacing=8,
            expand=True,
        )

        set_typing(True)
        if edit_task_dialog not in page.overlay:
            page.overlay.append(edit_task_dialog)
        if hasattr(page, "open"):
            page.open(edit_task_dialog)
        else:
            page.dialog = edit_task_dialog
            edit_task_dialog.open = True
            page.update()
# >>> SUB-SECTION A5b END: EDIT TASK & HABIT MODAL <<<
# =============================================================================
# >>> SECTION A5 END: VIEW 2 - ADD TASK & EDIT TASK MODAL FORM <<<
# =============================================================================

# =============================================================================
# >>> SECTION A6 START: VIEW 3 - BACKLOG QUEUE <<<
# =============================================================================
    backlog_state = {
        "filter_cat": "All",
        "quick_name": "",
        "quick_cat": "",
        "date_picker_tid": None,
        "cal_browse": datetime.now().replace(day=1),
        "recently_completed": [],
    }

    def load_backlog_view():
        backlog_view.controls.clear()
        all_backlog_tasks = fetch_backlog_tasks()

        present_cats = sorted({(t[2] or "General") for t in all_backlog_tasks})
        if backlog_state["filter_cat"] != "All" and backlog_state["filter_cat"] not in present_cats:
            backlog_state["filter_cat"] = "All"

        visible_tasks = [
            t
            for t in all_backlog_tasks
            if backlog_state["filter_cat"] == "All" or (t[2] or "General") == backlog_state["filter_cat"]
        ]

        # 1. Header Row (Clean title & subtitle without 'queued' badge)
        top_row = ft.Column(
            [
                ft.Text("Backlog Queue", size=20, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                ft.Text(
                    "Unscheduled ideas & tasks — check off directly or assign a date when ready.",
                    size=12,
                    color=get_subtext_color(theme_state["bg"]),
                ),
            ],
            spacing=2,
        )
        backlog_view.controls.append(top_row)

        # 2. Quick-Add Brain-Dump Bar
        quick_name_tf = ft.TextField(
            hint_text="Quick-add task to Backlog (press Enter)...",
            value=backlog_state["quick_name"],
            expand=True,
            dense=True,
            text_size=13,
            on_change=lambda e: backlog_state.update({"quick_name": e.control.value}),
            on_focus=lambda _: set_typing(True),
            on_blur=lambda _: set_typing(False),
        )

        quick_cat_tf = ft.TextField(
            hint_text="Category (General)",
            value=backlog_state["quick_cat"],
            width=165,
            dense=True,
            text_size=13,
            on_change=lambda e: backlog_state.update({"quick_cat": e.control.value}),
            on_focus=lambda _: set_typing(True),
            on_blur=lambda _: set_typing(False),
        )

        def submit_quick_backlog(e=None):
            raw_title = (quick_name_tf.value or "").strip()
            if not raw_title:
                show_message("Enter a task name first!")
                return
            chosen_cat = (quick_cat_tf.value or "").strip() or (
                backlog_state["filter_cat"] if backlog_state["filter_cat"] != "All" else "General"
            )
            add_task_db(
                name=raw_title,
                category=chosen_cat,
                time_frame="custom",
                target_date=None,
                recurrence_type="once",
                interval_days=0,
                end_date=None,
                custom_list="Backlog",
                note=None,
                unit=None,
                custom_days=None,
                custom_months=None,
                reminder_time=None,
            )
            backlog_state["quick_name"] = ""
            set_typing(False)
            show_message(f"📥 Added '{raw_title}' to Backlog ({chosen_cat})")
            load_backlog_view()

        quick_name_tf.on_submit = submit_quick_backlog
        quick_cat_tf.on_submit = submit_quick_backlog

        quick_add_bar = ft.Container(
            padding=10,
            bgcolor=theme_state["box"],
            border_radius=8,
            border=make_border(1, get_border_color(theme_state["box"])),
            content=ft.Row(
                [
                    quick_name_tf,
                    quick_cat_tf,
                    ft.FilledButton(
                        content=ft.Text("Add", weight=ft.FontWeight.BOLD, color=get_text_color(theme_state["accent"])),
                        icon=ft.Icons.ADD_ROUNDED,
                        icon_color=get_text_color(theme_state["accent"]),
                        bgcolor=theme_state["accent"],
                        on_click=submit_quick_backlog,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        backlog_view.controls.append(quick_add_bar)

        # 3. Clearly Labeled Category Filter Row
        if present_cats:
            filter_chips = [
                ft.Text(
                    "Categories:",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    color=get_subtext_color(theme_state["bg"]),
                )
            ]
            for cat_opt in ["All"] + present_cats:
                is_active = (backlog_state["filter_cat"] == cat_opt)
                count_for_cat = (
                    len(all_backlog_tasks)
                    if cat_opt == "All"
                    else len([x for x in all_backlog_tasks if (x[2] or "General") == cat_opt])
                )

                def select_cat_filter(e, c_val=cat_opt):
                    backlog_state["filter_cat"] = c_val
                    load_backlog_view()

                filter_chips.append(
                    ft.Container(
                        padding=ft.Padding(left=10, right=10, top=5, bottom=5),
                        border_radius=6,
                        bgcolor=theme_state["accent"] if is_active else theme_state["surface"],
                        border=make_border(
                            1.5 if is_active else 1,
                            theme_state["accent"] if is_active else get_border_color(theme_state["surface"]),
                        ),
                        on_click=select_cat_filter,
                        content=ft.Text(
                            f"{cat_opt} ({count_for_cat})",
                            size=11,
                            weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.W_500,
                            color=get_text_color(theme_state["accent"])
                            if is_active
                            else get_subtext_color(theme_state["surface"]),
                        ),
                    )
                )
            backlog_view.controls.append(
                ft.Row(
                    filter_chips,
                    spacing=6,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

        backlog_view.controls.append(ft.Divider(color=get_border_color(theme_state["bg"]), height=4))

        # 4. Empty State or Backlog Task Cards
        if not visible_tasks:
            empty_msg = (
                "Backlog is empty! Type above or pick 'Backlog' on Page 2 to stash unscheduled tasks here."
                if not all_backlog_tasks
                else f"No Backlog tasks in '{backlog_state['filter_cat']}'."
            )
            backlog_view.controls.append(
                ft.Container(
                    padding=22,
                    bgcolor=theme_state["box"],
                    border_radius=8,
                    border=make_border(1, get_border_color(theme_state["box"])),
                    alignment=ft.Alignment(0, 0),
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.INBOX_ROUNDED, size=28, color=theme_state["accent"]),
                            ft.Text(empty_msg, italic=True, color=get_subtext_color(theme_state["box"]), size=12),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                )
            )
        else:
            for t in visible_tasks:
                task_id, name, category, _, _, recurrence, _, _, _, note, unit = t[:11]
                t_rem = t[13] if len(t) > 13 else None
                is_picking_date = (backlog_state["date_picker_tid"] == task_id)
                card_bg = theme_state["box"]

                def complete_backlog_directly(
                    e,
                    tid=task_id,
                    tname=name,
                    tcat=category or "General",
                    tnote=note,
                    trem=t_rem,
                ):
                    if not e.control.value:
                        return
                    today_s = datetime.now().strftime("%Y-%m-%d")
                    schedule_backlog_task_db(tid, today_s)
                    mark_complete_db(tid, completed_dt=f"{today_s} 12:00:00")
                    if backlog_state["date_picker_tid"] == tid:
                        backlog_state["date_picker_tid"] = None
                    backlog_state["recently_completed"].insert(
                        0,
                        {
                            "id": tid,
                            "name": tname,
                            "category": tcat,
                            "note": tnote,
                            "reminder_time": trem,
                            "date": today_s,
                        },
                    )
                    del backlog_state["recently_completed"][10:]
                    show_message(f"✓ Completed '{tname}' (logged to Today)")
                    load_backlog_view()

                chk_box = ft.Checkbox(
                    value=False,
                    on_change=complete_backlog_directly,
                    tooltip="Mark completed now (logs to Today & Page 4 analytics)",
                    fill_color={
                        ft.ControlState.SELECTED: theme_state["accent"],
                        ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT,
                    },
                    check_color=get_text_color(theme_state["accent"]),
                )

                def make_schedule_btn(days_offset: int, label: str, tid=task_id, tname=name):
                    target_dt = datetime.now() + timedelta(days=days_offset)
                    dt_str = target_dt.strftime("%Y-%m-%d")
                    return ft.Container(
                        padding=ft.Padding(left=10, right=10, top=5, bottom=5),
                        border_radius=6,
                        bgcolor=theme_state["accent"],
                        tooltip=f"Schedule '{tname}' for {target_dt.strftime('%a, %d %b')}",
                        on_click=lambda _, i=tid, ds=dt_str, lbl=label, nm=tname: (
                            backlog_state.update({"date_picker_tid": None}),
                            schedule_backlog_task_db(i, ds),
                            show_message(f"📅 Scheduled '{nm}' for {lbl}!"),
                            load_backlog_view(),
                        ),
                        content=ft.Text(
                            label,
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color=get_text_color(theme_state["accent"]),
                        ),
                    )

                def toggle_card_date_picker(e, tid=task_id):
                    if backlog_state["date_picker_tid"] == tid:
                        backlog_state["date_picker_tid"] = None
                    else:
                        backlog_state["date_picker_tid"] = tid
                        backlog_state["cal_browse"] = datetime.now().replace(day=1)
                    load_backlog_view()

                pick_date_btn = ft.Container(
                    width=30,
                    height=28,
                    border_radius=6,
                    bgcolor=theme_state["accent"] if is_picking_date else theme_state["surface_card"],
                    border=make_border(1, theme_state["accent"]),
                    alignment=ft.Alignment(0, 0),
                    on_click=toggle_card_date_picker,
                    tooltip="Schedule on a specific date",
                    content=ft.Icon(
                        ft.Icons.CALENDAR_MONTH_ROUNDED,
                        size=15,
                        color=get_text_color(theme_state["accent"]) if is_picking_date else theme_state["accent"],
                    ),
                )

                schedule_cluster = ft.Container(
                    padding=ft.Padding(left=8, right=6, top=4, bottom=4),
                    border_radius=8,
                    bgcolor=theme_state["surface"],
                    border=make_border(1, get_border_color(card_bg)),
                    content=ft.Row(
                        [
                            ft.Text(
                                "Schedule:",
                                size=11,
                                weight=ft.FontWeight.W_600,
                                color=get_subtext_color(theme_state["surface"]),
                            ),
                            make_schedule_btn(0, "Today"),
                            make_schedule_btn(1, "Tmrw"),
                            pick_date_btn,
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        tight=True,
                    ),
                )

                edit_btn = ft.Container(
                    width=34,
                    height=34,
                    alignment=ft.Alignment(0, 0),
                    border_radius=8,
                    bgcolor=theme_state["surface"],
                    on_click=lambda _, tid=task_id: open_edit_task_modal(tid),
                    tooltip="Edit or Delete Task",
                    content=ft.Icon(
                        ft.Icons.EDIT_OUTLINED,
                        size=18,
                        color=get_subtext_color(card_bg),
                    ),
                )

                desc_parts = [f"Category: {category or 'General'}"]
                if note:
                    desc_parts.append(f"📝 {note}")
                if t_rem:
                    desc_parts.append(f"🔔 {format_time_display(t_rem)}")
                desc_text = " • ".join(desc_parts)

                card_children = [
                    ft.Row(
                        [
                            chk_box,
                            ft.Column(
                                [
                                    ft.Text(
                                        name,
                                        weight=ft.FontWeight.W_600,
                                        size=14,
                                        color=get_text_color(card_bg),
                                    ),
                                    ft.Text(
                                        desc_text,
                                        size=11,
                                        color=get_subtext_color(card_bg),
                                    ),
                                ],
                                expand=True,
                                spacing=2,
                            ),
                            ft.Row(
                                [
                                    schedule_cluster,
                                    edit_btn,
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                tight=True,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    )
                ]

                if is_picking_date:
                    browse_dt = backlog_state["cal_browse"]
                    yr, mo = browse_dt.year, browse_dt.month
                    cal_obj = calendar.Calendar(firstweekday=0)
                    weeks = cal_obj.monthdatescalendar(yr, mo)
                    today_s = datetime.now().strftime("%Y-%m-%d")

                    def shift_bg_cal(delta):
                        nm = backlog_state["cal_browse"].month + delta
                        ny = backlog_state["cal_browse"].year + (nm - 1) // 12
                        nm = (nm - 1) % 12 + 1
                        backlog_state["cal_browse"] = backlog_state["cal_browse"].replace(year=ny, month=nm, day=1)
                        load_backlog_view()

                    cal_rows = [
                        ft.Row(
                            [
                                ft.IconButton(
                                    icon=ft.Icons.CHEVRON_LEFT,
                                    icon_size=16,
                                    on_click=lambda _: shift_bg_cal(-1),
                                ),
                                ft.Text(
                                    browse_dt.strftime("%B %Y"),
                                    size=13,
                                    weight=ft.FontWeight.BOLD,
                                    color=theme_state["accent"],
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.CHEVRON_RIGHT,
                                    icon_size=16,
                                    on_click=lambda _: shift_bg_cal(1),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Row(
                            [
                                ft.Container(
                                    width=32,
                                    alignment=ft.Alignment(0, 0),
                                    content=ft.Text(
                                        d_lbl,
                                        size=10,
                                        weight=ft.FontWeight.BOLD,
                                        color=get_subtext_color(theme_state["surface"]),
                                    ),
                                )
                                for d_lbl in ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=4,
                        ),
                    ]

                    for wk in weeks:
                        day_cells = []
                        for d_o in wk:
                            ds = d_o.strftime("%Y-%m-%d")
                            in_m = (d_o.month == mo)
                            is_tod = (ds == today_s)

                            def pick_bg_date(e, chosen_ds=ds, i=task_id, nm=name):
                                backlog_state["date_picker_tid"] = None
                                schedule_backlog_task_db(i, chosen_ds)
                                show_message(f"📅 Scheduled '{nm}' for {format_ui_date(chosen_ds, 'short_text')}!")
                                load_backlog_view()

                            day_cells.append(
                                ft.Container(
                                    width=32,
                                    height=28,
                                    border_radius=6,
                                    bgcolor=theme_state["surface_card"] if is_tod else (theme_state["box"] if in_m else theme_state["surface"]),
                                    border=make_border(1, theme_state["accent"]) if is_tod else None,
                                    alignment=ft.Alignment(0, 0),
                                    on_click=pick_bg_date,
                                    content=ft.Text(
                                        str(d_o.day),
                                        size=11,
                                        weight=ft.FontWeight.BOLD if is_tod else ft.FontWeight.NORMAL,
                                        color=theme_state["accent"]
                                        if is_tod
                                        else (get_text_color(theme_state["box"]) if in_m else get_subtext_color(theme_state["surface"])),
                                    ),
                                )
                            )
                        cal_rows.append(ft.Row(day_cells, alignment=ft.MainAxisAlignment.CENTER, spacing=4))

                    card_children.append(
                        ft.Container(
                            margin=ft.Margin(top=8, left=0, right=0, bottom=0),
                            padding=10,
                            width=300,
                            bgcolor=theme_state["surface"],
                            border_radius=8,
                            border=make_border(1.5, theme_state["accent"]),
                            content=ft.Column(cal_rows, spacing=4),
                        )
                    )

                backlog_view.controls.append(
                    ft.Container(
                        content=ft.Column(card_children, spacing=0, tight=True),
                        padding=12,
                        bgcolor=card_bg,
                        border_radius=8,
                        border=make_border(1, get_border_color(theme_state["box"])),
                    )
                )

        # 5. Recently Completed in Session (With One-Click Undo back to Backlog)
        if backlog_state["recently_completed"]:
            done_cards = []
            for item in backlog_state["recently_completed"]:
                def undo_backlog_complete(e, rec=item):
                    remove_completion_db(rec["id"], rec["date"])
                    update_task_db(
                        task_id=rec["id"],
                        name=rec["name"],
                        category=rec["category"],
                        time_frame="custom",
                        target_date=None,
                        recurrence_type="once",
                        interval_days=0,
                        end_date=None,
                        note=rec["note"],
                        unit=None,
                        custom_days=None,
                        custom_months=None,
                        reminder_time=rec["reminder_time"],
                    )
                    try:
                        conn = get_db_connection()
                        conn.execute("UPDATE tasks SET custom_list = 'Backlog' WHERE id = ?", (rec["id"],))
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass
                    backlog_state["recently_completed"] = [
                        x for x in backlog_state["recently_completed"] if x["id"] != rec["id"]
                    ]
                    show_message(f"↩ Restored '{rec['name']}' to Backlog")
                    load_backlog_view()

                done_cards.append(
                    ft.Container(
                        padding=ft.Padding(left=12, right=10, top=8, bottom=8),
                        bgcolor=theme_state["surface"],
                        border_radius=8,
                        border=make_border(1, get_border_color(theme_state["surface"])),
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, size=18, color=theme_state["accent"]),
                                ft.Text(
                                    f"{item['name']} ({item['category']})",
                                    size=13,
                                    color=get_subtext_color(theme_state["surface"]),
                                    expand=True,
                                ),
                                ft.TextButton(
                                    content=ft.Text("Undo", size=11, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                                    on_click=undo_backlog_complete,
                                ),
                            ],
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    )
                )

            backlog_view.controls.append(ft.Divider(color=get_border_color(theme_state["bg"]), height=12))
            backlog_view.controls.append(
                ft.Text(
                    "Completed This Session (Logged to Today)",
                    size=12,
                    weight=ft.FontWeight.BOLD,
                    color=get_subtext_color(theme_state["bg"]),
                )
            )
            backlog_view.controls.extend(done_cards)

        page.update()
# =============================================================================
# >>> SECTION A6 END: VIEW 3 - BACKLOG QUEUE <<<
# =============================================================================

# =============================================================================
# >>> SECTION A7 START: VIEW 4 - HABITS & DATA DASHBOARD <<<
# =============================================================================
    active_heatmap_scope = "global"
    active_heatmap_identifier = None

    STREAK_MILESTONES = [3, 7, 14, 21, 30, 50, 60, 75, 100, 150, 200, 365]

    def get_habit_consistency_target(habit_name: str) -> int:
        if not habit_name:
            return 85
        raw = get_all_settings().get(f"consistency_goal_{habit_name.strip().lower()}", "85")
        try:
            val = int(float(raw))
            return max(50, min(100, val))
        except Exception:
            return 85

    def set_habit_consistency_target(habit_name: str, pct_val: int):
        if not habit_name:
            return
        clamped = max(50, min(100, int(pct_val)))
        save_setting(f"consistency_goal_{habit_name.strip().lower()}", str(clamped))

    def get_consistency_tier_label(pct_val: int) -> str:
        if pct_val >= 100:
            return "Extreme"
        if pct_val >= 95:
            return "Intense"
        if pct_val >= 90:
            return "High Focus"
        if pct_val >= 85:
            return "Recommended"
        if pct_val >= 75:
            return "Balanced"
        return "Flexible"

    def get_streak_hype_copy(streak_len: int):
        if streak_len < 3:
            return None
        if streak_len >= 365:
            return f"👑 {streak_len}-DAY STREAK! A FULL YEAR UNBROKEN — ABSOLUTE LEGEND!"
        if streak_len >= 100:
            return f"💎 {streak_len}-DAY STREAK! TRIPLE DIGITS — YOU ARE UNSTOPPABLE!"
        if streak_len >= 60:
            return f"🏆 {streak_len}-DAY STREAK! TWO MONTHS OF PURE MOMENTUM — LET'S GO!"
        if streak_len >= 30:
            return f"🚀 {streak_len}-DAY STREAK! 30+ DAYS LOCKED IN — THIS HABIT IS PART OF YOU NOW!"
        if streak_len >= 21:
            return f"⚡ {streak_len}-DAY STREAK! THREE WEEKS STRONG — KEEP THAT ENGINE RUNNING!"
        if streak_len >= 14:
            return f"🔥 {streak_len}-DAY STREAK! TWO FULL WEEKS UNBROKEN — LET'S GO!"
        if streak_len >= 7:
            return f"🔥 {streak_len}-DAY STREAK! ONE FULL WEEK CRUSHED — LET'S GO!"
        return f"✨ {streak_len}-DAY STREAK! MOMENTUM IS BUILDING — KEEP IT ROLLING!"

    def _normalize_period_date(raw_str: str):
        """Parse DD-MM-YYYY, DD/MM/YYYY, DD.MM.YYYY, or YYYY-MM-DD into (DD-MM-YYYY, datetime) or (None, None)."""
        if not raw_str:
            return None, None
        cleaned = raw_str.strip().replace("/", "-").replace(".", "-")
        for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.strftime("%d-%m-%Y"), dt
            except ValueError:
                continue
        return None, None

    def evaluate_habit_goals_live(habit_name: str) -> list:
        """Evaluate goals strictly from `start_date` onward; keep weekly_avg & all_time_avg live/loseable."""
        raw_goals = get_habit_goals_list(habit_name)
        if not raw_goals:
            return []

        _, all_logs = get_habit_unit_logs(habit_name)
        now_dt = datetime.now()

        conn = get_db_connection()
        evaluated = []

        for g in raw_goals:
            gid = g["id"]
            g_type = g.get("goal_type", "max")
            target_v = float(g.get("target_value", 0.0))
            s_date = g.get("start_date") or "1970-01-01"
            e_date = g.get("end_date")

            scoped_logs = [
                (d_s, float(v))
                for d_s, v in all_logs
                if d_s >= s_date and (not e_date or d_s <= e_date)
            ]

            new_achieved = False
            new_ach_date = None
            status_detail = ""

            if g_type == "max":
                hit_dates = [d_s for d_s, v in scoped_logs if v >= target_v]
                if hit_dates:
                    new_achieved = True
                    new_ach_date = sorted(hit_dates)[0]
                elif g.get("achieved") and g.get("achieved_date") and g["achieved_date"] >= s_date:
                    new_achieved = True
                    new_ach_date = g["achieved_date"]
                best_since = max([v for _, v in scoped_logs], default=0.0)
                status_detail = f"Best since start: {best_since:g}"

            elif g_type == "weekly_avg":
                ref_dt = datetime.strptime(e_date, "%Y-%m-%d") if (e_date and e_date < now_dt.strftime("%Y-%m-%d")) else now_dt
                ref_yr, ref_wk, _ = ref_dt.isocalendar()
                wk_logs = []
                for d_s, v in scoped_logs:
                    try:
                        dt_obj = datetime.strptime(d_s, "%Y-%m-%d")
                        if dt_obj.isocalendar()[:2] == (ref_yr, ref_wk):
                            wk_logs.append((d_s, v))
                    except Exception:
                        continue
                if wk_logs:
                    wk_avg = sum(v for _, v in wk_logs) / len(wk_logs)
                    status_detail = f"This week avg: {wk_avg:.1f}"
                    if wk_avg >= target_v:
                        new_achieved = True
                        new_ach_date = wk_logs[-1][0]
                else:
                    status_detail = "No logs this week yet"

            elif g_type == "all_time_avg":
                if scoped_logs:
                    ov_avg = sum(v for _, v in scoped_logs) / len(scoped_logs)
                    status_detail = f"Avg since start: {ov_avg:.1f}"
                    if ov_avg >= target_v:
                        new_achieved = True
                        new_ach_date = scoped_logs[-1][0]
                else:
                    status_detail = "No logs since start yet"

            old_achieved = bool(g.get("achieved"))
            if new_achieved != old_achieved or (new_achieved and new_ach_date != g.get("achieved_date")):
                try:
                    conn.execute(
                        "UPDATE habit_goals SET achieved = ?, achieved_date = ? WHERE id = ?",
                        (1 if new_achieved else 0, new_ach_date if new_achieved else None, gid),
                    )
                except Exception:
                    pass

            g_copy = dict(g)
            g_copy["achieved"] = new_achieved
            g_copy["achieved_date"] = new_ach_date
            g_copy["status_detail"] = status_detail
            evaluated.append(g_copy)

        try:
            conn.commit()
            conn.close()
        except Exception:
            pass

        return evaluated

    def check_and_celebrate_habit_milestones(habit_name: str):
        """Cross-page trigger: fires non-intrusive celebration banner + chime on Goal or Streak milestones."""
        if not habit_name:
            return
        settings_now = get_all_settings()
        triggered = False

        try:
            goals_now = evaluate_habit_goals_live(habit_name)
            seen_raw = settings_now.get("celebrated_goal_ids", "")
            seen_ids = {x.strip() for x in seen_raw.split(",") if x.strip()}
            changed_seen = False

            for g in goals_now:
                gid_str = str(g["id"])
                if g.get("achieved"):
                    if gid_str not in seen_ids:
                        seen_ids.add(gid_str)
                        changed_seen = True
                        unit_n, _ = get_habit_unit_logs(habit_name)
                        u_suffix = f" {unit_n}" if unit_n else ""
                        trigger_celebration_popup(
                            headline=f"GOAL ACHIEVED! ({g['target_value']:g}{u_suffix})",
                            subtext=f"'{habit_name}' hit your target — keep it up or set your next milestone!",
                            is_streak=False,
                        )
                        triggered = True
                else:
                    if gid_str in seen_ids and g.get("goal_type") in ("weekly_avg", "all_time_avg"):
                        seen_ids.remove(gid_str)
                        changed_seen = True

            if changed_seen:
                save_setting("celebrated_goal_ids", ",".join(sorted(seen_ids)))
        except Exception:
            pass

        try:
            h_stats = get_streak_and_stats("habit", habit_name)
            cur_s = int(h_stats.get("current_streak", 0))
            if cur_s in STREAK_MILESTONES:
                m_key = f"celebrated_streak_{habit_name.strip().lower()}"
                last_celebrated_s = int(settings_now.get(m_key, "0") or "0")
                if cur_s > last_celebrated_s:
                    save_setting(m_key, str(cur_s))
                    hype = get_streak_hype_copy(cur_s)
                    if hype and not triggered:
                        trigger_celebration_popup(
                            headline=f"{cur_s}-DAY STREAK!",
                            subtext=f"{habit_name} — {hype}",
                            is_streak=True,
                        )
        except Exception:
            pass

    # --- Section-by-Section Guide Modal for Page 4 ---
    guide_step_idx = 0
    guide_steps_data = [
        (
            "Section 1 — Filter Scope & Timeframe",
            ft.Icons.INSIGHTS_ROUNDED,
            "Use 'Filter By' to view Everything (Global) or isolate one Habit or Category. When inspecting a habit, use the 7D / 30D / 90D / All Time chips (or custom dates) to zoom into any window.",
        ),
        (
            "Section 2 — Streaks & Custom Consistency Goal",
            ft.Icons.BOLT_ROUNDED,
            "Streaks count scheduled days completed in a row—unscheduled rest days never break your streak. Each habit stores its own Consistency Goal (defaulting to 85% • Recommended, or click 'Change Target' to set any custom percentage up to 100% Extreme).",
        ),
        (
            "Section 3 — Review Heatmap",
            ft.Icons.GRID_VIEW_ROUNDED,
            "Each column is a week (Mon–Sun). Solid colored tiles mark completed days, dim tiles mark missed scheduled days, subtle outline squares mark unscheduled days, and Today is highlighted with a crisp white border.",
        ),
        (
            "Section 4 — Unit Goals, Hover Chart & Fullscreen View",
            ft.Icons.TRENDING_UP_ROUNDED,
            "Goals stay visible as black-and-white striped lines across all graph views and evaluate strictly from the date you create them onward. Charts with 1–3 entries display as bars automatically before unlocking Line mode at 4+ points.",
        ),
    ]

    guide_modal_box = ft.Container(
        padding=18,
        width=490,
        bgcolor=theme_state["surface"],
        border_radius=12,
        border=make_border(1.5, theme_state["accent"]),
    )

    guide_dialog = ft.AlertDialog(
        content=guide_modal_box,
        bgcolor=theme_state["surface"],
        shape=ft.RoundedRectangleBorder(radius=12),
    )

    def close_page4_guide(e=None):
        if hasattr(page, "close"):
            page.close(guide_dialog)
        else:
            guide_dialog.open = False
            page.update()

    def render_page4_guide_step():
        title_s, icon_s, body_s = guide_steps_data[guide_step_idx]
        total_steps = len(guide_steps_data)

        dots_row = ft.Row(
            [
                ft.Container(
                    width=22 if i == guide_step_idx else 8,
                    height=8,
                    border_radius=4,
                    bgcolor=theme_state["accent"] if i == guide_step_idx else get_border_color(theme_state["surface"]),
                )
                for i in range(total_steps)
            ],
            spacing=5,
        )

        def step_guide(delta: int):
            nonlocal guide_step_idx
            guide_step_idx = max(0, min(total_steps - 1, guide_step_idx + delta))
            render_page4_guide_step()
            page.update()

        nav_buttons = []
        if guide_step_idx > 0:
            nav_buttons.append(
                ft.OutlinedButton(
                    content=ft.Text("Back", size=12, weight=ft.FontWeight.W_600),
                    on_click=lambda _: step_guide(-1),
                )
            )
        if guide_step_idx < total_steps - 1:
            nav_buttons.append(
                ft.FilledButton(
                    content=ft.Text("Next →", size=12, weight=ft.FontWeight.BOLD, color=get_text_color(theme_state["accent"])),
                    bgcolor=theme_state["accent"],
                    on_click=lambda _: step_guide(1),
                )
            )
        else:
            nav_buttons.append(
                ft.FilledButton(
                    content=ft.Text("Got It", size=12, weight=ft.FontWeight.BOLD, color=get_text_color(theme_state["accent"])),
                    icon=ft.Icons.CHECK_ROUNDED,
                    icon_color=get_text_color(theme_state["accent"]),
                    bgcolor=theme_state["accent"],
                    on_click=close_page4_guide,
                )
            )

        guide_modal_box.bgcolor = theme_state["surface"]
        guide_modal_box.border = make_border(1.5, theme_state["accent"])
        guide_dialog.bgcolor = theme_state["surface"]

        guide_modal_box.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.INSIGHTS_ROUNDED, size=18, color=theme_state["accent"]),
                                ft.Text("Analytics & Habits Guide", size=14, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                            ],
                            spacing=6,
                        ),
                        ft.IconButton(icon=ft.Icons.CLOSE_ROUNDED, icon_size=18, on_click=close_page4_guide),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(color=get_border_color(theme_state["surface"]), height=4),
                ft.Container(
                    padding=14,
                    bgcolor=theme_state["box"],
                    border_radius=8,
                    border=make_border(1.5, get_border_color(theme_state["box"])),
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(icon_s, size=20, color=theme_state["accent"]),
                                    ft.Text(title_s, size=15, weight=ft.FontWeight.BOLD, color=get_text_color(theme_state["box"])),
                                ],
                                spacing=8,
                            ),
                            ft.Text(
                                body_s,
                                size=12,
                                color=get_subtext_color(theme_state["box"]),
                            ),
                        ],
                        spacing=8,
                    ),
                ),
                ft.Row(
                    [
                        dots_row,
                        ft.Row(nav_buttons, spacing=8),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=10,
            tight=True,
        )

    def open_page4_guide(e=None):
        nonlocal guide_step_idx
        guide_step_idx = 0
        render_page4_guide_step()
        if guide_dialog not in page.overlay:
            page.overlay.append(guide_dialog)
        if hasattr(page, "open"):
            page.open(guide_dialog)
        else:
            page.dialog = guide_dialog
            guide_dialog.open = True
            page.update()

    scope_dropdown = ft.Dropdown(
        label="Filter By",
        width=210,
        border_width=1.5,
        focused_border_width=1.5,
        options=[
            ft.dropdown.Option(key="global", text="Everything (Global)"),
            ft.dropdown.Option(key="habit", text="Individual Habit"),
            ft.dropdown.Option(key="category", text="Category"),
        ],
        value="global",
    )

    target_dropdown = ft.Dropdown(
        label="Select Habit / Category",
        width=250,
        visible=False,
        border_width=1.5,
        focused_border_width=1.5,
    )

    habit_analytics_state = {
        "start": None,
        "end": None,
        "period_preset": "all",
        "chart_style": "line",
        "time_bucket": "daily",
        "weekly_agg_mode": "avg",
        "show_trend": False,
        "show_forecast": False,
        "forecast_horizon_days": 30,
        "forecast_to_goal": False,
        "lookback_days": None,
        "goal_type": "max",
        "goal_end_date": None,
        "goal_cal_open": False,
        "goal_cal_browse": datetime.now().replace(day=1),
        "editing_consistency": False,
        "chart_fullscreen": False,
    }

    def sync_target_dropdown_options():
        nonlocal active_heatmap_identifier
        scope_dropdown.border_color = get_border_color(theme_state["box"])
        scope_dropdown.focused_border_color = theme_state["accent"]
        target_dropdown.border_color = get_border_color(theme_state["box"])
        target_dropdown.focused_border_color = theme_state["accent"]

        if active_heatmap_scope == "global":
            target_dropdown.visible = False
            active_heatmap_identifier = None
        elif active_heatmap_scope == "category":
            cats = get_distinct_categories()
            target_dropdown.label = "Select Category"
            target_dropdown.options = [ft.dropdown.Option(key=c, text=c) for c in cats]
            if active_heatmap_identifier not in cats:
                active_heatmap_identifier = cats[0] if cats else None
            target_dropdown.value = active_heatmap_identifier
            target_dropdown.visible = True
        elif active_heatmap_scope == "habit":
            habs = get_distinct_habits()
            target_dropdown.label = "Select Habit (Daily / Weekly / Monthly)"
            target_dropdown.options = [ft.dropdown.Option(key=h, text=h) for h in habs]
            if active_heatmap_identifier not in habs:
                active_heatmap_identifier = habs[0] if habs else None
            target_dropdown.value = active_heatmap_identifier
            target_dropdown.visible = True

    def on_scope_change(e):
        nonlocal active_heatmap_scope
        active_heatmap_scope = scope_dropdown.value or "global"
        habit_analytics_state["start"] = None
        habit_analytics_state["end"] = None
        habit_analytics_state["period_preset"] = "all"
        habit_analytics_state["goal_cal_open"] = False
        habit_analytics_state["editing_consistency"] = False
        habit_analytics_state["chart_fullscreen"] = False
        sync_target_dropdown_options()
        load_habits_dashboard()

    def on_target_change(e):
        nonlocal active_heatmap_identifier
        active_heatmap_identifier = target_dropdown.value
        habit_analytics_state["start"] = None
        habit_analytics_state["end"] = None
        habit_analytics_state["period_preset"] = "all"
        habit_analytics_state["goal_cal_open"] = False
        habit_analytics_state["editing_consistency"] = False
        habit_analytics_state["chart_fullscreen"] = False
        load_habits_dashboard()

    scope_dropdown.on_select = on_scope_change
    scope_dropdown.on_change = on_scope_change
    target_dropdown.on_select = on_target_change
    target_dropdown.on_change = on_target_change

    def build_anki_heatmap_widget(data: dict, is_daily_mode: bool, today_str: str) -> ft.Control:
        base_r, base_g, base_b = hex_to_rgb(theme_state["surface"])
        acc_r, acc_g, acc_b = hex_to_rgb(theme_state["accent"])

        colors = {}
        for lvl in range(5):
            t = lvl / 4.0
            r = int(base_r + (acc_r - base_r) * t)
            g = int(base_g + (acc_g - base_g) * t)
            b = int(base_b + (acc_b - base_b) * t)
            colors[lvl] = rgb_to_hex(r, g, b)

        sorted_dates = sorted(data.keys())
        raw_start = datetime.strptime(sorted_dates[0], "%Y-%m-%d")
        raw_end = datetime.strptime(sorted_dates[-1], "%Y-%m-%d")

        _, custom_start_dt = _normalize_period_date(habit_analytics_state["start"])
        _, custom_end_dt = _normalize_period_date(habit_analytics_state["end"])

        if custom_start_dt is not None:
            start_dt = custom_start_dt
        else:
            min_window_start = datetime.now() - timedelta(days=182)
            start_dt = max(raw_start, min_window_start)

        if custom_end_dt is not None:
            end_dt = custom_end_dt
        else:
            max_window_end = datetime.now() + timedelta(days=14)
            end_dt = min(max(raw_end, datetime.now()), max_window_end)

        if end_dt < start_dt:
            start_dt = end_dt - timedelta(days=28)

        start_dt = start_dt - timedelta(days=start_dt.weekday())
        end_dt = end_dt + timedelta(days=(6 - end_dt.weekday()))

        sub_col = get_subtext_color(theme_state["box"])
        box_r, box_g, box_b = hex_to_rgb(theme_state["box"])
        txt_r, txt_g, txt_b = hex_to_rgb(get_text_color(theme_state["box"]))
        off_day_border_col = rgb_to_hex(
            int(box_r + (txt_r - box_r) * 0.35),
            int(box_g + (txt_g - box_g) * 0.35),
            int(box_b + (txt_b - box_b) * 0.35),
        )

        day_labels_col = ft.Column(
            [
                ft.Container(height=16),
                ft.Container(height=15, alignment=ft.Alignment(-1, 0), content=ft.Text("Mon", size=9, color=sub_col)),
                ft.Container(height=15),
                ft.Container(height=15, alignment=ft.Alignment(-1, 0), content=ft.Text("Wed", size=9, color=sub_col)),
                ft.Container(height=15),
                ft.Container(height=15, alignment=ft.Alignment(-1, 0), content=ft.Text("Fri", size=9, color=sub_col)),
                ft.Container(height=15),
                ft.Container(height=15, alignment=ft.Alignment(-1, 0), content=ft.Text("Sun", size=9, color=sub_col)),
            ],
            spacing=3,
            tight=True,
        )

        weeks_columns = []
        curr = start_dt
        last_month_shown = None

        while curr <= end_dt:
            month_label_str = ""
            for offset in range(7):
                check_d = curr + timedelta(days=offset)
                if check_d.day <= 7 and check_d.month != last_month_shown:
                    month_label_str = check_d.strftime("%b")
                    last_month_shown = check_d.month
                    break

            col_controls = [
                ft.Container(
                    height=16,
                    width=15,
                    content=ft.Text(month_label_str, size=9, color=sub_col, no_wrap=True),
                )
            ]

            for _ in range(7):
                d_key = curr.strftime("%Y-%m-%d")
                ui_d = format_ui_date(d_key, "short_text")
                info = data.get(d_key, {"count": 0, "due": 0, "intensity": 0})
                is_today = d_key == today_str
                due_cnt = info.get("due", 0)
                done_cnt = info.get("count", 0)

                has_activity_or_due = is_daily_mode or (due_cnt > 0) or (done_cnt > 0)

                if not has_activity_or_due:
                    cell = ft.Container(
                        width=15,
                        height=15,
                        alignment=ft.Alignment(0, 0),
                        tooltip=f"{ui_d}: {'Today • ' if is_today else ''}Unscheduled (Rest day)",
                        content=ft.Container(
                            width=8,
                            height=8,
                            border_radius=2,
                            bgcolor=theme_state["bg"],
                            border=make_border(1.5, "#FFFFFF" if is_today else off_day_border_col),
                        ),
                    )
                else:
                    tile_color = colors.get(info["intensity"], colors[0])
                    if is_today and info.get("intensity", 0) == 0:
                        tile_color = theme_state["surface_card"]
                    status_lbl = (
                        f"{done_cnt} done / {due_cnt} due"
                        if active_heatmap_scope == "global"
                        else ("Completed" if done_cnt > 0 else ("Missed" if d_key < today_str and due_cnt > 0 else "Scheduled"))
                    )
                    if is_today:
                        status_lbl = f"Today • {status_lbl}"
                    cell = ft.Container(
                        width=15,
                        height=15,
                        bgcolor=tile_color,
                        border_radius=3,
                        border=make_border(1.5, "#FFFFFF") if is_today else None,
                        tooltip=f"{ui_d}: {status_lbl}",
                    )

                col_controls.append(cell)
                curr += timedelta(days=1)

            weeks_columns.append(ft.Column(col_controls, spacing=3, tight=True))

        bounded_weeks_scroller = ft.Container(
            height=152,
            expand=True,
            alignment=ft.Alignment(-1, -1),
            content=ft.Row(weeks_columns, spacing=3, scroll=ft.ScrollMode.AUTO, vertical_alignment=ft.CrossAxisAlignment.START),
        )

        grid_row = ft.Row(
            [
                day_labels_col,
                bounded_weeks_scroller,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        legend_items = []
        if not is_daily_mode:
            legend_items.extend(
                [
                    ft.Container(
                        width=8,
                        height=8,
                        border_radius=2,
                        bgcolor=theme_state["bg"],
                        border=make_border(1.5, off_day_border_col),
                    ),
                    ft.Text("Unscheduled   ", size=10, color=sub_col),
                ]
            )

        legend_items.append(ft.Text("Less", size=10, color=sub_col))
        for lvl in range(5):
            legend_items.append(
                ft.Container(width=12, height=12, bgcolor=colors[lvl], border_radius=2)
            )
        legend_items.append(ft.Text("More", size=10, color=sub_col))

        legend_row = ft.Row(
            legend_items,
            spacing=4,
            alignment=ft.MainAxisAlignment.END,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        return ft.Column([grid_row, legend_row], spacing=8, tight=True)

    def _build_unit_chart_bundle(
        unit_name: str,
        unit_logs: list,
        goals_list: list,
        pace_info: dict,
        is_fullscreen: bool = False,
    ) -> ft.Column:
        curr_style = habit_analytics_state.get("chart_style", "line")
        curr_bucket = habit_analytics_state.get("time_bucket", "daily")
        curr_wk_agg = habit_analytics_state.get("weekly_agg_mode", "avg")
        curr_trend = bool(habit_analytics_state.get("show_trend", False))
        curr_forecast = bool(habit_analytics_state.get("show_forecast", False))
        curr_horizon = int(habit_analytics_state.get("forecast_horizon_days", 30))
        curr_to_goal = bool(habit_analytics_state.get("forecast_to_goal", False))
        curr_lookback = habit_analytics_state.get("lookback_days", None)

        active_series = _build_chart_series(unit_logs, time_bucket=curr_bucket, weekly_agg_mode=curr_wk_agg)
        n_hist_pts = len(active_series)
        forced_pillars = (n_hist_pts <= 3)

        proj_accent = theme_state["accent"]
        is_dark_bg = (get_text_color(theme_state["bg"]) == "#FFFFFF")
        avg_legend_col = "#F1F5F9" if is_dark_bg else "#0F172A"

        def make_seg_pill(label: str, is_active: bool, fn, is_locked: bool = False):
            return ft.Container(
                padding=ft.Padding(left=11, right=11, top=6, bottom=6),
                bgcolor=theme_state["accent"] if is_active else theme_state["surface"],
                border_radius=6,
                border=make_border(
                    1.5,
                    theme_state["accent"] if is_active else get_border_color(theme_state["surface"]),
                ),
                on_click=fn,
                content=ft.Text(
                    label,
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    color=get_text_color(theme_state["accent"])
                    if is_active
                    else (get_subtext_color(theme_state["surface"]) if is_locked else get_text_color(theme_state["surface"])),
                ),
            )

        def make_segmented_group(items_list: list):
            return ft.Container(
                padding=3,
                bgcolor=theme_state["surface"],
                border_radius=8,
                border=make_border(1.5, get_border_color(theme_state["surface"])),
                content=ft.Row(items_list, spacing=3, tight=True),
            )

        bucket_group = make_segmented_group(
            [
                make_seg_pill(
                    "Daily",
                    curr_bucket == "daily",
                    lambda _: (habit_analytics_state.update({"time_bucket": "daily"}), load_habits_dashboard()),
                ),
                make_seg_pill(
                    "Weekly",
                    curr_bucket == "weekly",
                    lambda _: (habit_analytics_state.update({"time_bucket": "weekly"}), load_habits_dashboard()),
                ),
            ]
        )

        wk_mode_group = ft.Container(
            visible=(curr_bucket == "weekly"),
            content=make_segmented_group(
                [
                    make_seg_pill(
                        "Weekly Avg",
                        curr_wk_agg == "avg",
                        lambda _: (habit_analytics_state.update({"weekly_agg_mode": "avg"}), load_habits_dashboard()),
                    ),
                    make_seg_pill(
                        "Weekly Total",
                        curr_wk_agg == "sum",
                        lambda _: (habit_analytics_state.update({"weekly_agg_mode": "sum"}), load_habits_dashboard()),
                    ),
                ]
            ),
        )

        # For 1-3 points, Bars are active automatically; Line unlocks at 4+ points
        style_group = make_segmented_group(
            [
                make_seg_pill(
                    "Line (4+ pts)" if forced_pillars else "Line",
                    (not forced_pillars) and (curr_style == "line"),
                    (
                        lambda _: show_message("Bars are used automatically for 1–3 data points. Log 4+ points to switch to Line!")
                        if forced_pillars
                        else lambda _: (habit_analytics_state.update({"chart_style": "line"}), load_habits_dashboard())
                    ),
                    is_locked=forced_pillars,
                ),
                make_seg_pill(
                    "Bars",
                    forced_pillars or (curr_style == "pillars"),
                    lambda _: (habit_analytics_state.update({"chart_style": "pillars"}), load_habits_dashboard()),
                ),
            ]
        )

        avg_toggle_pill = make_seg_pill(
            "Avg Line: On" if curr_trend else "Avg Line",
            curr_trend,
            lambda _: (habit_analytics_state.update({"show_trend": not curr_trend}), load_habits_dashboard()),
        )

        proj_toggle_pill = make_seg_pill(
            "Project Future: On" if curr_forecast else "Project Future",
            curr_forecast,
            lambda _: (habit_analytics_state.update({"show_forecast": not curr_forecast}), load_habits_dashboard()),
        )

        fs_toggle_btn = ft.Container(
            padding=ft.Padding(left=11, right=11, top=6, bottom=6),
            bgcolor=theme_state["surface_card"],
            border_radius=6,
            border=make_border(1.5, theme_state["accent"]),
            on_click=lambda _: (
                habit_analytics_state.update({"chart_fullscreen": not is_fullscreen}),
                load_habits_dashboard(),
            ),
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.FULLSCREEN_EXIT_ROUNDED if is_fullscreen else ft.Icons.FULLSCREEN_ROUNDED,
                        size=15,
                        color=theme_state["accent"],
                    ),
                    ft.Text(
                        "Exit Fullscreen" if is_fullscreen else "Fullscreen",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=theme_state["accent"],
                    ),
                ],
                spacing=5,
                tight=True,
            ),
        )

        chart_controls_row = ft.Row(
            [
                bucket_group,
                wk_mode_group,
                style_group,
                avg_toggle_pill,
                proj_toggle_pill,
                fs_toggle_btn,
            ],
            spacing=8,
            wrap=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        visible_goals = _filter_visible_chart_goals(
            goals_list,
            time_bucket=curr_bucket,
            weekly_agg_mode=curr_wk_agg,
            show_trend=curr_trend,
        )
        has_any_unachieved_goal = any(not g.get("achieved", False) for g in (goals_list or []))

        def make_proj_opt_chip(lbl: str, active: bool, fn):
            return ft.Container(
                padding=ft.Padding(left=9, right=9, top=4, bottom=4),
                border_radius=6,
                bgcolor=theme_state["accent"] if active else theme_state["box"],
                border=make_border(
                    1.5,
                    theme_state["accent"] if active else get_border_color(theme_state["box"]),
                ),
                on_click=fn,
                content=ft.Text(
                    lbl,
                    size=11,
                    weight=ft.FontWeight.BOLD if active else ft.FontWeight.W_500,
                    color=get_text_color(theme_state["accent"])
                    if active
                    else get_text_color(theme_state["box"]),
                ),
            )

        lookback_opts = [
            ("Last 14D", 14),
            ("Last 30D", 30),
            ("Last 90D", 90),
            ("All Data", None),
        ]
        lookback_chips = [
            make_proj_opt_chip(
                lbl,
                curr_lookback == lb_val,
                lambda _, lv=lb_val: (habit_analytics_state.update({"lookback_days": lv}), load_habits_dashboard()),
            )
            for lbl, lb_val in lookback_opts
        ]

        horizon_opts = [
            ("+2 Wks", 14),
            ("+1 Mo", 30),
            ("+3 Mos", 90),
            ("+6 Mos", 180),
        ]
        horizon_chips = [
            make_proj_opt_chip(
                lbl,
                (not curr_to_goal) and (curr_horizon == h_val),
                lambda _, hv=h_val: (
                    habit_analytics_state.update({"forecast_horizon_days": hv, "forecast_to_goal": False}),
                    load_habits_dashboard(),
                ),
            )
            for lbl, h_val in horizon_opts
        ]
        if has_any_unachieved_goal:
            horizon_chips.append(
                make_proj_opt_chip(
                    "To Goal",
                    curr_to_goal,
                    lambda _: (habit_analytics_state.update({"forecast_to_goal": True}), load_habits_dashboard()),
                )
            )

        projection_config_panel = ft.Container(
            visible=curr_forecast,
            padding=10,
            bgcolor=theme_state["surface"],
            border_radius=8,
            border=make_border(1.5, theme_state["accent"]),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                "Based on:",
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color=get_subtext_color(theme_state["surface"]),
                            ),
                            *lookback_chips,
                            ft.Container(width=10),
                            ft.Text(
                                "Project ahead:",
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color=get_subtext_color(theme_state["surface"]),
                            ),
                            *horizon_chips,
                        ],
                        spacing=6,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        "Disclaimer: Projections are estimates based on a standardized trend model and can be inaccurate as real-world progress varies.",
                        size=11,
                        italic=True,
                        color=get_subtext_color(theme_state["surface"]),
                    ),
                ],
                spacing=6,
                tight=True,
            ),
        )

        def legend_dot(col_hex: str, txt: str, border_col: str = None):
            return ft.Row(
                [
                    ft.Container(
                        width=10,
                        height=10,
                        border_radius=5,
                        bgcolor=col_hex,
                        border=make_border(1.5, border_col or get_border_color(theme_state["box"])),
                    ),
                    ft.Text(txt, size=11, color=get_subtext_color(theme_state["box"])),
                ],
                spacing=5,
                tight=True,
            )

        series_lbl = (
            f"Logged ({unit_name})"
            if curr_bucket == "daily"
            else (f"Weekly Avg ({unit_name})" if curr_wk_agg == "avg" else f"Weekly Total ({unit_name})")
        )
        legend_items_row = [legend_dot(theme_state["accent"], series_lbl)]
        if curr_trend:
            legend_items_row.append(
                legend_dot(avg_legend_col, "Daily Avg Line" if curr_bucket == "daily" else "Weekly Avg Line")
            )
        if visible_goals:
            legend_items_row.append(
                legend_dot("#FFFFFF", "Target Goal (B&W Striped)", border_col="#000000")
            )
        if curr_forecast:
            proj_lbl = (
                "Projected Pace & Avg (Dashed)"
                if curr_trend
                else ("Daily Forecast (Dashed)" if curr_bucket == "daily" else "Weekly Forecast (Dashed)")
            )
            legend_items_row.append(legend_dot(ft.Colors.TRANSPARENT, proj_lbl, border_col=proj_accent))

        pace_banner = ft.Container(visible=False)
        if len(unit_logs) >= 1:
            mode_tag = (
                "Daily"
                if curr_bucket == "daily"
                else ("Weekly Avg" if curr_wk_agg == "avg" else "Weekly Total")
            )
            lb_tag = f"Last {curr_lookback}D" if curr_lookback else "All Data"
            if not pace_info["has_pace"]:
                pace_msg = f"Log at least 2 {'weeks' if curr_bucket == 'weekly' else 'days'} in '{lb_tag}' to calculate your {mode_tag.lower()} pace."
            else:
                wk_slope = pace_info["slope_per_week"]
                sign_str = "+" if wk_slope > 0 else ""
                f_v = pace_info["first_val"]
                l_v = pace_info["last_val"]
                pace_head = f"{mode_tag} Pace ({lb_tag}): {sign_str}{wk_slope:.2f} {unit_name}/wk ({f_v:g} → {l_v:g})"

                if pace_info["target_goal"] is not None:
                    tg_val = pace_info["target_goal"]
                    if pace_info["days_to_goal"] is not None and pace_info["eta_date_str"]:
                        d_left = pace_info["days_to_goal"]
                        w_left = max(1, int(round(d_left / 7.0)))
                        eta_nice = format_ui_date(pace_info["eta_date_str"], "short_text")
                        eta_tail = f"Est. {tg_val:g} {unit_name} by {eta_nice} (~{w_left} wk{'s' if w_left != 1 else ''})"
                    elif wk_slope <= 0:
                        eta_tail = f"Log higher sessions to estimate ETA to {tg_val:g} {unit_name}"
                    else:
                        eta_tail = f"{tg_val:g} {unit_name} is 2+ years out at this pace"
                else:
                    h_days_preview = 14 if curr_to_goal else curr_horizon
                    proj_end = _damped_project_value(l_v, wk_slope, h_days_preview)
                    eta_tail = f"Est. in {h_days_preview}d: {proj_end:.1f} {unit_name}"

                pace_msg = f"{pace_head}   •   {eta_tail}"

            pace_banner = ft.Container(
                padding=ft.Padding(left=12, right=12, top=8, bottom=8),
                bgcolor=theme_state["surface"],
                border_radius=8,
                border=make_border(
                    1.5,
                    theme_state["accent"] if curr_forecast else get_border_color(theme_state["surface"]),
                ),
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.TRENDING_UP_ROUNDED, size=17, color=theme_state["accent"]),
                        ft.Text(
                            pace_msg,
                            size=12,
                            weight=ft.FontWeight.W_600,
                            color=get_text_color(theme_state["surface"]),
                            expand=True,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )

        raw_win_w = getattr(getattr(page, "window", None), "width", None) or getattr(page, "width", None) or 1240
        raw_win_h = getattr(getattr(page, "window", None), "height", None) or getattr(page, "height", None) or 820
        overhead_h = 395 if curr_forecast else 318
        fs_w = max(840, int(raw_win_w - 84)) if is_fullscreen else None
        fs_h = max(250, int(raw_win_h - overhead_h)) if is_fullscreen else None

        chart_widget = build_area_line_chart_image(
            unit_name,
            unit_logs,
            chart_style=curr_style,
            show_trend=curr_trend,
            time_bucket=curr_bucket,
            weekly_agg_mode=curr_wk_agg,
            goals_list=goals_list,
            show_forecast=curr_forecast,
            forecast_horizon_days=curr_horizon,
            forecast_to_goal=curr_to_goal,
            lookback_days=curr_lookback,
            custom_width=fs_w,
            custom_height=fs_h,
        )

        return ft.Column(
            [
                chart_controls_row,
                projection_config_panel,
                ft.Row(legend_items_row, spacing=14, wrap=True),
                pace_banner,
                chart_widget,
            ],
            spacing=10,
            tight=True,
        )

    def load_habits_dashboard():
        sync_target_dropdown_options()
        scope_dropdown.value = active_heatmap_scope

        # --- Zero-Scroll Full-Bleed In-Page Fullscreen Mode for Unit Chart ---
        if (
            habit_analytics_state.get("chart_fullscreen", False)
            and active_heatmap_scope == "habit"
            and active_heatmap_identifier
        ):
            unit_name, unit_logs = get_habit_unit_logs(
                active_heatmap_identifier,
                start_override=habit_analytics_state["start"],
                end_override=habit_analytics_state["end"],
            )
            if unit_name and unit_logs:
                try:
                    habits_view.scroll_to(offset=0, duration=0)
                except Exception:
                    pass
                habits_view.scroll = None
                habits_view.controls.clear()

                goals_list = evaluate_habit_goals_live(active_heatmap_identifier)
                pace_info = compute_unit_pace_and_forecast(
                    unit_logs,
                    goals_list=goals_list,
                    time_bucket=habit_analytics_state.get("time_bucket", "daily"),
                    weekly_agg_mode=habit_analytics_state.get("weekly_agg_mode", "avg"),
                    lookback_days=habit_analytics_state.get("lookback_days", None),
                )
                fs_bundle = _build_unit_chart_bundle(
                    unit_name,
                    unit_logs,
                    goals_list,
                    pace_info,
                    is_fullscreen=True,
                )
                habits_view.controls.append(
                    build_shelf(
                        f"{active_heatmap_identifier} ({unit_name}) — Fullscreen Chart",
                        "Hover over any point, bar, or Avg Line node to inspect values.",
                        fs_bundle,
                    )
                )
                page.update()
                return
            else:
                habit_analytics_state["chart_fullscreen"] = False

        habits_view.scroll = ft.ScrollMode.AUTO
        habits_view.controls.clear()

        # Page Header
        test_celeb_btn = ft.OutlinedButton(
            content=ft.Text("Test Celebration", size=12, weight=ft.FontWeight.W_600, color=theme_state["accent"]),
            icon=ft.Icons.EMOJI_EVENTS_ROUNDED,
            icon_color=theme_state["accent"],
            style=ft.ButtonStyle(
                side=ft.BorderSide(1.5, get_border_color(theme_state["bg"])),
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            tooltip="Preview the non-intrusive Celebration toast + chime",
            on_click=lambda _: trigger_celebration_popup(
                headline="7-DAY STREAK MILESTONE!",
                subtext="Morning Run — One full week unbroken! Keep that momentum rolling!",
                is_streak=True,
            ),
        )

        guide_info_btn = ft.Container(
            padding=ft.Padding(left=12, right=12, top=8, bottom=8),
            border_radius=8,
            bgcolor=theme_state["surface_card"],
            border=make_border(1.5, theme_state["accent"]),
            on_click=open_page4_guide,
            tooltip="How to use Sections 1–4 of Habits & Analytics",
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.INFO_OUTLINED, size=16, color=theme_state["accent"]),
                    ft.Text("How It Works", size=12, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                ],
                spacing=6,
                tight=True,
            ),
        )

        habits_view.controls.append(
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text("Habits & Data Analytics", size=20, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                            ft.Text(
                                "Inspect streaks, consistency goals, heatmaps, and future pace projections.",
                                size=12,
                                color=get_subtext_color(theme_state["bg"]),
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Row(
                        [test_celeb_btn, guide_info_btn],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        tight=True,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

        # 1. Combined Filter Scope & Period Inspector Shelf
        filter_controls_col = ft.Column(
            [
                ft.Row([scope_dropdown, target_dropdown], spacing=12, wrap=True),
            ],
            spacing=10,
            tight=True,
        )

        if active_heatmap_scope == "habit" and active_heatmap_identifier:
            earliest_b, latest_b = get_habit_date_bounds(active_heatmap_identifier)
            ui_earliest = format_ui_date(earliest_b, "numeric")
            ui_latest = format_ui_date(latest_b, "numeric")
            cur_preset = habit_analytics_state.get("period_preset", "all")

            start_field = ft.TextField(
                label="From (DD-MM-YYYY)",
                value=habit_analytics_state["start"] or ui_earliest,
                width=145,
                text_size=12,
                border_width=1.5,
                focused_border_width=1.5,
                border_color=get_border_color(theme_state["box"]),
                focused_border_color=theme_state["accent"],
                on_focus=lambda _: set_typing(True),
                on_blur=lambda _: set_typing(False),
            )
            end_field = ft.TextField(
                label="To (DD-MM-YYYY)",
                value=habit_analytics_state["end"] or ui_latest,
                width=145,
                text_size=12,
                border_width=1.5,
                focused_border_width=1.5,
                border_color=get_border_color(theme_state["box"]),
                focused_border_color=theme_state["accent"],
                on_focus=lambda _: set_typing(True),
                on_blur=lambda _: set_typing(False),
            )

            def apply_quick_period(preset_key: str, days_back: int = None):
                set_typing(False)
                habit_analytics_state["period_preset"] = preset_key
                if days_back is None:
                    habit_analytics_state["start"] = None
                    habit_analytics_state["end"] = None
                else:
                    end_d = datetime.now()
                    start_d = end_d - timedelta(days=days_back)
                    habit_analytics_state["start"] = start_d.strftime("%d-%m-%Y")
                    habit_analytics_state["end"] = end_d.strftime("%d-%m-%Y")
                load_habits_dashboard()

            def apply_date_range(e=None):
                s_norm, s_dt = _normalize_period_date(start_field.value)
                e_norm, e_dt = _normalize_period_date(end_field.value)
                if not s_norm or not e_norm:
                    show_message("Enter valid dates as DD-MM-YYYY (e.g. 01-11-2026)!")
                    return
                if e_dt < s_dt:
                    s_norm, e_norm = e_norm, s_norm
                habit_analytics_state["start"] = s_norm
                habit_analytics_state["end"] = e_norm
                habit_analytics_state["period_preset"] = "custom"
                set_typing(False)
                load_habits_dashboard()

            start_field.on_submit = apply_date_range
            end_field.on_submit = apply_date_range

            def make_period_chip(lbl: str, p_key: str, days_b):
                is_act = (cur_preset == p_key)
                return ft.Container(
                    padding=ft.Padding(left=10, right=10, top=6, bottom=6),
                    border_radius=6,
                    bgcolor=theme_state["accent"] if is_act else theme_state["surface"],
                    border=make_border(
                        1.5,
                        theme_state["accent"] if is_act else get_border_color(theme_state["surface"]),
                    ),
                    on_click=lambda _: apply_quick_period(p_key, days_b),
                    content=ft.Text(
                        lbl,
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=get_text_color(theme_state["accent"]) if is_act else theme_state["accent"],
                    ),
                )

            apply_btn = ft.FilledButton(
                content=ft.Text("Apply", size=11, weight=ft.FontWeight.BOLD, color=get_text_color(theme_state["accent"])),
                on_click=apply_date_range,
                bgcolor=theme_state["accent"],
                height=38,
            )

            filter_controls_col.controls.append(ft.Divider(color=get_border_color(theme_state["box"]), height=4))
            filter_controls_col.controls.append(
                ft.Row(
                    [
                        ft.Text("Period:", size=11, weight=ft.FontWeight.BOLD, color=get_subtext_color(theme_state["box"])),
                        make_period_chip("7D", "7d", 7),
                        make_period_chip("30D", "30d", 30),
                        make_period_chip("90D", "90d", 90),
                        make_period_chip("All Time", "all", None),
                        start_field,
                        end_field,
                        apply_btn,
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True,
                )
            )

        habits_view.controls.append(
            build_shelf(
                "1. Filter Scope & Timeframe",
                "Inspect all activity or isolate a specific habit or category.",
                filter_controls_col,
            )
        )

        # Global Habits Overview Shelf
        if active_heatmap_scope == "global":
            all_habs = get_distinct_habits()
            if all_habs:
                hab_cards = []
                for h_name in all_habs:
                    hs = get_streak_and_stats("habit", h_name)
                    c_target = get_habit_consistency_target(h_name)
                    c_tier = get_consistency_tier_label(c_target)
                    c_rate = hs.get("completion_rate", 0)
                    cur_strk = hs.get("current_streak", 0)
                    total_occ = hs.get("completed_days", 0) + hs.get("missed_days", 0)
                    exceeded_goal = (total_occ >= 3 and c_rate >= c_target)

                    if exceeded_goal:
                        goal_status_badge = ft.Container(
                            padding=ft.Padding(left=9, right=9, top=4, bottom=4),
                            border_radius=6,
                            bgcolor=theme_state["accent"],
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.CHECK_CIRCLE_ROUNDED,
                                        size=13,
                                        color=get_text_color(theme_state["accent"]),
                                    ),
                                    ft.Text(
                                        f"Goal Exceeded ({c_rate:g}% / {c_target}% • {c_tier})",
                                        size=11,
                                        weight=ft.FontWeight.BOLD,
                                        color=get_text_color(theme_state["accent"]),
                                    ),
                                ],
                                spacing=5,
                                tight=True,
                            ),
                        )
                    else:
                        progress_lbl = (
                            f"{total_occ}/3 days logged"
                            if total_occ < 3
                            else f"{c_rate:g}% / {c_target}% ({c_tier})"
                        )
                        goal_status_badge = ft.Container(
                            padding=ft.Padding(left=9, right=9, top=4, bottom=4),
                            border_radius=6,
                            bgcolor=theme_state["box"],
                            border=make_border(1.5, get_border_color(theme_state["box"])),
                            content=ft.Text(
                                progress_lbl,
                                size=11,
                                weight=ft.FontWeight.W_600,
                                color=get_subtext_color(theme_state["box"]),
                            ),
                        )

                    def inspect_this_habit(e, hn=h_name):
                        nonlocal active_heatmap_scope, active_heatmap_identifier
                        active_heatmap_scope = "habit"
                        active_heatmap_identifier = hn
                        scope_dropdown.value = "habit"
                        habit_analytics_state["start"] = None
                        habit_analytics_state["end"] = None
                        habit_analytics_state["period_preset"] = "all"
                        habit_analytics_state["editing_consistency"] = False
                        load_habits_dashboard()

                    hab_cards.append(
                        ft.Container(
                            padding=ft.Padding(left=14, right=12, top=10, bottom=10),
                            bgcolor=theme_state["surface"],
                            border_radius=8,
                            border=make_border(
                                1.5,
                                theme_state["accent"] if exceeded_goal else get_border_color(theme_state["surface"]),
                            ),
                            on_click=inspect_this_habit,
                            content=ft.Row(
                                [
                                    ft.Column(
                                        [
                                            ft.Text(
                                                h_name,
                                                size=14,
                                                weight=ft.FontWeight.BOLD,
                                                color=get_text_color(theme_state["surface"]),
                                            ),
                                            ft.Text(
                                                f"Streak: {cur_strk}  •  Completed: {hs.get('completed_days', 0)}  •  Missed: {hs.get('missed_days', 0)}",
                                                size=11,
                                                color=get_subtext_color(theme_state["surface"]),
                                            ),
                                        ],
                                        spacing=2,
                                        expand=True,
                                    ),
                                    ft.Row(
                                        [
                                            goal_status_badge,
                                            ft.Container(
                                                padding=ft.Padding(left=10, right=10, top=5, bottom=5),
                                                border_radius=6,
                                                bgcolor=theme_state["surface_card"],
                                                border=make_border(1.5, theme_state["accent"]),
                                                content=ft.Text(
                                                    "Inspect →",
                                                    size=11,
                                                    weight=ft.FontWeight.BOLD,
                                                    color=theme_state["accent"],
                                                ),
                                            ),
                                        ],
                                        spacing=8,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                        tight=True,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        )
                    )

                habits_view.controls.append(
                    build_shelf(
                        "Your Habits Overview",
                        "Highlighted cards have exceeded their consistency goal. Click any habit to inspect.",
                        ft.Column(hab_cards, spacing=8, tight=True),
                    )
                )

        # 2. Streak & Saved Consistency Goal Shelf
        stats = get_streak_and_stats(
            active_heatmap_scope,
            active_heatmap_identifier,
            start_override=habit_analytics_state["start"],
            end_override=habit_analytics_state["end"],
        )

        def make_stat_card(label: str, main_val: str, is_accent: bool = False):
            bg_c = theme_state["surface_card"] if is_accent else theme_state["surface"]
            return ft.Container(
                padding=12,
                bgcolor=bg_c,
                border_radius=8,
                expand=True,
                border=make_border(1.5, theme_state["accent"] if is_accent else get_border_color(bg_c)),
                content=ft.Column(
                    [
                        ft.Text(label, size=11, color=get_subtext_color(bg_c)),
                        ft.Text(
                            main_val,
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=theme_state["accent"] if is_accent else get_text_color(bg_c),
                        ),
                    ],
                    spacing=2,
                    tight=True,
                ),
            )

        cur_streak_val = int(stats.get("current_streak", 0))
        comp_rate_val = float(stats.get("completion_rate", 0))
        done_days_val = int(stats.get("completed_days", 0))
        missed_days_val = int(stats.get("missed_days", 0))
        total_due_val = done_days_val + missed_days_val

        stats_row = ft.Row(
            [
                make_stat_card("Current Streak", f"{cur_streak_val}", is_accent=True),
                make_stat_card("Best Streak", f"{stats['longest_streak']}"),
                make_stat_card("Completion Rate", f"{comp_rate_val:g}%"),
                make_stat_card("Completed / Missed", f"{done_days_val} done  •  {missed_days_val} missed"),
            ],
            spacing=10,
        )

        streak_shelf_children = [stats_row]

        hype_msg = get_streak_hype_copy(cur_streak_val)
        if hype_msg:
            streak_shelf_children.append(
                ft.Container(
                    padding=ft.Padding(left=12, right=12, top=9, bottom=9),
                    bgcolor=theme_state["surface_card"],
                    border_radius=8,
                    border=make_border(1.5, theme_state["accent"]),
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.BOLT_ROUNDED, color=theme_state["accent"], size=20),
                            ft.Text(
                                hype_msg,
                                size=12,
                                weight=ft.FontWeight.BOLD,
                                color=theme_state["accent"],
                                expand=True,
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )

        if active_heatmap_scope == "habit" and active_heatmap_identifier:
            cons_target = get_habit_consistency_target(active_heatmap_identifier)
            cons_tier = get_consistency_tier_label(cons_target)
            cons_ratio = min(1.0, max(0.0, comp_rate_val / max(1.0, float(cons_target))))
            cons_achieved = (total_due_val >= 3 and comp_rate_val >= cons_target)
            is_editing_cons = bool(habit_analytics_state.get("editing_consistency", False))

            cons_status_label = (
                f"✓ Consistency Goal Exceeded: {comp_rate_val:g}% / {cons_target}% ({cons_tier})"
                if cons_achieved
                else (
                    f"Saved Consistency Goal: {cons_target}% ({cons_tier})  •  {3 - total_due_val} more scheduled day(s) to unlock status"
                    if total_due_val < 3
                    else f"Saved Consistency Goal: {comp_rate_val:g}% / {cons_target}% ({cons_tier})"
                )
            )

            def toggle_cons_editor(e=None):
                habit_analytics_state["editing_consistency"] = not is_editing_cons
                set_typing(False)
                load_habits_dashboard()

            edit_cons_btn = ft.Container(
                padding=ft.Padding(left=10, right=10, top=5, bottom=5),
                border_radius=6,
                bgcolor=theme_state["surface_card"],
                border=make_border(1.5, theme_state["accent"]),
                on_click=toggle_cons_editor,
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.CLOSE_ROUNDED if is_editing_cons else ft.Icons.EDIT_OUTLINED,
                            size=13,
                            color=theme_state["accent"],
                        ),
                        ft.Text(
                            "Close" if is_editing_cons else "Change Target",
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color=theme_state["accent"],
                        ),
                    ],
                    spacing=4,
                    tight=True,
                ),
            )

            cons_box_children = [
                ft.Row(
                    [
                        ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.CHECK_CIRCLE_ROUNDED if cons_achieved else ft.Icons.FLAG_ROUNDED,
                                    size=17,
                                    color=theme_state["accent"],
                                ),
                                ft.Text(
                                    cons_status_label,
                                    size=12,
                                    weight=ft.FontWeight.BOLD,
                                    color=theme_state["accent"],
                                    expand=True,
                                ),
                            ],
                            spacing=6,
                            expand=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        edit_cons_btn,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.ProgressBar(
                    value=cons_ratio,
                    color=theme_state["accent"],
                    bgcolor=theme_state["box"],
                    height=7,
                    border_radius=4,
                ),
            ]

            if is_editing_cons:
                custom_pct_field = ft.TextField(
                    label="Custom % (50–100)",
                    value=str(cons_target),
                    width=145,
                    dense=True,
                    text_size=12,
                    border_width=1.5,
                    focused_border_width=1.5,
                    border_color=get_border_color(theme_state["surface"]),
                    focused_border_color=theme_state["accent"],
                    on_focus=lambda _: set_typing(True),
                    on_blur=lambda _: set_typing(False),
                )

                def save_custom_cons_pct(val_raw):
                    try:
                        parsed_p = int(round(float(str(val_raw).strip().replace("%", ""))))
                    except ValueError:
                        show_message("Enter a valid percentage between 50 and 100!")
                        return
                    clamped_p = max(50, min(100, parsed_p))
                    set_habit_consistency_target(active_heatmap_identifier, clamped_p)
                    habit_analytics_state["editing_consistency"] = False
                    set_typing(False)
                    tier_name = get_consistency_tier_label(clamped_p)
                    show_message(f"🎯 Saved {clamped_p}% ({tier_name}) consistency goal for '{active_heatmap_identifier}'")
                    load_habits_dashboard()

                custom_pct_field.on_submit = lambda e: save_custom_cons_pct(custom_pct_field.value)

                quick_tier_chips = []
                for p_val, p_tag in [
                    (85, "85% Recommended"),
                    (90, "90% High Focus"),
                    (95, "95% Intense"),
                    (100, "100% Extreme"),
                ]:
                    is_sel_p = (cons_target == p_val)
                    quick_tier_chips.append(
                        ft.Container(
                            padding=ft.Padding(left=9, right=9, top=5, bottom=5),
                            border_radius=6,
                            bgcolor=theme_state["accent"] if is_sel_p else theme_state["box"],
                            border=make_border(
                                1.5,
                                theme_state["accent"] if is_sel_p else get_border_color(theme_state["box"]),
                            ),
                            on_click=lambda _, pv=p_val: save_custom_cons_pct(pv),
                            content=ft.Text(
                                p_tag,
                                size=11,
                                weight=ft.FontWeight.BOLD if is_sel_p else ft.FontWeight.W_500,
                                color=get_text_color(theme_state["accent"])
                                if is_sel_p
                                else get_text_color(theme_state["box"]),
                            ),
                        )
                    )

                cons_box_children.append(
                    ft.Container(
                        padding=10,
                        bgcolor=theme_state["box"],
                        border_radius=8,
                        border=make_border(1.5, theme_state["accent"]),
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        custom_pct_field,
                                        ft.FilledButton(
                                            content=ft.Text(
                                                "Save Target",
                                                size=11,
                                                weight=ft.FontWeight.BOLD,
                                                color=get_text_color(theme_state["accent"]),
                                            ),
                                            bgcolor=theme_state["accent"],
                                            height=38,
                                            on_click=lambda _: save_custom_cons_pct(custom_pct_field.value),
                                        ),
                                        *quick_tier_chips,
                                    ],
                                    spacing=8,
                                    wrap=True,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                            ],
                            spacing=6,
                            tight=True,
                        ),
                    )
                )

            streak_shelf_children.append(
                ft.Container(
                    padding=12,
                    bgcolor=theme_state["surface_card"] if cons_achieved else theme_state["surface"],
                    border_radius=8,
                    border=make_border(
                        1.5,
                        theme_state["accent"] if cons_achieved else get_border_color(theme_state["surface"]),
                    ),
                    content=ft.Column(cons_box_children, spacing=8, tight=True),
                )
            )

        habits_view.controls.append(
            build_shelf(
                "2. Streak & Consistency",
                "Counts only scheduled occurrences up to today (Completed vs. Missed).",
                ft.Column(streak_shelf_children, spacing=10, tight=True),
            )
        )

        # 3. Review Heatmap Shelf
        data = get_unified_heatmap_data(
            active_heatmap_scope,
            active_heatmap_identifier,
            start_override=habit_analytics_state["start"],
            end_override=habit_analytics_state["end"],
        )
        today_str = datetime.now().strftime("%Y-%m-%d")

        if not data:
            habits_view.controls.append(
                build_shelf(
                    "3. Review Heatmap",
                    "Shows scheduled dates for this selection.",
                    ft.Text(
                        "No scheduled dates or completions found yet.",
                        italic=True,
                        color=get_subtext_color(theme_state["box"]),
                        size=13,
                    ),
                )
            )
        else:
            is_daily_mode = (
                True
                if active_heatmap_scope == "global"
                else (is_habit_daily(active_heatmap_identifier) if active_heatmap_scope == "habit" else False)
            )
            heatmap_title = (
                "3. Global Review Heatmap"
                if active_heatmap_scope == "global"
                else f"3. Habit Review Heatmap ({active_heatmap_identifier})"
            )
            heatmap_subtitle = (
                "Anki-style daily grid. Highlights when all tasks due that day are completed."
                if is_daily_mode
                else "Non-daily schedule: solid tiles mark scheduled days, outline tiles mark unscheduled days."
            )
            habits_view.controls.append(
                build_shelf(
                    heatmap_title,
                    heatmap_subtitle,
                    build_anki_heatmap_widget(data, is_daily_mode, today_str),
                )
            )

        # 4. Goals Front-and-Center + High-Contrast Chart & Fullscreen View
        has_unit_chart = False
        if active_heatmap_scope == "habit" and active_heatmap_identifier:
            unit_name, unit_logs = get_habit_unit_logs(
                active_heatmap_identifier,
                start_override=habit_analytics_state["start"],
                end_override=habit_analytics_state["end"],
            )
            if unit_name:
                has_unit_chart = True
                goals_list = evaluate_habit_goals_live(active_heatmap_identifier)

                curr_bucket = habit_analytics_state.get("time_bucket", "daily")
                curr_wk_agg = habit_analytics_state.get("weekly_agg_mode", "avg")
                curr_lookback = habit_analytics_state.get("lookback_days", None)

                pace_info = compute_unit_pace_and_forecast(
                    unit_logs,
                    goals_list=goals_list,
                    time_bucket=curr_bucket,
                    weekly_agg_mode=curr_wk_agg,
                    lookback_days=curr_lookback,
                )

                # --- Prominent Goal Setter & Active Goals Cards ---
                goal_type_dd = ft.Dropdown(
                    label="Goal Type",
                    width=185,
                    border_width=1.5,
                    focused_border_width=1.5,
                    border_color=get_border_color(theme_state["surface"]),
                    focused_border_color=theme_state["accent"],
                    value=habit_analytics_state["goal_type"],
                    options=[
                        ft.dropdown.Option(key="max", text="Max / Peak Value"),
                        ft.dropdown.Option(key="weekly_avg", text="Weekly Average"),
                        ft.dropdown.Option(key="all_time_avg", text="Overall Average"),
                    ],
                )

                def on_gtype_change(e):
                    habit_analytics_state["goal_type"] = goal_type_dd.value or "max"

                goal_type_dd.on_select = on_gtype_change
                goal_type_dd.on_change = on_gtype_change

                target_goal_input = ft.TextField(
                    label=f"Target ({unit_name})",
                    hint_text="e.g. 90",
                    width=135,
                    text_size=12,
                    border_width=1.5,
                    focused_border_width=1.5,
                    border_color=get_border_color(theme_state["surface"]),
                    focused_border_color=theme_state["accent"],
                    on_focus=lambda _: set_typing(True),
                    on_blur=lambda _: set_typing(False),
                )

                cur_deadline_iso = habit_analytics_state["goal_end_date"]
                deadline_btn_lbl = (
                    format_ui_date(cur_deadline_iso, "short_text")
                    if cur_deadline_iso
                    else "Deadline (Optional)"
                )

                goal_cal_box = ft.Container(
                    visible=habit_analytics_state["goal_cal_open"],
                    padding=10,
                    width=300,
                    bgcolor=theme_state["surface_card"],
                    border_radius=8,
                    border=make_border(1.5, theme_state["accent"]),
                )

                if habit_analytics_state["goal_cal_open"]:
                    gb_dt = habit_analytics_state["goal_cal_browse"]
                    yr, mo = gb_dt.year, gb_dt.month
                    cal_g = calendar.Calendar(firstweekday=0)
                    g_weeks = cal_g.monthdatescalendar(yr, mo)

                    def shift_g_cal(delta):
                        nm = habit_analytics_state["goal_cal_browse"].month + delta
                        ny = habit_analytics_state["goal_cal_browse"].year + (nm - 1) // 12
                        nm = (nm - 1) % 12 + 1
                        habit_analytics_state["goal_cal_browse"] = habit_analytics_state["goal_cal_browse"].replace(
                            year=ny, month=nm, day=1
                        )
                        load_habits_dashboard()

                    g_rows = [
                        ft.Row(
                            [
                                ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, icon_size=16, on_click=lambda _: shift_g_cal(-1)),
                                ft.Text(gb_dt.strftime("%B %Y"), size=12, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                                ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_size=16, on_click=lambda _: shift_g_cal(1)),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        )
                    ]
                    for wk in g_weeks:
                        rc = []
                        for d_o in wk:
                            ds = d_o.strftime("%Y-%m-%d")
                            in_m = (d_o.month == mo)
                            is_s = (ds == cur_deadline_iso)

                            def pick_g_date(e, chosen_ds=ds):
                                habit_analytics_state["goal_end_date"] = chosen_ds
                                habit_analytics_state["goal_cal_open"] = False
                                load_habits_dashboard()

                            rc.append(
                                ft.Container(
                                    width=32,
                                    height=28,
                                    border_radius=6,
                                    bgcolor=theme_state["accent"] if is_s else (theme_state["box"] if in_m else theme_state["surface"]),
                                    alignment=ft.Alignment(0, 0),
                                    on_click=pick_g_date,
                                    content=ft.Text(
                                        str(d_o.day),
                                        size=11,
                                        color=get_text_color(theme_state["accent"])
                                        if is_s
                                        else (get_text_color(theme_state["box"]) if in_m else get_subtext_color(theme_state["surface"])),
                                    ),
                                )
                            )
                        g_rows.append(ft.Row(rc, alignment=ft.MainAxisAlignment.CENTER, spacing=4))
                    goal_cal_box.content = ft.Column(g_rows, spacing=4, tight=True)

                def toggle_goal_cal(e=None):
                    habit_analytics_state["goal_cal_open"] = not habit_analytics_state["goal_cal_open"]
                    load_habits_dashboard()

                goal_deadline_btn = ft.Container(
                    padding=ft.Padding(left=12, right=12, top=10, bottom=10),
                    bgcolor=theme_state["surface_card"] if cur_deadline_iso else theme_state["box"],
                    border_radius=8,
                    border=make_border(
                        1.5,
                        theme_state["accent"] if cur_deadline_iso else get_border_color(theme_state["box"]),
                    ),
                    on_click=toggle_goal_cal,
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.CALENDAR_MONTH_ROUNDED, size=16, color=theme_state["accent"]),
                            ft.Text(
                                deadline_btn_lbl,
                                size=12,
                                weight=ft.FontWeight.BOLD if cur_deadline_iso else ft.FontWeight.W_500,
                                color=theme_state["accent"] if cur_deadline_iso else get_subtext_color(theme_state["box"]),
                            ),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                )

                def add_new_goal_click(e):
                    try:
                        t_val = float((target_goal_input.value or "").strip().replace(",", "."))
                    except (ValueError, AttributeError):
                        show_message("Please enter a valid number for your goal!")
                        return

                    today_iso = datetime.now().strftime("%Y-%m-%d")
                    add_habit_goal_db(
                        habit_name=active_heatmap_identifier,
                        goal_type=goal_type_dd.value or "max",
                        target_value=t_val,
                        start_date=today_iso,
                        end_date=habit_analytics_state["goal_end_date"],
                    )
                    habit_analytics_state["goal_end_date"] = None
                    habit_analytics_state["goal_cal_open"] = False
                    set_typing(False)
                    check_and_celebrate_habit_milestones(active_heatmap_identifier)
                    show_message("🎯 Goal set (tracking from today onward)!")
                    load_habits_dashboard()

                add_goal_btn = ft.FilledButton(
                    content=ft.Text("Set Goal", color=get_text_color(theme_state["accent"]), weight=ft.FontWeight.BOLD),
                    icon=ft.Icons.ADD_TASK_ROUNDED,
                    icon_color=get_text_color(theme_state["accent"]),
                    on_click=add_new_goal_click,
                    bgcolor=theme_state["accent"],
                    height=40,
                )

                goals_cards_col = ft.Column(spacing=6, tight=True)
                type_labels = {
                    "max": "Peak Goal",
                    "weekly_avg": "Weekly Avg Goal",
                    "all_time_avg": "Overall Avg Goal",
                }
                for g in goals_list:
                    gid = g["id"]
                    is_ach = g["achieved"]
                    g_type = g.get("goal_type", "max")
                    tv = float(g["target_value"])
                    s_lbl = format_ui_date(g["start_date"], "short_text")
                    e_lbl = format_ui_date(g["end_date"], "short_text") if g["end_date"] else "Open"
                    detail_str = g.get("status_detail", "")

                    if is_ach:
                        if g_type == "max":
                            status_text = f"✓ Achieved {format_ui_date(g['achieved_date'], 'short_text')}"
                        else:
                            status_text = f"✓ Active ({detail_str}) • From {s_lbl}"
                    else:
                        status_text = f"{detail_str}  •  Window: {s_lbl} → {e_lbl}"

                    def remove_goal_click(e, target_gid=gid):
                        delete_habit_goal_db(target_gid)
                        load_habits_dashboard()

                    goals_cards_col.controls.append(
                        ft.Container(
                            padding=ft.Padding(left=12, right=8, top=6, bottom=6),
                            bgcolor=theme_state["surface_card"] if is_ach else theme_state["box"],
                            border_radius=8,
                            border=make_border(1.5, theme_state["accent"] if is_ach else get_border_color(theme_state["box"])),
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.EMOJI_EVENTS_ROUNDED if is_ach else ft.Icons.FLAG_ROUNDED,
                                        color=theme_state["accent"] if is_ach else get_subtext_color(theme_state["box"]),
                                        size=16,
                                    ),
                                    ft.Text(
                                        f"{type_labels.get(g_type, 'Goal')}: {tv:g} {unit_name}",
                                        size=12,
                                        weight=ft.FontWeight.BOLD,
                                        color=theme_state["accent"] if is_ach else get_text_color(theme_state["box"]),
                                    ),
                                    ft.Text(f"({status_text})", size=11, color=get_subtext_color(theme_state["box"])),
                                    ft.Container(expand=True),
                                    ft.IconButton(
                                        icon=ft.Icons.CLOSE_ROUNDED,
                                        icon_size=14,
                                        tooltip="Remove Goal",
                                        on_click=remove_goal_click,
                                    ),
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        )
                    )

                goals_top_card = ft.Container(
                    padding=12,
                    bgcolor=theme_state["surface"],
                    border_radius=8,
                    border=make_border(1.5, theme_state["accent"]),
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.FLAG_ROUNDED, size=16, color=theme_state["accent"]),
                                    ft.Text(
                                        f"Target Goals ({unit_name}) — Tracked From Creation Date Onward",
                                        size=13,
                                        weight=ft.FontWeight.BOLD,
                                        color=theme_state["accent"],
                                    ),
                                ],
                                spacing=6,
                            ),
                            ft.Row(
                                [goal_type_dd, target_goal_input, goal_deadline_btn, add_goal_btn],
                                spacing=10,
                                wrap=True,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            goal_cal_box,
                            goals_cards_col if goals_list else ft.Container(),
                        ],
                        spacing=8,
                        tight=True,
                    ),
                )

                if not unit_logs:
                    habits_view.controls.append(
                        build_shelf(
                            f"4. Goals & Progress Chart ({unit_name})",
                            "Set target goals and track your progression curve over time.",
                            ft.Column(
                                [
                                    goals_top_card,
                                    ft.Text(
                                        f"No {unit_name} values logged in this period yet. Check off '{active_heatmap_identifier}' on Page 1 to log units!",
                                        italic=True,
                                        color=get_subtext_color(theme_state["box"]),
                                        size=12,
                                    ),
                                ],
                                spacing=10,
                                tight=True,
                            ),
                        )
                    )
                else:
                    inline_chart_bundle = _build_unit_chart_bundle(
                        unit_name,
                        unit_logs,
                        goals_list,
                        pace_info,
                        is_fullscreen=False,
                    )

                    habits_view.controls.append(
                        build_shelf(
                            f"4. Goals & Progress Chart ({unit_name})",
                            "Hover over any point, bar, or Avg Line node to inspect values. Click Fullscreen to expand.",
                            ft.Column(
                                [
                                    goals_top_card,
                                    inline_chart_bundle,
                                ],
                                spacing=10,
                                tight=True,
                            ),
                        )
                    )

        # Weekly Output Trend Shelf (Shown when not already covered by the Unit Chart)
        if not has_unit_chart:
            trends = get_habit_trend_data(active_heatmap_scope, active_heatmap_identifier)
            if trends:
                max_val = max(trends.values()) if trends.values() else 1
                if max_val <= 0:
                    max_val = 1
                trend_col = ft.Column(spacing=6, tight=True)
                for wk, val in list(trends.items())[-8:]:
                    bar_width = max(10, int((val / max_val) * 280))
                    trend_col.controls.append(
                        ft.Row(
                            [
                                ft.Container(
                                    width=75,
                                    content=ft.Text(wk, size=11, color=get_subtext_color(theme_state["box"])),
                                ),
                                ft.Container(
                                    width=bar_width,
                                    height=14,
                                    bgcolor=theme_state["accent"],
                                    border_radius=3,
                                ),
                                ft.Text(f"{val:g}", size=11, weight=ft.FontWeight.BOLD),
                            ],
                            spacing=8,
                        )
                    )
                habits_view.controls.append(
                    build_shelf(
                        "Weekly Output Trend",
                        "Total completions or logged volume per ISO week.",
                        trend_col,
                    )
                )

        page.update()
# =============================================================================
# >>> SECTION A7 END: VIEW 4 - HABITS & DATA DASHBOARD <<<
# =============================================================================

# =============================================================================
# >>> SECTION A8 START: VIEW 5 - ALL ACTIVE TASKS (WITH BATCH SELECT & SEARCH) <<<
# =============================================================================
    batch_selection_mode = False
    selected_batch_ids = set()
    search_query = ""
    selected_filter_category = "All Categories"

    batch_confirm_banner = ft.Container(
        visible=False,
        padding=12,
        bgcolor="#2a1212",
        border_radius=8,
        border=make_border(1.5, ft.Colors.RED_400),
    )

    def load_all_tasks_view():
        all_tasks_view.controls.clear()

        def toggle_batch_mode(e):
            nonlocal batch_selection_mode
            batch_selection_mode = not batch_selection_mode
            selected_batch_ids.clear()
            batch_confirm_banner.visible = False
            load_all_tasks_view()

        def execute_batch_delete(e):
            count = len(selected_batch_ids)
            batch_remove_tasks_db(list(selected_batch_ids))
            selected_batch_ids.clear()
            batch_confirm_banner.visible = False
            show_message(f"🗑️ Deleted {count} task(s) securely.")
            load_all_tasks_view()

        def open_batch_confirm(e):
            if not selected_batch_ids:
                show_message("Select at least one task first!")
                return
            batch_confirm_banner.content = ft.Row(
                [
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.RED_400, size=20),
                    ft.Text(
                        f"Are you sure you want to permanently delete {len(selected_batch_ids)} selected task(s)?",
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.RED_200,
                        expand=True,
                    ),
                    ft.FilledButton(
                        content=ft.Text("Yes, Delete All", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                        bgcolor=ft.Colors.RED_700,
                        on_click=execute_batch_delete,
                    ),
                    ft.TextButton(
                        content=ft.Text("Cancel", color=ft.Colors.GREY_300),
                        on_click=lambda _: setattr(batch_confirm_banner, "visible", False) or page.update(),
                    ),
                ],
                spacing=10,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            batch_confirm_banner.visible = True
            page.update()

        top_row_controls = [ft.Text("All Database Tasks", size=18, weight=ft.FontWeight.BOLD, color=theme_state["accent"])]

        batch_toggle_btn = ft.OutlinedButton(
            content=ft.Text(
                "Exit Select Mode" if batch_selection_mode else "Select / Batch Delete",
                size=12,
                color=ft.Colors.RED_400 if batch_selection_mode else theme_state["accent"],
            ),
            icon=ft.Icons.CLOSE_ROUNDED if batch_selection_mode else ft.Icons.DELETE_SWEEP_ROUNDED,
            icon_color=ft.Colors.RED_400 if batch_selection_mode else theme_state["accent"],
            on_click=toggle_batch_mode,
        )

        right_header_controls = [batch_toggle_btn]
        if batch_selection_mode and selected_batch_ids:
            confirm_btn = ft.FilledButton(
                content=ft.Text(
                    f"Confirm Delete ({len(selected_batch_ids)})",
                    color=ft.Colors.WHITE,
                    weight=ft.FontWeight.BOLD,
                ),
                icon=ft.Icons.DELETE_FOREVER_ROUNDED,
                bgcolor=ft.Colors.RED_900,
                on_click=open_batch_confirm,
            )
            right_header_controls.insert(0, confirm_btn)

        all_tasks_view.controls.append(
            ft.Row(
                top_row_controls + [ft.Row(right_header_controls, spacing=8)],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
        )
        all_tasks_view.controls.append(batch_confirm_banner)

        def on_search_change(e):
            nonlocal search_query
            search_query = (e.control.value or "").strip().lower()
            render_filtered_task_list()

        def on_cat_filter_change(e):
            nonlocal selected_filter_category
            selected_filter_category = cat_filter_dd.value or "All Categories"
            render_filtered_task_list()

        cats = get_distinct_categories()
        cat_filter_options = [ft.dropdown.Option(key="All Categories", text="All Categories")] + [
            ft.dropdown.Option(key=c, text=c) for c in cats
        ]

        search_field = ft.TextField(
            hint_text="Search tasks or notes...",
            prefix_icon=ft.Icons.SEARCH,
            expand=True,
            text_size=12,
            value=search_query,
            on_change=on_search_change,
            on_focus=lambda _: set_typing(True),
            on_blur=lambda _: set_typing(False),
        )

        cat_filter_dd = ft.Dropdown(
            value=selected_filter_category,
            options=cat_filter_options,
            width=200,
            text_size=12,
        )
        cat_filter_dd.on_change = on_cat_filter_change
        cat_filter_dd.on_select = on_cat_filter_change

        filter_bar = ft.Row([search_field, cat_filter_dd], spacing=10)
        all_tasks_view.controls.append(filter_bar)
        all_tasks_view.controls.append(ft.Divider(color=get_border_color(theme_state["bg"]), height=10))

        tasks_list_col = ft.Column(spacing=8)
        all_tasks_view.controls.append(tasks_list_col)

        def render_filtered_task_list():
            tasks_list_col.controls.clear()
            tasks = fetch_all_tasks()

            filtered_tasks = []
            for t in tasks:
                t_name = (t[1] or "").lower()
                t_cat = t[2] or "General"
                t_note = (t[9] or "").lower() if len(t) > 9 else ""

                if search_query and (search_query not in t_name and search_query not in t_note):
                    continue
                if selected_filter_category != "All Categories" and t_cat != selected_filter_category:
                    continue
                filtered_tasks.append(t)

            if not filtered_tasks:
                tasks_list_col.controls.append(
                    ft.Text(
                        "No tasks match your search or filter.",
                        italic=True,
                        color=get_subtext_color(theme_state["bg"]),
                        size=13,
                    )
                )
                page.update()
                return

            for t in filtered_tasks:
                task_id, name, category, time_frame, target_date, recurrence = t[:6]
                end_date = t[7] if len(t) > 7 else None
                note = t[9] if len(t) > 9 else None
                unit = t[10] if len(t) > 10 else None
                custom_days = t[11] if len(t) > 11 else None
                custom_months = t[12] if len(t) > 12 else None

                is_selected = task_id in selected_batch_ids
                is_expanded = (expanded_edit_task_id == task_id)

                def toggle_select_item(e, tid=task_id):
                    if tid in selected_batch_ids:
                        selected_batch_ids.remove(tid)
                    else:
                        selected_batch_ids.add(tid)
                    batch_confirm_banner.visible = False
                    load_all_tasks_view()

                if time_frame == "custom":
                    status_label = "Backlog"
                elif target_date:
                    status_label = f"Start: {format_ui_date(target_date, 'short_text')}"
                else:
                    status_label = "No Date"

                if end_date:
                    status_label += f" • Ends: {format_ui_date(end_date, 'short_text')}"

                rec_label = recurrence or "once"
                if recurrence == "weekly" and custom_days:
                    rec_label = f"weekly ({custom_days})"
                elif recurrence in ["monthly", "yearly"]:
                    extra = []
                    if custom_months:
                        extra.append(f"mo:{custom_months}")
                    if extra:
                        rec_label = f"{recurrence} ({' | '.join(extra)})"

                unit_label = f" • Unit: {unit}" if (unit and unit != "None") else ""
                note_label = f" • 📝 {note}" if note else ""
                desc_text = f"{category or 'General'} • {rec_label} • {status_label}{unit_label}{note_label}"

                edit_btn = ft.Container(
                    content=ft.Icon(
                        ft.Icons.EXPAND_LESS_ROUNDED if is_expanded else ft.Icons.MORE_VERT_ROUNDED,
                        size=20,
                        color=theme_state["accent"] if is_expanded else get_subtext_color(theme_state["box"]),
                    ),
                    padding=6,
                    border_radius=6,
                    bgcolor=theme_state["surface_card"] if is_expanded else theme_state["surface"],
                    on_click=lambda _, tid=task_id: toggle_inline_edit(tid),
                    tooltip="Collapse Edit" if is_expanded else "Edit Task",
                )

                row_controls = [
                    ft.Column(
                        [
                            ft.Text(
                                name,
                                weight=ft.FontWeight.BOLD,
                                size=14,
                                color=ft.Colors.RED_300 if (batch_selection_mode and is_selected) else get_text_color(theme_state["surface_card"]),
                            ),
                            ft.Text(desc_text, size=11, color=get_subtext_color(theme_state["surface_card"])),
                        ],
                        expand=True,
                        spacing=2,
                    )
                ]

                if batch_selection_mode:
                    row_controls.append(
                        ft.Checkbox(
                            value=is_selected,
                            on_change=lambda _, tid=task_id: toggle_select_item(None, tid),
                            fill_color={
                                ft.ControlState.SELECTED: theme_state["accent"],
                                ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT,
                            },
                        )
                    )
                else:
                    row_controls.append(edit_btn)

                card_children = [
                    ft.Row(row_controls, alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER)
                ]

                if is_expanded:
                    card_children.append(build_inline_edit_drawer(task_id))

                card_bg = (
                    theme_state["surface_card"]
                    if is_expanded
                    else ("#2a1616" if (batch_selection_mode and is_selected) else theme_state["box"])
                )

                tasks_list_col.controls.append(
                    ft.Container(
                        on_click=(lambda _, tid=task_id: toggle_select_item(None, tid)) if batch_selection_mode else None,
                        content=ft.Column(card_children, spacing=8),
                        padding=12 if is_expanded else 10,
                        bgcolor=card_bg,
                        border_radius=8,
                        border=make_border(
                            1.5 if (is_expanded or (batch_selection_mode and is_selected)) else 1,
                            theme_state["accent"] if is_expanded else (ft.Colors.RED_400 if (batch_selection_mode and is_selected) else get_border_color(theme_state["box"])),
                        ),
                    )
                )
            page.update()

        render_filtered_task_list()
        page.update()
# =============================================================================
# >>> SECTION A8 END: VIEW 5 - ALL ACTIVE TASKS <<<
# =============================================================================

# =============================================================================
# >>> SECTION A9 START: UNIFIED NOTIFICATIONS, KEYBOARD NAV & APP ENTRY <<<
# =============================================================================
    import sys

    # --- Unified Cross-Platform Notification Engine (PC + Mobile) ---
    try:
        import flet_notifications as ftn
        _HAS_FTN = True
    except Exception:
        ftn = None
        _HAS_FTN = False

    def _on_notification_tap(e):
        payload_date = getattr(e, "payload", None)
        if payload_date:
            try:
                target_dt = datetime.strptime(payload_date, "%Y-%m-%d")
                if current_view_index != 0:
                    switch_view(0)
                jump_to_specific_day(target_dt)
            except Exception:
                pass

    _ftn_service = None
    if _HAS_FTN:
        try:
            _ftn_service = ftn.Notifications(on_tap=_on_notification_tap)
            if hasattr(page, "services") and _ftn_service not in page.services:
                page.services.append(_ftn_service)
        except Exception:
            _ftn_service = None

    fired_alert_keys = set()
    _last_os_schedule_sig = None

    def _extract_days_before(offset_code: str) -> int:
        if not offset_code:
            return 0
        if offset_code.startswith("-") and offset_code.endswith("d") and offset_code[1:-1].isdigit():
            return int(offset_code[1:-1])
        if offset_code == "-1w":
            return 7
        return 0

    def _collect_upcoming_alerts(now_dt: datetime, horizon_days: int = 14) -> list:
        """Build all pending (uncompleted) alert instances over the next `horizon_days`."""
        upcoming = []
        for days_ahead in range(horizon_days + 1):
            occ_dt = now_dt + timedelta(days=days_ahead)
            occ_str = occ_dt.strftime("%Y-%m-%d")
            due_tasks = fetch_tasks_for_date(occ_str)
            if not due_tasks:
                continue
            comp_map = get_completions_for_date(occ_str)

            for t in due_tasks:
                tid = t[0]
                if tid in comp_map:
                    continue  # Skip already completed occurrences
                t_rem = t[13] if len(t) > 13 else None
                if not t_rem:
                    continue

                tname = t[1]
                tcat = t[2] or "General"
                tnote = t[9] if len(t) > 9 else None

                for a_idx, raw_entry in enumerate(t_rem.split(";;")):
                    parts = raw_entry.strip().split("|")
                    base_t = parts[0]
                    offset_code = parts[1] if len(parts) > 1 else ""
                    days_before = _extract_days_before(offset_code)

                    fire_date = occ_dt - timedelta(days=days_before)
                    try:
                        hh, mm = map(int, base_t.split(":"))
                        fire_dt = datetime(fire_date.year, fire_date.month, fire_date.day, hh, mm, 0)
                    except Exception:
                        continue

                    if days_before == 0:
                        n_title = f"🔔 {tname}"
                    elif days_before == 1:
                        n_title = f"🔔 {tname} (Tomorrow)"
                    else:
                        n_title = f"🔔 {tname} (In {days_before} days)"

                    n_body = f"{tcat} • {occ_dt.strftime('%a, %d %b')}"
                    if tnote:
                        n_body += f" • 📝 {tnote}"

                    notif_id = ((tid * 100000) + (occ_dt.timetuple().tm_yday * 10) + a_idx) % 2000000000 + 1
                    upcoming.append(
                        {
                            "id": notif_id,
                            "tid": tid,
                            "occ_str": occ_str,
                            "a_idx": a_idx,
                            "fire_dt": fire_dt,
                            "title": n_title,
                            "body": n_body,
                        }
                    )
        return upcoming

    def _send_desktop_fallback_toast(title: str, body: str):
        system_name = platform.system()
        safe_title = title.replace('"', "'").replace("\n", " ")
        safe_body = body.replace('"', "'").replace("\n", " — ")
        try:
            if system_name == "Windows":
                ps_script = (
                    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
                    "$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
                    "$textNodes = $template.GetElementsByTagName('text');"
                    f"$textNodes.Item(0).AppendChild($template.CreateTextNode(\"{safe_title}\")) > $null;"
                    f"$textNodes.Item(1).AppendChild($template.CreateTextNode(\"{safe_body}\")) > $null;"
                    "$audio = $template.CreateElement('audio');"
                    "$audio.SetAttribute('silent', 'true');"
                    "$template.DocumentElement.AppendChild($audio) > $null;"
                    "$toast = [Windows.UI.Notifications.ToastNotification]::new($template);"
                    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Habit & Task Tracker').Show($toast);"
                )
                no_win = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                    creationflags=no_win,
                    capture_output=True,
                    timeout=5,
                )
            elif system_name == "Darwin":
                subprocess.run(
                    ["osascript", "-e", f'display notification "{safe_body}" with title "{safe_title}"'],
                    capture_output=True,
                    timeout=5,
                )
            elif system_name == "Linux":
                subprocess.run(
                    ["notify-send", "-a", "Habit & Task Tracker", safe_title, safe_body],
                    capture_output=True,
                    timeout=5,
                )
        except Exception:
            pass

    async def dispatch_immediate_notification(title: str, body: str, payload: str = None, notif_id: int = 1):
        play_notification_sound()
        try:
            show_message(f"{title} — {body}")
        except Exception:
            pass

        if _ftn_service is not None:
            try:
                await _ftn_service.show(id=notif_id, title=title, body=body, payload=payload)
                return
            except Exception:
                pass
        await asyncio.to_thread(_send_desktop_fallback_toast, title, body)

    async def sync_os_scheduled_notifications(now_dt: datetime):
        """Sync future alerts with native OS scheduler (Android/iOS/macOS/Windows/Linux)."""
        global _last_os_schedule_sig
        if _ftn_service is None:
            return
        try:
            upcoming = _collect_upcoming_alerts(now_dt, horizon_days=14)
            future_items = [item for item in upcoming if item["fire_dt"] > now_dt + timedelta(seconds=15)]
            sig = tuple((x["id"], x["fire_dt"].strftime("%Y-%m-%d %H:%M"), x["title"], x["body"]) for x in future_items)
            if sig == _last_os_schedule_sig:
                return
            _last_os_schedule_sig = sig

            await _ftn_service.cancel_all()
            for item in future_items[:60]:  # Stay well within iOS 64-notification OS limit
                await _ftn_service.schedule(
                    item["id"],
                    when=item["fire_dt"],
                    title=item["title"],
                    body=item["body"],
                    payload=item["occ_str"],
                )
        except Exception:
            pass

    async def unified_notification_loop():
        # Request OS notification permission once on startup (needed on Android 13+, iOS, macOS)
        if _ftn_service is not None:
            try:
                await _ftn_service.request_permissions()
            except Exception:
                pass

        while True:
            try:
                now = datetime.now()
                cur_key = now.strftime("%Y-%m-%d %H:%M")

                # 1. Keep native OS scheduled alarms (mobile lock-screen + desktop) in sync
                await sync_os_scheduled_notifications(now)

                # 2. Check for any alert firing right now (live desktop toast / in-app banner)
                for item in _collect_upcoming_alerts(now, horizon_days=14):
                    if item["fire_dt"].strftime("%Y-%m-%d %H:%M") != cur_key:
                        continue
                    dedup_key = (item["tid"], item["occ_str"], item["a_idx"], cur_key)
                    if dedup_key in fired_alert_keys:
                        continue
                    fired_alert_keys.add(dedup_key)
                    await dispatch_immediate_notification(
                        title=item["title"],
                        body=item["body"],
                        payload=item["occ_str"],
                        notif_id=item["id"],
                    )
            except Exception:
                pass

            await asyncio.sleep(20)

    page.run_task(unified_notification_loop)

    # --- Keyboard Shortcuts & Window Controls ---
    def on_keyboard(e: ft.KeyboardEvent):
        nonlocal selected_task_idx, inline_unit_task_id
        if e.key == "Escape":
            if inline_unit_task_id is not None:
                inline_unit_task_id = None
                set_typing(False)
                refresh_schedule_view()
                return
            if unit_popup_banner.visible:
                close_unit_popup()
                return
            if getattr(settings_dialog, "open", False):
                close_settings_modal()
                return
        if is_typing:
            return
        if e.key == "1":
            switch_view(0)
        elif e.key == "2":
            switch_view(1)
        elif e.key == "3":
            switch_view(2)
        elif e.key == "4":
            switch_view(3)
        elif e.key == "5":
            switch_view(4)
        elif current_view_index == 0:
            if e.key == "Arrow Left":
                shift_date(-1)
            elif e.key == "Arrow Right":
                shift_date(1)
            elif e.key in ["t", "T"]:
                snap_to_today()
            elif e.key in ["d", "D"]:
                set_mode("day")
            elif e.key in ["w", "W"]:
                set_mode("week")
            elif e.key in ["m", "M"]:
                set_mode("month")
            elif current_view_mode == "day" and current_day_tasks:
                if e.key == "Arrow Down":
                    selected_task_idx = (selected_task_idx + 1) % len(current_day_tasks)
                    refresh_schedule_view()
                elif e.key == "Arrow Up":
                    selected_task_idx = (selected_task_idx - 1) % len(current_day_tasks)
                    refresh_schedule_view()
                elif e.key in ["Enter", " "] and selected_task_idx >= 0:
                    target_date_str = current_selected_date.strftime("%Y-%m-%d")
                    t = current_day_tasks[selected_task_idx]
                    tid, tname, _, _, _, trec = t[:6]
                    tunit = t[10] if len(t) > 10 else None
                    comp_map = get_completions_for_date(target_date_str)
                    if tid not in comp_map:
                        trigger_task_completion(tid, tname, target_date_str, tunit, trec, None)
                    else:
                        remove_completion_db(tid, target_date_str)
                        unit_popup_banner.visible = False
                        show_message(f"↩ {tname}")
                        refresh_schedule_view()

    page.on_keyboard_event = on_keyboard

    # Settings gear button
    settings_gear_btn = ft.IconButton(
        icon=ft.Icons.SETTINGS_ROUNDED,
        icon_size=20,
        icon_color=theme_state["accent"],
        tooltip="Settings & Color Studio",
        on_click=open_settings_modal,
    )

    sub_c = get_subtext_color(theme_state["bg"])

    def make_clean_win_btn(icon_data, on_click, is_close=False, tip=None):
        return ft.IconButton(
            icon=icon_data,
            icon_size=15,
            style=ft.ButtonStyle(
                color={
                    ft.ControlState.HOVERED: "#FFFFFF" if is_close else theme_state["accent"],
                    ft.ControlState.DEFAULT: sub_c,
                },
                bgcolor={
                    ft.ControlState.HOVERED: "#E11D48" if is_close else theme_state["surface_card"],
                    ft.ControlState.PRESSED: "#BE123C" if is_close else theme_state["box"],
                    ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT,
                },
                shape=ft.RoundedRectangleBorder(radius=4),
                padding=ft.Padding(8, 6, 8, 6),
            ),
            on_click=on_click,
            tooltip=tip,
        )

    # Window Action Handlers
    def win_minimize(e):
        try:
            page.window.minimized = True
            page.update()
        except Exception:
            pass

    max_win_btn = make_clean_win_btn(ft.Icons.CROP_SQUARE_ROUNDED, None, tip="Maximize")

    def win_maximize(e):
        try:
            is_max = getattr(page.window, "maximized", False)
            page.window.maximized = not is_max
            max_win_btn.icon = (
                ft.Icons.FILTER_NONE_ROUNDED if page.window.maximized else ft.Icons.CROP_SQUARE_ROUNDED
            )
            max_win_btn.tooltip = "Restore" if page.window.maximized else "Maximize"
            page.update()
        except Exception:
            pass

    max_win_btn.on_click = win_maximize

    def win_close(e):
        try:
            page.window.close()
        except Exception:
            pass
        sys.exit(0)

    window_controls_cluster = ft.Row(
        [
            settings_gear_btn,
            ft.Container(width=4),
            make_clean_win_btn(ft.Icons.REMOVE_ROUNDED, win_minimize, tip="Minimize"),
            max_win_btn,
            make_clean_win_btn(ft.Icons.CLOSE_ROUNDED, win_close, is_close=True, tip="Close"),
        ],
        spacing=2,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        tight=True,
    )

    # Top Header Bar: Stack centers the 5 navigation icons mathematically while keeping window buttons on the right
    top_header_bar = ft.Container(
        padding=ft.Padding(left=12, right=10, top=10, bottom=6),
        height=56,
        content=ft.Stack(
            [
                ft.WindowDragArea(
                    left=0,
                    right=0,
                    top=0,
                    bottom=0,
                    content=ft.Container(expand=True),
                ),
                ft.Container(
                    left=0,
                    right=0,
                    top=0,
                    bottom=0,
                    alignment=ft.Alignment(0, 0),
                    content=top_nav_row,
                ),
                ft.Container(
                    right=0,
                    top=0,
                    bottom=0,
                    alignment=ft.Alignment(1, 0),
                    content=window_controls_cluster,
                ),
            ],
        ),
    )

    page.padding = 0
    switch_view(0)

    page.add(
        top_header_bar,
        ft.Divider(color=get_border_color(theme_state["bg"]), height=1),
        ft.Container(content=content_area, padding=ft.Padding(20, 10, 20, 20), expand=True),
    )


ft.run(main)
# =============================================================================
# >>> SECTION A9 END: UNIFIED NOTIFICATIONS, KEYBOARD NAV & APP ENTRY <<<
# =============================================================================
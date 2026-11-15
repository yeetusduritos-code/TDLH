#app.py
# =============================================================================
# >>> SECTION A1 START: IMPORTS & DYNAMIC THEME STATE SETUP <<<
# =============================================================================
import flet as ft
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
# >>> SECTION A2 START: SHARED UI HELPERS & SVG CHART GENERATOR <<<
# =============================================================================
    def build_shelf(title: str, subtitle: str, body_control: ft.Control):
        t_col = theme_state["accent"]
        sub_col = get_subtext_color(theme_state["box"])
        header_col = ft.Column(
            [
                ft.Text(title, size=15, weight=ft.FontWeight.BOLD, color=t_col),
                ft.Text(subtitle, size=11, color=sub_col),
            ],
            spacing=2,
        )
        return ft.Container(
            padding=16,
            bgcolor=theme_state["box"],
            border_radius=10,
            border=make_border(1, get_border_color(theme_state["box"])),
            content=ft.Column(
                [header_col, ft.Divider(color=get_border_color(theme_state["box"]), height=10), body_control],
                spacing=10,
            ),
        )

    def build_area_line_chart_image(
        unit_name: str,
        unit_logs: list,
        target_goal: float = None,
        is_average_goal: int = 0,
        chart_style: str = "line",
        avg_mode: str = "running",
        time_bucket: str = "daily",
        weekly_agg_mode: str = "avg",
        goals_list: list = None,
    ) -> ft.Image:
        import base64

        iso_week_groups = {}
        for d_str, val in unit_logs:
            try:
                dt = datetime.strptime(d_str, "%Y-%m-%d")
                iso_yr, iso_wk, _ = dt.isocalendar()
                wk_key = f"{iso_yr}-W{iso_wk:02d}"
            except Exception:
                wk_key = d_str
            iso_week_groups.setdefault(wk_key, []).append(float(val))

        if time_bucket == "weekly":
            processed_logs = []
            for wk_key in sorted(iso_week_groups.keys()):
                w_vals = iso_week_groups[wk_key]
                agg_v = sum(w_vals) if weekly_agg_mode == "sum" else (sum(w_vals) / len(w_vals))
                short_wk = wk_key.split("-")[1] if "-" in wk_key else wk_key
                processed_logs.append((short_wk, agg_v, wk_key))
        else:
            processed_logs = []
            for d_str, val in unit_logs:
                try:
                    dt = datetime.strptime(d_str, "%Y-%m-%d")
                    iso_yr, iso_wk, _ = dt.isocalendar()
                    wk_key = f"{iso_yr}-W{iso_wk:02d}"
                except Exception:
                    wk_key = d_str
                processed_logs.append((d_str, float(val), wk_key))

        if not processed_logs:
            processed_logs = [("2026-01-01", 0.0, "2026-W01")]

        n_pts = len(processed_logs)
        width = 680
        height = 250
        pad_l, pad_r, pad_t, pad_b = 48, 112, 28, 40
        plot_w = width - pad_l - pad_r
        plot_h = height - pad_t - pad_b

        dates = [x[0] for x in processed_logs]
        vals = [float(x[1]) for x in processed_logs]
        wk_keys = [x[2] for x in processed_logs]

        running_avgs = []
        weekly_avgs = []
        curr_sum = 0.0
        for idx, (v, wk_k) in enumerate(zip(vals, wk_keys)):
            curr_sum += v
            running_avgs.append(curr_sum / (idx + 1))
            if time_bucket == "weekly":
                w_slice = vals[max(0, idx - 3) : idx + 1]
                weekly_avgs.append(sum(w_slice) / len(w_slice))
            else:
                w_sessions = iso_week_groups.get(wk_k, [v])
                weekly_avgs.append(sum(w_sessions) / len(w_sessions))

        all_goal_vals = [g["target_value"] for g in (goals_list or []) if g.get("target_value") is not None]
        if target_goal is not None:
            all_goal_vals.append(float(target_goal))

        max_v = max(vals + all_goal_vals + [1.0]) * 1.15
        min_v = 0.0

        def val_to_y(v: float) -> float:
            if max_v <= min_v:
                return pad_t + plot_h / 2
            return pad_t + plot_h - ((v - min_v) / (max_v - min_v)) * plot_h

        def idx_to_x(i: int) -> float:
            if n_pts <= 1:
                return pad_l + plot_w / 2
            if chart_style == "pillars":
                slot_w = plot_w / n_pts
                return pad_l + slot_w * (i + 0.5)
            return pad_l + (i / (n_pts - 1)) * plot_w

        accent_hex = theme_state["accent"]
        bg_card_hex = theme_state["surface_card"]
        bg_base_hex = theme_state["bg"]

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            f'<rect width="100%" height="100%" fill="{bg_base_hex}" rx="8"/>',
        ]

        # 1. Background Grid & ISO Week Separators
        for step in range(5):
            gv = min_v + (max_v - min_v) * (step / 4.0)
            gy = val_to_y(gv)
            svg_parts.append(
                f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" stroke="#183e44" stroke-width="1"/>'
            )
            gv_str = f"{gv:.2f}".rstrip("0").rstrip(".")
            svg_parts.append(
                f'<text x="{pad_l - 8}" y="{gy + 4:.1f}" fill="#789ea3" font-size="10" font-family="sans-serif" text-anchor="end">{gv_str}</text>'
            )

        if time_bucket == "daily" and n_pts > 1:
            prev_wk = None
            for i, wk_k in enumerate(wk_keys):
                if wk_k != prev_wk:
                    if prev_wk is not None:
                        sep_x = idx_to_x(i) - ((idx_to_x(1) - idx_to_x(0)) / 2)
                        svg_parts.append(
                            f'<line x1="{sep_x:.1f}" y1="{pad_t}" x2="{sep_x:.1f}" y2="{height - pad_b}" stroke="#1f4b52" stroke-width="1" stroke-dasharray="3,3"/>'
                        )
                    prev_wk = wk_k

        # 2. Goal Benchmark Lines
        if goals_list:
            placed_goal_ys = []
            for g in goals_list:
                gv = float(g["target_value"])
                gy = val_to_y(gv)
                is_ach = g.get("achieved", False)
                gx1, gx2 = pad_l, width - pad_r

                if is_ach:
                    stroke_col = "#64748B"
                    bg_col = "#161E29"
                    txt_col = "#94A3B8"
                    dash = "2,4"
                    width_sw = "1.2"
                else:
                    stroke_col = "#C084FC"
                    bg_col = "#241634"
                    txt_col = "#F3E8FF"
                    dash = "6,4"
                    width_sw = "1.6"

                svg_parts.append(
                    f'<line x1="{gx1:.1f}" y1="{gy:.1f}" x2="{gx2:.1f}" y2="{gy:.1f}" stroke="{stroke_col}" stroke-width="{width_sw}" stroke-dasharray="{dash}" stroke-opacity="0.85"/>'
                )

                mode_short = "Max" if g["goal_type"] == "max" else ("WkAvg" if g["goal_type"] == "weekly_avg" else "Avg")
                prefix = "✓ " if is_ach else "🎯 "
                gv_str = f"{gv:.2f}".rstrip("0").rstrip(".")
                lbl_text = f"{prefix}{mode_short}: {gv_str}"
                badge_w = max(68, len(lbl_text) * 5.8 + 10)

                by = max(pad_t + 10, min(height - pad_b - 10, gy - 9))
                for py_prev in placed_goal_ys:
                    if abs(by - py_prev) < 18:
                        by = py_prev + 18
                placed_goal_ys.append(by)

                svg_parts.append(
                    f'<rect x="{pad_l + 6}" y="{by - 8:.1f}" width="{badge_w:.1f}" height="16" rx="4" fill="{bg_col}" fill-opacity="0.92" stroke="{stroke_col}" stroke-width="1"/>'
                )
                svg_parts.append(
                    f'<text x="{pad_l + 11}" y="{by + 3:.1f}" fill="{txt_col}" font-size="9.5" font-weight="bold" font-family="sans-serif">{lbl_text}</text>'
                )

        # 3. Primary Data Rendered in Live Theme Accent
        pts = [(idx_to_x(i), val_to_y(v)) for i, v in enumerate(vals)]
        show_all_val_labels = n_pts <= 18
        peak_idx = vals.index(max(vals)) if vals else 0

        if chart_style == "pillars":
            slot_w = plot_w / max(1, n_pts)
            bar_w = max(2.0, min(28.0, slot_w * 0.74))
            rx_val = 3 if bar_w >= 6 else 1
            base_y = val_to_y(0.0)
            for i, (px, py) in enumerate(pts):
                bh = max(2.0, base_y - py)
                bx = px - bar_w / 2
                val_str = f"{vals[i]:.2f}".rstrip("0").rstrip(".")
                svg_parts.append(
                    f'<rect x="{bx:.1f}" y="{py:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" fill="{accent_hex}" fill-opacity="0.82" rx="{rx_val}">'
                    f'<title>{dates[i]}: {val_str} {unit_name}</title></rect>'
                )
                if show_all_val_labels or i in (0, n_pts - 1, peak_idx):
                    svg_parts.append(
                        f'<text x="{px:.1f}" y="{py - 5:.1f}" fill="{accent_hex}" font-size="9" font-family="sans-serif" text-anchor="middle">{val_str}</text>'
                    )
        else:
            if len(pts) > 1:
                poly_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                area_pts = f"{pts[0][0]:.1f},{val_to_y(0):.1f} " + poly_pts + f" {pts[-1][0]:.1f},{val_to_y(0):.1f}"
                svg_parts.append(f'<polygon points="{area_pts}" fill="{accent_hex}" fill-opacity="0.16"/>')
                stroke_w = "2.4" if n_pts <= 35 else ("1.8" if n_pts <= 80 else "1.3")
                svg_parts.append(
                    f'<polyline points="{poly_pts}" fill="none" stroke="{accent_hex}" stroke-width="{stroke_w}" stroke-linecap="round" stroke-linejoin="round"/>'
                )
            dot_r = 4.2 if n_pts <= 25 else (2.8 if n_pts <= 60 else 1.8)
            for i, (px, py) in enumerate(pts):
                val_str = f"{vals[i]:.2f}".rstrip("0").rstrip(".")
                svg_parts.append(
                    f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{dot_r}" fill="{accent_hex}" stroke="{bg_base_hex}" stroke-width="1.2">'
                    f'<title>{dates[i]}: {val_str} {unit_name}</title></circle>'
                )
                if show_all_val_labels or i in (0, n_pts - 1, peak_idx):
                    svg_parts.append(
                        f'<text x="{px:.1f}" y="{py - 7:.1f}" fill="{accent_hex}" font-size="9" font-family="sans-serif" text-anchor="middle">{val_str}</text>'
                    )

        # 4. Foreground Average Line
        if avg_mode in ("running", "weekly") and len(vals) >= 1:
            avg_series = weekly_avgs if avg_mode == "weekly" else running_avgs
            avg_label_prefix = "Wk Avg" if avg_mode == "weekly" else "Run Avg"

            avg_pts = [(idx_to_x(i), val_to_y(av)) for i, av in enumerate(avg_series)]
            if len(avg_pts) > 1:
                avg_poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in avg_pts)
                svg_parts.append(
                    f'<polyline points="{avg_poly}" fill="none" stroke="{bg_base_hex}" stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round"/>'
                )
                svg_parts.append(
                    f'<polyline points="{avg_poly}" fill="none" stroke="#38BDF8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
                )
            if n_pts <= 30:
                for idx_av, (ax, ay) in enumerate(avg_pts):
                    av_str = f"{avg_series[idx_av]:.2f}".rstrip("0").rstrip(".")
                    svg_parts.append(
                        f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="2.6" fill="#38BDF8" stroke="{bg_base_hex}" stroke-width="1">'
                        f'<title>{avg_label_prefix}: {av_str}</title></circle>'
                    )

            last_ay = max(pad_t + 10, min(height - pad_b - 10, avg_pts[-1][1]))
            last_av = avg_series[-1]
            last_av_str = f"{last_av:.2f}".rstrip("0").rstrip(".")
            svg_parts.append(
                f'<rect x="{width - pad_r + 6}" y="{last_ay - 10:.1f}" width="{pad_r - 10}" height="18" rx="4" fill="#0F293A" stroke="#38BDF8" stroke-width="1.2"/>'
            )
            svg_parts.append(
                f'<text x="{width - pad_r + 11}" y="{last_ay + 3:.1f}" fill="#E0F2FE" font-size="9.5" font-weight="bold" font-family="sans-serif">{avg_label_prefix}: {last_av_str}</text>'
            )

        # 5. X-Axis Labels
        max_x_labels = 8
        step_x = max(1, (n_pts - 1) // max_x_labels) if n_pts > max_x_labels else 1
        for i, d_str in enumerate(dates):
            if i % step_x == 0 or i == n_pts - 1:
                if i != n_pts - 1 and (n_pts - 1 - i) < max(1, step_x // 2):
                    continue
                px = idx_to_x(i)
                lbl = d_str if time_bucket == "weekly" else format_ui_date(d_str, "day_month")
                svg_parts.append(
                    f'<text x="{px:.1f}" y="{height - 13}" fill="#789ea3" font-size="10" font-family="sans-serif" text-anchor="middle">{lbl}</text>'
                )

        svg_parts.append("</svg>")
        svg_str = "".join(svg_parts)
        b64 = base64.b64encode(svg_str.encode("utf-8")).decode("utf-8")
        return ft.Image(src=f"data:image/svg+xml;base64,{b64}", width=width, height=height)
# =============================================================================
# >>> SECTION A2 END: SHARED UI HELPERS & SVG CHART GENERATOR <<<
# =============================================================================

# =============================================================================
# >>> SECTION A3 START: TOP NAVIGATION, POPUP MODALS & SETTINGS ENGINE <<<
# =============================================================================
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

    # Time Format Preference: "24h" or "12h"
    current_time_format = saved_settings.get("time_format", "24h")

    def format_time_display(time_str: str) -> str:
        if not time_str:
            return ""
        try:
            parts = time_str.strip().split(":")
            h, m = int(parts[0]), int(parts[1])
            if current_time_format == "12h":
                suffix = "AM" if h < 12 else "PM"
                h_12 = h % 12
                if h_12 == 0:
                    h_12 = 12
                return f"{h_12}:{m:02d} {suffix}"
            return f"{h:02d}:{m:02d}"
        except Exception:
            return time_str

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
        mini_preview_frame.border = make_border(1, get_border_color(bg_col))
        mini_preview_frame.content.controls[0].controls[0].color = get_text_color(bg_col)
        mini_preview_frame.content.controls[0].controls[2].color = get_subtext_color(bg_col)

        mini_shelf_box.bgcolor = box_col
        mini_shelf_box.border = make_border(1, get_border_color(box_col))
        mini_shelf_box.content.controls[0].controls[0].color = acc_col
        mini_shelf_box.content.controls[0].controls[1].color = get_subtext_color(box_col)

        mini_task_card.bgcolor = card_col
        mini_task_card.border = make_border(1, get_border_color(card_col))
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
            btn.border = make_border(1.5 if is_sel else 1, staged_theme["accent"])
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
        ("Y2K Brushed Chrome","#8E99A4","#10171E","#AAB4BE","#1A2632", "#00E5FF","#008394",),
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
            border=make_border(1, acc_val),
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
        border=make_border(1, theme_state["accent"]),
        on_click=lambda _: set_time_format("24h"),
        content=ft.Text("24-Hour (14:30)", size=11, weight=ft.FontWeight.BOLD, color=get_text_color(theme_state["accent"]) if current_time_format == "24h" else get_subtext_color(theme_state["box"])),
    )

    time_12_btn = ft.Container(
        padding=ft.Padding(left=12, right=12, top=6, bottom=6),
        bgcolor=theme_state["accent"] if current_time_format == "12h" else theme_state["box"],
        border_radius=6,
        border=make_border(1, theme_state["accent"]),
        on_click=lambda _: set_time_format("12h"),
        content=ft.Text("12-Hour AM/PM (2:30 PM)", size=11, weight=ft.FontWeight.BOLD, color=get_text_color(theme_state["accent"]) if current_time_format == "12h" else get_subtext_color(theme_state["box"])),
    )

    def commit_staged_theme(e=None):
        for k, v in staged_theme.items():
            theme_state[k] = v
            save_setting(f"theme_{k}", v)

        apply_page_theme()
        rebuild_top_nav()
        if 'settings_gear_btn' in locals() or 'settings_gear_btn' in globals():
            try:
                settings_gear_btn.icon_color = theme_state["accent"]
            except Exception:
                pass

        close_settings_modal()
        switch_view(current_view_index)
        show_message("🎨 New theme applied & saved!")
        page.update()

    settings_modal_content = ft.Container(
        padding=16,
        width=460,
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
                ft.Text("Time Format Display:", size=11, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                ft.Row([time_24_btn, time_12_btn], spacing=8),
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

    popup_title_text = ft.Text(size=16, weight=ft.FontWeight.BOLD, color=theme_state["accent"])
    popup_amount_field = ft.TextField(
        label="Value",
        width=220,
        autofocus=True,
        on_focus=lambda _: set_typing(True),
        on_blur=lambda _: set_typing(False),
    )

    def close_unit_popup(e=None):
        unit_popup_banner.visible = False
        set_typing(False)
        refresh_schedule_view()

    def save_unit_popup(e=None):
        if popup_task_id is None or not popup_date_str:
            return
        raw_val = (popup_amount_field.value or "").strip()
        amt_val = int(raw_val) if raw_val.lstrip("-").isdigit() else None
        mark_complete_db(popup_task_id, completed_dt=f"{popup_date_str} 12:00:00", amount=amt_val)
        unit_popup_banner.visible = False
        set_typing(False)
        show_message(
            f"✓ {popup_task_name}" + (f": {amt_val} {popup_unit_str}" if amt_val is not None else "")
        )
        refresh_schedule_view()

    popup_amount_field.on_submit = save_unit_popup

    unit_popup_banner = ft.Container(
        visible=False,
        padding=14,
        bgcolor=theme_state["surface_card"],
        border_radius=10,
        border=make_border(2, theme_state["accent"]),
        content=ft.Row(
            [
                ft.Icon(ft.Icons.BOLT_ROUNDED, color=theme_state["accent"]),
                popup_title_text,
                popup_amount_field,
                ft.FilledButton(
                    content=ft.Text("Log (Enter)", color=get_text_color(theme_state["accent"]), weight=ft.FontWeight.BOLD),
                    icon=ft.Icons.CHECK,
                    bgcolor=theme_state["accent"],
                    on_click=save_unit_popup,
                ),
                ft.TextButton(content=ft.Text("Cancel"), on_click=close_unit_popup),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
            wrap=True,
        ),
    )

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
                icon_size=23,  # Slightly larger for clear visibility
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

            # Clean container without bottom border line
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
    date_header_text = ft.Text(size=17, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
    right_rail_container = ft.Container(width=60, alignment=ft.Alignment(0, 0))
    expanded_edit_task_id = None
    delete_confirm_task_id = None

    def is_current_day_today() -> bool:
        return current_selected_date.strftime("%Y-%m-%d") == datetime.now().strftime("%Y-%m-%d")

    def update_date_header():
        date_header_text.color = get_text_color(theme_state["bg"])
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

    def trigger_task_completion(
        tid: int,
        tname: str,
        date_str: str,
        unit_str: str = None,
        recurrence: str = "once",
        existing_amt=None,
    ):
        nonlocal popup_task_id, popup_date_str, popup_task_name, popup_unit_str
        has_unit = bool(unit_str and unit_str != "None" and recurrence != "once")
        if has_unit:
            mark_complete_db(tid, completed_dt=f"{date_str} 12:00:00", amount=existing_amt)
            popup_task_id = tid
            popup_date_str = date_str
            popup_task_name = tname
            popup_unit_str = unit_str
            popup_title_text.value = f"Log {tname} ({unit_str}):"
            popup_title_text.color = theme_state["accent"]
            popup_amount_field.label = f"Amount ({unit_str})"
            popup_amount_field.value = str(existing_amt) if existing_amt is not None else ""
            unit_popup_banner.visible = True
            set_typing(True)
            refresh_schedule_view()
            try:
                popup_amount_field.focus()
            except Exception:
                pass
        else:
            mark_complete_db(tid, completed_dt=f"{date_str} 12:00:00")
            show_message(f"✓ {tname}")
            refresh_schedule_view()

# >>> SUB-SECTION A4b START: DAY TASKS LIST <<<
    def build_day_tasks_view():
        nonlocal current_day_tasks, selected_task_idx
        target_date_str = current_selected_date.strftime("%Y-%m-%d")
        tasks = fetch_tasks_for_date(target_date_str)
        comp_map = get_completions_for_date(target_date_str)
        current_day_tasks = tasks

        if selected_task_idx >= len(tasks):
            selected_task_idx = max(0, len(tasks) - 1)

        day_col = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=8)

        total_cnt = len(tasks)
        done_cnt = len([t for t in tasks if t[0] in comp_map])
        pct = (done_cnt / total_cnt) if total_cnt > 0 else 0.0

        # Day Mastery Progress Header
        if total_cnt > 0:
            status_text = (
                f"Mastered {done_cnt}/{total_cnt} ({int(pct * 100)}%)"
                if pct < 1.0
                else "★ All Daily Tasks Completed!"
            )
            day_progress_header = ft.Container(
                padding=10,
                bgcolor=theme_state["surface_card"] if pct == 1.0 else theme_state["box"],
                border_radius=8,
                border=make_border(
                    1.5 if pct == 1.0 else 1,
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
                        ft.ProgressBar(
                            value=pct,
                            color=theme_state["accent"],
                            bgcolor=theme_state["surface"],
                            height=6,
                        ),
                    ],
                    spacing=6,
                ),
            )
            day_col.controls.append(day_progress_header)

        if not tasks:
            empty_card = ft.Container(
                padding=24,
                bgcolor=theme_state["box"],
                border_radius=8,
                border=make_border(1, get_border_color(theme_state["box"])),
                alignment=ft.Alignment(0, 0),
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.AUTO_AWESOME_OUTLINED, color=theme_state["accent"], size=30),
                        ft.Text("Clear Day", size=15, weight=ft.FontWeight.BOLD, color=get_text_color(theme_state["box"])),
                        ft.Text(
                            "Nothing scheduled. Enjoy the downtime or tap '+' above to plan a task or start a habit.",
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

        for idx, t in enumerate(tasks):
            task_id, name, category, _, _, recurrence, _, _, _, note, unit = t[:11]
            custom_days = t[11] if len(t) > 11 else None
            t_rem = t[13] if len(t) > 13 else None
            is_done = task_id in comp_map
            logged_amt = comp_map[task_id]["amount"] if is_done else None
            is_focused = idx == selected_task_idx
            is_expanded = (expanded_edit_task_id == task_id)
            has_unit = bool(unit and unit != "None" and recurrence != "once")

            def toggle_task(
                e, tid=task_id, tname=name, u_str=unit, rec_str=recurrence, cur_amt=logged_amt
            ):
                currently_done = tid in get_completions_for_date(target_date_str)
                if not currently_done:
                    trigger_task_completion(tid, tname, target_date_str, u_str, rec_str, cur_amt)
                else:
                    remove_completion_db(tid, target_date_str)
                    unit_popup_banner.visible = False
                    show_message(f"↩ {tname}")
                    refresh_schedule_view()

            border_color = theme_state["accent"] if (is_focused or is_expanded) else get_border_color(theme_state["box"])
            card_border = ft.Border(
                top=ft.BorderSide(2 if is_expanded else (1.5 if is_focused else 1), border_color),
                bottom=ft.BorderSide(2 if is_expanded else (1.5 if is_focused else 1), border_color),
                left=ft.BorderSide(4 if (is_focused or is_expanded) else 1, border_color),
                right=ft.BorderSide(2 if is_expanded else (1.5 if is_focused else 1), border_color),
            )

            tag_parts = [category or "General"]
            if recurrence and recurrence != "once":
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
                fill_color={
                    ft.ControlState.SELECTED: theme_state["accent"],
                    ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT,
                },
                check_color=get_text_color(theme_state["accent"]),
            )
            left_col_items = [chk_control]
            if note and not is_expanded:
                left_col_items.append(
                    ft.Container(
                        padding=ft.Padding(left=32, top=0, right=0, bottom=2),
                        content=ft.Text(f"📝 {note}", size=11, italic=True, color=get_subtext_color(theme_state["box"])),
                    )
                )

            right_items = []
            if has_unit:
                badge_label = (
                    f"{logged_amt} {unit}" if (is_done and logged_amt is not None) else f"+ {unit}"
                )
                right_items.append(
                    ft.OutlinedButton(
                        content=ft.Text(badge_label, size=12, color=theme_state["accent"]),
                        tooltip="Click to edit unit value",
                        on_click=lambda _, tid=task_id, tn=name, us=unit, rs=recurrence, ca=logged_amt: trigger_task_completion(
                            tid, tn, target_date_str, us, rs, ca
                        ),
                    )
                )
            right_items.append(ft.Text(tag_text, size=12, color=get_subtext_color(theme_state["box"])))

            edit_btn = ft.Container(
                content=ft.Icon(
                    ft.Icons.EXPAND_LESS_ROUNDED if is_expanded else ft.Icons.MORE_VERT_ROUNDED,
                    size=22,
                    color=theme_state["accent"] if is_expanded else get_subtext_color(theme_state["box"]),
                ),
                padding=6,
                border_radius=6,
                bgcolor=theme_state["surface_card"] if is_expanded else theme_state["surface"],
                on_click=lambda _, tid=task_id: toggle_inline_edit(tid),
                tooltip="Collapse Edit" if is_expanded else "Edit or Delete Task",
            )
            right_items.append(edit_btn)

            card_children = [
                ft.Row(
                    [
                        ft.Column(left_col_items, spacing=2, expand=True),
                        ft.Row(right_items, spacing=8),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            ]

            if is_expanded:
                card_children.append(build_inline_edit_drawer(task_id))

            card_bg = (
                theme_state["surface_card"]
                if (is_expanded or is_done)
                else theme_state["box"]
            )

            day_col.controls.append(
                ft.Container(
                    content=ft.Column(card_children, spacing=10, tight=True),
                    padding=14 if is_expanded else 12,
                    bgcolor=card_bg,
                    border_radius=8,
                    border=card_border,
                )
            )

        return day_col
# >>> SUB-SECTION A4b END: DAY TASKS LIST <<<

# >>> SUB-SECTION A4c START: SINGLE-LINE WEEK VIEW, MONTH VIEW & SCHEDULE LAYOUT <<<
    def build_week_day_tile(day_dt: datetime, today_str: str) -> ft.Control:
        d_str = day_dt.strftime("%Y-%m-%d")
        is_today = d_str == today_str
        is_selected = d_str == current_selected_date.strftime("%Y-%m-%d")

        day_tasks = fetch_tasks_for_date(d_str)
        comp_map = get_completions_for_date(d_str)

        total_cnt = len(day_tasks)
        done_cnt = len([t for t in day_tasks if t[0] in comp_map])
        is_fully_done = (total_cnt > 0 and done_cnt == total_cnt)

        pct_badge = ft.Container(
            padding=ft.Padding(left=5, right=5, top=2, bottom=2),
            border_radius=4,
            bgcolor=theme_state["accent"] if is_fully_done else theme_state["surface"],
            content=ft.Text(
                "✓" if is_fully_done else (f"{done_cnt}/{total_cnt}" if total_cnt > 0 else "Clear"),
                size=9,
                weight=ft.FontWeight.BOLD,
                color=get_text_color(theme_state["accent"]) if is_fully_done else get_subtext_color(theme_state["box"]),
            ),
        )

        header_row = ft.Row(
            [
                ft.Container(
                    on_click=lambda _, dt=day_dt: jump_to_specific_day(dt),
                    tooltip=f"Open {day_dt.strftime('%A, %d %b')}",
                    content=ft.Column(
                        [
                            ft.Text(
                                day_dt.strftime("%a").upper(),
                                size=10,
                                weight=ft.FontWeight.BOLD,
                                color=theme_state["accent"] if is_today else get_subtext_color(theme_state["box"]),
                            ),
                            ft.Text(
                                day_dt.strftime("%d"),
                                size=14,
                                weight=ft.FontWeight.BOLD,
                                color=theme_state["accent"] if (is_today or is_selected) else get_text_color(theme_state["box"]),
                            ),
                        ],
                        spacing=0,
                    ),
                ),
                pct_badge,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        tasks_list_col = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=4)

        if not day_tasks:
            tasks_list_col.controls.append(
                ft.Container(
                    expand=True,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Icon(
                        ft.Icons.COMPASS_CALIBRATION_OUTLINED,
                        size=16,
                        color=get_subtext_color(theme_state["box"]),
                    ),
                )
            )
        else:
            for t in day_tasks:
                tid, tname, _, _, _, trec, _, _, _, _, tunit = t[:11]
                t_rem = t[13] if len(t) > 13 else None
                done = tid in comp_map
                logged_amt = comp_map[tid]["amount"] if done else None

                def toggle_w_task(
                    e,
                    task_id=tid,
                    name_s=tname,
                    date_s=d_str,
                    u_s=tunit,
                    r_s=trec,
                    amt_s=logged_amt,
                ):
                    if e.control.value:
                        trigger_task_completion(task_id, name_s, date_s, u_s, r_s, amt_s)
                    else:
                        remove_completion_db(task_id, date_s)
                        unit_popup_banner.visible = False
                        refresh_schedule_view()

                rem_suffix = f" 🔔{format_time_display(t_rem)}" if t_rem else ""
                label_display = (
                    f"{tname} ({logged_amt}{tunit}){rem_suffix}"
                    if (done and logged_amt is not None and tunit)
                    else f"{tname}{rem_suffix}"
                )

                tasks_list_col.controls.append(
                    ft.Container(
                        padding=ft.Padding(left=2, right=4, top=2, bottom=2),
                        bgcolor=theme_state["surface_card"] if done else theme_state["surface"],
                        border_radius=5,
                        tooltip=label_display,
                        content=ft.Row(
                            [
                                ft.Checkbox(
                                    value=done,
                                    on_change=toggle_w_task,
                                    fill_color={
                                        ft.ControlState.SELECTED: theme_state["accent"],
                                        ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT,
                                    },
                                    check_color=get_text_color(theme_state["accent"]),
                                ),
                                ft.Text(
                                    label_display,
                                    size=11,
                                    weight=ft.FontWeight.W_500 if done else ft.FontWeight.NORMAL,
                                    color=theme_state["accent"] if done else get_text_color(theme_state["box"]),
                                    expand=True,
                                    no_wrap=True,
                                ),
                            ],
                            spacing=2,
                        ),
                    )
                )

        border_col = (
            theme_state["accent"]
            if is_today
            else (theme_state["accent_dim"] if is_selected else get_border_color(theme_state["box"]))
        )

        return ft.Container(
            expand=1,
            height=245,
            padding=8,
            bgcolor=theme_state["box"],
            border_radius=8,
            border=make_border(1.5 if (is_today or is_selected) else 1, border_col),
            content=ft.Column(
                [
                    header_row,
                    ft.Divider(color=get_border_color(theme_state["box"]), height=2),
                    tasks_list_col,
                ],
                spacing=4,
            ),
        )

    def build_week_tasks_view():
        start_w = current_selected_date - timedelta(days=current_selected_date.weekday())
        today_str = datetime.now().strftime("%Y-%m-%d")
        all_7_days = [start_w + timedelta(days=i) for i in range(7)]

        # Calculate Weekly Completion Stats for the unified bottom shelf
        week_total_tasks = 0
        week_done_tasks = 0
        for d in all_7_days:
            d_s = d.strftime("%Y-%m-%d")
            tasks = fetch_tasks_for_date(d_s)
            comp = get_completions_for_date(d_s)
            week_total_tasks += len(tasks)
            week_done_tasks += len([t for t in tasks if t[0] in comp])

        week_pct = (week_done_tasks / week_total_tasks) if week_total_tasks > 0 else 0.0

        # Single horizontal chronological row: Mon -> Sun
        week_linear_row = ft.Row(
            [build_week_day_tile(d, today_str) for d in all_7_days],
            spacing=6,
            expand=False,
        )

        # Unified Full-Width Weekly Mastery Shelf below the 7 days
        weekly_summary_shelf = ft.Container(
            padding=12,
            bgcolor=theme_state["surface_card"] if week_pct == 1.0 else theme_state["box"],
            border_radius=8,
            border=make_border(
                1.5 if week_pct == 1.0 else 1,
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
                    ft.ProgressBar(
                        value=week_pct,
                        color=theme_state["accent"],
                        bgcolor=theme_state["surface"],
                        height=6,
                    ),
                ],
                spacing=6,
            ),
        )

        return ft.Column(
            [
                week_linear_row,
                weekly_summary_shelf,
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def build_month_tasks_view():
        year = current_selected_date.year
        month = current_selected_date.month
        cal = calendar.Calendar(firstweekday=0)
        month_weeks = cal.monthdatescalendar(year, month)
        today_str = datetime.now().strftime("%Y-%m-%d")

        grid_col = ft.Column(spacing=6, expand=True)

        header_row = ft.Row(
            [
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
            w_row = ft.Row(spacing=6, expand=1)
            for day_date in week:
                d_str = day_date.strftime("%Y-%m-%d")
                in_month = day_date.month == month
                is_today = d_str == today_str
                day_dt = datetime(day_date.year, day_date.month, day_date.day)

                tasks = fetch_tasks_for_date(d_str) if in_month else []
                comp_map = get_completions_for_date(d_str) if in_month else {}

                cell_header = ft.Row(
                    [
                        ft.Text(
                            str(day_date.day),
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color=get_text_color(theme_state["box"]) if in_month else get_subtext_color(theme_state["bg"]),
                        ),
                        ft.Text(
                            f"{len(comp_map)}/{len(tasks)}" if tasks else "",
                            size=10,
                            color=theme_state["accent"],
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
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
                        f" ({logged_amt}{tunit})" if (done and logged_amt is not None and tunit) else ""
                    )
                    task_entries_col.controls.append(
                        ft.Container(
                            on_click=toggle_m_task,
                            tooltip="Click to complete / log unit",
                            content=ft.Text(
                                txt_label,
                                size=10,
                                color=theme_state["accent"] if done else get_subtext_color(theme_state["box"]),
                                no_wrap=True,
                            ),
                        )
                    )

                border_col = theme_state["accent"] if is_today else get_border_color(theme_state["box"])
                w_row.controls.append(
                    ft.Container(
                        expand=1,
                        padding=6,
                        bgcolor=theme_state["box"] if in_month else theme_state["surface"],
                        border_radius=6,
                        border=make_border(1.5 if is_today else 1, border_col),
                        on_click=lambda _, dt=day_dt: jump_to_specific_day(dt),
                        content=ft.Column([cell_header, task_entries_col], spacing=3, expand=True),
                    )
                )
            grid_col.controls.append(w_row)
        return grid_col

    def jump_to_specific_day(dt: datetime):
        nonlocal current_selected_date, current_view_mode
        current_selected_date = dt
        current_view_mode = "day"
        refresh_schedule_view()

    def set_mode(mode: str):
        nonlocal current_view_mode
        current_view_mode = mode
        refresh_schedule_view()

    def cycle_view_mode(delta: int):
        if delta == 0:
            return
        modes = ["day", "week", "month"]
        cur_idx = modes.index(current_view_mode)
        new_idx = max(0, min(len(modes) - 1, cur_idx + delta))
        if new_idx != cur_idx:
            set_mode(modes[new_idx])

    def update_right_rail():
        def rail_button(label: str, mode_val: str, box_height: int):
            active = current_view_mode == mode_val

            btn_container = ft.Container(
                width=56,
                height=box_height,
                border_radius=8,
                bgcolor=theme_state["surface_card"] if active else theme_state["surface"],
                border=make_border(1.5, theme_state["accent"] if active else get_border_color(theme_state["surface"])),
                alignment=ft.Alignment(0, 0),
                on_click=lambda _: set_mode(mode_val),
                tooltip=f"Switch to {label} view",
                content=ft.Container(
                    alignment=ft.Alignment(0, 0),
                    rotate=ft.Rotate(angle=-1.5708),
                    content=ft.Text(
                        label,
                        size=14,
                        weight=ft.FontWeight.BOLD if active else ft.FontWeight.W_500,
                        color=theme_state["accent"] if active else get_subtext_color(theme_state["surface"]),
                        no_wrap=True,
                    ),
                ),
            )
            return btn_container

        right_rail_container.content = ft.Column(
            [
                rail_button("Day", "day", 75),
                ft.Text("─", size=14, color=get_subtext_color(theme_state["bg"]), weight=ft.FontWeight.BOLD),
                rail_button("Week", "week", 85),
                ft.Text("─", size=14, color=get_subtext_color(theme_state["bg"]), weight=ft.FontWeight.BOLD),
                rail_button("Month", "month", 120),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
        )

        right_rail_container.content = ft.GestureDetector(
            on_scroll=lambda e: cycle_view_mode(get_scroll_direction(e)),
            content=right_rail_container.content,
        )

    def refresh_schedule_view():
        update_date_header()
        update_right_rail()

        is_today = is_current_day_today()
        today_btn_pill.bgcolor = theme_state["surface"] if is_today else theme_state["surface_card"]
        today_btn_pill.border = make_border(
            1.5 if not is_today else 1,
            theme_state["accent"] if not is_today else get_border_color(theme_state["surface"]),
        )
        today_btn_text.color = theme_state["accent"] if not is_today else get_subtext_color(theme_state["surface"])
        today_btn_icon.color = theme_state["accent"] if not is_today else get_subtext_color(theme_state["surface"])

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
        nonlocal current_selected_date
        if current_view_mode == "day":
            current_selected_date += timedelta(days=delta_steps)
        elif current_view_mode == "week":
            current_selected_date += timedelta(weeks=delta_steps)
        elif current_view_mode == "month":
            month = current_selected_date.month + delta_steps
            year = current_selected_date.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            current_selected_date = current_selected_date.replace(year=year, month=month, day=1)
        refresh_schedule_view()

    def snap_to_today(e=None):
        nonlocal current_selected_date
        current_selected_date = datetime.now()
        refresh_schedule_view()

    def open_quick_add_for_date(e=None):
        date_str = current_selected_date.strftime("%Y-%m-%d")
        switch_view(1)
        load_add_task_form(default_date=date_str)

    today_btn_text = ft.Text("Today", size=12, weight=ft.FontWeight.BOLD)
    today_btn_icon = ft.Icon(ft.Icons.CALENDAR_TODAY_ROUNDED, size=14)
    today_btn_pill = ft.Container(
        padding=ft.Padding(left=10, right=10, top=6, bottom=6),
        border_radius=8,
        on_click=snap_to_today,
        tooltip="Jump back to Today (Shortcut: T)",
        content=ft.Row([today_btn_icon, today_btn_text], spacing=6, tight=True),
    )

    def build_schedule_layout():
        update_date_header()
        update_right_rail()

        # Unified Date Header with Adjacent Navigation Chevrons
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
            ),
        )

        # Subtle Edge Navigation Cues (Visual affordance that whole canvas scrolls/swipes)
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

        # Whole main schedule body supports wheel scrolling & horizontal thumb/trackpad swipe
        swipeable_body_wrapper = ft.GestureDetector(
            expand=True,
            on_scroll=lambda e: shift_date(get_scroll_direction(e)),
            on_horizontal_drag_end=lambda e: shift_date(-1 if (e.primary_velocity or 0) > 250 else (1 if (e.primary_velocity or 0) < -250 else 0)),
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

        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Row(
                            [
                                today_btn_pill,
                                ft.IconButton(
                                    icon=ft.Icons.ADD_ROUNDED,
                                    icon_color=theme_state["accent"],
                                    tooltip="Add task for this specific day",
                                    on_click=open_quick_add_for_date,
                                ),
                            ],
                            spacing=6,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Container(expand=True),
                        date_nav_cluster,
                        ft.Container(expand=True),
                        ft.Container(width=110),  # Keeps center date aligned
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(color=get_border_color(theme_state["bg"]), height=1),
                unit_popup_banner,
                ft.Row(
                    [
                        swipeable_body_wrapper,
                        ft.VerticalDivider(color=get_border_color(theme_state["bg"]), width=1),
                        right_rail_container,
                    ],
                    expand=True,
                    spacing=6,
                ),
            ],
            expand=True,
        )
# >>> SUB-SECTION A4c END: SINGLE-LINE WEEK VIEW, MONTH VIEW & SCHEDULE LAYOUT <<<
# =============================================================================
# >>> SECTION A4 END: VIEW 1 - SCHEDULE & TODAY (DAY / WEEK / MONTH) <<<
# =============================================================================

# =============================================================================
# >>> SECTION A5 START: VIEW 2 - ADD TASK & EDIT TASK MODAL FORM <<<
# =============================================================================
# >>> SUB-SECTION A5a START: ADD TASK FORM CONTROLS & RECURRENCE <<<
    name_field = ft.TextField(
        label="Task or Habit Name",
        on_focus=lambda _: set_typing(True),
        on_blur=lambda _: set_typing(False),
    )

    linked_habit_badge = ft.Container(
        visible=False,
        padding=ft.Padding(left=10, right=10, top=5, bottom=5),
        bgcolor=theme_state["surface_card"],
        border_radius=6,
        border=make_border(1, theme_state["accent"]),
        content=ft.Row(
            [
                ft.Icon(ft.Icons.LINK_ROUNDED, size=15, color=theme_state["accent"]),
                ft.Text(
                    "Links to existing habit history on Page 4 (Completions & units will merge)",
                    size=11,
                    color=theme_state["accent"],
                ),
            ],
            spacing=6,
            tight=True,
        ),
    )

    def check_live_linked_habit(e=None):
        val = (name_field.value or "").strip().lower()
        if not val:
            linked_habit_badge.visible = False
        else:
            existing = [h.lower() for h in get_distinct_habits()]
            linked_habit_badge.visible = (val in existing)
        page.update()

    name_field.on_change = check_live_linked_habit

    restart_habit_dropdown = ft.Dropdown(
        label="⚡ Restart / Copy Existing Habit (Optional)",
        hint_text="Select a past habit to auto-fill its settings",
        width=380,
    )

    backlog_checkbox = ft.Checkbox(label="Send to Backlog (No date yet)", value=False)

    category_dropdown = ft.Dropdown(label="Category", width=220, value="+ New Category")
    custom_category_field = ft.TextField(
        label="New Category (Leave blank for General)",
        width=280,
        visible=True,
        on_focus=lambda _: set_typing(True),
        on_blur=lambda _: set_typing(False),
    )

    def handle_category_select(e):
        custom_category_field.visible = category_dropdown.value == "+ New Category"
        page.update()

    category_dropdown.on_select = handle_category_select
    category_dropdown.on_change = handle_category_select

    # --- Apple-Alarm-Style Hour & Minute Time Picker Widget Builder ---
    def build_time_wheel_picker(initial_time="09:00"):
        h_val, m_val = 9, 0
        if initial_time and ":" in initial_time:
            try:
                parts = initial_time.split(":")
                h_val, m_val = int(parts[0]) % 24, int(parts[1]) % 60
            except Exception:
                pass

        hour_text = ft.Text(f"{h_val:02d}", size=22, weight=ft.FontWeight.BOLD)
        min_text = ft.Text(f"{m_val:02d}", size=22, weight=ft.FontWeight.BOLD)

        def step_hour(delta):
            nonlocal h_val
            h_val = (h_val + delta) % 24
            hour_text.value = f"{h_val:02d}"
            update_picker_ui()

        def step_min(delta):
            nonlocal m_val
            m_val = (m_val + delta) % 60
            min_text.value = f"{m_val:02d}"
            update_picker_ui()

        def update_picker_ui():
            hour_text.color = theme_state["accent"]
            min_text.color = theme_state["accent"]
            page.update()

        def get_time_string():
            return f"{h_val:02d}:{m_val:02d}"

        def set_preset_time(h, m):
            nonlocal h_val, m_val
            h_val, m_val = h, m
            hour_text.value = f"{h_val:02d}"
            min_text.value = f"{m_val:02d}"
            update_picker_ui()

        h_col = ft.Column(
            [
                ft.IconButton(icon=ft.Icons.KEYBOARD_ARROW_UP_ROUNDED, icon_size=18, on_click=lambda _: step_hour(1)),
                ft.Container(
                    width=54,
                    height=44,
                    bgcolor=theme_state["surface_card"],
                    border_radius=8,
                    alignment=ft.Alignment(0, 0),
                    border=make_border(1.5, theme_state["accent"]),
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
                    width=54,
                    height=44,
                    bgcolor=theme_state["surface_card"],
                    border_radius=8,
                    alignment=ft.Alignment(0, 0),
                    border=make_border(1.5, theme_state["accent"]),
                    content=min_text,
                ),
                ft.IconButton(icon=ft.Icons.KEYBOARD_ARROW_DOWN_ROUNDED, icon_size=18, on_click=lambda _: step_min(-5)),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        )

        presets_row = ft.Row(
            [
                ft.TextButton(content=ft.Text("Morning (08:00)", size=11), on_click=lambda _: set_preset_time(8, 0)),
                ft.TextButton(content=ft.Text("Noon (12:00)", size=11), on_click=lambda _: set_preset_time(12, 0)),
                ft.TextButton(content=ft.Text("Afternoon (17:00)", size=11), on_click=lambda _: set_preset_time(17, 0)),
                ft.TextButton(content=ft.Text("Evening (20:00)", size=11), on_click=lambda _: set_preset_time(20, 0)),
            ],
            spacing=2,
            wrap=True,
        )

        wheel_container = ft.Container(
            padding=10,
            bgcolor=theme_state["surface"],
            border_radius=8,
            border=make_border(1, get_border_color(theme_state["surface"])),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            h_col,
                            ft.Text(":", size=24, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                            m_col,
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    presets_row,
                ],
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        return wheel_container, get_time_string, set_preset_time

    # --- Add Task Reminder UI Controls ---
    has_reminder = False
    add_time_picker, get_add_time, set_add_time = build_time_wheel_picker("09:00")

    def toggle_reminder_checkbox(e):
        nonlocal has_reminder
        has_reminder = e.control.value
        reminder_section_container.visible = has_reminder
        page.update()

    reminder_checkbox = ft.Checkbox(
        label="Set Reminder / Notification Time",
        value=False,
        on_change=toggle_reminder_checkbox,
    )

    reminder_section_container = ft.Container(
        visible=False,
        padding=10,
        bgcolor=theme_state["surface"],
        border_radius=8,
        border=make_border(1, theme_state["accent"]),
        content=ft.Column(
            [
                ft.Text("Set Time (Apple Alarm Style):", size=11, color=get_subtext_color(theme_state["box"])),
                add_time_picker,
            ],
            spacing=6,
        ),
    )

    selected_target_date = datetime.now()
    calendar_Browse_date = datetime.now()
    calendar_popup_open = False

    date_btn_label = ft.Text(
        selected_target_date.strftime("%d %b %Y"),
        color=theme_state["accent"],
        weight=ft.FontWeight.BOLD,
        size=13,
    )

    calendar_popup_container = ft.Container(
        visible=False,
        padding=14,
        bgcolor=theme_state["surface"],
        border_radius=10,
        border=make_border(1.5, theme_state["accent"]),
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
            date_btn_label.value = selected_target_date.strftime("%d %b %Y")
            calendar_popup_open = False
            calendar_popup_container.visible = False
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
                bdr = make_border(1, theme_state["accent"]) if (is_tod and not is_sel) else None

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
        padding=ft.Padding(left=14, right=14, top=10, bottom=10),
        bgcolor=theme_state["surface_card"],
        border_radius=8,
        border=make_border(1.5, theme_state["accent"]),
        on_click=toggle_calendar_popup,
        tooltip="Click to choose start / target date from calendar",
        content=ft.Row(
            [
                ft.Icon(ft.Icons.CALENDAR_MONTH_ROUNDED, color=theme_state["accent"], size=18),
                date_btn_label,
                ft.Icon(ft.Icons.ARROW_DROP_DOWN, color=theme_state["accent"], size=18),
            ],
            spacing=8,
            tight=True,
        ),
    )

    is_recurring_habit = False
    recurrence_freq = "weekly"

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

    active_weekly_days = {"Mon", "Wed", "Fri"}
    active_monthly_months = set(range(1, 13))
    single_month_mode = False

    interval_days_field = ft.TextField(
        label="Repeat Every X Days",
        value="2",
        width=160,
        on_focus=lambda _: set_typing(True),
        on_blur=lambda _: set_typing(False),
    )

    common_units = ["None", "kg", "lb", "km", "sets", "reps", "mins", "hours", "pages", "+ Custom Unit"]
    unit_dropdown = ft.Dropdown(
        label="Habit Unit",
        width=180,
        options=[ft.dropdown.Option(key=u, text=u) for u in common_units],
        value="None",
    )

    custom_unit_field = ft.TextField(
        label="Custom Unit",
        width=160,
        visible=False,
        on_focus=lambda _: set_typing(True),
        on_blur=lambda _: set_typing(False),
    )

    note_field = ft.TextField(
        label="Note (Optional)",
        on_focus=lambda _: set_typing(True),
        on_blur=lambda _: set_typing(False),
    )

    def handle_unit_select(e):
        custom_unit_field.visible = unit_dropdown.value == "+ Custom Unit"
        page.update()

    unit_dropdown.on_select = handle_unit_select
    unit_dropdown.on_change = handle_unit_select

    recurrence_visual_container = ft.Column(spacing=12)
    unit_section_container = ft.Container(
        visible=False,
        padding=12,
        bgcolor=theme_state["box"],
        border_radius=8,
        border=make_border(1, get_border_color(theme_state["box"])),
    )
    schedule_section_container = ft.Container(
        padding=12,
        bgcolor=theme_state["box"],
        border_radius=8,
        border=make_border(1, get_border_color(theme_state["box"])),
    )

    def set_recurring_state(recurring: bool):
        nonlocal is_recurring_habit, recurrence_freq
        is_recurring_habit = recurring
        if is_recurring_habit and not recurrence_freq:
            recurrence_freq = "weekly"
        unit_section_container.visible = is_recurring_habit and (not backlog_checkbox.value)
        rebuild_recurrence_visuals()
        page.update()

    def set_recurrence_freq(freq_val: str):
        nonlocal recurrence_freq
        recurrence_freq = freq_val
        rebuild_recurrence_visuals()
        page.update()

    def toggle_daily_all_days(e=None):
        if len(active_weekly_days) == 7:
            active_weekly_days.clear()
            active_weekly_days.add(selected_target_date.strftime("%a"))
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

        def mode_pill(title: str, active: bool, click_fn):
            return ft.Container(
                padding=ft.Padding(left=16, right=16, top=8, bottom=8),
                bgcolor=theme_state["accent"] if active else theme_state["surface"],
                border_radius=8,
                border=make_border(1.5, theme_state["accent"] if active else get_border_color(theme_state["surface"])),
                on_click=click_fn,
                content=ft.Text(
                    title,
                    size=13,
                    weight=ft.FontWeight.BOLD,
                    color=get_text_color(theme_state["accent"]) if active else get_subtext_color(theme_state["surface"]),
                ),
            )

        top_toggle_row = ft.Row(
            [
                mode_pill(
                    "No Recurrence (Once)",
                    not is_recurring_habit,
                    lambda _: set_recurring_state(False),
                ),
                mode_pill(
                    "Recurring Habit",
                    is_recurring_habit,
                    lambda _: set_recurring_state(True),
                ),
            ],
            spacing=10,
            wrap=True,
        )
        recurrence_visual_container.controls.append(top_toggle_row)

        target_weekday_str = selected_target_date.strftime("%a")
        is_all_7_days = len(active_weekly_days) == 7

        balls_row = ft.Row(spacing=8, wrap=True)
        for d_key, d_init in week_days_list:
            is_date_weekday = target_weekday_str == d_key
            ball_lit = d_key in active_weekly_days if recurrence_freq == "weekly" else is_date_weekday

            def click_day_ball(e, day_code=d_key):
                nonlocal is_recurring_habit, recurrence_freq
                if not is_recurring_habit:
                    is_recurring_habit = True
                    recurrence_freq = "weekly"
                    unit_section_container.visible = not backlog_checkbox.value
                    active_weekly_days.clear()
                    active_weekly_days.add(day_code)
                elif recurrence_freq == "weekly":
                    if day_code in active_weekly_days and len(active_weekly_days) > 1:
                        active_weekly_days.remove(day_code)
                    else:
                        active_weekly_days.add(day_code)
                elif recurrence_freq in ["monthly", "custom_interval"]:
                    recurrence_freq = "weekly"
                    active_weekly_days.clear()
                    active_weekly_days.add(day_code)
                rebuild_recurrence_visuals()
                page.update()

            border_c = theme_state["accent"] if ball_lit else get_border_color(theme_state["surface"])

            balls_row.controls.append(
                ft.Container(
                    width=38,
                    height=38,
                    border_radius=19,
                    bgcolor=theme_state["accent"]
                    if (ball_lit and is_recurring_habit and recurrence_freq == "weekly")
                    else (theme_state["surface_card"] if ball_lit else theme_state["surface"]),
                    border=make_border(1.5, border_c),
                    alignment=ft.Alignment(0, 0),
                    on_click=click_day_ball,
                    tooltip=f"Click to toggle {d_key}",
                    content=ft.Text(
                        d_init,
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=get_text_color(theme_state["accent"])
                        if (ball_lit and is_recurring_habit and recurrence_freq == "weekly")
                        else (theme_state["accent"] if ball_lit else get_subtext_color(theme_state["surface"])),
                    ),
                )
            )

        if not is_recurring_habit:
            recurrence_visual_container.controls.append(
                ft.Column(
                    [
                        ft.Text(
                            "One-time task on selected date (Click any day ball below to turn into a Weekly Habit):",
                            size=11,
                            color=get_subtext_color(theme_state["box"]),
                        ),
                        balls_row,
                    ],
                    spacing=6,
                )
            )
            return

        def freq_pill(label: str, f_val: str):
            active = recurrence_freq == f_val
            return ft.Container(
                padding=ft.Padding(left=14, right=14, top=7, bottom=7),
                bgcolor=theme_state["surface_card"] if active else theme_state["surface"],
                border_radius=6,
                border=make_border(1.5, theme_state["accent"] if active else get_border_color(theme_state["surface"])),
                on_click=lambda _: set_recurrence_freq(f_val),
                content=ft.Text(
                    label,
                    size=12,
                    weight=ft.FontWeight.BOLD if active else ft.FontWeight.NORMAL,
                    color=theme_state["accent"] if active else get_subtext_color(theme_state["surface"]),
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
            daily_toggle_btn = ft.Container(
                padding=ft.Padding(left=12, right=12, top=6, bottom=6),
                bgcolor=theme_state["accent"] if is_all_7_days else theme_state["surface"],
                border_radius=19,
                border=make_border(1.5, theme_state["accent"] if is_all_7_days else get_border_color(theme_state["surface"])),
                on_click=toggle_daily_all_days,
                tooltip="Toggle all 7 days on or off",
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE if is_all_7_days else ft.Icons.CIRCLE_OUTLINED,
                            size=15,
                            color=get_text_color(theme_state["accent"]) if is_all_7_days else get_subtext_color(theme_state["surface"]),
                        ),
                        ft.Text(
                            "Daily (All 7)",
                            size=12,
                            weight=ft.FontWeight.BOLD,
                            color=get_text_color(theme_state["accent"]) if is_all_7_days else get_text_color(theme_state["surface"]),
                        ),
                    ],
                    spacing=6,
                    tight=True,
                ),
            )

            recurrence_visual_container.controls.append(
                ft.Column(
                    [
                        ft.Text(
                            "Every day of the week is active (Daily)!"
                            if is_all_7_days
                            else f"Repeating {len(active_weekly_days)} day(s) per week (Click balls or toggle Daily):",
                            size=11,
                            color=theme_state["accent"] if is_all_7_days else get_subtext_color(theme_state["box"]),
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
            recurrence_visual_container.controls.append(
                ft.Text(
                    f"Repeats every month on day #{selected_target_date.day} of the selected month(s):",
                    size=11,
                    color=get_subtext_color(theme_state["box"]),
                )
            )

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
                        bgcolor=theme_state["accent"] if has_dot else theme_state["surface"],
                        border=make_border(1, theme_state["accent"] if has_dot else get_border_color(theme_state["surface"])),
                    )
                    m_row_controls.append(
                        ft.Container(
                            width=54,
                            height=48,
                            bgcolor=theme_state["surface_card"] if has_dot else theme_state["surface"],
                            border_radius=6,
                            border=make_border(
                                1.5 if has_dot else 1,
                                theme_state["accent"] if has_dot else get_border_color(theme_state["surface"]),
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
                                        else get_subtext_color(theme_state["surface"]),
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
                    bgcolor=theme_state["surface_card"] if active else theme_state["surface"],
                    border_radius=6,
                    border=make_border(1, theme_state["accent"] if active else get_border_color(theme_state["surface"])),
                    on_click=fn,
                    content=ft.Text(
                        txt,
                        size=11,
                        weight=ft.FontWeight.BOLD if active else ft.FontWeight.NORMAL,
                        color=theme_state["accent"] if active else get_subtext_color(theme_state["surface"]),
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
                ft.Container(
                    padding=12,
                    bgcolor=theme_state["surface"],
                    border_radius=8,
                    border=make_border(1, get_border_color(theme_state["surface"])),
                    content=ft.Column(
                        [
                            month_mode_toggle,
                            ft.Text(
                                "Single-Month (Yearly) Mode: Click any month below to move the dot:"
                                if single_month_mode
                                else "Multi-Month Mode: Click any month below to toggle it on/off:",
                                size=11,
                                color=get_subtext_color(theme_state["surface"]),
                            ),
                            ft.Column(m_grid_rows, spacing=6),
                        ],
                        spacing=8,
                    ),
                )
            )

        elif recurrence_freq == "custom_interval":
            recurrence_visual_container.controls.append(
                ft.Container(
                    padding=12,
                    bgcolor=theme_state["surface"],
                    border_radius=8,
                    border=make_border(1, get_border_color(theme_state["surface"])),
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    interval_days_field,
                                    ft.Column(
                                        [
                                            ft.Text(
                                                "First occurrence starts on:",
                                                size=11,
                                                color=get_subtext_color(theme_state["surface"]),
                                            ),
                                            ft.Container(
                                                padding=ft.Padding(left=12, right=12, top=8, bottom=8),
                                                bgcolor=theme_state["surface_card"],
                                                border_radius=8,
                                                border=make_border(1, theme_state["accent"]),
                                                on_click=toggle_calendar_popup,
                                                content=ft.Row(
                                                    [
                                                        ft.Icon(
                                                            ft.Icons.EVENT_REPEAT_ROUNDED,
                                                            size=16,
                                                            color=theme_state["accent"],
                                                        ),
                                                        ft.Text(
                                                            selected_target_date.strftime("%d %b %Y"),
                                                            size=12,
                                                            weight=ft.FontWeight.BOLD,
                                                            color=theme_state["accent"],
                                                        ),
                                                        ft.Text(
                                                            "(Click to change)",
                                                            size=10,
                                                            color=get_subtext_color(theme_state["surface"]),
                                                        ),
                                                    ],
                                                    spacing=6,
                                                    tight=True,
                                                ),
                                            ),
                                        ],
                                        spacing=4,
                                    ),
                                ],
                                spacing=16,
                                wrap=True,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=8,
                    ),
                )
            )

    def handle_backlog_toggle(e):
        is_bg = backlog_checkbox.value
        schedule_section_container.visible = not is_bg
        unit_section_container.visible = is_recurring_habit and (not is_bg)
        page.update()

    backlog_checkbox.on_change = handle_backlog_toggle

    has_end_date = False
    end_target_date = datetime.now() + timedelta(days=30)
    end_calendar_open = False
    end_calendar_browse = datetime.now()

    end_date_btn_label = ft.Text(
        end_target_date.strftime("%d %b %Y"),
        color=ft.Colors.RED_300,
        weight=ft.FontWeight.BOLD,
        size=12,
    )

    end_calendar_container = ft.Container(
        visible=False,
        padding=12,
        bgcolor=theme_state["surface"],
        border_radius=10,
        border=make_border(1.5, ft.Colors.RED_400),
        width=320,
    )

    def toggle_end_date_toggle(e):
        nonlocal has_end_date
        has_end_date = e.control.value
        end_date_section.visible = has_end_date
        page.update()

    end_date_checkbox = ft.Checkbox(
        label="Set End Date (Stop habit after a specific point)",
        value=False,
        on_change=toggle_end_date_toggle,
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
                    ft.Text(end_calendar_browse.strftime("%B %Y"), weight=ft.FontWeight.BOLD, size=13, color=ft.Colors.RED_400),
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
                        bgcolor=ft.Colors.RED_400 if is_s else (theme_state["box"] if in_m else theme_state["surface"]),
                        border_radius=6,
                        alignment=ft.Alignment(0, 0),
                        on_click=lambda _, dp=dt_f: pick_end_d(dp),
                        content=ft.Text(
                            str(d_o.day),
                            size=11,
                            color=ft.Colors.BLACK if is_s else (get_text_color(theme_state["box"]) if in_m else get_subtext_color(theme_state["surface"])),
                        ),
                    )
                )
            c_rows.append(ft.Row(r_c, alignment=ft.MainAxisAlignment.CENTER, spacing=4))
        end_calendar_container.content = ft.Column(c_rows, spacing=4)

    end_date_selector_btn = ft.Container(
        padding=ft.Padding(left=12, right=12, top=8, bottom=8),
        bgcolor="#2a1616",
        border_radius=8,
        border=make_border(1.5, ft.Colors.RED_400),
        on_click=toggle_end_cal_popup,
        content=ft.Row([ft.Icon(ft.Icons.EVENT_BUSY_ROUNDED, color=ft.Colors.RED_400, size=16), end_date_btn_label], spacing=6, tight=True),
    )

    end_date_section = ft.Container(
        visible=False,
        padding=10,
        bgcolor="#181212",
        border_radius=8,
        border=make_border(1, ft.Colors.RED_900),
        content=ft.Column(
            [
                ft.Text("Select End Date or Quick Duration:", size=11, color=ft.Colors.RED_300),
                ft.Row([end_date_selector_btn, duration_chips_row], spacing=10, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                end_calendar_container,
            ],
            spacing=6,
        ),
    )

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
            note_field.value = note_db or ""

            cats = [opt.key for opt in category_dropdown.options]
            if cat_db and cat_db in cats:
                category_dropdown.value = cat_db
                custom_category_field.visible = False
            else:
                category_dropdown.value = "+ New Category"
                custom_category_field.value = cat_db or "General"
                custom_category_field.visible = True

            if unit_db and unit_db != "None":
                if unit_db in common_units:
                    unit_dropdown.value = unit_db
                    custom_unit_field.visible = False
                else:
                    unit_dropdown.value = "+ Custom Unit"
                    custom_unit_field.value = unit_db
                    custom_unit_field.visible = True
            else:
                unit_dropdown.value = "None"
                custom_unit_field.visible = False

            nonlocal has_reminder
            if rem_db:
                has_reminder = True
                reminder_checkbox.value = True
                reminder_section_container.visible = True
                try:
                    rh, rm = int(rem_db.split(":")[0]), int(rem_db.split(":")[1])
                    set_add_time(rh, rm)
                except Exception:
                    pass
            else:
                has_reminder = False
                reminder_checkbox.value = False
                reminder_section_container.visible = False

            is_rec = rec_db and rec_db != "once"
            set_recurring_state(is_rec)
            if is_rec:
                if rec_db in ["daily", "weekly"]:
                    set_recurrence_freq("weekly")
                    if rec_db == "daily":
                        active_weekly_days.update([d for d, _ in week_days_list])
                    elif cdays_db:
                        active_weekly_days.clear()
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

            nonlocal selected_target_date
            selected_target_date = datetime.now()
            date_btn_label.value = selected_target_date.strftime("%d %b %Y")

            check_live_linked_habit()
            rebuild_recurrence_visuals()
            show_message(f"⚡ Loaded habit settings for '{h_name}'! Start date set to Today.")
            page.update()

    restart_habit_dropdown.on_select = on_restart_habit_selected
    restart_habit_dropdown.on_change = on_restart_habit_selected

    def handle_save_task(e):
        if not name_field.value or not name_field.value.strip():
            show_message("Task name cannot be empty!")
            return

        cat_val = category_dropdown.value
        if cat_val == "+ New Category" or not cat_val:
            final_category = (
                custom_category_field.value.strip() if custom_category_field.value else "General"
            )
        else:
            final_category = cat_val
        if not final_category:
            final_category = "General"

        note_val = (
            note_field.value.strip() if (note_field.value and note_field.value.strip()) else None
        )
        is_backlog = backlog_checkbox.value

        if is_backlog or not is_recurring_habit:
            rec_val = "once"
        elif recurrence_freq == "weekly":
            rec_val = "daily" if len(active_weekly_days) == 7 else "weekly"
        elif recurrence_freq == "monthly":
            rec_val = "yearly" if (single_month_mode and len(active_monthly_months) == 1) else "monthly"
        else:
            rec_val = "custom_interval"

        final_unit = None
        if rec_val != "once" and not is_backlog:
            u_choice = unit_dropdown.value
            if u_choice == "+ Custom Unit":
                final_unit = (
                    custom_unit_field.value.strip() if custom_unit_field.value else None
                )
            elif u_choice and u_choice != "None":
                final_unit = u_choice

        ordered_days = [d for d, _ in week_days_list if d in active_weekly_days]
        custom_days_str = None
        custom_months_str = None

        if rec_val == "weekly":
            custom_days_str = ",".join(ordered_days)
        elif rec_val in ["monthly", "yearly"]:
            ordered_months = [str(m) for m in sorted(active_monthly_months)]
            custom_months_str = ",".join(ordered_months)

        final_end_date = end_target_date.strftime("%Y-%m-%d") if (is_recurring_habit and has_end_date and not is_backlog) else None
        final_reminder = get_add_time() if (has_reminder and not is_backlog) else None

        if is_backlog:
            add_task_db(
                name=name_field.value.strip(),
                category=final_category,
                time_frame="custom",
                target_date=None,
                recurrence_type="once",
                interval_days=0,
                end_date=final_end_date,
                custom_list="Backlog",
                note=note_val,
                unit=None,
                custom_days=None,
                custom_months=None,
                reminder_time=None,
            )
            name_field.value = ""
            note_field.value = ""
            custom_category_field.value = ""
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
                name=name_field.value.strip(),
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
            name_field.value = ""
            note_field.value = ""
            custom_category_field.value = ""
            custom_unit_field.value = ""
            custom_unit_field.visible = False
            unit_dropdown.value = "None"
            show_message(f"✅ Saved '{final_category}' item!")
            switch_view(0)

    def load_add_task_form(default_date=None):
        nonlocal selected_target_date, calendar_popup_open
        cats = get_distinct_categories()
        if "General" not in cats:
            cats.insert(0, "General")
        category_dropdown.options = [
            ft.dropdown.Option(key="+ New Category", text="+ New Category")
        ] + [ft.dropdown.Option(key=c, text=c) for c in cats]
        category_dropdown.value = "+ New Category"
        custom_category_field.visible = True

        distinct_habs = get_distinct_habits()
        if distinct_habs:
            restart_habit_dropdown.options = [ft.dropdown.Option(key=h, text=h) for h in distinct_habs]
            restart_habit_dropdown.visible = True
            restart_habit_dropdown.value = None
        else:
            restart_habit_dropdown.visible = False

        if default_date:
            selected_target_date = datetime.strptime(default_date, "%Y-%m-%d")
        else:
            selected_target_date = datetime.now()

        if single_month_mode:
            active_monthly_months.clear()
            active_monthly_months.add(selected_target_date.month)

        date_btn_label.value = selected_target_date.strftime("%d %b %Y")
        date_btn_label.color = theme_state["accent"]
        date_selector_button.bgcolor = theme_state["surface_card"]
        date_selector_button.border = make_border(1.5, theme_state["accent"])
        date_selector_button.content.controls[0].color = theme_state["accent"]
        date_selector_button.content.controls[2].color = theme_state["accent"]

        calendar_popup_open = False
        calendar_popup_container.visible = False
        calendar_popup_container.bgcolor = theme_state["surface"]
        calendar_popup_container.border = make_border(1.5, theme_state["accent"])

        check_live_linked_habit()
        rebuild_recurrence_visuals()

        schedule_section_container.bgcolor = theme_state["box"]
        schedule_section_container.border = make_border(1, get_border_color(theme_state["box"]))
        schedule_section_container.visible = not backlog_checkbox.value

        unit_section_container.bgcolor = theme_state["box"]
        unit_section_container.border = make_border(1, get_border_color(theme_state["box"]))
        unit_section_container.visible = is_recurring_habit and (not backlog_checkbox.value)
        unit_section_container.content = ft.Column(
            [
                ft.Text(
                    "3. Quantifiable Unit Tracking (Optional)",
                    size=13,
                    weight=ft.FontWeight.BOLD,
                    color=theme_state["accent"],
                ),
                ft.Text(
                    "Track numeric progress (e.g., kg, km, mins, pages) on Page 4 charts:",
                    size=11,
                    color=get_subtext_color(theme_state["box"]),
                ),
                ft.Row([unit_dropdown, custom_unit_field], spacing=12, wrap=True),
            ],
            spacing=8,
        )

        reminder_section_container.bgcolor = theme_state["surface"]
        reminder_section_container.border = make_border(1, theme_state["accent"])

        schedule_section_container.content = ft.Column(
            [
                ft.Text(
                    "2. Date, Recurrence & Reminders",
                    size=13,
                    weight=ft.FontWeight.BOLD,
                    color=theme_state["accent"],
                ),
                ft.Column(
                    [
                        ft.Text("Start / Target Date:", size=11, color=get_subtext_color(theme_state["box"])),
                        date_selector_button,
                        calendar_popup_container,
                    ],
                    spacing=6,
                ),
                ft.Divider(color=get_border_color(theme_state["box"]), height=8),
                recurrence_visual_container,
                ft.Divider(color=get_border_color(theme_state["box"]), height=8),
                reminder_checkbox,
                reminder_section_container,
                ft.Divider(color=get_border_color(theme_state["box"]), height=8),
                end_date_checkbox,
                end_date_section,
            ],
            spacing=10,
        )

        add_task_view.controls.clear()
        add_task_view.controls.extend(
            [
                ft.Text(
                    "Create Task or Habit",
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=theme_state["accent"],
                ),
                ft.Text(
                    "Set up a one-off to-do, a recurring routine, or a quantifiable habit.",
                    size=12,
                    color=get_subtext_color(theme_state["bg"]),
                ),
                ft.Divider(color=get_border_color(theme_state["bg"]), height=15),
                ft.Container(
                    padding=12,
                    bgcolor=theme_state["box"],
                    border_radius=8,
                    border=make_border(1, get_border_color(theme_state["box"])),
                    content=ft.Column(
                        [
                            ft.Text(
                                "1. Task Details",
                                size=13,
                                weight=ft.FontWeight.BOLD,
                                color=theme_state["accent"],
                            ),
                            restart_habit_dropdown if restart_habit_dropdown.visible else ft.Container(),
                            name_field,
                            linked_habit_badge,
                            backlog_checkbox,
                            ft.Row([category_dropdown, custom_category_field], wrap=True, spacing=12),
                            note_field,
                        ],
                        spacing=10,
                    ),
                ),
                schedule_section_container,
                unit_section_container,
                ft.Container(
                    padding=ft.Padding(top=10, left=0, right=0, bottom=0),
                    content=ft.FilledButton(
                        content=ft.Text(
                            "Save Task / Habit",
                            color=get_text_color(theme_state["accent"]),
                            weight=ft.FontWeight.BOLD,
                        ),
                        icon=ft.Icons.CHECK,
                        on_click=handle_save_task,
                        bgcolor=theme_state["accent"],
                    ),
                ),
            ]
        )
        page.update()
# >>> SUB-SECTION A5a END: ADD TASK FORM CONTROLS & RECURRENCE <<<

# >>> SUB-SECTION A5b START: INLINE CARD EXPANSION EDITOR <<<
    def toggle_inline_edit(task_id: int):
        nonlocal expanded_edit_task_id, delete_confirm_task_id
        if expanded_edit_task_id == task_id:
            expanded_edit_task_id = None
            delete_confirm_task_id = None
            set_typing(False)
        else:
            expanded_edit_task_id = task_id
            delete_confirm_task_id = None
            set_typing(True)

        if current_view_index == 0:
            refresh_schedule_view()
        elif current_view_index == 2:
            load_backlog_view()
        elif current_view_index == 4:
            load_all_tasks_view()

    def build_inline_edit_drawer(task_id: int) -> ft.Control:
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
            return ft.Container()

        tid, t_name, t_cat, t_tf, t_tdate, t_rec, t_int, t_end_date, t_note, t_unit, t_cdays, t_cmonths, t_rem = row

        edit_name_f = ft.TextField(
            label="Task or Habit Name",
            value=t_name or "",
            width=280,
            on_focus=lambda _: set_typing(True),
            on_blur=lambda _: set_typing(False),
        )
        edit_cat_f = ft.TextField(
            label="Category",
            value=t_cat or "General",
            width=180,
            on_focus=lambda _: set_typing(True),
            on_blur=lambda _: set_typing(False),
        )
        edit_note_f = ft.TextField(
            label="Note (Optional)",
            value=t_note or "",
            width=280,
            on_focus=lambda _: set_typing(True),
            on_blur=lambda _: set_typing(False),
        )
        edit_unit_f = ft.TextField(
            label="Unit (Blank = None)",
            value=t_unit if (t_unit and t_unit != "None") else "",
            width=160,
            on_focus=lambda _: set_typing(True),
            on_blur=lambda _: set_typing(False),
        )

        # Inline Edit Time Picker
        has_edit_rem = bool(t_rem)
        edit_wheel_widget, get_edit_time, set_edit_time = build_time_wheel_picker(t_rem or "09:00")

        def toggle_edit_rem(e):
            nonlocal has_edit_rem
            has_edit_rem = e.control.value
            edit_rem_box.visible = has_edit_rem
            page.update()

        edit_rem_check = ft.Checkbox(
            label="Set Reminder / Notification Time",
            value=has_edit_rem,
            on_change=toggle_edit_rem,
        )

        edit_rem_box = ft.Container(
            visible=has_edit_rem,
            padding=8,
            bgcolor=theme_state["surface"],
            border_radius=8,
            border=make_border(1, theme_state["accent"]),
            content=edit_wheel_widget,
        )

        edit_dt = datetime.strptime(t_tdate, "%Y-%m-%d") if t_tdate else datetime.now()
        edit_cal_browse = edit_dt.replace(day=1)
        edit_cal_open = False
        edit_date_text = ft.Text(
            edit_dt.strftime("%d %b %Y"),
            color=theme_state["accent"],
            weight=ft.FontWeight.BOLD,
            size=13,
        )
        edit_cal_box = ft.Container(
            visible=False,
            padding=12,
            bgcolor=theme_state["surface"],
            border_radius=10,
            border=make_border(1.5, theme_state["accent"]),
            width=340,
        )

        has_edit_end = bool(t_end_date)
        edit_end_dt = datetime.strptime(t_end_date, "%Y-%m-%d") if t_end_date else (edit_dt + timedelta(days=30))
        edit_end_browse = edit_end_dt.replace(day=1)
        edit_end_cal_open = False

        edit_end_date_text = ft.Text(
            edit_end_dt.strftime("%d %b %Y"),
            color=ft.Colors.RED_300,
            weight=ft.FontWeight.BOLD,
            size=12,
        )
        edit_end_cal_box = ft.Container(
            visible=False,
            padding=12,
            bgcolor=theme_state["surface"],
            border_radius=10,
            border=make_border(1.5, ft.Colors.RED_400),
            width=320,
        )

        edit_end_section = ft.Container(
            visible=has_edit_end,
            padding=10,
            bgcolor="#181212",
            border_radius=8,
            border=make_border(1, ft.Colors.RED_900),
        )

        def toggle_edit_end_checkbox(e):
            nonlocal has_edit_end
            has_edit_end = e.control.value
            edit_end_section.visible = has_edit_end
            page.update()

        edit_end_checkbox = ft.Checkbox(
            label="Set End Date (Stop habit after a specific point)",
            value=has_edit_end,
            on_change=toggle_edit_end_checkbox,
        )

        def set_edit_duration_offset(days_delta: int, months_delta: int = 0):
            nonlocal edit_end_dt
            if months_delta > 0:
                new_m = edit_dt.month + months_delta
                new_y = edit_dt.year + (new_m - 1) // 12
                new_m = (new_m - 1) % 12 + 1
                edit_end_dt = edit_dt.replace(
                    year=new_y,
                    month=new_m,
                    day=min(edit_dt.day, calendar.monthrange(new_y, new_m)[1]),
                )
            else:
                edit_end_dt = edit_dt + timedelta(days=days_delta)
            edit_end_date_text.value = edit_end_dt.strftime("%d %b %Y")
            page.update()

        edit_duration_row = ft.Row(
            [
                ft.TextButton(content=ft.Text("2 Weeks", size=11), on_click=lambda _: set_edit_duration_offset(14)),
                ft.TextButton(content=ft.Text("1 Month", size=11), on_click=lambda _: set_edit_duration_offset(0, 1)),
                ft.TextButton(content=ft.Text("3 Months", size=11), on_click=lambda _: set_edit_duration_offset(0, 3)),
                ft.TextButton(content=ft.Text("1 Year", size=11), on_click=lambda _: set_edit_duration_offset(0, 12)),
            ],
            spacing=4,
            wrap=True,
        )

        def toggle_edit_end_cal(e):
            nonlocal edit_end_cal_open, edit_end_browse
            edit_end_cal_open = not edit_end_cal_open
            if edit_end_cal_open:
                edit_end_browse = edit_end_dt.replace(day=1)
                rebuild_edit_end_cal()
            edit_end_cal_box.visible = edit_end_cal_open
            page.update()

        def rebuild_edit_end_cal():
            yr, mo = edit_end_browse.year, edit_end_browse.month
            cal = calendar.Calendar(firstweekday=0)
            weeks = cal.monthdatescalendar(yr, mo)
            sel_s = edit_end_dt.strftime("%Y-%m-%d")

            def shift_end_m(delta):
                nonlocal edit_end_browse
                nm = edit_end_browse.month + delta
                ny = edit_end_browse.year + (nm - 1) // 12
                nm = (nm - 1) % 12 + 1
                edit_end_browse = edit_end_browse.replace(year=ny, month=nm, day=1)
                rebuild_edit_end_cal()
                page.update()

            def pick_end_d(dt_val: datetime):
                nonlocal edit_end_dt, edit_end_cal_open
                edit_end_dt = dt_val
                edit_end_date_text.value = edit_end_dt.strftime("%d %b %Y")
                edit_end_cal_open = False
                edit_end_cal_box.visible = False
                page.update()

            c_rows = [
                ft.Row(
                    [
                        ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, icon_size=16, on_click=lambda _: shift_end_m(-1)),
                        ft.Text(edit_end_browse.strftime("%B %Y"), weight=ft.FontWeight.BOLD, size=13, color=ft.Colors.RED_400),
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
                    is_s = ds == sel_s
                    dt_f = datetime(d_o.year, d_o.month, d_o.day)
                    r_c.append(
                        ft.Container(
                            width=34,
                            height=30,
                            bgcolor=ft.Colors.RED_400 if is_s else (theme_state["box"] if in_m else theme_state["surface"]),
                            border_radius=6,
                            alignment=ft.Alignment(0, 0),
                            on_click=lambda _, dp=dt_f: pick_end_d(dp),
                            content=ft.Text(
                                str(d_o.day),
                                size=11,
                                color=ft.Colors.BLACK
                                if is_s
                                else (get_text_color(theme_state["box"]) if in_m else get_subtext_color(theme_state["surface"])),
                            ),
                        )
                    )
                c_rows.append(ft.Row(r_c, alignment=ft.MainAxisAlignment.CENTER, spacing=4))
            edit_end_cal_box.content = ft.Column(c_rows, spacing=4)

        edit_end_date_selector_btn = ft.Container(
            padding=ft.Padding(left=12, right=12, top=8, bottom=8),
            bgcolor="#2a1616",
            border_radius=8,
            border=make_border(1.5, ft.Colors.RED_400),
            on_click=toggle_edit_end_cal,
            content=ft.Row([ft.Icon(ft.Icons.EVENT_BUSY_ROUNDED, color=ft.Colors.RED_400, size=16), edit_end_date_text], spacing=6, tight=True),
        )

        edit_end_section.content = ft.Column(
            [
                ft.Text("Select End Date or Quick Duration:", size=11, color=ft.Colors.RED_300),
                ft.Row([edit_end_date_selector_btn, edit_duration_row], spacing=10, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                edit_end_cal_box,
            ],
            spacing=6,
        )

        edit_is_recurring = (t_rec is not None and t_rec != "once")
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
            edit_days = {edit_dt.strftime("%a")}

        if t_cmonths:
            edit_months = {int(m.strip()) for m in t_cmonths.split(",") if m.strip().isdigit()}
        else:
            edit_months = {edit_dt.month} if t_rec == "yearly" else set(range(1, 13))

        edit_single_month = (t_rec == "yearly")
        edit_int_f = ft.TextField(
            label="Repeat Every X Days",
            value=str(t_int if (t_int and t_int > 0) else 2),
            width=160,
            on_focus=lambda _: set_typing(True),
            on_blur=lambda _: set_typing(False),
        )

        def execute_confirmed_delete(e):
            nonlocal expanded_edit_task_id
            expanded_edit_task_id = None
            set_typing(False)
            remove_task_db(tid)
            show_message(f"🗑️ Deleted '{t_name}'")
            if current_view_index == 0:
                refresh_schedule_view()
            elif current_view_index == 2:
                load_backlog_view()
            elif current_view_index == 4:
                load_all_tasks_view()

        def show_delete_safeguard(e):
            delete_confirm_row.visible = True
            page.update()

        def hide_delete_safeguard(e):
            delete_confirm_row.visible = False
            page.update()

        delete_confirm_row = ft.Container(
            visible=False,
            padding=10,
            bgcolor="#2a1212",
            border_radius=8,
            border=make_border(1.5, ft.Colors.RED_400),
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.RED_400, size=18),
                    ft.Text(
                        f"Delete '{t_name}'?",
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.RED_200,
                    ),
                    ft.Container(expand=True),
                    ft.TextButton(
                        content=ft.Text("Yes, Delete", color=ft.Colors.RED_400, weight=ft.FontWeight.BOLD, size=12),
                        on_click=execute_confirmed_delete,
                    ),
                    ft.TextButton(
                        content=ft.Text("Cancel", color=ft.Colors.GREY_300, size=12),
                        on_click=hide_delete_safeguard,
                    ),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
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
                edit_date_text.value = edit_dt.strftime("%d %b %Y")
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
                            bgcolor=theme_state["accent"] if is_s else (theme_state["box"] if in_m else theme_state["surface"]),
                            border_radius=6,
                            alignment=ft.Alignment(0, 0),
                            on_click=lambda _, dp=dt_f: pick_d(dp),
                            content=ft.Text(
                                str(d_o.day),
                                size=11,
                                color=get_text_color(theme_state["accent"])
                                if is_s
                                else (get_text_color(theme_state["box"]) if in_m else get_subtext_color(theme_state["surface"])),
                            ),
                        )
                    )
                c_rows.append(ft.Row(r_c, alignment=ft.MainAxisAlignment.CENTER, spacing=6))
            edit_cal_box.content = ft.Column(c_rows, spacing=4)

        def toggle_edit_cal(e):
            nonlocal edit_cal_open, edit_cal_browse
            edit_cal_open = not edit_cal_open
            if edit_cal_open:
                edit_cal_browse = edit_dt.replace(day=1)
                rebuild_edit_cal()
            edit_cal_box.visible = edit_cal_open
            page.update()

        def rebuild_edit_rec():
            edit_rec_visuals.controls.clear()

            def e_pill(label: str, active: bool, fn):
                return ft.Container(
                    padding=ft.Padding(left=12, right=12, top=6, bottom=6),
                    bgcolor=theme_state["accent"] if active else theme_state["surface"],
                    border_radius=8,
                    border=make_border(1.5, theme_state["accent"] if active else get_border_color(theme_state["surface"])),
                    on_click=fn,
                    content=ft.Text(
                        label,
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color=get_text_color(theme_state["accent"]) if active else get_subtext_color(theme_state["surface"]),
                    ),
                )

            def set_e_rec(state: bool):
                nonlocal edit_is_recurring
                edit_is_recurring = state
                rebuild_edit_rec()
                page.update()

            def set_e_freq(f_val: str):
                nonlocal edit_freq
                edit_freq = f_val
                rebuild_edit_rec()
                page.update()

            edit_rec_visuals.controls.append(
                ft.Row(
                    [
                        e_pill("No Recurrence (Once)", not edit_is_recurring, lambda _: set_e_rec(False)),
                        e_pill("Recurring Habit", edit_is_recurring, lambda _: set_e_rec(True)),
                    ],
                    spacing=8,
                    wrap=True,
                )
            )

            if not edit_is_recurring:
                return

            edit_rec_visuals.controls.append(
                ft.Row(
                    [
                        e_pill("Weekly / Daily", edit_freq == "weekly", lambda _: set_e_freq("weekly")),
                        e_pill("Monthly / Yearly", edit_freq == "monthly", lambda _: set_e_freq("monthly")),
                        e_pill("Every X Days", edit_freq == "custom_interval", lambda _: set_e_freq("custom_interval")),
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
                        if d_code in edit_days and len(edit_days) > 1:
                            edit_days.remove(d_code)
                        else:
                            edit_days.add(d_code)
                        rebuild_edit_rec()
                        page.update()

                    b_row.controls.append(
                        ft.Container(
                            width=38,
                            height=38,
                            border_radius=19,
                            bgcolor=theme_state["accent"] if lit else theme_state["surface"],
                            border=make_border(1.5, theme_state["accent"] if lit else get_border_color(theme_state["surface"])),
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
                        edit_days.add(edit_dt.strftime("%a"))
                    else:
                        for d_k, _ in week_days_list:
                            edit_days.add(d_k)
                    rebuild_edit_rec()
                    page.update()

                edit_rec_visuals.controls.append(
                    ft.Row(
                        [b_row, e_pill("Daily (All 7)", all_7, toggle_e_daily)],
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
                                width=50,
                                height=42,
                                bgcolor=theme_state["surface_card"] if has_m else theme_state["surface"],
                                border_radius=6,
                                border=make_border(1.5 if has_m else 1, theme_state["accent"] if has_m else get_border_color(theme_state["surface"])),
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

        rebuild_edit_rec()

        def save_task_changes(e):
            nonlocal expanded_edit_task_id
            if not edit_name_f.value or not edit_name_f.value.strip():
                show_message("Task name cannot be empty!")
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
            u_val = edit_unit_f.value.strip() if (edit_unit_f.value and edit_unit_f.value.strip()) else None
            final_end_date = edit_end_dt.strftime("%Y-%m-%d") if (edit_is_recurring and has_edit_end) else None
            final_edit_rem = get_edit_time() if has_edit_rem else None

            update_task_db(
                task_id=tid,
                name=edit_name_f.value.strip(),
                category=edit_cat_f.value.strip() if edit_cat_f.value else "General",
                time_frame=t_tf,
                target_date=edit_dt.strftime("%Y-%m-%d") if t_tf == "day" else None,
                recurrence_type=final_rec,
                interval_days=int_val,
                end_date=final_end_date,
                note=edit_note_f.value.strip() if edit_note_f.value else None,
                unit=u_val,
                custom_days=ord_days,
                custom_months=ord_months,
                reminder_time=final_edit_rem,
            )
            expanded_edit_task_id = None
            set_typing(False)
            show_message("✏️ Task updated!")
            if current_view_index == 0:
                refresh_schedule_view()
            elif current_view_index == 2:
                load_backlog_view()
            elif current_view_index == 4:
                load_all_tasks_view()

        top_delete_btn = ft.FilledButton(
            content=ft.Text("Delete Task", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            icon=ft.Icons.DELETE_FOREVER_ROUNDED,
            bgcolor=ft.Colors.RED_900,
            on_click=show_delete_safeguard,
        )

        return ft.Container(
            padding=14,
            bgcolor=theme_state["box"],
            border_radius=8,
            border=make_border(1.5, theme_state["accent"]),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Edit Task Details", size=14, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                            top_delete_btn,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    delete_confirm_row,
                    ft.Divider(color=get_border_color(theme_state["box"]), height=6),
                    ft.Row([edit_name_f, edit_cat_f, edit_unit_f], spacing=10, wrap=True),
                    edit_note_f,
                    ft.Row(
                        [
                            ft.Text("Start / Target Date:", size=12, color=get_subtext_color(theme_state["box"])),
                            ft.Container(
                                padding=ft.Padding(left=12, right=12, top=6, bottom=6),
                                bgcolor=theme_state["surface_card"],
                                border_radius=8,
                                border=make_border(1.5, theme_state["accent"]),
                                on_click=toggle_edit_cal,
                                content=ft.Row(
                                    [
                                        ft.Icon(ft.Icons.CALENDAR_MONTH_ROUNDED, color=theme_state["accent"], size=15),
                                        edit_date_text,
                                    ],
                                    spacing=6,
                                    tight=True,
                                ),
                            ),
                        ],
                        spacing=10,
                    ),
                    edit_cal_box,
                    edit_rec_visuals,
                    ft.Divider(color=get_border_color(theme_state["box"]), height=6),
                    edit_rem_check,
                    edit_rem_box,
                    ft.Divider(color=get_border_color(theme_state["box"]), height=6),
                    edit_end_checkbox,
                    edit_end_section,
                    ft.Divider(color=get_border_color(theme_state["box"]), height=6),
                    ft.Row(
                        [
                            ft.FilledButton(
                                content=ft.Text("Save Changes", color=get_text_color(theme_state["accent"]), weight=ft.FontWeight.BOLD),
                                icon=ft.Icons.CHECK,
                                bgcolor=theme_state["accent"],
                                on_click=save_task_changes,
                            ),
                            ft.TextButton(
                                content=ft.Text("Collapse / Cancel"),
                                on_click=lambda _: toggle_inline_edit(tid),
                            ),
                        ],
                        spacing=10,
                    ),
                ],
                spacing=10,
            ),
        )
# >>> SUB-SECTION A5b END: INLINE CARD EXPANSION EDITOR <<<
# =============================================================================
# >>> SECTION A5 END: VIEW 2 - ADD TASK & EDIT TASK MODAL FORM <<<
# =============================================================================

# =============================================================================
# >>> SECTION A6 START: VIEW 3 - BACKLOG QUEUE <<<
# =============================================================================
    def load_backlog_view():
        backlog_view.controls.clear()
        tasks = fetch_backlog_tasks()

        top_row = ft.Row(
            [
                ft.Text("Backlog Queue", size=18, weight=ft.FontWeight.BOLD, color=theme_state["accent"]),
                ft.Text(f"{len(tasks)} unscheduled task(s)", size=12, color=get_subtext_color(theme_state["bg"])),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        backlog_view.controls.append(top_row)
        backlog_view.controls.append(ft.Divider(color=get_border_color(theme_state["bg"]), height=5))

        if not tasks:
            backlog_view.controls.append(
                ft.Text(
                    "Backlog is empty! Create tasks with 'Send to Backlog' checked to stash them here.",
                    italic=True,
                    color=get_subtext_color(theme_state["bg"]),
                    size=13,
                )
            )
            page.update()
            return

        for t in tasks:
            task_id, name, category, _, _, recurrence, _, _, _, note, unit = t[:11]
            t_rem = t[13] if len(t) > 13 else None
            is_expanded = (expanded_edit_task_id == task_id)

            def make_schedule_btn(days_offset: int, label: str):
                target_dt = datetime.now() + timedelta(days=days_offset)
                dt_str = target_dt.strftime("%Y-%m-%d")
                return ft.FilledButton(
                    content=ft.Text(label, size=11, weight=ft.FontWeight.BOLD, color=get_text_color(theme_state["accent"])),
                    bgcolor=theme_state["accent"],
                    height=28,
                    on_click=lambda _, tid=task_id, ds=dt_str: (
                        schedule_backlog_task_db(tid, ds),
                        show_message(f"Scheduled '{name}' for {label}!"),
                        load_backlog_view(),
                    ),
                )

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

            desc_parts = [category or "General"]
            if note:
                desc_parts.append(f"📝 {note}")
            if t_rem:
                desc_parts.append(f"🔔 {format_time_display(t_rem)}")
            desc_text = " • ".join(desc_parts)

            card_children = [
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(name, weight=ft.FontWeight.BOLD, size=14, color=get_text_color(theme_state["surface_card"])),
                                ft.Text(desc_text, size=11, color=get_subtext_color(theme_state["surface_card"])),
                            ],
                            expand=True,
                            spacing=2,
                        ),
                        ft.Row(
                            [
                                make_schedule_btn(0, "Today"),
                                make_schedule_btn(1, "Tmrw"),
                                edit_btn,
                            ],
                            spacing=6,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            ]

            if is_expanded:
                card_children.append(build_inline_edit_drawer(task_id))

            backlog_view.controls.append(
                ft.Container(
                    content=ft.Column(card_children, spacing=8),
                    padding=12 if is_expanded else 10,
                    bgcolor=theme_state["surface_card"] if is_expanded else theme_state["box"],
                    border_radius=8,
                    border=make_border(
                        1.5 if is_expanded else 1,
                        theme_state["accent"] if is_expanded else get_border_color(theme_state["box"]),
                    ),
                )
            )

        page.update()
# =============================================================================
# >>> SECTION A6 END: VIEW 3 - BACKLOG QUEUE <<<
# =============================================================================

# =============================================================================
# >>> SECTION A7 START: VIEW 4 - HABITS & DATA DASHBOARD <<<
# =============================================================================
    active_heatmap_scope = "global"
    active_heatmap_identifier = None

    scope_dropdown = ft.Dropdown(
        label="Filter By",
        width=200,
        options=[
            ft.dropdown.Option(key="global", text="Everything (Global)"),
            ft.dropdown.Option(key="habit", text="Individual Habit"),
            ft.dropdown.Option(key="category", text="Category"),
        ],
        value="global",
    )

    target_dropdown = ft.Dropdown(label="Select Habit / Category", width=240, visible=False)

    habit_analytics_state = {
        "start": None,
        "end": None,
        "chart_style": "line",
        "time_bucket": "daily",
        "weekly_agg_mode": "avg",
        "avg_mode": "running",
        "goal_type": "max",
        "goal_end_date": None,
    }

    def sync_target_dropdown_options():
        nonlocal active_heatmap_identifier
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
        sync_target_dropdown_options()
        load_habits_dashboard()

    def on_target_change(e):
        nonlocal active_heatmap_identifier
        active_heatmap_identifier = target_dropdown.value
        habit_analytics_state["start"] = None
        habit_analytics_state["end"] = None
        load_habits_dashboard()

    scope_dropdown.on_select = on_scope_change
    scope_dropdown.on_change = on_scope_change
    target_dropdown.on_select = on_target_change
    target_dropdown.on_change = on_target_change

    def build_anki_heatmap_widget(data: dict, is_daily_mode: bool, today_str: str) -> ft.Control:
        # Dynamic 5-level ramp calculated from current surface and accent colors
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
        start_dt = datetime.strptime(sorted_dates[0], "%Y-%m-%d")
        end_dt = max(datetime.strptime(sorted_dates[-1], "%Y-%m-%d"), datetime.now())

        start_dt = start_dt - timedelta(days=start_dt.weekday())
        end_dt = end_dt + timedelta(days=(6 - end_dt.weekday()))

        sub_col = get_subtext_color(theme_state["box"])
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

                if not is_daily_mode and due_cnt == 0:
                    cell = ft.Container(
                        width=15,
                        height=15,
                        alignment=ft.Alignment(0, 0),
                        tooltip=f"{ui_d}: Not scheduled",
                        content=ft.Container(
                            width=4,
                            height=4,
                            border_radius=2,
                            bgcolor=theme_state["accent"] if is_today else theme_state["surface"],
                        ),
                    )
                else:
                    tile_color = colors.get(info["intensity"], colors[0])
                    status_lbl = (
                        f"{done_cnt} done / {due_cnt} due"
                        if active_heatmap_scope == "global"
                        else ("Completed" if done_cnt > 0 else ("Missed" if d_key < today_str and due_cnt > 0 else "Scheduled"))
                    )
                    cell = ft.Container(
                        width=15,
                        height=15,
                        bgcolor=tile_color,
                        border_radius=3,
                        border=make_border(1.5, theme_state["accent"]) if is_today else None,
                        tooltip=f"{ui_d}: {status_lbl}",
                    )

                col_controls.append(cell)
                curr += timedelta(days=1)

            weeks_columns.append(ft.Column(col_controls, spacing=3))

        grid_row = ft.Row(
            [
                day_labels_col,
                ft.Row(weeks_columns, spacing=3, scroll=ft.ScrollMode.AUTO),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        legend_items = [ft.Text("Less", size=10, color=sub_col)]
        for lvl in range(5):
            legend_items.append(
                ft.Container(width=12, height=12, bgcolor=colors[lvl], border_radius=2)
            )
        legend_items.append(ft.Text("More", size=10, color=sub_col))

        if not is_daily_mode:
            legend_items.insert(0, ft.Text("· Unscheduled   ", size=10, color=sub_col))

        legend_row = ft.Row(legend_items, spacing=4, alignment=ft.MainAxisAlignment.END)

        return ft.Column([grid_row, legend_row], spacing=8)

    def load_habits_dashboard():
        sync_target_dropdown_options()
        habits_view.controls.clear()

        filter_shelf = build_shelf(
            "1. Filter Scope",
            "Inspect all activity or isolate a specific recurring habit (Daily, Weekly, Monthly) or Category.",
            ft.Row([scope_dropdown, target_dropdown], spacing=12, wrap=True),
        )
        habits_view.controls.append(filter_shelf)

        if active_heatmap_scope == "habit" and active_heatmap_identifier:
            earliest_b, latest_b = get_habit_date_bounds(active_heatmap_identifier)
            ui_earliest = format_ui_date(earliest_b, "numeric")
            ui_latest = format_ui_date(latest_b, "numeric")

            start_field = ft.TextField(
                label="From (DD-MM-YYYY)",
                value=habit_analytics_state["start"] or ui_earliest,
                width=145,
                text_size=12,
                on_focus=lambda _: set_typing(True),
                on_blur=lambda _: set_typing(False),
            )
            end_field = ft.TextField(
                label="To (DD-MM-YYYY)",
                value=habit_analytics_state["end"] or ui_latest,
                width=145,
                text_size=12,
                on_focus=lambda _: set_typing(True),
                on_blur=lambda _: set_typing(False),
            )

            def apply_date_range(e):
                habit_analytics_state["start"] = start_field.value.strip() or None
                habit_analytics_state["end"] = end_field.value.strip() or None
                set_typing(False)
                load_habits_dashboard()

            def reset_date_range(e):
                habit_analytics_state["start"] = None
                habit_analytics_state["end"] = None
                set_typing(False)
                load_habits_dashboard()

            apply_btn = ft.FilledButton(
                content=ft.Text("Inspect Period", size=11, color=get_text_color(theme_state["accent"])),
                on_click=apply_date_range,
                bgcolor=theme_state["accent"],
                height=36,
            )
            reset_btn = ft.TextButton(
                content=ft.Text("Reset Full Span", size=11, color=get_subtext_color(theme_state["box"])),
                on_click=reset_date_range,
            )

            habits_view.controls.append(
                build_shelf(
                    "Custom Date Range Inspector",
                    f"Active span for '{active_heatmap_identifier}': {format_ui_date(earliest_b, 'short_text')} to {format_ui_date(latest_b, 'short_text')}",
                    ft.Row(
                        [start_field, end_field, apply_btn, reset_btn],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        wrap=True,
                    ),
                )
            )

        stats = get_streak_and_stats(
            active_heatmap_scope,
            active_heatmap_identifier,
            start_override=habit_analytics_state["start"],
            end_override=habit_analytics_state["end"],
        )

        def make_stat_card(label: str, main_val: str, is_accent: bool = False):
            return ft.Container(
                padding=12,
                bgcolor=theme_state["surface_card"] if is_accent else theme_state["surface"],
                border_radius=8,
                expand=True,
                border=make_border(1, theme_state["accent"] if is_accent else get_border_color(theme_state["surface"])),
                content=ft.Column(
                    [
                        ft.Text(label, size=11, color=get_subtext_color(theme_state["surface"])),
                        ft.Text(
                            main_val,
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=theme_state["accent"] if is_accent else get_text_color(theme_state["surface"]),
                        ),
                    ],
                    spacing=2,
                ),
            )

        stats_row = ft.Row(
            [
                make_stat_card("Current Streak", f"{stats['current_streak']}", is_accent=True),
                make_stat_card("Best Streak", f"{stats['longest_streak']}"),
                make_stat_card("Completion Rate", f"{stats['completion_rate']}%"),
                make_stat_card("Completed / Missed", f"{stats['completed_days']} done  •  {stats['missed_days']} missed"),
            ],
            spacing=10,
        )

        habits_view.controls.append(
            build_shelf(
                "2. Streak & Consistency",
                "Counts only scheduled occurrences up to today (Completed vs. Missed).",
                stats_row,
            )
        )

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
                else "Non-daily schedule: full tiles mark scheduled days, subtle dots (·) mark unscheduled days."
            )
            habits_view.controls.append(
                build_shelf(
                    heatmap_title,
                    heatmap_subtitle,
                    build_anki_heatmap_widget(data, is_daily_mode, today_str),
                )
            )

        # 4. Unit Progression & Multi-Goal Engine
        if active_heatmap_scope == "habit" and active_heatmap_identifier:
            unit_name, unit_logs = get_habit_unit_logs(
                active_heatmap_identifier,
                start_override=habit_analytics_state["start"],
                end_override=habit_analytics_state["end"],
            )
            if unit_name:
                goals_list = get_habit_goals_list(active_heatmap_identifier)

                def set_chart_style(style_name: str):
                    habit_analytics_state["chart_style"] = style_name
                    load_habits_dashboard()

                def set_time_bucket(bucket_name: str):
                    habit_analytics_state["time_bucket"] = bucket_name
                    load_habits_dashboard()

                def set_weekly_agg(agg_name: str):
                    habit_analytics_state["weekly_agg_mode"] = agg_name
                    load_habits_dashboard()

                def set_avg_mode(mode_name: str):
                    habit_analytics_state["avg_mode"] = mode_name
                    load_habits_dashboard()

                curr_style = habit_analytics_state.get("chart_style", "line")
                curr_bucket = habit_analytics_state.get("time_bucket", "daily")
                curr_wk_agg = habit_analytics_state.get("weekly_agg_mode", "avg")
                curr_avg = habit_analytics_state.get("avg_mode", "running")

                def make_toggle_chip(label: str, is_active: bool, active_col: str, click_fn):
                    return ft.Container(
                        padding=ft.Padding(left=10, right=10, top=5, bottom=5),
                        bgcolor=active_col if is_active else theme_state["surface"],
                        border_radius=6,
                        border=make_border(1, active_col if is_active else get_border_color(theme_state["surface"])),
                        on_click=click_fn,
                        content=ft.Text(
                            label,
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color=get_text_color(active_col) if is_active else get_subtext_color(theme_state["surface"]),
                        ),
                    )

                toolbar_items = [
                    ft.Text("Style:", size=11, color=get_subtext_color(theme_state["box"])),
                    make_toggle_chip("Line", curr_style == "line", theme_state["accent"], lambda _: set_chart_style("line")),
                    make_toggle_chip("Pillars", curr_style == "pillars", theme_state["accent"], lambda _: set_chart_style("pillars")),
                    ft.Container(width=8),
                    ft.Text("Group:", size=11, color=get_subtext_color(theme_state["box"])),
                    make_toggle_chip("Daily", curr_bucket == "daily", theme_state["accent"], lambda _: set_time_bucket("daily")),
                    make_toggle_chip("By Week", curr_bucket == "weekly", theme_state["accent"], lambda _: set_time_bucket("weekly")),
                ]

                if curr_bucket == "weekly":
                    toolbar_items.extend(
                        [
                            ft.Container(width=4),
                            make_toggle_chip("Wk Avg", curr_wk_agg == "avg", "#A78BFA", lambda _: set_weekly_agg("avg")),
                            make_toggle_chip("Wk Total", curr_wk_agg == "sum", "#A78BFA", lambda _: set_weekly_agg("sum")),
                        ]
                    )

                toolbar_items.extend(
                    [
                        ft.Container(width=8),
                        ft.Text("Avg Line:", size=11, color=get_subtext_color(theme_state["box"])),
                        make_toggle_chip("Running", curr_avg == "running", "#38BDF8", lambda _: set_avg_mode("running")),
                        make_toggle_chip("Weekly (Session)", curr_avg == "weekly", "#38BDF8", lambda _: set_avg_mode("weekly")),
                        make_toggle_chip("Hide", curr_avg == "off", theme_state["surface"], lambda _: set_avg_mode("off")),
                    ]
                )

                style_toggle_row = ft.Row(
                    toolbar_items,
                    spacing=6,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )

                goal_type_dd = ft.Dropdown(
                    label="Goal Type",
                    width=185,
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
                    width=130,
                    text_size=12,
                    on_focus=lambda _: set_typing(True),
                    on_blur=lambda _: set_typing(False),
                )

                goal_end_input = ft.TextField(
                    label="Target Window (DD-MM-YYYY)",
                    value=habit_analytics_state["goal_end_date"] or "",
                    hint_text="Optional deadline",
                    width=175,
                    text_size=12,
                    on_focus=lambda _: set_typing(True),
                    on_blur=lambda _: set_typing(False),
                )

                def set_goal_window_preset(days_delta: int = 0, months_delta: int = 0):
                    base_dt = datetime.now()
                    if months_delta > 0:
                        nm = base_dt.month + months_delta
                        ny = base_dt.year + (nm - 1) // 12
                        nm = (nm - 1) % 12 + 1
                        end_dt = base_dt.replace(year=ny, month=nm, day=min(base_dt.day, calendar.monthrange(ny, nm)[1]))
                    else:
                        end_dt = base_dt + timedelta(days=days_delta)
                    habit_analytics_state["goal_end_date"] = end_dt.strftime("%d-%m-%Y")
                    goal_end_input.value = habit_analytics_state["goal_end_date"]
                    page.update()

                window_chips_row = ft.Row(
                    [
                        ft.Text("Window:", size=11, color=get_subtext_color(theme_state["box"])),
                        ft.TextButton(content=ft.Text("2 Weeks", size=11), on_click=lambda _: set_goal_window_preset(days_delta=14)),
                        ft.TextButton(content=ft.Text("1 Month", size=11), on_click=lambda _: set_goal_window_preset(months_delta=1)),
                        ft.TextButton(content=ft.Text("3 Months", size=11), on_click=lambda _: set_goal_window_preset(months_delta=3)),
                        ft.TextButton(content=ft.Text("No Limit", size=11), on_click=lambda _: (habit_analytics_state.update({"goal_end_date": None}), setattr(goal_end_input, "value", ""), page.update())),
                    ],
                    spacing=2,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )

                def add_new_goal_click(e):
                    try:
                        t_val = float(target_goal_input.value.strip())
                    except (ValueError, AttributeError):
                        show_message("Please enter a valid number for your goal!")
                        return

                    iso_end = parse_ui_date_to_iso(goal_end_input.value) if goal_end_input.value else None
                    today_iso = datetime.now().strftime("%Y-%m-%d")
                    add_habit_goal_db(
                        habit_name=active_heatmap_identifier,
                        goal_type=goal_type_dd.value or "max",
                        target_value=t_val,
                        start_date=today_iso,
                        end_date=iso_end,
                    )
                    habit_analytics_state["goal_end_date"] = None
                    set_typing(False)
                    show_message("🎯 New goal added to your progression tracker!")
                    load_habits_dashboard()

                add_goal_btn = ft.FilledButton(
                    content=ft.Text("Add Goal", color=get_text_color(theme_state["accent"]), weight=ft.FontWeight.BOLD),
                    icon=ft.Icons.ADD_TASK_ROUNDED,
                    on_click=add_new_goal_click,
                    bgcolor=theme_state["accent"],
                    height=38,
                )

                goals_builder_col = ft.Column(
                    [
                        ft.Row(
                            [goal_type_dd, target_goal_input, goal_end_input, add_goal_btn],
                            spacing=10,
                            wrap=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        window_chips_row,
                    ],
                    spacing=4,
                )

                goals_cards_col = ft.Column(spacing=6)
                type_labels = {
                    "max": "Peak / Max Goal",
                    "weekly_avg": "Weekly Average Goal",
                    "all_time_avg": "Overall Average Goal",
                }
                for g in goals_list:
                    gid = g["id"]
                    is_ach = g["achieved"]
                    s_lbl = format_ui_date(g["start_date"], "short_text")
                    e_lbl = format_ui_date(g["end_date"], "short_text") if g["end_date"] else "Open"
                    status_text = (
                        f"✓ Achieved on {format_ui_date(g['achieved_date'], 'short_text')}"
                        if is_ach
                        else f"Active Window: {s_lbl} → {e_lbl}"
                    )

                    def remove_goal_click(e, target_gid=gid):
                        delete_habit_goal_db(target_gid)
                        load_habits_dashboard()

                    goals_cards_col.controls.append(
                        ft.Container(
                            padding=ft.Padding(left=12, right=8, top=6, bottom=6),
                            bgcolor=theme_state["surface_card"] if is_ach else theme_state["surface"],
                            border_radius=6,
                            border=make_border(1, theme_state["accent"] if is_ach else get_border_color(theme_state["surface"])),
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.EMOJI_EVENTS_ROUNDED if is_ach else ft.Icons.FLAG_ROUNDED,
                                        color=theme_state["accent"] if is_ach else "#C084FC",
                                        size=16,
                                    ),
                                    ft.Text(
                                        f"{type_labels.get(g['goal_type'], 'Goal')}: {g['target_value']:g} {unit_name}",
                                        size=12,
                                        weight=ft.FontWeight.BOLD,
                                        color=theme_state["accent"] if is_ach else get_text_color(theme_state["surface"]),
                                    ),
                                    ft.Text(f"({status_text})", size=11, color=get_subtext_color(theme_state["surface"])),
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

                if not unit_logs:
                    habits_view.controls.append(
                        build_shelf(
                            f"4. Unit Progression & Goals ({unit_name})",
                            "Set Peak, Weekly Average, or Overall Average goals with custom completion windows.",
                            ft.Column(
                                [
                                    goals_builder_col,
                                    goals_cards_col if goals_list else ft.Container(),
                                    ft.Divider(color=get_border_color(theme_state["box"]), height=10),
                                    ft.Text(
                                        f"No {unit_name} values logged in this period yet. Check off '{active_heatmap_identifier}' on your schedule to log units!",
                                        italic=True,
                                        color=get_subtext_color(theme_state["box"]),
                                        size=12,
                                    ),
                                ],
                                spacing=10,
                            ),
                        )
                    )
                else:
                    chart_img = build_area_line_chart_image(
                        unit_name,
                        unit_logs,
                        chart_style=curr_style,
                        avg_mode=curr_avg,
                        time_bucket=curr_bucket,
                        weekly_agg_mode=curr_wk_agg,
                        goals_list=goals_list,
                    )

                    habits_view.controls.append(
                        build_shelf(
                            f"4. Unit Progression & Goals ({unit_name})",
                            f"Accent: Logged {unit_name}  •  Sky-Blue (Right): Average Curve  •  Violet Dashed (Left): Goal Benchmark",
                            ft.Column(
                                [
                                    style_toggle_row,
                                    chart_img,
                                    ft.Divider(color=get_border_color(theme_state["box"]), height=10),
                                    ft.Text("Goal Progression & History", size=13, weight=ft.FontWeight.BOLD, color=get_text_color(theme_state["box"])),
                                    goals_builder_col,
                                    goals_cards_col,
                                ],
                                spacing=10,
                            ),
                        )
                    )

        trends = get_habit_trend_data(active_heatmap_scope, active_heatmap_identifier)
        if trends:
            max_val = max(trends.values()) if trends.values() else 1
            if max_val <= 0:
                max_val = 1
            trend_col = ft.Column(spacing=6)
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
# >>> SECTION A9 START: KEYBOARD NAVIGATION & APP ENTRY <<<
# =============================================================================
    def on_keyboard(e: ft.KeyboardEvent):
        nonlocal selected_task_idx
        if e.key == "Escape":
            if unit_popup_banner.visible:
                close_unit_popup()
                return
            if getattr(settings_dialog, "open", False):
                settings_dialog.open = False
                page.update()
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
            elif current_view_mode == "day" and current_day_tasks:
                if e.key == "Arrow Down":
                    selected_task_idx = (selected_task_idx + 1) % len(current_day_tasks)
                    refresh_schedule_view()
                elif e.key == "Arrow Up":
                    selected_task_idx = (selected_task_idx - 1) % len(current_day_tasks)
                    refresh_schedule_view()
                elif e.key in ["Enter", " "]:
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

    # Window Action Handlers
    def win_minimize(e):
        try:
            page.window.minimized = True
            page.update()
        except Exception:
            pass

    def win_maximize(e):
        try:
            is_max = getattr(page.window, "maximized", False)
            page.window.maximized = not is_max
            page.update()
        except Exception:
            pass

    def win_close(e):
        try:
            page.window.close()
        except Exception:
            pass
        sys.exit(0)

    sub_c = get_subtext_color(theme_state["bg"])

    def make_clean_win_btn(icon_data, on_click, is_close=False):
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
            tooltip="Close" if is_close else None,
        )

    window_controls_cluster = ft.Row(
        [
            settings_gear_btn,
            ft.Container(width=4),
            make_clean_win_btn(ft.Icons.REMOVE_ROUNDED, win_minimize),
            make_clean_win_btn(ft.Icons.CROP_SQUARE_ROUNDED, win_maximize),
            make_clean_win_btn(ft.Icons.CLOSE_ROUNDED, win_close, is_close=True),
        ],
        spacing=2,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # Top Header Bar: Increased top padding so symbols breathe and sit naturally down from edge
    top_header_bar = ft.Container(
      padding=ft.Padding(left=20, right=10, top=10, bottom=6),
      content=ft.Row(
          [
              ft.WindowDragArea(
                  expand=True,
                  content=ft.Row(
                      [
                          ft.Container(width=160),
                          top_nav_row,
                          ft.Container(expand=True),
                      ],
                      alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                      vertical_alignment=ft.CrossAxisAlignment.CENTER,
                  ),
              ),
              window_controls_cluster,
          ],
          alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
          vertical_alignment=ft.CrossAxisAlignment.CENTER,
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
# >>> SECTION A9 END: KEYBOARD NAVIGATION & APP ENTRY <<<
# =============================================================================
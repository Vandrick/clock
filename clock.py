import sys
import math
import time
import calendar
import warnings
from datetime import datetime

import pygame

try:
    from pygame._sdl2.video import Window
    SDL2_WINDOW_AVAILABLE = True
except Exception:
    Window = None
    SDL2_WINDOW_AVAILABLE = False


START_WIDTH = 700
START_HEIGHT = 760
FPS = 60
TITLE = "Clock / Calendar"

BG_COLOR = (20, 22, 26)
PANEL_COLOR = (35, 38, 45)
FACE_COLOR = (28, 31, 37)
TEXT_COLOR = (235, 235, 235)
SUBTEXT_COLOR = (180, 185, 195)
ACCENT_COLOR = (95, 170, 255)
SECOND_COLOR = (255, 110, 110)
HOUR_COLOR = (245, 245, 245)
MINUTE_COLOR = (180, 220, 255)
GRID_COLOR = (70, 75, 88)
BUTTON_ON = (70, 170, 100)
BUTTON_OFF = (120, 120, 130)
BUTTON_TEXT = (255, 255, 255)
TODAY_COLOR = (255, 220, 100)
ARROW_BG = (55, 60, 70)
ARROW_HOVER = (75, 80, 95)
GRAYED_DAY_COLOR = (110, 115, 125)

TIMER_IDLE = "idle"
TIMER_RUNNING = "running"
TIMER_STOPPED = "stopped"


def clamp(value, low, high):
    return max(low, min(high, value))


def point_in_rect(pos, rect):
    return rect.collidepoint(pos)


def draw_text(surface, text, font, color, center=None, topleft=None):
    rendered = font.render(text, True, color)
    rect = rendered.get_rect()
    if center is not None:
        rect.center = center
    elif topleft is not None:
        rect.topleft = topleft
    surface.blit(rendered, rect)
    return rect


def month_add(year, month, delta):
    month_index = (year * 12 + (month - 1)) + delta
    new_year = month_index // 12
    new_month = (month_index % 12) + 1
    return new_year, new_month


class ClockCalendarApp:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((START_WIDTH, START_HEIGHT), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.running = True

        self.mode_order = ["analog", "digital", "calendar", "timer"]
        self.mode_index = 0

        now = datetime.now()
        self.calendar_year = now.year
        self.calendar_month = now.month

        self.always_on_top = False
        self.window_handle = None
        self.on_top_supported = False

        self.top_button_rect = pygame.Rect(0, 0, 0, 0)
        self.left_arrow_rect = pygame.Rect(0, 0, 0, 0)
        self.right_arrow_rect = pygame.Rect(0, 0, 0, 0)
        self.timer_button_rect = pygame.Rect(0, 0, 0, 0)

        self.cached_time_key = None
        self.cached_time_text = ""
        self.cached_ampm_text = ""
        self.cached_date_text = ""

        self.timer_state = TIMER_IDLE
        self.timer_elapsed = 0.0
        self.timer_start_perf = None

        self.layout_dirty = True
        self.layout_cache = {"top_bar_h": 42}
        self.last_window_size = self.screen.get_size()
        self.last_mode = self.mode

        self.view_surface = None
        self.view_surface_mode = None
        self.view_state_key = None

        self.init_window_handle()
        self.update_time_cache()
        self.resize_window_for_mode()

    @property
    def mode(self):
        return self.mode_order[self.mode_index]

    def init_window_handle(self):
        if SDL2_WINDOW_AVAILABLE:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    self.window_handle = Window.from_display_module()
                self.on_top_supported = True
            except Exception:
                self.window_handle = None
                self.on_top_supported = False

    def set_always_on_top(self, enabled):
        self.always_on_top = enabled
        if self.window_handle is not None:
            try:
                self.window_handle.always_on_top = enabled
            except Exception:
                self.on_top_supported = False

    def toggle_always_on_top(self):
        self.set_always_on_top(not self.always_on_top)

    def invalidate_layout(self):
        self.layout_dirty = True
        self.invalidate_view_cache()

    def invalidate_view_cache(self):
        self.view_surface = None
        self.view_surface_mode = None
        self.view_state_key = None

    def update_time_cache(self):
        now = datetime.now()
        time_key = (now.year, now.month, now.day, now.hour, now.minute, now.second)
        if time_key != self.cached_time_key:
            hour_12 = now.hour % 12
            if hour_12 == 0:
                hour_12 = 12
            self.cached_time_text = f"{hour_12}:{now.minute:02d}:{now.second:02d}"
            self.cached_ampm_text = "AM" if now.hour < 12 else "PM"
            self.cached_date_text = now.strftime("%A, %B %d, %Y")
            self.cached_time_key = time_key

    def get_timer_elapsed(self):
        if self.timer_state == TIMER_RUNNING and self.timer_start_perf is not None:
            return self.timer_elapsed + (time.perf_counter() - self.timer_start_perf)
        return self.timer_elapsed

    def get_timer_display_text(self):
        elapsed = self.get_timer_elapsed()
        total_seconds = int(elapsed)
        hundredths = int((elapsed - total_seconds) * 100)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{hundredths:02d}"

    def get_timer_button_text(self):
        if self.timer_state == TIMER_IDLE:
            return "Start"
        if self.timer_state == TIMER_RUNNING:
            return "Stop"
        return "Reset"

    def handle_timer_button(self):
        if self.timer_state == TIMER_IDLE:
            self.timer_state = TIMER_RUNNING
            self.timer_start_perf = time.perf_counter()
        elif self.timer_state == TIMER_RUNNING:
            if self.timer_start_perf is not None:
                self.timer_elapsed += time.perf_counter() - self.timer_start_perf
            self.timer_start_perf = None
            self.timer_state = TIMER_STOPPED
        else:
            self.timer_state = TIMER_IDLE
            self.timer_elapsed = 0.0
            self.timer_start_perf = None
        self.invalidate_view_cache()

    def get_topbar_metrics(self, width, height_reference):
        top_bar_h = max(42, height_reference // 14)
        outer_gap = max(10, height_reference // 30)
        outer_bottom = max(12, height_reference // 30)
        side_margin = max(16, width // 40)
        return top_bar_h, outer_gap, outer_bottom, side_margin

    def get_target_size_for_mode(self, mode, requested_width=None):
        current_w, current_h = self.screen.get_size()
        width = requested_width if requested_width is not None else current_w
        width = max(int(width), 420)

        # Use a stable reference height for spacing heuristics.
        ref_h = max(current_h, START_HEIGHT)

        top_bar_h, outer_gap, outer_bottom, side_margin = self.get_topbar_metrics(width, ref_h)

        if mode in ("analog", "calendar"):
            content_size = max(280, width - side_margin * 2)
            height = top_bar_h + outer_gap + content_size + outer_bottom
            return width, int(height)

        if mode == "digital":
            content_width = width - side_margin * 2
            panel_w = int(content_width * 0.84)

            # Use a large probe font, then shrink to fit width.
            base_size = 120
            time_font = pygame.font.SysFont("consolas", base_size, bold=True)
            ampm_font = pygame.font.SysFont("consolas", clamp(int(base_size * 0.34), 12, 64), bold=True)

            available_w = panel_w - 28
            time_surface = time_font.render(self.cached_time_text, True, TEXT_COLOR)
            ampm_surface = ampm_font.render(self.cached_ampm_text, True, ACCENT_COLOR)
            total_w = time_surface.get_width() + 14 + ampm_surface.get_width()

            while total_w > available_w and base_size > 12:
                base_size -= 1
                time_font = pygame.font.SysFont("consolas", base_size, bold=True)
                ampm_font = pygame.font.SysFont("consolas", clamp(int(base_size * 0.34), 12, 64), bold=True)
                time_surface = time_font.render(self.cached_time_text, True, TEXT_COLOR)
                ampm_surface = ampm_font.render(self.cached_ampm_text, True, ACCENT_COLOR)
                total_w = time_surface.get_width() + 14 + ampm_surface.get_width()

            date_font_size = clamp(int(base_size * 0.32), 14, 40)
            date_font = pygame.font.SysFont("arial", date_font_size, bold=True)
            date_surface = date_font.render(self.cached_date_text, True, SUBTEXT_COLOR)

            panel_h = max(time_surface.get_height() + 44, int(base_size * 1.35))
            date_h = date_surface.get_height() + 10
            inner_top = max(18, int(base_size * 0.35))
            gap = max(10, int(base_size * 0.20))
            inner_bottom = max(18, int(base_size * 0.28))

            content_h = inner_top + panel_h + gap + date_h + inner_bottom
            height = top_bar_h + outer_gap + content_h + outer_bottom
            return width, int(max(220, height))

        # timer
        content_width = width - side_margin * 2
        container_w = int(content_width * 0.75)
        
        base_size = 110
        timer_font = pygame.font.SysFont("consolas", base_size, bold=True)
        available_w = container_w - 40
        timer_surface = timer_font.render("00:00:00.00", True, TEXT_COLOR)
        
        while timer_surface.get_width() > available_w and base_size > 12:
            base_size -= 1
            timer_font = pygame.font.SysFont("consolas", base_size, bold=True)
            timer_surface = timer_font.render("00:00:00.00", True, TEXT_COLOR)
        
        button_font = pygame.font.SysFont("arial", clamp(int(base_size * 0.40), 14, 34), bold=True)
        button_surface = button_font.render("Reset", True, BUTTON_TEXT)
        
        panel_h = max(timer_surface.get_height() + 42, int(base_size * 1.25))
        button_h = max(button_surface.get_height() + 20, int(base_size * 0.85))
        gap = max(16, int(base_size * 0.45))
        
        inner_top = max(18, int(base_size * 0.30))
        inner_bottom = max(18, int(base_size * 0.30))
        
        content_h = inner_top + panel_h + gap + button_h + inner_bottom
        height = top_bar_h + outer_gap + content_h + outer_bottom
        return width, int(max(220, height))

    def apply_window_size(self, width, height):
        width = int(width)
        height = int(height)
        current_w, current_h = self.screen.get_size()
        if (width, height) != (current_w, current_h):
            self.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
            pygame.display.set_caption(TITLE)
            self.init_window_handle()
            self.set_always_on_top(self.always_on_top)
            self.invalidate_layout()

    def resize_window_for_mode(self):
        target_w, target_h = self.get_target_size_for_mode(self.mode)
        self.apply_window_size(target_w, target_h)

    def handle_mode_resize(self, requested_width, _requested_height):
        target_w, target_h = self.get_target_size_for_mode(self.mode, requested_width=requested_width)
        self.apply_window_size(target_w, target_h)

    def next_mode(self):
        self.mode_index = (self.mode_index + 1) % len(self.mode_order)
        self.resize_window_for_mode()
        self.invalidate_layout()

    def rebuild_layout_cache(self):
        width, height = self.screen.get_size()
        cache = {}

        top_bar_h, outer_gap, outer_bottom, side_margin = self.get_topbar_metrics(width, height)
        cache["top_bar_h"] = top_bar_h

        if self.mode in ("digital", "timer"):
            content_rect = pygame.Rect(
                side_margin,
                top_bar_h + outer_gap,
                width - side_margin * 2,
                height - top_bar_h - outer_gap - outer_bottom
            )
        else:
            size = min(width - side_margin * 2, height - top_bar_h - outer_gap - outer_bottom)
            content_rect = pygame.Rect(
                (width - size) // 2,
                top_bar_h + outer_gap,
                size,
                size
            )

        cache["content_rect"] = content_rect
        cache["content_radius"] = max(10, content_rect.width // 30)

        font_size = clamp(top_bar_h // 3, 16, 28)
        top_font = pygame.font.SysFont("arial", font_size, bold=True)
        label_surface = top_font.render("Always On Top", True, TEXT_COLOR)
        label_rect = label_surface.get_rect()
        label_rect.midleft = (16, top_bar_h // 2)

        button_w = max(96, width // 7)
        button_h = max(28, top_bar_h - 14)
        button_x = label_rect.right + 14
        button_y = (top_bar_h - button_h) // 2
        self.top_button_rect = pygame.Rect(button_x, button_y, button_w, button_h)

        cache["top_font"] = top_font
        cache["top_label_surface"] = label_surface
        cache["top_label_rect"] = label_rect
        cache["view_font"] = pygame.font.SysFont("arial", clamp(top_bar_h // 3, 14, 24), bold=True)
        cache["small_font"] = pygame.font.SysFont("arial", clamp(top_bar_h // 4, 12, 18)) if not self.on_top_supported else None

        if self.mode == "analog":
            inner = content_rect.inflate(-int(content_rect.width * 0.06), -int(content_rect.height * 0.06))
            cx, cy = inner.center
            radius = int(min(inner.width, inner.height) * 0.42)

            cache["analog_cx"] = cx
            cache["analog_cy"] = cy
            cache["analog_radius"] = radius
            cache["analog_number_font"] = pygame.font.SysFont("arial", clamp(content_rect.width // 16, 14, 44), bold=True)
            cache["analog_date_font"] = pygame.font.SysFont("arial", clamp(content_rect.width // 24, 12, 28), bold=True)
            cache["analog_border_thickness"] = max(2, content_rect.width // 150)
            cache["analog_center_outer"] = max(5, content_rect.width // 60)
            cache["analog_center_inner"] = max(2, content_rect.width // 110)
            cache["analog_hour_thickness"] = max(6, content_rect.width // 55)
            cache["analog_minute_thickness"] = max(4, content_rect.width // 80)
            cache["analog_second_thickness"] = max(2, content_rect.width // 160)

            tick_lines = []
            for i in range(60):
                angle = math.radians(i * 6 - 90)
                outer = radius - 6
                inner_tick = radius - (28 if i % 5 == 0 else 16)
                x1 = cx + math.cos(angle) * inner_tick
                y1 = cy + math.sin(angle) * inner_tick
                x2 = cx + math.cos(angle) * outer
                y2 = cy + math.sin(angle) * outer
                thickness = max(1, content_rect.width // 180) if i % 5 else max(2, content_rect.width // 120)
                color = TEXT_COLOR if i % 5 == 0 else GRID_COLOR
                tick_lines.append(((x1, y1), (x2, y2), thickness, color))

            number_positions = []
            for n in range(1, 13):
                angle = math.radians(n * 30 - 90)
                tx = cx + math.cos(angle) * (radius * 0.72)
                ty = cy + math.sin(angle) * (radius * 0.72)
                number_positions.append((str(n), (tx, ty)))

            cache["analog_tick_lines"] = tick_lines
            cache["analog_number_positions"] = number_positions

        elif self.mode == "digital":
            panel_w = int(content_rect.width * 0.84)
            available_w = panel_w - 28
            base_size = 120
            time_font = pygame.font.SysFont("consolas", base_size, bold=True)
            ampm_font = pygame.font.SysFont("consolas", clamp(int(base_size * 0.34), 12, 64), bold=True)

            time_surface = time_font.render(self.cached_time_text, True, TEXT_COLOR)
            ampm_surface = ampm_font.render(self.cached_ampm_text, True, ACCENT_COLOR)
            total_w = time_surface.get_width() + 14 + ampm_surface.get_width()

            while total_w > available_w and base_size > 12:
                base_size -= 1
                time_font = pygame.font.SysFont("consolas", base_size, bold=True)
                ampm_font = pygame.font.SysFont("consolas", clamp(int(base_size * 0.34), 12, 64), bold=True)
                time_surface = time_font.render(self.cached_time_text, True, TEXT_COLOR)
                ampm_surface = ampm_font.render(self.cached_ampm_text, True, ACCENT_COLOR)
                total_w = time_surface.get_width() + 14 + ampm_surface.get_width()

            date_font = pygame.font.SysFont("arial", clamp(int(base_size * 0.32), 14, 40), bold=True)
            date_surface = date_font.render(self.cached_date_text, True, SUBTEXT_COLOR)

            panel_h = max(time_surface.get_height() + 44, int(base_size * 1.35))
            date_h = date_surface.get_height() + 10

            panel_rect = pygame.Rect(0, 0, panel_w, panel_h)
            panel_rect.centerx = content_rect.centerx
            panel_rect.top = int(content_rect.top + max(18, base_size * 0.35))

            date_rect = pygame.Rect(0, 0, panel_w, date_h)
            date_rect.centerx = content_rect.centerx
            date_rect.top = panel_rect.bottom + max(10, int(base_size * 0.20))

            cache["digital_panel_rect"] = panel_rect
            cache["digital_date_rect"] = date_rect
            cache["digital_panel_radius"] = max(10, content_rect.width // 45)
            cache["digital_time_font"] = time_font
            cache["digital_ampm_font"] = ampm_font
            cache["digital_date_font"] = date_font

        elif self.mode == "calendar":
            title_font = pygame.font.SysFont("arial", clamp(content_rect.width // 14, 18, 44), bold=True)
            header_font = pygame.font.SysFont("arial", clamp(content_rect.width // 22, 14, 28), bold=True)
            day_font = pygame.font.SysFont("arial", clamp(content_rect.width // 20, 14, 30), bold=False)

            title_y = content_rect.top + int(content_rect.height * 0.08)
            title_text = f"{calendar.month_name[self.calendar_month]} {self.calendar_year}"

            arrow_size = max(34, content_rect.width // 10)
            arrow_y = title_y - arrow_size // 2

            self.left_arrow_rect = pygame.Rect(
                int(content_rect.left + content_rect.width * 0.08),
                int(arrow_y),
                arrow_size,
                arrow_size
            )
            self.right_arrow_rect = pygame.Rect(
                int(content_rect.right - content_rect.width * 0.08 - arrow_size),
                int(arrow_y),
                arrow_size,
                arrow_size
            )

            weekday_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
            grid_top = content_rect.top + int(content_rect.height * 0.22)
            grid_bottom = content_rect.bottom - int(content_rect.height * 0.06)
            grid_height = grid_bottom - grid_top

            month_weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(self.calendar_year, self.calendar_month)
            rows = len(month_weeks)
            cols = 7
            header_h = int(grid_height * 0.12)
            cell_h = (grid_height - header_h) / rows
            cell_w = content_rect.width / cols
            grid_y0 = grid_top + header_h

            weekday_positions = []
            for i, name in enumerate(weekday_names):
                x = content_rect.left + i * cell_w + cell_w / 2
                y = grid_top + header_h / 2
                weekday_positions.append((name, (x, y)))

            day_cells = []
            for row_idx, week in enumerate(month_weeks):
                for col_idx, day_date in enumerate(week):
                    cell_rect = pygame.Rect(
                        int(content_rect.left + col_idx * cell_w),
                        int(grid_y0 + row_idx * cell_h),
                        int(math.ceil(cell_w)),
                        int(math.ceil(cell_h))
                    )
                    day_cells.append((day_date, cell_rect))

            vlines = [((content_rect.left + c * cell_w, grid_y0), (content_rect.left + c * cell_w, grid_bottom)) for c in range(cols + 1)]
            hlines = [((content_rect.left, grid_y0 + r * cell_h), (content_rect.right, grid_y0 + r * cell_h)) for r in range(rows + 1)]

            cache["calendar_title_font"] = title_font
            cache["calendar_header_font"] = header_font
            cache["calendar_day_font"] = day_font
            cache["calendar_title_y"] = title_y
            cache["calendar_title_text"] = title_text
            cache["calendar_weekday_positions"] = weekday_positions
            cache["calendar_day_cells"] = day_cells
            cache["calendar_vlines"] = vlines
            cache["calendar_hlines"] = hlines

        elif self.mode == "timer":
            container_w = int(content_rect.width * 0.75)
        
            base_size = 110
            timer_font = pygame.font.SysFont("consolas", base_size, bold=True)
            timer_surface = timer_font.render("00:00:00.00", True, TEXT_COLOR)
        
            available_w = container_w - 40
            while timer_surface.get_width() > available_w and base_size > 12:
                base_size -= 1
                timer_font = pygame.font.SysFont("consolas", base_size, bold=True)
                timer_surface = timer_font.render("00:00:00.00", True, TEXT_COLOR)
        
            button_font = pygame.font.SysFont(
                "arial",
                clamp(int(base_size * 0.40), 14, 34),
                bold=True
            )
            button_surface = button_font.render("Reset", True, BUTTON_TEXT)
        
            panel_h = max(timer_surface.get_height() + 42, int(base_size * 1.25))
            button_h = max(button_surface.get_height() + 20, int(base_size * 0.85))
            gap = max(16, int(base_size * 0.45))
        
            container_h = panel_h + gap + button_h
            container_rect = pygame.Rect(0, 0, container_w, container_h)
            container_rect.centerx = content_rect.centerx
            container_rect.top = content_rect.top + max(18, int(base_size * 0.30))
        
            panel_rect = pygame.Rect(
                container_rect.left,
                container_rect.top,
                container_w,
                panel_h
            )
        
            button_rect = pygame.Rect(
                0,
                0,
                int(container_w * 0.32),
                button_h
            )
            button_rect.centerx = container_rect.centerx
            button_rect.top = panel_rect.bottom + gap
        
            self.timer_button_rect = button_rect
        
            cache["timer_container_rect"] = container_rect
            cache["timer_panel_rect"] = panel_rect
            cache["timer_panel_radius"] = max(10, content_rect.width // 45)
            cache["timer_font"] = timer_font
            cache["timer_button_font"] = button_font

        self.layout_cache = cache
        self.layout_dirty = False

    def get_view_state_key(self):
        size = self.screen.get_size()

        if self.mode == "calendar":
            return ("calendar", size, self.calendar_year, self.calendar_month, self.always_on_top, self.on_top_supported)

        if self.mode == "digital":
            return ("digital", size, self.cached_time_text, self.cached_ampm_text, self.cached_date_text, self.always_on_top, self.on_top_supported)

        if self.mode == "analog":
            now = datetime.now()
            return ("analog", size, now.year, now.month, now.day, now.hour, now.minute, now.second, self.always_on_top, self.on_top_supported)

        return ("timer", size, self.get_timer_display_text(), self.get_timer_button_text(), self.always_on_top, self.on_top_supported)

    def draw(self):
        current_size = self.screen.get_size()
        if current_size != self.last_window_size or self.mode != self.last_mode:
            self.invalidate_layout()
            self.last_window_size = current_size
            self.last_mode = self.mode

        if self.layout_dirty or "top_bar_h" not in self.layout_cache:
            self.rebuild_layout_cache()

        state_key = self.get_view_state_key()
        if self.view_surface is None or self.view_surface_mode != self.mode or self.view_state_key != state_key:
            self.view_surface = self.render_current_view_surface()
            self.view_surface_mode = self.mode
            self.view_state_key = state_key

        self.screen.blit(self.view_surface, (0, 0))

    def render_current_view_surface(self):
        width, height = self.screen.get_size()
        surface = pygame.Surface((width, height))
        surface.fill(BG_COLOR)

        top_bar_h = self.layout_cache["top_bar_h"]
        content_rect = self.layout_cache["content_rect"]

        self.draw_top_bar_to(surface, top_bar_h)

        pygame.draw.rect(surface, PANEL_COLOR, content_rect, border_radius=self.layout_cache["content_radius"])

        if self.mode == "analog":
            self.draw_analog_clock_to(surface)
        elif self.mode == "digital":
            self.draw_digital_clock_to(surface)
        elif self.mode == "calendar":
            self.draw_calendar_to(surface)
        else:
            self.draw_timer_to(surface)

        return surface

    def draw_top_bar_to(self, surface, height):
        width = surface.get_width()
        pygame.draw.rect(surface, PANEL_COLOR, pygame.Rect(0, 0, width, height))
        surface.blit(self.layout_cache["top_label_surface"], self.layout_cache["top_label_rect"])

        mouse_pos = pygame.mouse.get_pos()
        hovered = self.top_button_rect.collidepoint(mouse_pos)

        color = BUTTON_ON if self.always_on_top else BUTTON_OFF
        border = tuple(min(255, c + 25) for c in color) if hovered else color

        pygame.draw.rect(surface, color, self.top_button_rect, border_radius=self.top_button_rect.height // 2)
        pygame.draw.rect(surface, border, self.top_button_rect, width=2, border_radius=self.top_button_rect.height // 2)

        draw_text(surface, "ON" if self.always_on_top else "OFF", self.layout_cache["top_font"], BUTTON_TEXT, center=self.top_button_rect.center)
        draw_text(surface, f"View: {self.mode.title()}", self.layout_cache["view_font"], ACCENT_COLOR, center=(width - 110, height // 2))

        if not self.on_top_supported and self.layout_cache["small_font"] is not None:
            draw_text(
                surface,
                "(window manager support may vary)",
                self.layout_cache["small_font"],
                SUBTEXT_COLOR,
                topleft=(self.top_button_rect.right + 12, max(4, height // 2 - 8))
            )

    def draw_analog_clock_to(self, surface):
        rect = self.layout_cache["content_rect"]
        cx = self.layout_cache["analog_cx"]
        cy = self.layout_cache["analog_cy"]
        radius = self.layout_cache["analog_radius"]

        now = datetime.now()

        pygame.draw.circle(surface, FACE_COLOR, (cx, cy), radius)
        pygame.draw.circle(surface, GRID_COLOR, (cx, cy), radius, self.layout_cache["analog_border_thickness"])

        for p1, p2, thickness, color in self.layout_cache["analog_tick_lines"]:
            pygame.draw.line(surface, color, p1, p2, thickness)

        for text, pos in self.layout_cache["analog_number_positions"]:
            draw_text(surface, text, self.layout_cache["analog_number_font"], TEXT_COLOR, center=pos)

        second = now.second
        minute = now.minute + (second / 60.0)
        hour = (now.hour % 12) + (minute / 60.0)

        self.draw_hand(surface, cx, cy, math.radians(hour * 30 - 90), radius * 0.50, self.layout_cache["analog_hour_thickness"], HOUR_COLOR)
        self.draw_hand(surface, cx, cy, math.radians(minute * 6 - 90), radius * 0.72, self.layout_cache["analog_minute_thickness"], MINUTE_COLOR)
        self.draw_hand(surface, cx, cy, math.radians(second * 6 - 90), radius * 0.84, self.layout_cache["analog_second_thickness"], SECOND_COLOR)

        pygame.draw.circle(surface, TEXT_COLOR, (cx, cy), self.layout_cache["analog_center_outer"])
        pygame.draw.circle(surface, SECOND_COLOR, (cx, cy), self.layout_cache["analog_center_inner"])

        draw_text(surface, self.cached_date_text, self.layout_cache["analog_date_font"], SUBTEXT_COLOR, center=(rect.centerx, rect.bottom - rect.height * 0.08))

    def draw_digital_clock_to(self, surface):
        panel_rect = self.layout_cache["digital_panel_rect"]
        date_rect = self.layout_cache["digital_date_rect"]
        radius = self.layout_cache["digital_panel_radius"]

        pygame.draw.rect(surface, (18, 18, 20), panel_rect, border_radius=radius)
        pygame.draw.rect(surface, GRID_COLOR, panel_rect, width=2, border_radius=radius)

        time_font = self.layout_cache["digital_time_font"]
        ampm_font = self.layout_cache["digital_ampm_font"]

        time_surface = time_font.render(self.cached_time_text, True, TEXT_COLOR)
        ampm_surface = ampm_font.render(self.cached_ampm_text, True, ACCENT_COLOR)

        spacing = 14
        total_w = time_surface.get_width() + spacing + ampm_surface.get_width()
        group_left = panel_rect.centerx - total_w // 2

        time_rect = time_surface.get_rect()
        time_rect.left = group_left
        time_rect.centery = panel_rect.centery

        ampm_rect = ampm_surface.get_rect()
        ampm_rect.left = time_rect.right + spacing
        ampm_rect.centery = panel_rect.centery

        surface.blit(time_surface, time_rect)
        surface.blit(ampm_surface, ampm_rect)

        date_surface = self.layout_cache["digital_date_font"].render(self.cached_date_text, True, SUBTEXT_COLOR)
        surface.blit(date_surface, date_surface.get_rect(center=date_rect.center))

    def draw_calendar_to(self, surface):
        today = datetime.now().date()
        rect = self.layout_cache["content_rect"]

        draw_text(surface, self.layout_cache["calendar_title_text"], self.layout_cache["calendar_title_font"], TEXT_COLOR, center=(rect.centerx, self.layout_cache["calendar_title_y"]))

        self.draw_arrow_button_to(surface, self.left_arrow_rect, "<")
        self.draw_arrow_button_to(surface, self.right_arrow_rect, ">")

        for name, pos in self.layout_cache["calendar_weekday_positions"]:
            draw_text(surface, name, self.layout_cache["calendar_header_font"], ACCENT_COLOR, center=pos)

        for p1, p2 in self.layout_cache["calendar_vlines"]:
            pygame.draw.line(surface, GRID_COLOR, p1, p2, 1)
        for p1, p2 in self.layout_cache["calendar_hlines"]:
            pygame.draw.line(surface, GRID_COLOR, p1, p2, 1)

        for day_date, cell_rect in self.layout_cache["calendar_day_cells"]:
            is_current_month = (day_date.month == self.calendar_month)
            is_today = (day_date == today)

            if is_today:
                inset = max(4, int(min(cell_rect.width, cell_rect.height) * 0.12))
                rr = max(6, int(min(cell_rect.width, cell_rect.height) * 0.12))
                highlight_rect = cell_rect.inflate(-inset, -inset)
                pygame.draw.rect(surface, (80, 70, 30), highlight_rect, border_radius=rr)
                pygame.draw.rect(surface, TODAY_COLOR, highlight_rect, width=2, border_radius=rr)

            color = TODAY_COLOR if is_today else (TEXT_COLOR if is_current_month else GRAYED_DAY_COLOR)
            draw_text(surface, str(day_date.day), self.layout_cache["calendar_day_font"], color, center=cell_rect.center)

    def draw_timer_to(self, surface):
        panel_rect = self.layout_cache["timer_panel_rect"]
        button_rect = self.timer_button_rect
        panel_radius = self.layout_cache["timer_panel_radius"]

        pygame.draw.rect(surface, (18, 18, 20), panel_rect, border_radius=panel_radius)
        pygame.draw.rect(surface, GRID_COLOR, panel_rect, width=2, border_radius=panel_radius)

        timer_text = self.get_timer_display_text()
        timer_surface = self.layout_cache["timer_font"].render(timer_text, True, TEXT_COLOR)
        surface.blit(timer_surface, timer_surface.get_rect(center=panel_rect.center))

        mouse_pos = pygame.mouse.get_pos()
        hovered = button_rect.collidepoint(mouse_pos)

        if self.timer_state == TIMER_RUNNING:
            base_color = (170, 90, 90)
        elif self.timer_state == TIMER_STOPPED:
            base_color = (160, 140, 90)
        else:
            base_color = (70, 170, 100)

        border_color = tuple(min(255, c + 25) for c in base_color) if hovered else base_color
        pygame.draw.rect(surface, base_color, button_rect, border_radius=button_rect.height // 2)
        pygame.draw.rect(surface, border_color, button_rect, width=2, border_radius=button_rect.height // 2)

        draw_text(surface, self.get_timer_button_text(), self.layout_cache["timer_button_font"], BUTTON_TEXT, center=button_rect.center)

    def draw_arrow_button_to(self, surface, rect, symbol):
        mouse_pos = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse_pos)
        bg = ARROW_HOVER if hovered else ARROW_BG

        pygame.draw.rect(surface, bg, rect, border_radius=max(8, rect.width // 4))
        pygame.draw.rect(surface, GRID_COLOR, rect, width=2, border_radius=max(8, rect.width // 4))

        font = pygame.font.SysFont("arial", clamp(rect.width // 2, 16, 28), bold=True)
        draw_text(surface, symbol, font, TEXT_COLOR, center=rect.center)

    def draw_hand(self, surface, cx, cy, angle, length, thickness, color):
        x = cx + math.cos(angle) * length
        y = cy + math.sin(angle) * length
        pygame.draw.line(surface, color, (cx, cy), (x, y), thickness)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                self.handle_mode_resize(event.w, event.h)
                self.invalidate_layout()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.handle_click(event.pos)

    def handle_click(self, pos):
        if point_in_rect(pos, self.top_button_rect):
            self.toggle_always_on_top()
            self.invalidate_view_cache()
            return

        if self.mode == "calendar":
            if point_in_rect(pos, self.left_arrow_rect):
                self.calendar_year, self.calendar_month = month_add(self.calendar_year, self.calendar_month, -1)
                self.invalidate_layout()
                return
            if point_in_rect(pos, self.right_arrow_rect):
                self.calendar_year, self.calendar_month = month_add(self.calendar_year, self.calendar_month, 1)
                self.invalidate_layout()
                return

        if self.mode == "timer" and point_in_rect(pos, self.timer_button_rect):
            self.handle_timer_button()
            return

        self.next_mode()

    def run(self):
        while self.running:
            self.handle_events()
            self.update_time_cache()
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    ClockCalendarApp().run()
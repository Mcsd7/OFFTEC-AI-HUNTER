"""Shared menu movement rules used by the terminal UI and Pilot regressions."""


def normalize_key(key):
    return {"escape": "esc", "shift+tab": "shift_tab", "ctrl+c": "ctrlc"}.get(key, key)


def move_index(index, count, key):
    if count <= 0:
        return 0
    if key in ("up", "left", "k"):
        return (index - 1) % count
    if key in ("down", "right", "j"):
        return (index + 1) % count
    return max(0, min(index, count - 1))


class NavigationState:
    """Small focus/navigation state machine for menu and status panels."""
    def __init__(self, menu_count, panel_count=1):
        self.menu_count = max(0, menu_count)
        self.panel_count = max(0, panel_count)
        self.menu_index = 0
        self.panel_index = 0
        self.panel_focus = False

    def handle(self, key):
        if key in ("tab", "shift_tab"):
            self.panel_focus = not self.panel_focus
            return "focus_changed"
        if key == "esc":
            if self.panel_focus:
                self.panel_focus = False
                return "focus_changed"
            return "back"
        if key == "ctrlc":
            return "quit"
        if key == "enter":
            return "activate"
        if self.panel_focus:
            self.panel_index = move_index(self.panel_index, self.panel_count, key)
        else:
            self.menu_index = move_index(self.menu_index, self.menu_count, key)
        return "moved"

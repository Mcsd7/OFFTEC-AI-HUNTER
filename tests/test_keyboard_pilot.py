"""Pilot tests exercise the same focus/navigation state machine as the TTY UI."""
import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Input, Static

from offtec.interface.navigation import NavigationState, normalize_key


class FocusPanel(Static):
    can_focus = True


class NavigationPilotApp(App):
    def __init__(self):
        super().__init__()
        self.navigation = NavigationState(menu_count=4, panel_count=2)
        self.activations = 0
        self.last_action = None

    def compose(self) -> ComposeResult:
        yield FocusPanel("Menu", id="menu")
        yield FocusPanel("Status", id="panel")
        yield Input(placeholder="Texto", id="text-input")

    def on_mount(self):
        self.query_one("#menu", FocusPanel).focus()

    def on_key(self, event):
        # Text inputs own their cursor keys; navigation never cancels input events.
        if isinstance(self.focused, Input):
            return
        action = self.navigation.handle(normalize_key(event.key))
        self.last_action = action
        if event.key in {"up", "down", "left", "right", "j", "k", "enter", "escape", "tab", "shift+tab", "ctrl+c"}:
            event.stop()
        if action == "focus_changed":
            target = "panel" if self.navigation.panel_focus else "menu"
            self.query_one("#" + target, FocusPanel).focus()
        elif action == "activate":
            self.activations += 1


def test_pilot_arrows_enter_escape_and_focus_cycle():
    async def run():
        app = NavigationPilotApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.focused.id == "menu"
            await pilot.press("down")
            assert app.navigation.menu_index == 1
            await pilot.press("right")
            assert app.navigation.menu_index == 2
            await pilot.press("up")
            assert app.navigation.menu_index == 1
            await pilot.press("left")
            assert app.navigation.menu_index == 0
            await pilot.press("k")
            assert app.navigation.menu_index == 3
            await pilot.press("j")
            assert app.navigation.menu_index == 0
            await pilot.press("enter")
            assert app.activations == 1
            await pilot.press("tab")
            assert app.focused.id == "panel" and app.navigation.panel_focus
            await pilot.press("down")
            assert app.navigation.panel_index == 1
            await pilot.press("shift+tab")
            assert app.focused.id == "menu" and not app.navigation.panel_focus
            await pilot.press("escape")
            assert app.last_action == "back"
    asyncio.run(run())


def test_pilot_text_input_keeps_arrow_cursor_editing():
    async def run():
        app = NavigationPilotApp()
        async with app.run_test() as pilot:
            field = app.query_one("#text-input", Input)
            field.focus()
            await pilot.press("a", "b", "c", "left", "x")
            assert field.value == "abxc"
    asyncio.run(run())


def test_pilot_ctrl_c_is_quit_action():
    async def run():
        app = NavigationPilotApp()
        async with app.run_test() as pilot:
            await pilot.press("ctrl+c")
            assert app.last_action == "quit"
    asyncio.run(run())

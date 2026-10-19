from time import sleep

from rich.console import Console
from rich.panel import Panel
from rich.spinner import Spinner
from rich.status import Status
from rich.text import Text


def test_status():
    console = Console(
        color_system=None, width=80, legacy_windows=False, get_time=lambda: 0.0
    )
    status = Status("foo", console=console)
    assert status.console == console
    previous_status_renderable = status.renderable
    status.update(status="bar", spinner_style="red", speed=2.0)

    assert previous_status_renderable == status.renderable
    assert isinstance(status.renderable, Spinner)
    status.update(spinner="dots2")
    assert previous_status_renderable != status.renderable

    # TODO: Testing output is tricky with threads
    with status:
        sleep(0.2)


def test_renderable():
    console = Console(
        color_system=None, width=80, legacy_windows=False, get_time=lambda: 0.0
    )
    status = Status("foo", console=console)
    console.begin_capture()
    console.print(status)
    assert console.end_capture() == "⠋ foo\n"


def test_renderable_text_status():
    console = Console(
        color_system="standard",
        width=80,
        force_terminal=True,
        legacy_windows=False,
        _environ={},
        get_time=lambda: 0.0,
    )
    status = Status(Text("working", style="magenta"), console=console)
    console.begin_capture()
    console.print(status)
    result = console.end_capture()
    assert "\x1b[35mworking\x1b[0m" in result


def test_renderable_block_status():
    console = Console(
        color_system=None,
        width=80,
        force_terminal=True,
        legacy_windows=False,
        _environ={},
        get_time=lambda: 0.0,
    )
    status = Status(Panel("starting"), console=console)
    console.begin_capture()
    console.print(status)
    result = console.end_capture()
    assert "starting" in result
    assert "╭" in result


def test_update_status_renderable():
    console = Console(
        color_system="standard",
        width=80,
        force_terminal=True,
        legacy_windows=False,
        _environ={},
        get_time=lambda: 0.0,
    )
    status = Status("foo", console=console)
    status.update(status=Text("bar", style="blue"))
    assert isinstance(status._spinner.text, Text)
    assert str(status._spinner.text) == "bar"
    console.begin_capture()
    console.print(status)
    assert "\x1b[34mbar\x1b[0m" in console.end_capture()

    # A falsy renderable still replaces the previous status.
    status.update(status=Text(""))
    assert isinstance(status._spinner.text, Text)
    assert str(status._spinner.text) == ""

# encoding=utf-8

import io
import os
import re
import tempfile
import threading
from types import SimpleNamespace

import pytest

import rich.progress
from rich.console import Console
from rich.highlighter import NullHighlighter
from rich.progress import (
    BarColumn,
    DownloadColumn,
    FileSizeColumn,
    MofNCompleteColumn,
    Progress,
    RenderableColumn,
    SpinnerColumn,
    Task,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TotalFileSizeColumn,
    TransferSpeedColumn,
    _TrackThread,
    track,
)
from rich.measure import Measurement
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.text import Text


class MockClock:
    """A clock that is manually advanced."""

    def __init__(self, time=0.0, auto=True) -> None:
        self.time = time
        self.auto = auto

    def __call__(self) -> float:
        try:
            return self.time
        finally:
            if self.auto:
                self.time += 1

    def tick(self, advance: float = 1) -> None:
        self.time += advance


def test_bar_columns():
    bar_column = BarColumn(100)
    assert bar_column.bar_width == 100
    task = Task(1, "test", 100, 20, _get_time=lambda: 1.0)
    bar = bar_column(task)
    assert isinstance(bar, ProgressBar)
    assert bar.completed == 20
    assert bar.total == 100


def test_text_column():
    text_column = TextColumn("[b]foo", highlighter=NullHighlighter())
    task = Task(1, "test", 100, 20, _get_time=lambda: 1.0)
    text = text_column.render(task)
    assert str(text) == "foo"

    text_column = TextColumn("[b]bar", markup=False)
    task = Task(1, "test", 100, 20, _get_time=lambda: 1.0)
    text = text_column.render(task)
    assert text == Text("[b]bar")


def test_time_elapsed_column():
    column = TimeElapsedColumn()
    task = Task(1, "test", 100, 20, _get_time=lambda: 1.0)
    text = column.render(task)
    assert str(text) == "-:--:--"


def test_time_remaining_column():
    class FakeTask(Task):
        time_remaining = 60

    column = TimeRemainingColumn()
    task = Task(1, "test", 100, 20, _get_time=lambda: 1.0)
    text = column(task)
    assert str(text) == "-:--:--"

    text = column(FakeTask(1, "test", 100, 20, _get_time=lambda: 1.0))
    assert str(text) == "0:01:00"


@pytest.mark.parametrize(
    "task_time, formatted",
    [
        (None, "--:--"),
        (0, "00:00"),
        (59, "00:59"),
        (71, "01:11"),
        (4210, "1:10:10"),
    ],
)
def test_compact_time_remaining_column(task_time, formatted):
    task = SimpleNamespace(finished=False, time_remaining=task_time, total=100)
    column = TimeRemainingColumn(compact=True)

    assert str(column.render(task)) == formatted


def test_time_remaining_column_elapsed_when_finished():
    task_time = 71
    formatted = "0:01:11"

    task = SimpleNamespace(finished=True, finished_time=task_time, total=100)
    column = TimeRemainingColumn(elapsed_when_finished=True)

    assert str(column.render(task)) == formatted


def test_renderable_column():
    column = RenderableColumn("foo")
    task = Task(1, "test", 100, 20, _get_time=lambda: 1.0)
    assert column.render(task) == "foo"


def test_spinner_column():
    time = 1.0

    def get_time():
        nonlocal time
        return time

    column = SpinnerColumn()
    column.set_spinner("dots2")
    task = Task(1, "test", 100, 20, _get_time=get_time)
    result = column.render(task)
    print(repr(result))
    expected = "⣾"
    assert str(result) == expected

    time += 1.0
    column.spinner.update(speed=0.5)
    result = column.render(task)
    print(repr(result))
    expected = "⡿"
    assert str(result) == expected


def test_download_progress_uses_decimal_units() -> None:
    column = DownloadColumn()
    test_task = Task(1, "test", 1000, 500, _get_time=lambda: 1.0)
    rendered_progress = str(column.render(test_task))
    expected = "0.5/1.0 kB"
    assert rendered_progress == expected


def test_download_progress_uses_binary_units() -> None:
    column = DownloadColumn(binary_units=True)
    test_task = Task(1, "test", 1024, 512, _get_time=lambda: 1.0)
    rendered_progress = str(column.render(test_task))
    expected = "0.5/1.0 KiB"
    assert rendered_progress == expected


def test_task_ids():
    progress = make_progress()
    assert progress.task_ids == [0, 1, 2, 4]


def test_finished():
    progress = make_progress()
    assert not progress.finished


def make_progress() -> Progress:
    _time = 0.0

    def fake_time():
        nonlocal _time
        try:
            return _time
        finally:
            _time += 1

    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        color_system="truecolor",
        width=80,
        legacy_windows=False,
        _environ={},
    )
    progress = Progress(console=console, get_time=fake_time, auto_refresh=False)
    task1 = progress.add_task("foo")
    task2 = progress.add_task("bar", total=30)
    progress.advance(task2, 16)
    task3 = progress.add_task("baz", visible=False)
    task4 = progress.add_task("egg")
    progress.remove_task(task4)
    task4 = progress.add_task("foo2", completed=50, start=False)
    progress.stop_task(task4)
    progress.start_task(task4)
    progress.update(
        task4, total=200, advance=50, completed=200, visible=True, refresh=True
    )
    progress.stop_task(task4)
    return progress


def render_progress() -> str:
    progress = make_progress()
    progress.start()  # superfluous noop
    with progress:
        pass
    progress.stop()  # superfluous noop
    progress_render = progress.console.file.getvalue()
    return progress_render


def test_expand_bar() -> None:
    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        width=10,
        color_system="truecolor",
        legacy_windows=False,
        _environ={},
    )
    progress = Progress(
        BarColumn(bar_width=None),
        console=console,
        get_time=lambda: 1.0,
        auto_refresh=False,
    )
    progress.add_task("foo")
    with progress:
        pass
    expected = "\x1b[?25l\x1b[38;5;237m━━━━━━━━━━\x1b[0m\r\x1b[2K\x1b[38;5;237m━━━━━━━━━━\x1b[0m\n\x1b[?25h"
    render_result = console.file.getvalue()
    print("RESULT\n", repr(render_result))
    print("EXPECTED\n", repr(expected))
    assert render_result == expected


def test_progress_with_none_total_renders_a_pulsing_bar() -> None:
    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        width=10,
        color_system="truecolor",
        legacy_windows=False,
        _environ={},
    )
    progress = Progress(
        BarColumn(bar_width=None),
        console=console,
        get_time=lambda: 1.0,
        auto_refresh=False,
    )
    progress.add_task("foo", total=None)
    with progress:
        pass
    expected = "\x1b[?25l\x1b[38;2;153;48;86m━\x1b[0m\x1b[38;2;183;44;94m━\x1b[0m\x1b[38;2;209;42;102m━\x1b[0m\x1b[38;2;230;39;108m━\x1b[0m\x1b[38;2;244;38;112m━\x1b[0m\x1b[38;2;249;38;114m━\x1b[0m\x1b[38;2;244;38;112m━\x1b[0m\x1b[38;2;230;39;108m━\x1b[0m\x1b[38;2;209;42;102m━\x1b[0m\x1b[38;2;183;44;94m━\x1b[0m\r\x1b[2K\x1b[38;2;153;48;86m━\x1b[0m\x1b[38;2;183;44;94m━\x1b[0m\x1b[38;2;209;42;102m━\x1b[0m\x1b[38;2;230;39;108m━\x1b[0m\x1b[38;2;244;38;112m━\x1b[0m\x1b[38;2;249;38;114m━\x1b[0m\x1b[38;2;244;38;112m━\x1b[0m\x1b[38;2;230;39;108m━\x1b[0m\x1b[38;2;209;42;102m━\x1b[0m\x1b[38;2;183;44;94m━\x1b[0m\n\x1b[?25h"
    render_result = console.file.getvalue()
    print("RESULT\n", repr(render_result))
    print("EXPECTED\n", repr(expected))
    assert render_result == expected


def test_render() -> None:
    expected = "\x1b[?25lfoo  \x1b[38;5;237m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[35m  0%\x1b[0m \x1b[36m-:--:--\x1b[0m\nbar  \x1b[38;2;249;38;114m━━━━━━━━━━━━━━━━━━━━━\x1b[0m\x1b[38;5;237m╺\x1b[0m\x1b[38;5;237m━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[35m 53%\x1b[0m \x1b[36m-:--:--\x1b[0m\nfoo2 \x1b[38;2;114;156;31m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[35m100%\x1b[0m \x1b[36m0:00:00\x1b[0m\r\x1b[2K\x1b[1A\x1b[2K\x1b[1A\x1b[2Kfoo  \x1b[38;5;237m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[35m  0%\x1b[0m \x1b[36m-:--:--\x1b[0m\nbar  \x1b[38;2;249;38;114m━━━━━━━━━━━━━━━━━━━━━\x1b[0m\x1b[38;5;237m╺\x1b[0m\x1b[38;5;237m━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[35m 53%\x1b[0m \x1b[36m-:--:--\x1b[0m\nfoo2 \x1b[38;2;114;156;31m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[35m100%\x1b[0m \x1b[36m0:00:00\x1b[0m\n\x1b[?25h"
    render_result = render_progress()
    print(repr(render_result))
    assert render_result == expected


def test_track() -> None:
    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        width=60,
        color_system="truecolor",
        legacy_windows=False,
        _environ={},
    )
    test = ["foo", "bar", "baz"]
    expected_values = iter(test)
    for value in track(
        test, "test", console=console, auto_refresh=False, get_time=MockClock(auto=True)
    ):
        assert value == next(expected_values)
    result = console.file.getvalue()
    print(repr(result))
    expected = "\x1b[?25l\r\x1b[2Ktest \x1b[38;5;237m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[35m  0%\x1b[0m \x1b[36m-:--:--\x1b[0m\r\x1b[2Ktest \x1b[38;2;249;38;114m━━━━━━━━━━━━━\x1b[0m\x1b[38;5;237m╺\x1b[0m\x1b[38;5;237m━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[35m 33%\x1b[0m \x1b[36m-:--:--\x1b[0m\r\x1b[2Ktest \x1b[38;2;249;38;114m━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m\x1b[38;2;249;38;114m╸\x1b[0m\x1b[38;5;237m━━━━━━━━━━━━━\x1b[0m \x1b[35m 67%\x1b[0m \x1b[36m0:00:06\x1b[0m\r\x1b[2Ktest \x1b[38;2;114;156;31m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[35m100%\x1b[0m \x1b[33m0:00:19\x1b[0m\r\x1b[2Ktest \x1b[38;2;114;156;31m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[35m100%\x1b[0m \x1b[33m0:00:19\x1b[0m\n\x1b[?25h"
    print("--")
    print("RESULT:")
    print(result)
    print(repr(result))
    print("EXPECTED:")
    print(expected)
    print(repr(expected))

    assert result == expected


def test_progress_track() -> None:
    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        width=60,
        color_system="truecolor",
        legacy_windows=False,
        _environ={},
    )
    progress = Progress(
        console=console, auto_refresh=False, get_time=MockClock(auto=True)
    )
    test = ["foo", "bar", "baz"]
    expected_values = iter(test)
    with progress:
        for value in progress.track(test, description="test"):
            assert value == next(expected_values)
    result = console.file.getvalue()
    print(repr(result))
    expected = "\x1b[?25l\r\x1b[2Ktest \x1b[38;5;237m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[35m  0%\x1b[0m \x1b[36m-:--:--\x1b[0m\r\x1b[2Ktest \x1b[38;2;249;38;114m━━━━━━━━━━━━━\x1b[0m\x1b[38;5;237m╺\x1b[0m\x1b[38;5;237m━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[35m 33%\x1b[0m \x1b[36m-:--:--\x1b[0m\r\x1b[2Ktest \x1b[38;2;249;38;114m━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m\x1b[38;2;249;38;114m╸\x1b[0m\x1b[38;5;237m━━━━━━━━━━━━━\x1b[0m \x1b[35m 67%\x1b[0m \x1b[36m0:00:06\x1b[0m\r\x1b[2Ktest \x1b[38;2;114;156;31m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[35m100%\x1b[0m \x1b[36m0:00:00\x1b[0m\r\x1b[2Ktest \x1b[38;2;114;156;31m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[35m100%\x1b[0m \x1b[36m0:00:00\x1b[0m\n\x1b[?25h"

    print(expected)
    print(repr(expected))
    print(result)
    print(repr(result))

    assert result == expected


def test_columns() -> None:
    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        width=80,
        log_time_format="[TIME]",
        color_system="truecolor",
        legacy_windows=False,
        log_path=False,
        _environ={},
    )
    progress = Progress(
        "test",
        TextColumn("{task.description}"),
        BarColumn(bar_width=None),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
        FileSizeColumn(),
        TotalFileSizeColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        MofNCompleteColumn(),
        MofNCompleteColumn(separator=" of "),
        transient=True,
        console=console,
        auto_refresh=False,
        get_time=MockClock(),
    )
    task1 = progress.add_task("foo", total=10)
    task2 = progress.add_task("bar", total=7)
    with progress:
        for n in range(4):
            progress.advance(task1, 3)
            progress.advance(task2, 4)
        print("foo")
        console.log("hello")
        console.print("world")
        progress.refresh()
    from .render import replace_link_ids

    result = replace_link_ids(console.file.getvalue())
    print(repr(result))
    expected = "\x1b[?25ltest foo \x1b[38;5;237m━━━━━━━━━━\x1b[0m \x1b[36m-:--:--\x1b[0m \x1b[33m0:00:07\x1b[0m \x1b[32m0 bytes\x1b[0m \x1b[32m10 bytes\x1b[0m \x1b[32m0/10 bytes\x1b[0m \x1b[31m?\x1b[0m \x1b[32m 0/10\x1b[0m \x1b[32m 0 of 10\x1b[0m\ntest bar \x1b[38;5;237m━━━━━━━━━━\x1b[0m \x1b[36m-:--:--\x1b[0m \x1b[33m0:00:18\x1b[0m \x1b[32m0 bytes\x1b[0m \x1b[32m7 bytes \x1b[0m \x1b[32m0/7 bytes \x1b[0m \x1b[31m?\x1b[0m \x1b[32m0/7  \x1b[0m \x1b[32m0 of 7  \x1b[0m\r\x1b[2K\x1b[1A\x1b[2Kfoo\ntest foo \x1b[38;5;237m━━━━━━━━━━\x1b[0m \x1b[36m-:--:--\x1b[0m \x1b[33m0:00:07\x1b[0m \x1b[32m0 bytes\x1b[0m \x1b[32m10 bytes\x1b[0m \x1b[32m0/10 bytes\x1b[0m \x1b[31m?\x1b[0m \x1b[32m 0/10\x1b[0m \x1b[32m 0 of 10\x1b[0m\ntest bar \x1b[38;5;237m━━━━━━━━━━\x1b[0m \x1b[36m-:--:--\x1b[0m \x1b[33m0:00:18\x1b[0m \x1b[32m0 bytes\x1b[0m \x1b[32m7 bytes \x1b[0m \x1b[32m0/7 bytes \x1b[0m \x1b[31m?\x1b[0m \x1b[32m0/7  \x1b[0m \x1b[32m0 of 7  \x1b[0m\r\x1b[2K\x1b[1A\x1b[2K\x1b[2;36m[TIME]\x1b[0m\x1b[2;36m \x1b[0mhello                                                                    \ntest foo \x1b[38;5;237m━━━━━━━━━━\x1b[0m \x1b[36m-:--:--\x1b[0m \x1b[33m0:00:07\x1b[0m \x1b[32m0 bytes\x1b[0m \x1b[32m10 bytes\x1b[0m \x1b[32m0/10 bytes\x1b[0m \x1b[31m?\x1b[0m \x1b[32m 0/10\x1b[0m \x1b[32m 0 of 10\x1b[0m\ntest bar \x1b[38;5;237m━━━━━━━━━━\x1b[0m \x1b[36m-:--:--\x1b[0m \x1b[33m0:00:18\x1b[0m \x1b[32m0 bytes\x1b[0m \x1b[32m7 bytes \x1b[0m \x1b[32m0/7 bytes \x1b[0m \x1b[31m?\x1b[0m \x1b[32m0/7  \x1b[0m \x1b[32m0 of 7  \x1b[0m\r\x1b[2K\x1b[1A\x1b[2Kworld\ntest foo \x1b[38;5;237m━━━━━━━━━━\x1b[0m \x1b[36m-:--:--\x1b[0m \x1b[33m0:00:07\x1b[0m \x1b[32m0 bytes\x1b[0m \x1b[32m10 bytes\x1b[0m \x1b[32m0/10 bytes\x1b[0m \x1b[31m?\x1b[0m \x1b[32m 0/10\x1b[0m \x1b[32m 0 of 10\x1b[0m\ntest bar \x1b[38;5;237m━━━━━━━━━━\x1b[0m \x1b[36m-:--:--\x1b[0m \x1b[33m0:00:18\x1b[0m \x1b[32m0 bytes\x1b[0m \x1b[32m7 bytes \x1b[0m \x1b[32m0/7 bytes \x1b[0m \x1b[31m?\x1b[0m \x1b[32m0/7  \x1b[0m \x1b[32m0 of 7  \x1b[0m\r\x1b[2K\x1b[1A\x1b[2Ktest foo \x1b[38;2;114;156;31m━━━━━━━\x1b[0m \x1b[36m0:00:00\x1b[0m \x1b[33m0:00:34\x1b[0m \x1b[32m12     \x1b[0m \x1b[32m10     \x1b[0m \x1b[32m12/10   \x1b[0m \x1b[31m1      \x1b[0m \x1b[32m12/10\x1b[0m \x1b[32m12 of 10\x1b[0m\n                                 \x1b[32mbytes  \x1b[0m \x1b[32mbytes  \x1b[0m \x1b[32mbytes   \x1b[0m \x1b[31mbyte/s \x1b[0m               \ntest bar \x1b[38;2;114;156;31m━━━━━━━\x1b[0m \x1b[36m0:00:00\x1b[0m \x1b[33m0:00:29\x1b[0m \x1b[32m16     \x1b[0m \x1b[32m7 bytes\x1b[0m \x1b[32m16/7    \x1b[0m \x1b[31m2      \x1b[0m \x1b[32m16/7 \x1b[0m \x1b[32m16 of 7 \x1b[0m\n                                 \x1b[32mbytes  \x1b[0m         \x1b[32mbytes   \x1b[0m \x1b[31mbytes/s\x1b[0m               \r\x1b[2K\x1b[1A\x1b[2K\x1b[1A\x1b[2K\x1b[1A\x1b[2Ktest foo \x1b[38;2;114;156;31m━━━━━━━\x1b[0m \x1b[36m0:00:00\x1b[0m \x1b[33m0:00:34\x1b[0m \x1b[32m12     \x1b[0m \x1b[32m10     \x1b[0m \x1b[32m12/10   \x1b[0m \x1b[31m1      \x1b[0m \x1b[32m12/10\x1b[0m \x1b[32m12 of 10\x1b[0m\n                                 \x1b[32mbytes  \x1b[0m \x1b[32mbytes  \x1b[0m \x1b[32mbytes   \x1b[0m \x1b[31mbyte/s \x1b[0m               \ntest bar \x1b[38;2;114;156;31m━━━━━━━\x1b[0m \x1b[36m0:00:00\x1b[0m \x1b[33m0:00:29\x1b[0m \x1b[32m16     \x1b[0m \x1b[32m7 bytes\x1b[0m \x1b[32m16/7    \x1b[0m \x1b[31m2      \x1b[0m \x1b[32m16/7 \x1b[0m \x1b[32m16 of 7 \x1b[0m\n                                 \x1b[32mbytes  \x1b[0m         \x1b[32mbytes   \x1b[0m \x1b[31mbytes/s\x1b[0m               \n\x1b[?25h\r\x1b[1A\x1b[2K\x1b[1A\x1b[2K\x1b[1A\x1b[2K\x1b[1A\x1b[2K"

    assert result == expected


def test_using_default_columns() -> None:
    # can only check types, as the instances do not '==' each other
    expected_default_types = [
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    ]

    progress = Progress()
    assert [type(c) for c in progress.columns] == expected_default_types

    progress = Progress(
        SpinnerColumn(),
        *Progress.get_default_columns(),
        "Elapsed:",
        TimeElapsedColumn(),
    )
    assert [type(c) for c in progress.columns] == [
        SpinnerColumn,
        *expected_default_types,
        str,
        TimeElapsedColumn,
    ]


def test_task_create() -> None:
    task = Task(TaskID(1), "foo", 100, 0, _get_time=lambda: 1)
    assert task.elapsed is None
    assert not task.finished
    assert task.percentage == 0.0
    assert task.speed is None
    assert task.time_remaining is None


def test_task_start() -> None:
    current_time = 1

    def get_time():
        nonlocal current_time
        return current_time

    task = Task(TaskID(1), "foo", 100, 0, _get_time=get_time)
    task.start_time = get_time()
    assert task.started == True
    assert task.elapsed == 0
    current_time += 1
    assert task.elapsed == 1
    current_time += 1
    task.stop_time = get_time()
    current_time += 1
    assert task.elapsed == 2


def test_task_zero_total() -> None:
    task = Task(TaskID(1), "foo", 0, 0, _get_time=lambda: 1)
    assert task.percentage == 0


def test_progress_create() -> None:
    progress = Progress()
    assert progress.finished
    assert progress.tasks == []
    assert progress.task_ids == []


def test_track_thread() -> None:
    progress = Progress()
    task_id = progress.add_task("foo")
    track_thread = _TrackThread(progress, task_id, 0.1)
    assert track_thread.completed == 0
    from time import sleep

    with track_thread:
        track_thread.completed = 1
        sleep(0.3)
        assert progress.tasks[task_id].completed >= 1
        track_thread.completed += 1


def test_reset() -> None:
    progress = Progress()
    task_id = progress.add_task("foo")
    progress.advance(task_id, 1)
    progress.advance(task_id, 1)
    progress.advance(task_id, 1)
    progress.advance(task_id, 7)
    task = progress.tasks[task_id]
    assert task.completed == 10
    progress.reset(
        task_id,
        total=200,
        completed=20,
        visible=False,
        description="bar",
        example="egg",
    )
    assert task.total == 200
    assert task.completed == 20
    assert task.visible == False
    assert task.description == "bar"
    assert task.fields == {"example": "egg"}
    assert not task._progress


def test_progress_max_refresh() -> None:
    """Test max_refresh argument."""
    time = 0.0

    def get_time() -> float:
        nonlocal time
        try:
            return time
        finally:
            time = time + 1.0

    console = Console(
        color_system=None,
        width=80,
        legacy_windows=False,
        force_terminal=True,
        _environ={},
    )
    column = TextColumn("{task.description}")
    column.max_refresh = 3
    progress = Progress(
        column,
        get_time=get_time,
        auto_refresh=False,
        console=console,
    )
    console.begin_capture()
    with progress:
        task_id = progress.add_task("start")
        for tick in range(6):
            progress.update(task_id, description=f"tick {tick}")
            progress.refresh()
    result = console.end_capture()
    print(repr(result))
    assert (
        result
        == "\x1b[?25l\r\x1b[2Kstart\r\x1b[2Kstart\r\x1b[2Ktick 1\r\x1b[2Ktick 1\r\x1b[2Ktick 3\r\x1b[2Ktick 3\r\x1b[2Ktick 5\r\x1b[2Ktick 5\n\x1b[?25h"
    )


def test_live_is_started_if_progress_is_enabled() -> None:
    progress = Progress(auto_refresh=False, disable=False)

    with progress:
        assert progress.live._started


def test_live_is_not_started_if_progress_is_disabled() -> None:
    progress = Progress(auto_refresh=False, disable=True)

    with progress:
        assert not progress.live._started


def test_no_output_if_progress_is_disabled() -> None:
    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        width=60,
        color_system="truecolor",
        legacy_windows=False,
        _environ={},
    )
    progress = Progress(
        console=console,
        disable=True,
    )
    test = ["foo", "bar", "baz"]
    expected_values = iter(test)
    with progress:
        for value in progress.track(test, description="test"):
            assert value == next(expected_values)
    result = console.file.getvalue()
    print(repr(result))
    expected = ""
    assert result == expected


def test_no_output_if_progress_is_disabled_non_interactive() -> None:
    console = Console(
        file=io.StringIO(),
        force_interactive=False,
        width=60,
        color_system="truecolor",
        legacy_windows=False,
        _environ={},
    )
    progress = Progress(
        console=console,
        disable=True,
    )
    test = ["foo", "bar", "baz"]
    expected_values = iter(test)
    with progress:
        for value in progress.track(test, description="test"):
            assert value == next(expected_values)
    result = console.file.getvalue()
    print(repr(result))
    expected = ""
    assert result == expected


def test_open() -> None:
    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        width=60,
        color_system="truecolor",
        legacy_windows=False,
        _environ={},
    )
    progress = Progress(
        console=console,
    )

    fd, filename = tempfile.mkstemp()
    with os.fdopen(fd, "wb") as f:
        f.write(b"Hello, World!")
    try:
        with rich.progress.open(filename) as f:
            assert f.read() == "Hello, World!"
        assert f.closed
    finally:
        os.remove(filename)


def test_open_text_mode() -> None:
    fd, filename = tempfile.mkstemp()
    with os.fdopen(fd, "wb") as f:
        f.write(b"Hello, World!")
    try:
        with rich.progress.open(filename, "r") as f:
            assert f.read() == "Hello, World!"
            assert f.name == filename
        assert f.closed
    finally:
        os.remove(filename)


def test_wrap_file() -> None:
    fd, filename = tempfile.mkstemp()
    with os.fdopen(fd, "wb") as f:
        total = f.write(b"Hello, World!")
    try:
        with open(filename, "rb") as file:
            with rich.progress.wrap_file(file, total=total) as f:
                assert f.read() == b"Hello, World!"
                assert f.mode == "rb"
                assert f.name == filename
            assert f.closed
            assert not f.handle.closed
            assert not file.closed
        assert file.closed
    finally:
        os.remove(filename)


def test_wrap_file_task_total() -> None:
    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        width=60,
        color_system="truecolor",
        legacy_windows=False,
        _environ={},
    )
    progress = Progress(
        console=console,
    )

    fd, filename = tempfile.mkstemp()
    with os.fdopen(fd, "wb") as f:
        total = f.write(b"Hello, World!")
    try:
        with progress:
            with open(filename, "rb") as file:
                task_id = progress.add_task("Reading", total=total)
                with progress.wrap_file(file, task_id=task_id) as f:
                    assert f.read() == b"Hello, World!"
    finally:
        os.remove(filename)


def test_task_progress_column_speed() -> None:
    speed_text = TaskProgressColumn.render_speed(None)
    assert speed_text.plain == ""

    speed_text = TaskProgressColumn.render_speed(5)
    assert speed_text.plain == "5.0 it/s"

    speed_text = TaskProgressColumn.render_speed(5000)
    assert speed_text.plain == "5.0×10³ it/s"

    speed_text = TaskProgressColumn.render_speed(8888888)
    assert speed_text.plain == "8.9×10⁶ it/s"


def _render_console(width=80, color_system="standard", record=False):
    return Console(
        file=io.StringIO(),
        force_terminal=True,
        width=width,
        color_system=color_system,
        legacy_windows=False,
        _environ={},
        record=record,
    )


def test_renderable_description_preserves_style_and_newlines() -> None:
    console = _render_console(width=80, color_system=None)
    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        console=console,
        auto_refresh=False,
    )
    task_id = progress.add_task(
        Text("first line\nsecond line", style="magenta"), total=100
    )
    progress.update(task_id, completed=50)
    console.print(progress)
    result = console.file.getvalue()
    assert "first line" in result
    assert "second line" in result
    assert result.index("second line") > result.index("first line")


def test_renderable_description_ansi_style() -> None:
    console = _render_console()
    progress = Progress(
        TextColumn("{task.description}"), console=console, auto_refresh=False
    )
    progress.add_task(Text("styled", style="bold magenta"))
    console.print(progress)
    result = console.file.getvalue()
    assert "\x1b[1;35mstyled\x1b[0m" in result


def test_renderable_field() -> None:
    console = _render_console()
    progress = Progress(
        TextColumn("{task.description}: {task.fields[note]}"),
        console=console,
        auto_refresh=False,
    )
    progress.add_task("task", note=Text("rich note", style="bold red"))
    console.print(progress)
    result = console.file.getvalue()
    assert "task: " in result
    assert "\x1b[1;31mrich note\x1b[0m" in result


def test_multiple_renderable_fields_stay_on_one_line() -> None:
    console = _render_console()
    progress = Progress(
        TextColumn("{task.description}|{task.fields[a]}|{task.fields[b]}"),
        console=console,
        auto_refresh=False,
    )
    progress.add_task(
        Text("x1"), a=Text("a1", style="red"), b=Text("b1", style="blue")
    )
    console.print(progress)
    result = console.file.getvalue()
    # All three renderable pieces flow inline on a single line.
    assert result.splitlines() == ["x1|\x1b[31ma1\x1b[0m|\x1b[34mb1\x1b[0m"]


def test_renderable_field_update() -> None:
    console = _render_console()
    progress = Progress(
        TextColumn("{task.description} {task.fields[x]}"),
        console=console,
        auto_refresh=False,
    )
    task_id = progress.add_task("task", x="one")
    console.print(progress)
    progress.update(task_id, x=Text("two", style="blue"))
    console.file = io.StringIO()
    console.print(progress)
    result = console.file.getvalue()
    assert "one" not in result
    assert "\x1b[34mtwo\x1b[0m" in result


def test_string_field_markup_unchanged() -> None:
    # markup enabled (default): square brackets in string values keep their
    # current markup meaning.
    console = _render_console()
    progress = Progress(
        TextColumn("{task.fields[x]}"), console=console, auto_refresh=False
    )
    progress.add_task("task", x="[bold]hi[/bold]")
    console.print(progress)
    assert "\x1b[1mhi\x1b[0m" in console.file.getvalue()

    # markup disabled: square brackets are literal text.
    console = _render_console()
    progress = Progress(
        TextColumn("{task.fields[x]}", markup=False),
        console=console,
        auto_refresh=False,
    )
    progress.add_task("task", x="not [bold]bold")
    console.print(progress)
    result = console.file.getvalue()
    assert "not [bold]bold\n" == result


def test_renderable_style_takes_precedence_over_template() -> None:
    console = _render_console()
    progress = Progress(
        TextColumn("[red]{task.description}[/red]"),
        console=console,
        auto_refresh=False,
    )
    progress.add_task(Text("mine", style="bold blue"))
    console.print(progress)
    result = console.file.getvalue()
    # Object style wins where template style and object style overlap.
    assert "\x1b[1;34mmine\x1b[0m" in result
    assert "31" not in result


def test_renderable_width_by_cell_width() -> None:
    console = _render_console()
    progress = Progress(
        TextColumn("[bold]{task.description}[/bold]"),
        console=console,
        auto_refresh=False,
    )
    progress.add_task("中文字😀x")
    rendered = progress.get_renderable()
    measurement = Measurement.get(console, console.options, rendered)
    # full-width characters and emoji count as 2 cells; [bold] tags don't count
    assert measurement.maximum == 9


def test_renderable_description_reflow_on_update() -> None:
    console = _render_console(width=40, color_system=None)
    progress = Progress(
        TextColumn("{task.description}"), console=console, auto_refresh=False
    )
    task_id = progress.add_task(Text("a much longer description"))
    console.print(progress)
    assert "a much longer description" in console.file.getvalue()

    # Shrink: the new frame contains no remnant of the old, longer text.
    progress.update(task_id, description=Text("short"))
    console.file = io.StringIO()
    console.print(progress)
    result = console.file.getvalue()
    assert "short\n" == result
    assert "longer" not in result

    # Grow: width follows the new content.
    progress.update(task_id, description=Text("an even longer description again"))
    console.file = io.StringIO()
    console.print(progress)
    result = console.file.getvalue()
    assert "an even longer description again" in result
    assert "short" not in result


def test_renderable_description_exports() -> None:
    console = _render_console(width=60, color_system="truecolor", record=True)
    progress = Progress(
        TextColumn("{task.description}"), console=console, auto_refresh=False
    )
    progress.add_task(Text("styled desc", style="bold magenta"))
    console.print(progress)
    html = console.export_html(clear=False)
    svg = console.export_svg(clear=False)
    text = console.export_text(styles=True)
    assert "styled desc" in text
    assert "\x1b[1;35mstyled desc\x1b[0m" in text
    assert "font-weight: bold" in html
    assert "#800080" in html
    assert "<svg" in svg
    assert "styled" in svg and "desc" in svg


def test_renderable_description_jupyter() -> None:
    console = _render_console(color_system=None)
    progress = Progress(
        TextColumn("{task.description}"), console=console, auto_refresh=False
    )
    progress.add_task(Text("jupyter text", style="magenta"))
    bundle = progress._repr_mimebundle_(None, None)
    assert "jupyter text" in bundle["text/plain"]
    assert "jupyter text" in bundle["text/html"]


def test_block_renderable_description() -> None:
    console = _render_console(width=40, color_system=None)
    progress = Progress(
        TextColumn("{task.description}"), console=console, auto_refresh=False
    )
    progress.add_task(Panel(Text("inside panel", style="yellow")))
    console.print(progress)
    result = console.file.getvalue()
    assert "inside panel" in result
    assert "╭" in result and "╰" in result


def test_concurrent_update_renders_consistent_description_and_fields() -> None:
    console = _render_console(width=200, color_system=None)
    progress = Progress(
        TextColumn("{task.description}|{task.fields[a]}|{task.fields[b]}"),
        console=console,
        auto_refresh=False,
    )
    task_id = progress.add_task(Text("x0"), a=Text("a0"), b=Text("b0"))
    stop = threading.Event()
    errors = []
    line_pattern = re.compile(r"^x(\d+)\|a(\d+)\|b(\d+)$")

    def updater():
        i = 0
        while not stop.is_set():
            progress.update(
                task_id,
                description=Text(f"x{i}"),
                a=Text(f"a{i}"),
                b=Text(f"b{i}"),
            )
            i += 1

    def checker():
        while not stop.is_set():
            snapshot = progress.get_renderable()
            captured = io.StringIO()
            check_console = Console(
                file=captured,
                force_terminal=True,
                width=200,
                color_system=None,
                legacy_windows=False,
                _environ={},
            )
            check_console.print(snapshot)
            for line in captured.getvalue().splitlines():
                match = line_pattern.match(line.strip())
                if match is None:
                    errors.append(f"unmatched line: {line!r}")
                    return
                d, a, b = (int(group) for group in match.groups())
                if not (d == a == b):
                    errors.append(f"split update: {line!r}")
                    return

    threads = [threading.Thread(target=updater) for _ in range(4)]
    threads += [threading.Thread(target=checker) for _ in range(2)]
    for thread in threads:
        thread.start()
    threading.Event().wait(1.0)
    stop.set()
    for thread in threads:
        thread.join()
    assert not errors, errors


if __name__ == "__main__":
    _render = render_progress()
    print(_render)
    print(repr(_render))

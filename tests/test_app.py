"""Headless Textual interaction tests for the dashboard."""

from __future__ import annotations

import pytest
from textual.widgets import DataTable, Input

from rot.app import RotApp
from rot.demo import demo_snapshot
from rot.screens import HelpScreen, InspectScreen
from rot.theme import MODE_TITLES

SIZES = ((150, 48), (120, 36), (100, 30), (80, 24))


async def settle(pilot, rounds: int = 4) -> None:
    for _ in range(rounds):
        await pilot.pause()


async def test_dashboard_mounts_and_fits_at_target_sizes():
    for width, height in SIZES:
        app = RotApp(demo_snapshot(), demo=True)
        async with app.run_test(size=(width, height)) as pilot:
            await settle(pilot)
            table = app.query_one("#files", DataTable)
            map_widget = app.query_one("#map")
            assert table.row_count == len(app.snapshot.files)
            assert table.show_horizontal_scrollbar is False
            assert sum(column.width for column in table.columns.values()) <= table.content_size.width
            assert table.content_size.width <= width
            assert map_widget.size.width > 0
            assert map_widget.size.height > 0
            assert app.query_one("#brand").size.height >= 0
            if height >= 44 and width >= 96:
                assert app.query_one("#dossier").size.width > 0
            else:
                assert app.query_one("#dossier").display is False
            if height < 28:
                assert app.query_one("#brand").display is False


async def test_dashboard_resize_updates_breakpoints_and_columns():
    app = RotApp(demo_snapshot(), demo=True)
    async with app.run_test(size=(150, 48)) as pilot:
        await settle(pilot)
        table = app.query_one("#files", DataTable)
        dossier = app.query_one("#dossier")
        wide_file_column = table.columns["file"].width
        assert dossier.display is True

        await pilot.resize_terminal(80, 24)
        await settle(pilot)
        assert dossier.display is False
        assert app.query_one("#brand").display is False
        assert table.columns["file"].width < wide_file_column
        assert table.show_horizontal_scrollbar is False
        assert sum(column.width for column in table.columns.values()) <= table.content_size.width

        await pilot.resize_terminal(150, 48)
        await settle(pilot)
        assert dossier.display is True
        assert table.columns["file"].width == wide_file_column


async def test_sort_filter_and_clear(demo):
    app = RotApp(demo, demo=True)
    async with app.run_test(size=(150, 48)) as pilot:
        await settle(pilot)
        table = app.query_one("#files", DataTable)

        assert app.sort_mode == "risk"
        assert app._table_files[0].path == demo.sorted_files("risk")[0].path
        await pilot.press("s")
        await settle(pilot, 2)
        assert app.sort_mode == "churn"
        assert app._table_files[0].path == demo.sorted_files("churn")[0].path

        await pilot.press("f")
        await settle(pilot, 2)
        assert app._filter_visible is True
        assert app.query_one("#filter", Input).has_focus
        await pilot.press(*"legacy")
        await settle(pilot, 2)
        assert app.filter_text == "legacy"
        assert table.row_count == 2
        assert all("legacy" in file.path for file in app._table_files)

        await pilot.press("enter")
        await settle(pilot, 2)
        assert app._filter_visible is False
        assert table.has_focus
        assert table.row_count == 2

        await pilot.press("escape")
        await settle(pilot, 2)
        assert app.filter_text == ""
        assert table.row_count == len(demo.files)


async def test_map_lens_cycles_and_renders(demo):
    app = RotApp(demo, demo=True)
    async with app.run_test(size=(150, 48)) as pilot:
        await settle(pilot)
        map_widget = app.query_one("#map")
        seen = []
        for _ in range(4):
            await pilot.press("c")
            await settle(pilot, 2)
            seen.append(app.map_mode)
            assert map_widget.mode == app.map_mode
            assert MODE_TITLES[app.map_mode].lower() in map_widget.border_title.lower()
            assert map_widget.render().plain
        assert seen == ["churn", "age", "complexity", "risk"]


async def test_first_and_last_file_bindings(demo):
    app = RotApp(demo, demo=True)
    async with app.run_test(size=(150, 48)) as pilot:
        await settle(pilot)
        ordered = demo.sorted_files("risk")
        await pilot.press("G")
        await settle(pilot, 2)
        assert app.selected_path == ordered[-1].path
        await pilot.press("g")
        await settle(pilot, 2)
        assert app.selected_path == ordered[0].path


async def test_help_and_inspect_modals(demo):
    app = RotApp(demo, demo=True)
    async with app.run_test(size=(150, 48)) as pilot:
        await settle(pilot)
        await pilot.press("question_mark")
        await settle(pilot, 2)
        assert isinstance(app.screen, HelpScreen)

        await pilot.press("escape")
        await settle(pilot, 2)
        assert not isinstance(app.screen, HelpScreen)

        await pilot.press("enter")
        await settle(pilot, 2)
        assert isinstance(app.screen, InspectScreen)
        assert app.screen.metric.path == app.selected_path

        await pilot.press("escape")
        await settle(pilot, 2)
        assert not isinstance(app.screen, InspectScreen)


async def test_help_modal_at_80x24():
    app = RotApp(demo_snapshot(), demo=True)
    async with app.run_test(size=(80, 24)) as pilot:
        await settle(pilot)
        app.action_help()
        await settle(pilot, 2)
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await settle(pilot, 2)
        assert not isinstance(app.screen, HelpScreen)


async def test_rescan_in_demo_mode_is_synchronous(demo):
    app = RotApp(demo, demo=True)
    async with app.run_test(size=(120, 36)) as pilot:
        await settle(pilot)
        original = app.snapshot.summary.risk_index
        await pilot.press("r")
        await settle(pilot, 2)
        assert app._scanning is False
        assert app.snapshot.summary.risk_index == original
        assert app.query_one("#brand").scanning is False


async def test_initial_filter_is_applied():
    app = RotApp(demo_snapshot(), demo=True, initial_filter="legacy")
    async with app.run_test(size=(150, 48)) as pilot:
        await settle(pilot)
        assert app.filter_text == "legacy"
        assert app._filter_visible is True
        assert app.query_one("#files", DataTable).row_count == 2
        assert all("legacy" in file.path for file in app._table_files)


async def test_escape_clears_initial_filter():
    app = RotApp(demo_snapshot(), demo=True, initial_filter="legacy")
    async with app.run_test(size=(150, 48)) as pilot:
        await settle(pilot)
        await pilot.press("escape")
        await settle(pilot, 2)
        assert app.filter_text == ""
        assert app._filter_visible is False
        assert app.query_one("#files", DataTable).row_count == len(app.snapshot.files)

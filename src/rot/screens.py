"""Modal screens: the full file dossier and the help / methodology view."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from .models import FileMetric, RepoSummary
from .render import help_text, inspect_text
from .theme import ACCENT, DIM, TEXT


class _ModalBase(ModalScreen[None]):
    BINDINGS = [
        Binding("escape,q,question_mark", "dismiss", "Close", show=False),
    ]

    def _hint(self) -> Text:
        text = Text()
        text.append(" esc ", style=f"bold {TEXT} on #22362a")
        text.append(" / ", style=DIM)
        text.append(" q ", style=f"bold {TEXT} on #22362a")
        text.append("  close   ", style=DIM)
        text.append(" ↑↓ ", style=f"bold {TEXT} on #22362a")
        text.append(" scroll", style=DIM)
        return text


class InspectScreen(_ModalBase):
    """Detailed, scrollable report for one file."""

    def __init__(self, metric: FileMetric, summary: RepoSummary, now: float) -> None:
        super().__init__()
        self.metric = metric
        self.summary = summary
        self.now = now

    def compose(self) -> ComposeResult:
        with Container(classes="modal-card", id="inspect-card"):
            with VerticalScroll(classes="modal-scroll", id="inspect-scroll"):
                yield Static(
                    inspect_text(self.metric, self.summary, self.now),
                    classes="modal-body",
                )
            yield Static(self._hint(), classes="modal-hint")

    def on_mount(self) -> None:
        self.query_one("#inspect-scroll", VerticalScroll).focus()


class HelpScreen(_ModalBase):
    """Keys and the scoring model, in the app's own visual language."""

    def compose(self) -> ComposeResult:
        with Container(classes="modal-card", id="help-card"):
            with VerticalScroll(classes="modal-scroll", id="help-scroll"):
                yield Static(help_text(), classes="modal-body")
            yield Static(self._hint(), classes="modal-hint")

    def on_mount(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).focus()

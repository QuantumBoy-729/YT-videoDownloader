"""One row in the download queue: owns a DownloadJob and its worker thread."""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout

from ..core import DownloadJob, DownloadRequest, JobState, Progress
from ..core.models import JobResult
from . import fmt
from .theme import Theme
from .widgets import ElidedLabel, IconButton

_STAGES = {
    "video": "Downloading video",
    "audio": "Downloading audio",
    "media": "Downloading",
    "processing": "Processing",
}


def reveal(path: Path) -> None:
    """Show ``path`` in the system file manager."""
    if os.name == "nt" and path.is_file():
        subprocess.Popen(["explorer", "/select,", str(path)])
        return
    folder = path if path.is_dir() else path.parent
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


class QueueItem(QFrame):
    """Card showing a download's progress with pause / cancel / retry controls."""

    #: Emitted whenever the job's state changes (so the queue can start the next one).
    changed = Signal()
    removeRequested = Signal(object)

    # Delivered from the worker thread; Qt queues them onto the GUI thread.
    _progress = Signal(object)
    _state = Signal(object)
    _finished = Signal(object)

    def __init__(
        self,
        request: DownloadRequest,
        title: str,
        theme: Theme,
        job_options: dict[str, Any] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.request = request
        self._theme = theme
        self._job_options = job_options or {}
        self._started = False
        self._last: Progress | None = None
        self.result: JobResult | None = None

        self._progress.connect(self._on_progress)
        self._state.connect(self._on_state)
        self._finished.connect(self._on_finished)

        self.title_label = ElidedLabel(title)
        self.title_label.setObjectName("itemTitle")
        chip_text = request.file_format.upper()
        if not request.audio_only:
            chip_text += f" · {fmt.height_label(request.max_height).split(' · ')[0]}"
        if request.playlist:
            chip_text += " · Playlist"
        chip = QLabel(chip_text)
        chip.setObjectName("chip")

        self.status_label = ElidedLabel()
        self.status_label.setObjectName("muted")
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)

        self.pause_button = IconButton("pause", "Pause", theme)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.retry_button = IconButton("retry", "Try again", theme)
        self.retry_button.clicked.connect(self.retry)
        self.folder_button = IconButton("folder", "Show in folder", theme)
        self.folder_button.clicked.connect(self._reveal)
        self.close_button = IconButton("close", "Cancel", theme)
        self.close_button.clicked.connect(self._close_clicked)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.title_label, 1)
        top.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(6)
        text.addLayout(top)
        text.addWidget(self.bar)
        text.addWidget(self.status_label)

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 10, 12)
        row.setSpacing(6)
        row.addLayout(text, 1)
        row.addSpacing(6)
        for button in (self.pause_button, self.retry_button, self.folder_button, self.close_button):
            row.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)

        self._new_job()

    # -- public ----------------------------------------------------------------

    @property
    def state(self) -> JobState:
        return self.job.state

    @property
    def waiting(self) -> bool:
        return self.job.state is JobState.QUEUED and not self._started

    @property
    def active(self) -> bool:
        return self._started and not self.job.state.finished

    def start(self) -> None:
        if not self.waiting:
            return
        self._started = True
        job = self.job
        threading.Thread(target=lambda: self._emit(self._finished, (job, job.run())), daemon=True).start()

    def toggle_pause(self) -> None:
        if self.job.state is JobState.PAUSED:
            self.job.resume()
        else:
            self.job.pause()

    def cancel(self) -> None:
        self.job.cancel()

    def retry(self) -> None:
        if self.job.state.finished:
            self._new_job()
            self.changed.emit()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        for button in (self.pause_button, self.retry_button, self.folder_button, self.close_button):
            button.set_theme(theme)

    # -- internals -------------------------------------------------------------

    def _new_job(self) -> None:
        job_ref: list[DownloadJob] = []
        self.job = DownloadJob(
            self.request,
            on_progress=lambda p: self._emit(self._progress, (job_ref[0], p)),
            on_state=lambda s: self._emit(self._state, (job_ref[0], s)),
            **self._job_options,
        )
        job_ref.append(self.job)
        self._started = False
        self._last = None
        self.result = None
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self._refresh()

    @staticmethod
    def _emit(signal, payload) -> None:
        try:
            signal.emit(payload)
        except RuntimeError:
            pass  # The widget was deleted while the worker was finishing.

    def _on_progress(self, payload) -> None:
        job, progress = payload
        if job is not self.job:
            return
        self._last = progress
        if progress.title and not self.request.playlist:
            self.title_label.setText(progress.title)
        self._refresh()

    def _on_state(self, payload) -> None:
        job, _state = payload
        if job is not self.job:
            return
        self._refresh()
        self.changed.emit()

    def _on_finished(self, payload) -> None:
        job, result = payload
        if job is not self.job:
            return
        self.result = result
        self._refresh()
        self.changed.emit()

    def _close_clicked(self) -> None:
        if self.job.state.finished:
            self.removeRequested.emit(self)
        else:
            self.cancel()

    def _reveal(self) -> None:
        files = self.result.files if self.result else []
        reveal(files[0] if files else self.request.output_dir)

    def _refresh(self) -> None:
        state = self.job.state
        progress = self._last
        finished = state.finished

        self.pause_button.setVisible(state in (JobState.RUNNING, JobState.PAUSED))
        if state is JobState.PAUSED:
            self.pause_button.set_icon("play", "Resume")
        else:
            self.pause_button.set_icon("pause", "Pause")
        self.retry_button.setVisible(state in (JobState.FAILED, JobState.CANCELLED))
        self.folder_button.setVisible(state is JobState.DONE)
        self.close_button.set_icon("close", "Remove from list" if finished else "Cancel")

        busy = state is JobState.RUNNING and (progress is None or progress.fraction is None)
        if busy:
            self.bar.setRange(0, 0)
        else:
            self.bar.setRange(0, 1000)
            if state is JobState.DONE:
                self.bar.setValue(1000)
            elif progress and progress.fraction is not None:
                self.bar.setValue(int(progress.fraction * 1000))

        bar_state = {
            JobState.DONE: "done", JobState.FAILED: "failed",
            JobState.PAUSED: "paused", JobState.CANCELLED: "paused",
        }.get(state, "")
        status_name = {JobState.FAILED: "error", JobState.DONE: "success"}.get(state, "muted")
        for widget, prop, value in (
            (self.bar, "state", bar_state),
            (self.status_label, "objectName", status_name),
        ):
            if widget.property(prop) != value:
                widget.setProperty(prop, value)
                widget.style().unpolish(widget)
                widget.style().polish(widget)

        self.status_label.setText(self._status_text(state, progress))

    def _status_text(self, state: JobState, progress: Progress | None) -> str:
        if state is JobState.QUEUED:
            return "Waiting to start"
        if state is JobState.CANCELLED:
            return "Cancelled"
        if state is JobState.FAILED:
            return (self.result.error if self.result else "") or "Download failed"
        if state is JobState.DONE:
            files = self.result.files if self.result else []
            where = str(files[0].parent if files else self.request.output_dir)
            count = f"{len(files)} files saved" if len(files) > 1 else "Saved"
            return f"{count} to {where}"
        if progress is None:
            return "Starting"

        parts = []
        if progress.playlist_index and progress.playlist_count:
            parts.append(f"Item {progress.playlist_index} of {progress.playlist_count}")
        if state is JobState.PAUSED:
            parts.append("Paused")
        else:
            parts.append(_STAGES.get(progress.stage, "Downloading"))
        if progress.stage != "processing":
            if progress.total:
                parts.append(f"{fmt.size(progress.downloaded)} of {fmt.size(progress.total)}")
            elif progress.downloaded:
                parts.append(fmt.size(progress.downloaded))
            if state is JobState.RUNNING:
                if progress.speed:
                    parts.append(fmt.speed(progress.speed))
                if progress.eta is not None:
                    parts.append(f"{fmt.clock(progress.eta)} left")
        return " · ".join(parts)

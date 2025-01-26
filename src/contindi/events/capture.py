from ..cache import Cache
from ..system import Connection
from ..config import CONFIG
from .base import Event, EventStatus


class Capture(Event):
    def __init__(self, job_name, duration, priority=0, keep=True, private=False):
        self.priority = priority
        self.duration = duration
        self.keep = keep
        self.private = private
        self.job_name = job_name
        self._status = EventStatus.Ready
        self.timestamp = None

    def cancel(self, cxn: Connection, _cache: Cache) -> EventStatus:
        """Cancel the running event."""
        self._status = EventStatus.Failed
        return self._status, "Capture was cancelled."

    def status(self, cxn: Connection, cache: Cache) -> EventStatus:
        """Check the status of the event."""
        if self._status == EventStatus.Running:
            cur_state = cxn[CONFIG.camera]["CCD1"]
            if self.timestamp != cur_state.timestamp:
                self._status = EventStatus.Finished
                cache.add_frame(
                    self.job_name,
                    cur_state.elements["CCD1"].frame,
                    solved=False,
                    keep_frame=self.keep,
                    private=self.private,
                )
        return self._status, None

    def trigger(self, cxn: Connection, _cache: Cache):
        """Trigger the beginning of the event."""
        self.timestamp = cxn[CONFIG.camera]["CCD1"].timestamp
        cxn.set_value(CONFIG.camera, "CCD_EXPOSURE", self.duration, block=False)
        self._status = EventStatus.Running

    def __repr__(self):
        return (
            f"Capture({self.job_name}, duration={self.duration}, "
            f"priority={self.priority}, keep={self.keep}, private={self.private})"
        )

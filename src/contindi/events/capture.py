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
        self.max_time = duration + 5

    def cancel(self, cxn: Connection, _cache: Cache):
        """Cancel the running event."""
        self._status = EventStatus.Failed

    def status(self, cxn: Connection, cache: Cache):
        """Check the status of the event."""
        if self._status == EventStatus.Running:
            cur_state = cxn[CONFIG.camera]["CCD1"]
            if self.timestamp != cur_state.timestamp:
                self._status = EventStatus.Finished
                if cache is None:
                    return self._status, "No Cache found, image not saved."
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
        self._status = EventStatus.Running
        cxn.set_value(CONFIG.camera, "CCD_EXPOSURE", self.duration, block=False)

    def __repr__(self):
        return (
            f"Capture({self.job_name}, duration={self.duration}, "
            f"priority={self.priority}, keep={self.keep}, private={self.private})"
        )

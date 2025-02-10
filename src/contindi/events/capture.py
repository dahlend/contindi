from ..cache import Cache
from ..system import Connection
from ..config import CONFIG
from .base import Event, EventStatus


class Capture(Event):
    def __init__(self, job_id, duration, priority=0):
        self.priority = priority
        self.duration = duration
        self.job_id = job_id
        self.status = EventStatus.Ready
        self.timestamp = None
        self.max_time = duration + 5

    def cancel(self, cxn: Connection, _cache: Cache):
        """Cancel the running event."""
        self.status = EventStatus.Failed

    def update(self, cxn: Connection, cache: Cache):
        """Check the status of the event."""
        if self.status == EventStatus.Running:
            cur_state = cxn[CONFIG.camera]["CCD1"]
            if self.timestamp != cur_state.timestamp:
                try:
                    cache.add_frame(self.job_id, cur_state.elements["CCD1"].frame)
                    self.status = EventStatus.Finished
                except Exception as e:
                    self.status = EventStatus.Failed
                    self.msg = f"Failed to upload file! {e}"

    def trigger(self, cxn: Connection, _cache: Cache):
        """Trigger the beginning of the event."""
        self.timestamp = cxn[CONFIG.camera]["CCD1"].timestamp
        self.status = EventStatus.Running
        cxn.set_value(CONFIG.camera, "CCD_EXPOSURE", self.duration, block=False)

    def __repr__(self):
        return (
            f"Capture({self.job_id}, duration={self.duration}, "
            f"priority={self.priority}, keep={self.keep}, private={self.private})"
        )

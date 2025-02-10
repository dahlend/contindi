from ..config import CONFIG
from .base import Event, EventStatus
from ..cache import SolveStatus


class Capture(Event):
    def __init__(self, job_id, duration, priority=0):
        self.priority = priority
        self.duration = duration
        self.job_id = job_id
        self.status = EventStatus.Ready
        self.timestamp = None
        self.max_time = duration + 5

    def cancel(self, cxn, _cache):
        """Cancel the running event."""
        self.status = EventStatus.Failed

    def update(self, cxn, cache):
        """Check the status of the event."""

        if self.status == EventStatus.Running:
            cur_state = cxn[CONFIG.camera]["CCD1"]
            if self.timestamp != cur_state.timestamp:
                try:
                    cache.add_frame(self.job_id, cur_state.elements["CCD1"].frame)
                    cache.update_job(
                        self.job_id,
                        log="Exposure complete",
                        solve=SolveStatus.UNSOLVED,
                    )
                    self.status = EventStatus.Finished
                except Exception as e:
                    self.status = EventStatus.Failed
                    cache.update_job(
                        self.job_id,
                        log=f"Exposure failed to upload file: {e}",
                    )

    def trigger(self, cxn, cache):
        """Trigger the beginning of the event."""
        cache.update_job(
            self.job_id,
            log=f"Exposure for {self.duration} seconds",
        )

        self.timestamp = cxn[CONFIG.camera]["CCD1"].timestamp
        self.status = EventStatus.Running
        cxn.set_value(CONFIG.camera, "CCD_EXPOSURE", self.duration, block=False)

    def __repr__(self):
        return (
            f"Capture({self.job_id}, duration={self.duration}, "
            f"priority={self.priority}, keep={self.keep}, private={self.private})"
        )

from .base import Event, EventStatus
from datetime import datetime, timedelta, UTC


class Delay(Event):
    def __init__(self, delay: float, priority=0):
        """
        Time delay in seconds.
        This event is always ready to run, and is useful for adding settle times after
        slews for example.
        """
        self.delay = timedelta(seconds=delay)
        self.priority = priority
        self.status = EventStatus.Ready
        self._end_time = None

    def update(self, _cxn, _cache):
        cur_time = datetime.now(UTC)
        if (
            self.status == EventStatus.Running
            and self._end_time is not None
            and cur_time > self._end_time
        ):
            self.status = EventStatus.Finished

    def cancel(self, _cxn, _cache):
        self.status = EventStatus.Failed
        self.msg = "Canceled"

    def trigger(self, _cxn, _cache):
        self._end_time = datetime.now(UTC) + self.delay
        self.status = EventStatus.Running

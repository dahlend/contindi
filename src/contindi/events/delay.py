from .base import Event, EventStatus
from datetime import datetime, timedelta


class Delay(Event):
    def __init__(self, delay: float, priority=0):
        """
        Time delay in seconds.
        This event is always ready to run, and is useful for adding settle times after
        slews for example.
        """
        self.delay = timedelta(seconds=delay)
        self.priority = priority
        self._status = EventStatus.Ready
        self._end_time = None

    def status(self, _cxn, _cache):
        cur_time = datetime.now()
        if (
            self._status == EventStatus.Running
            and self._end_time is not None
            and cur_time > self._end_time
        ):
            self._status = EventStatus.Finished
        return (self._status, None)

    def cancel(self, _cxn, _cache):
        self._status = EventStatus.Failed

    def trigger(self, _cxn, _cache):
        self._end_time = datetime.now() + self.delay
        self._status = EventStatus.Running

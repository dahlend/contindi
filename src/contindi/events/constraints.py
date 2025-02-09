"""
Constraints on events, IE: time or geometry
"""

from .base import Event, EventStatus
from datetime import datetime, UTC
from typing import Optional


class TimeConstrained(Event):
    """
    Add a time constraint to an event, if events are ready before a start
    time, then this will return NotReady, if events are ready after an end
    time, this will return Failed.
    """

    def __init__(
        self,
        event: Event,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ):
        self.start_time = start_time
        self.end_time = end_time
        self.event = event
        self.priority = event.priority

    def update(self, cxn, cache):
        # Get the current status, if it is ready, check if it is inside our
        # time limit.
        self.event.update(cxn, cache)
        self.status = self.event.status
        self.msg = self.event.msg
        if self.status == EventStatus.Ready:
            cur_time = datetime.now(UTC)
            if self.start_time is not None and cur_time < self.start_time:
                return (EventStatus.NotReady, None)
            if self.end_time is not None and cur_time > self.end_time:
                self.event.cancel(cxn, cache)
                self.status = self.event.status
                self.msg = "Event Ready after max time constraint met"

    def trigger(self, cxn, cache):
        return self.event.trigger(cxn, cache)

    def cancel(self, cxn, cache):
        return self.event.cancel(cxn, cache)

    def __repr__(self):
        return f"TimeConstrained({self.event.__repr__()}, '{self.start_time}', '{self.end_time}')"

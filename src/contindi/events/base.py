import dataclasses
from enum import Enum
from abc import abstractmethod, ABC
from typing import Optional
import time
from ..system import Connection
from ..cache import Cache


class EventStatus(Enum):
    NotReady = 0
    Ready = 1
    Running = 2
    Finished = 3
    Canceling = 4
    Failed = 5

    @property
    def is_done(self) -> bool:
        return self in [EventStatus.Finished, EventStatus.Failed]

    @property
    def is_active(self) -> bool:
        return self in [EventStatus.Running, EventStatus.Canceling]

    @property
    def is_started(self) -> bool:
        return self not in [EventStatus.Ready, EventStatus.NotReady]

    @property
    def next(self) -> "EventStatus":
        """
        Status is essentially a state machine, this allows for an advancement
        of the status states.
        """
        if self == EventStatus.NotReady:
            return EventStatus.Ready
        elif self == EventStatus.Ready:
            return EventStatus.Running
        elif self == EventStatus.Running:
            return EventStatus.Finished
        elif self == EventStatus.Finished:
            return EventStatus.Finished
        elif self == EventStatus.Canceling:
            return EventStatus.Failed
        elif self == EventStatus.Failed:
            return EventStatus.Failed


@dataclasses.dataclass
class Event(ABC):
    """
    Definition of a schedule event.
    Events have a priority value, along with a set of functions which define behavior.

    Higher priority events are run first.

    If an event needs to be canceled while running, the `cancel` method will be called.
    """

    priority: int
    """Priority of the event."""

    max_time: float = dataclasses.field(default=120, repr=False)
    """Maximum length of time this may run for."""

    _start_time: Optional[float] = dataclasses.field(default=None, repr=False)
    """Reserved value to keep track of when the event is triggered."""

    @abstractmethod
    def cancel(
        self, cxn: Connection, cache: Cache
    ) -> tuple[EventStatus, Optional[str]]:
        """Cancel the running event."""
        raise NotImplementedError()

    @abstractmethod
    def status(
        self, cxn: Connection, cache: Cache
    ) -> tuple[EventStatus, Optional[str]]:
        """Check the status of the event."""
        raise NotImplementedError()

    @abstractmethod
    def trigger(self, cxn: Connection, cache: Cache):
        """Trigger the beginning of the event."""
        raise NotImplementedError()

    def _cancel(self, cxn, cache):
        try:
            return self.cancel(cxn, cache)
        except Exception as e:
            return EventStatus.Failed, f"Failed with exception {str(e)}"

    def _get_status(self, cxn, cache):
        try:
            status, msg = self.status(cxn, cache)
            if (
                status == EventStatus.Running
                and (time.time() - self._start_time) > self.max_time
            ):
                self._cancel()
                return EventStatus.Failed, "Failed to complete within the time limit"
            return status, msg
        except Exception as e:
            return EventStatus.Failed, f"Failed with exception {str(e)}"

    def _trigger(self, cxn, cache):
        self._start_time = time.time()
        try:
            return self.trigger(cxn, cache)
        except Exception as e:
            return EventStatus.Failed, f"Failed with exception {str(e)}"

    def __lt__(self, other):
        return self.priority < other.priority

    def __add__(self, other):
        if isinstance(self, SeriesEvent):
            event_list = self.event_list
        else:
            event_list = [self]

        if isinstance(other, SeriesEvent):
            event_list.extend(other.event_list)
        else:
            event_list.append(other)
        return SeriesEvent(priority=self.priority, event_list=event_list)


class SeriesEvent(Event):
    def __init__(self, priority: int, event_list: list[Event]):
        self.priority = priority
        self.event_list = event_list
        if len(self.event_list) == 0:
            raise ValueError("Cannot create event with no contents.")
        self.current = 0
        self.max_time = sum([e.max_time for e in event_list]) + 10

    def cancel(self, cxn: Connection, cache: Cache):
        if self.current != len(self.event_list):
            return self.event_list[self.current].cancel(cxn, cache)

    def trigger(self, cxn: Connection, cache: Cache):
        raise NotImplementedError()

    def _trigger(self, cxn: Connection, cache: Cache):
        self._start_time = time.time()
        try:
            return self.event_list[self.current].trigger(cxn, cache)
        except Exception as e:
            return EventStatus.Failed, f"Failed with exception {str(e)}"

    def status(self, cxn: Connection, cache: Cache):
        status, msg = self.event_list[self.current].status(cxn, cache)
        while status == EventStatus.Finished:
            if len(self.event_list) == self.current + 1:
                return status, msg
            self.current += 1
            self._trigger(cxn, cache)
            status, msg = self.event_list[self.current].status(cxn, cache)
        return (status, msg)

    def __repr__(self):
        return f"SeriesEvent(priority={self.priority}, event_list={self.event_list})"

import dataclasses
from enum import Enum
from abc import abstractmethod, ABC
from typing import Optional
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

    @abstractmethod
    def cancel(self, cxn: Connection, cache: Cache) -> (EventStatus, Optional[str]):
        """Cancel the running event."""
        raise NotImplementedError()

    @abstractmethod
    def status(self, cxn: Connection, cache: Cache) -> (EventStatus, Optional[str]):
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
            return self.status(cxn, cache)
        except Exception as e:
            return EventStatus.Failed, f"Failed with exception {str(e)}"

    def _trigger(self, cxn, cache):
        try:
            return self.trigger(cxn, cache)
        except Exception as e:
            return EventStatus.Failed, f"Failed with exception {str(e)}"

    def __lt__(self, other):
        return self.priority < other.priority


class SeriesEvent(Event):
    def __init__(self, name: str, priority: int, event_list: list[Event]):
        self.name = name
        self.priority = priority
        self.event_list = event_list
        if len(self.event_list) == 0:
            raise ValueError("Cannot create event with no contents.")
        self.current = self.event_list.pop(0)

    def cancel(self, cxn: Connection, cache: Cache):
        if self.current is not None:
            return self.current.cancel(cxn, cache)

    def trigger(self, cxn: Connection, cache: Cache):
        self.current.trigger(cxn, cache)

    def status(self, cxn: Connection, cache: Cache):
        status, msg = self.current.status(cxn, cache)
        if status == EventStatus.Finished:
            if len(self.event_list) == 0:
                return status, msg
            self.current = self.event_list.pop(0)
            self.current.trigger(cxn, cache)
            return self.current.status(cxn, cache)
        return status

    def __repr__(self):
        return f"{self.name}(priority={self.priority}, event_list={self.event_list})"

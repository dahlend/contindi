import dataclasses
from enum import Enum
from abc import abstractmethod, ABC
from typing import Optional
import time
from ..connection import Connection

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..scheduler.cache import PBCache


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

    job_id: str
    """Job ID as stored in the cache"""

    priority: int
    """Priority of the event."""

    max_time: float = dataclasses.field(default=45, repr=False)
    """Maximum length of time this may run for."""

    _start_time: Optional[float] = dataclasses.field(default=None, repr=False)
    """Reserved value to keep track of when the event is triggered."""

    status: EventStatus = dataclasses.field(default=EventStatus.NotReady, repr=False)
    """Reserved value to keep track of when the current event status."""

    @abstractmethod
    def cancel(
        self, cxn: Connection, cache: "PBCache"
    ) -> tuple[EventStatus, Optional[str]]:
        """Cancel the running event."""
        raise NotImplementedError()

    @abstractmethod
    def update(self, cxn: Connection, cache: "PBCache"):
        """Check the status of the event."""
        raise NotImplementedError()

    @abstractmethod
    def trigger(self, cxn: Connection, cache: "PBCache"):
        """Trigger the beginning of the event."""
        raise NotImplementedError()

    def _cancel(self, cxn, cache):
        if self.status in [EventStatus.Failed, EventStatus.Finished]:
            return
        try:
            self.cancel(cxn, cache)
        except Exception as e:
            self.status = EventStatus.Failed
            cache.update_job(
                self.job_id, log=f"Failed with exception (cancel) {str(e)}"
            )

    def _update(self, cxn, cache):
        if self.status in [EventStatus.Failed, EventStatus.Finished]:
            return
        try:
            self.update(cxn, cache)
            if (
                self.status == EventStatus.Running
                and (time.time() - self._start_time) > self.max_time
            ):
                self._cancel(cxn, cache)
                self.status = EventStatus.Failed
                cache.update_job(
                    self.job_id, log="Failed to complete within the time limit"
                )
        except Exception as e:
            self.status = EventStatus.Failed
            cache.update_job(
                self.job_id, log=f"Failed with exception (update) {str(e)}"
            )

    def _trigger(self, cxn, cache):
        if self.status != EventStatus.Ready:
            return
        self._start_time = time.time()
        try:
            return self.trigger(cxn, cache)
        except Exception as e:
            self.status = EventStatus.Failed
            cache.update_job(
                self.job_id, log=f"Failed with exception (trigger) {str(e)}"
            )

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
        if len(set([e.job_id for e in event_list])) != 1:
            print(event_list)
            raise ValueError(
                "Multiple job IDs found, events can only be combined if they are the same job id."
            )
        return SeriesEvent(
            job_id=event_list[0].job_id,
            priority=self.priority,
            event_list=event_list,
        )


class SeriesEvent(Event):
    def __init__(self, job_id, priority: int, event_list: list[Event]):
        self.job_id = job_id
        self.priority = priority
        self.event_list = event_list
        if len(self.event_list) == 0:
            raise ValueError("Cannot create event with no contents.")
        self.current = 0
        self.max_time = sum([e.max_time for e in event_list]) + 10

    @property
    def _event(self):
        return self.event_list[self.current]

    def cancel(self, cxn: Connection, cache: "PBCache"):
        if self.current != len(self.event_list):
            return self._event.cancel(cxn, cache)

    def trigger(self, cxn: Connection, cache: "PBCache"):
        raise NotImplementedError("Trigger should not be called on Series Events")

    def _trigger(self, cxn: Connection, cache: "PBCache"):
        self._start_time = time.time()
        self._event._trigger(cxn, cache)

    def update(self, cxn: Connection, cache: "PBCache"):
        self._event.update(cxn, cache)
        self.status = self._event.status
        while self.status == EventStatus.Finished:
            if len(self.event_list) == self.current + 1:
                return
            self.current += 1
            self._trigger(cxn, cache)
            self._event.update(cxn, cache)
            self.status = self._event.status

    def __repr__(self):
        return f"SeriesEvent(priority={self.priority}, event_list={self.event_list})"

import dataclasses
from collections.abc import Callable
from enum import Enum
import time
from abc import abstractmethod, ABC


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
    def next(self) -> EventStatus:
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
    def cancel(self) -> EventStatus:
        """Cancel the running event."""
        raise NotImplementedError()

    @abstractmethod
    def status(self) -> EventStatus:
        """Check the status of the event."""
        raise NotImplementedError()

    @abstractmethod
    def trigger(self):
        """Trigger the beginning of the event."""
        raise NotImplementedError()

    def __lt__(self, other):
        return self.priority < other.priority


class SeriesEvent(Event):
    def __init__(self, priority: int, event_list: list[Event]):
        self.priority = priority
        self.event_list = event_list
        if len(self.event_list) == 0:
            raise ValueError("Cannot create event with no contents.")
        self.current = self.event_list.pop(0)

    def cancel(self):
        if self.current is not None:
            return self.current.cancel()

    def trigger(self):
        self.current.trigger()

    def status(self):
        status = self.current.status()
        if status == EventStatus.Finished:
            if len(self.event_list) == 0:
                return status
            self.current = self.event_list.pop(0)
            self.current.trigger()
            return self.current.status()
        return status


class Scheduler:
    """
    Greedy scheduler for running `Event`s.

    Keeps track of a sorted list of `Event` objects, checking them in order for the
    highest priority one which has its constraints satisfied. This event is run and
    the scheduler waits for completion of the event before repeating the process.

    Only one event is ever active at a time.
    """

    def __init__(self):
        self.event_list = []
        self.poll_rate = 1

    def add_event(self, event: Event):
        status = event.status()
        if status.is_started:
            raise ValueError("This event has already happened.")
        self.event_list.append(event)
        self.event_list.sort()

    def poll(self):
        keep = []
        trigger = None
        for event in self.event_list:
            status = event.status()
            if not status.is_done:
                keep.append(event)
                if trigger is None and status == EventStatus.Ready:
                    trigger = event
        self.event_list = keep

        if trigger is not None:
            trigger.trigger()

    def run(self):
        while True:
            try:
                self.poll()
                time.sleep(self.poll_rate)
            except KeyboardInterrupt:
                return

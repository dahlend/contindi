import dataclasses
from collections.abc import Callable
from enum import Enum
import time
from abc import abstractmethod, ABC


class ConstraintStatus(Enum):
    Satisfied = True
    NotSatisfied = False
    Unsatisfiable = None


class EventStatus(Enum):
    Running = 1
    Canceling = 2
    Canceled = 3
    Finished = 4


@dataclasses.dataclass
class Event(ABC):
    """
    Definition of a schedule event.
    Events have a priority value, along with a set of functions which define behavior.

    Higher priority events are run first.

    Events will always be checked to see if their constraints are satisfied before
    triggering the beginning of the event.
    After triggering, constraints will no longer be checked, but the `check` method
    will be called to check the status of the event.
    If an event needs to be canceled while running, the `cancel` method will be called.
    """

    priority: int
    """Priority of the event."""

    @abstractmethod
    def cancel(self) -> EventStatus:
        """Cancel the running event."""
        raise NotImplementedError()

    @abstractmethod
    def check(self) -> EventStatus:
        """Check the status of the event."""
        raise NotImplementedError()

    @abstractmethod
    def trigger(self):
        """Trigger the beginning of the event."""
        raise NotImplementedError()

    @abstractmethod
    def check_constraints(self) -> ConstraintStatus:
        """
        Are the constraints for the event currently satisfied.
        IE: If we trigger the event now is it ok to run.
        """
        raise NotImplementedError()

    def __lt__(self, other):
        return self.priority < other.priority


class Scheduler:
    """
    Greedy scheduler for running `Event`s.

    Keeps track of a sorted list of `Event` objects, checking them in order for the
    highest priority one which has its constraints satisfied. This event is run and
    the scheduler waits for completion of the event before repeating the process.

    Only one event is ever active at a time, if an event is active it is removed from
    the event list.
    """

    def __init__(self, poll_rate=0.1):
        self.event_list = []
        self.current_event = None
        self.poll_rate = poll_rate

    def add_event(self, event: Event):
        """
        Add a new event to the schedule.
        """
        self.event_list.append(event)

    def check(self):
        """
        Check the status of current running event, or start a new event if possible.

        Events which are running are removed from the event list.

        If the current event is not running, sorts the event list by priority, and
        trigger the next event which is possible.
        """
        if self.current_event is not None:
            status = self.current_event.check()
            if status == EventStatus.Running or status == EventStatus.Canceling:
                return
            else:
                self.current_event = None
        self.event_list.sort(reverse=True)
        keep = []
        for event in self.event_list:
            constraint = event.check_constraints()
            if constraint == ConstraintStatus.Satisfied and self.current_event is None:
                self.current_event = event
                self.current_event.trigger()
            elif constraint == ConstraintStatus.NotSatisfied:
                keep.append(event)
        self.event_list = keep

    def run(self):
        """
        Run the scheduler forever, running the check function at regular intervals.
        """
        while True:
            try:
                self.check()
                time.sleep(self.poll_rate)
            except KeyboardInterrupt:
                return

import dataclasses
from collections.abc import Callable
from enum import Enum
import multiprocessing
import signal
import logging
from queue import Empty
import time
from abc import abstractmethod, ABC
from .system import Connection


logger = logging.getLogger(__name__)


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

    name: str
    """Name of the event."""

    priority: int
    """Priority of the event."""

    @abstractmethod
    def cancel(self, cxn: Connection) -> EventStatus:
        """Cancel the running event."""
        raise NotImplementedError()

    @abstractmethod
    def status(self, cxn: Connection) -> EventStatus:
        """Check the status of the event."""
        raise NotImplementedError()

    @abstractmethod
    def trigger(self, cxn: Connection):
        """Trigger the beginning of the event."""
        raise NotImplementedError()

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

    def cancel(self, cxn: Connection):
        if self.current is not None:
            return self.current.cancel(cxn)

    def trigger(self, cxn: Connection):
        self.current.trigger(cxn)

    def status(self, cxn: Connection):
        status = self.current.status(cxn)
        if status == EventStatus.Finished:
            logger.info(
                "%s - %s - Finished with %s", self.name, self.current.name, str(status)
            )
            if len(self.event_list) == 0:
                return status
            self.current = self.event_list.pop(0)
            logger.info("%s - %s - Trigger", self.name, self.current.name)
            self.current.trigger(cxn)
            return self.current.status(cxn)
        return status


class Scheduler:
    """
    Greedy scheduler for running `Event`s.

    Keeps track of a sorted list of `Event` objects, checking them in order for the
    highest priority one which has its constraints satisfied. This event is run and
    the scheduler waits for completion of the event before repeating the process.

    Only one event is ever active at a time.
    """

    timeout = 10

    def __init__(self, host="localhost", port=7624):
        """
        Parameters
        ----------
        host:
            Host address for the INDI server, defaults to `localhost`.
        port:
            Port number of the INDI server, defaults to 7624.
        """
        self.host = (host, port)

        self.task_queue = multiprocessing.Queue()
        self.response_queue = multiprocessing.Queue()
        self.process = None
        self.connect()

    def connect(self):
        if self.is_connected:
            # already connected
            return
        elif self.process is not None:
            del self.process
        self.process = multiprocessing.Process(
            target=self._process_tasks,
            args=(self.task_queue, self.response_queue, self.host),
        )
        # Ensures process exits when main program ends
        self.process.start()

    @property
    def is_connected(self):
        if self.process is None:
            return False
        return self.process.is_alive()

    def add_event(self, event: Event):
        self.task_queue.put(("event", event))

    def status(self):
        self.task_queue.put(("status", None))

    def cancel(self):
        self.task_queue.put(("clear", None))

    def close(self):
        """
        Close the connection.
        """
        self.task_queue.put(("stop", None))
        self.process.terminate()

    @staticmethod
    def _process_tasks(task_queue: multiprocessing.Queue, response_queue, host):
        """
        Threaded process which keeps track of the server connection and data packets.
        """
        # Ignore interrupt signals
        # this allows keyboard interrupts to run without issue
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        event_list = []
        cxn = Connection(*host)
        running = None

        while True:
            # if there is nothing to do, chill for bit.
            if len(event_list) == 0 and task_queue.empty():
                time.sleep(0.05)

            # Get new commands from queue
            while not task_queue.empty():
                # Get the next command and possibly event
                cmd, value = task_queue.get_nowait()

                if cmd == "stop":
                    logger.error("Closing Connection!")
                    cxn.close()
                    return
                elif cmd == "clear":
                    logger.warning("Clearing event list, %s removed ", len(event_list))
                    if running is not None:
                        logger.warning("%s Cancelling", running.name)
                        running.cancel(cxn)
                        event_list = [running]
                    else:
                        event_list = []
                elif cmd == "status":
                    if running is not None:
                        logger.warning("%s Running", running.name)
                    if len(event_list) > 0:
                        logger.warning("%s remaining in queue", len(event_list))
                    else:
                        logger.warning("Waiting for new jobs")
                elif cmd == "event":
                    if not isinstance(value, Event):
                        logger.error(
                            "Submitted object is not an Event, ignoring it %s",
                            str(value),
                        )
                        continue
                    status = value.status(cxn)
                    if status.is_started:
                        logger.error("This event has already happened, ignoring it")
                        continue
                    event_list.append(value)
                    event_list.sort()
                else:
                    logger.error("Unkown Command")

            keep = []
            trigger = None
            running = None
            for event in event_list:
                status = event.status(cxn)
                logger.debug("%s - %s", event.name, str(status))
                if status.is_active:
                    running = event
                if not status.is_done:
                    keep.append(event)
                    if trigger is None and status == EventStatus.Ready:
                        trigger = event
                else:
                    logger.info("%s - Finished with %s", event.name, str(status))
            event_list = keep

            if running is None and trigger is not None:
                logger.info("%s - Triggered", trigger.name)
                trigger.trigger(cxn)

        logger.error("Closing Connection!")
        cxn.close()

    def __del__(self):
        self.close()

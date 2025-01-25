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
from .cache import Cache


logger = logging.getLogger(__name__)


class Scheduler:
    """
    Greedy scheduler for running `Event`s.

    Keeps track of a sorted list of `Event` objects, checking them in order for the
    highest priority one which has its constraints satisfied. This event is run and
    the scheduler waits for completion of the event before repeating the process.

    Only one event is ever active at a time.
    """

    timeout = 10

    def __init__(self, host="localhost", port=7624, cache_path=None):
        """
        Parameters
        ----------
        host:
            Host address for the INDI server, defaults to `localhost`.
        port:
            Port number of the INDI server, defaults to 7624.
        cache_path:
            File where the cache should be, if `None`, no cache will be used.
        """
        self.host = (host, port)

        self.task_queue = multiprocessing.Queue()
        self.response_queue = multiprocessing.Queue()
        self.process = None
        self.cache_path = cache_path
        self.connect()

    def connect(self):
        if self.is_connected:
            # already connected
            return
        elif self.process is not None:
            del self.process
        self.process = multiprocessing.Process(
            target=self._process_tasks,
            args=(self.task_queue, self.response_queue, self.host, self.cache_path),
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
    def _process_tasks(
        task_queue: multiprocessing.Queue, response_queue, host, cache_path
    ):
        """
        Threaded process which keeps track of the server connection and data packets.
        """
        # Ignore interrupt signals
        # this allows keyboard interrupts to run without issue
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        event_list = []
        cxn = Connection(*host)
        if cache_path is not None:
            cache = Cache(cache_path)
        else:
            cache = None
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
                        _, msg = running._cancel(cxn, cache)
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
                    status, msg = value._status(cxn, cache)
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
                status, msg = event._status(cxn, cache)
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
                _, msg = trigger._trigger(cxn, cache)

        logger.error("Closing Connection!")
        cxn.close()

    def __del__(self):
        self.close()

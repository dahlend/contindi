import multiprocessing
import signal
import logging
import time
from .system import Connection
from .cache import Cache
from .events import Event, EventStatus
from .config import CONFIG


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

    def __init__(self):
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
            args=(self.task_queue, self.response_queue, CONFIG),
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
    def _process_tasks(task_queue: multiprocessing.Queue, response_queue, config):
        """
        Threaded process which keeps track of the server connection and data packets.
        """
        CONFIG.update(config)
        # Ignore interrupt signals
        # this allows keyboard interrupts to run without issue
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        event_list = []
        cxn = Connection(*CONFIG.host)
        cxn.set_camera_recv()

        if CONFIG.cache is not None:
            cache = Cache(CONFIG.cache)
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
                        logger.warning("%s Cancelling", running)
                        _, msg = running._cancel(cxn, cache)
                        event_list = [running]
                    else:
                        event_list = []
                elif cmd == "status":
                    if running is not None:
                        logger.warning("%s Running", running)
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
                    status, msg = value._get_status(cxn, cache)
                    if status == EventStatus.Failed:
                        logger.error(
                            "Event %s Failed with message:  %s", str(value), str(msg)
                        )
                    if status.is_started:
                        logger.error(
                            "This event has already occurred, ignoring it %s - %s",
                            str(value),
                            str(status),
                        )
                        continue
                    event_list.append(value)
                    event_list.sort()
                else:
                    logger.error("Unkown Command")

            keep = []
            trigger = None
            running = None
            for event in event_list:
                status, msg = event._get_status(cxn, cache)
                logger.debug("%s - %s", event, str(status))
                if msg is not None:
                    logger.error(msg)
                if status.is_active:
                    running = event
                if not status.is_done:
                    keep.append(event)
                    if trigger is None and status == EventStatus.Ready:
                        trigger = event
                else:
                    logger.info("%s - Finished with %s", event, str(status))
            event_list = keep

            if running is None and trigger is not None:
                logger.info("%s - Triggered", trigger)
                trigger._trigger(cxn, cache)

    def __del__(self):
        self.close()

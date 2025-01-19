from collections import defaultdict
import socket
import select
import signal
import multiprocessing
import copy
import logging
import time
import xml.etree.ElementTree as ET
import dataclasses
from queue import Empty
from collections import OrderedDict, UserDict
from .command import GetProperties, SetValue, DeleteProperty
from .base import GenericVector
from .blob import BlobVector
from .message import Message
from .parsing import chunk_xml, parse_chunk


logger = logging.getLogger(__name__)


class Device(UserDict):
    """
    A dictionary of setting vectors which define a hardware device.
    """

    def __init__(self, name):
        super().__init__()
        self.name = name

    def __repr__(self):
        vals = [self.name]
        for group, prop_names in self.groups.items():
            vals.append("  " + group)
            for prop in prop_names:
                val = self[prop]
                vals.append(val.to_string(prefix="    "))
        return "\n".join(vals)

    @property
    def groups(self):
        groups = {}
        for name, prop in self.items():
            group = prop.group
            if group not in groups:
                groups[group] = []
            groups[group].append(name)
        return groups


class State(UserDict):
    """
    A dictionary of `Devices` which define the state of a hardware system.
    """

    def __repr__(self):
        vals = []
        for device in self.values():
            vals.append(str(device))
        return "\n".join(vals)

    def find_cameras(self):
        found = []
        for dev_name, dev in self.items():
            for name, item in dev.items():
                if isinstance(item, BlobVector):
                    found.append((dev_name, name, item))
        return found


class Connection:
    """
    Connection to a INDI server.

    Handles the full communication to an INDI server, by creating a second
    child thread to keep track of all messages sent by the server. The second
    thread keeps a copy of the current state of the system up to date, and
    a copy of it can be requested at any time using the `Connection.state`
    property.
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
        self.connect()

    def connect(self):
        self.process = multiprocessing.Process(
            target=self._process_tasks,
            args=(self.task_queue, self.response_queue, self.host),
        )
        # Ensures process exits when main program ends
        self.process.daemon = True
        self.process.start()

    def set_value(
        self,
        dev_name: str,
        property_name: str,
        block=True,
        timeout=None,
        *args,
        **kwargs,
    ):
        """
        Set parameters on devices which are currently connected.

        Properties can either be set by keywords, or if the correct number of
        arguments are provided, then values are sufficient.

        This will raise value errors if inputs do not appear to be correct.

        Parameters
        ----------
        dev_name:
            Name of the device to set the values of.
        property_name:
            Name of the property to set on the device.
        """
        timeout = timeout if timeout is not None else self.timeout
        state = self.state

        if dev_name not in state:
            raise ValueError(
                "Device %s not found, try one of: %s", dev_name, list(state.keys())
            )
        if property_name not in state[dev_name]:
            raise ValueError(
                "Device %s does not have the property %s, try one of: %s",
                dev_name,
                property_name,
                list(state[dev_name].keys()),
            )
        if len(args) == 0 and len(kwargs) == 0:
            raise ValueError(
                "No properties are specified, try one of: \n%s",
                state[dev_name].to_string(),
            )

        param = state[dev_name][property_name]
        cmd = param.create_xml_command(*args, **kwargs)
        if cmd is None:
            return None
        self.task_queue.put("send " + cmd)

        if block:
            t = time.time()
            while (time.time() - t) < timeout:
                state = self.state
                if state[dev_name][property_name].is_set(*args, **kwargs):
                    return None

            raise ValueError("Timeout. Failed to set value in time.")

    def set_camera_recv(self, devs=None, send_here="Also"):
        """
        Set the camera(s) of the system to send images to this connection.

        By default INDI cameras do not send the images to new connections, this
        sends a command to inform the INDI server it should also send images here.

        Parameters
        ----------
        devs:
            List of camera devices, by default this will find all cameras.
        send_here:
            Option for what images the camera sends to this connection, one of the
            following: "Also", "Only", "Never". Defaults to "Also" - IE: send an
            image here in addition to any other existing connections.
        """
        if devs is None:
            cameras = self.state.find_cameras()
            devs = set([d[0] for d in cameras])
        for dev in devs:
            cmd = ET.Element("enableBLOB", device=dev)
            cmd.text = str(send_here).capitalize()
            cmd = ET.tostring(cmd)
            self.task_queue.put("send " + cmd.decode())

    @staticmethod
    def _process_tasks(task_queue: multiprocessing.Queue, response_queue, host):
        """
        Threaded process which keeps track of the server connection and data packets.
        """
        # Ignore interrupt signals
        # this allows keyboard interrupts to run without issue
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        partial = ""
        chunks = []
        state = State()
        cxn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cxn.connect(host)
        cxn.send(GetProperties().to_xml().encode())
        first_time = True
        time.sleep(0.1)

        while True:
            if not first_time:
                # Get new commands from queue
                try:
                    task = task_queue.get_nowait()
                    if task == "get state":
                        response_queue.put(copy.deepcopy(state))
                    elif task[:4] == "send":
                        _, cmd = task.split(maxsplit=1)
                        logger.debug("Sending Command %s", cmd)
                        cxn.send(cmd.encode())
                    elif task == "stop":
                        break
                    else:
                        logger.error("Unkown Command")
                except Empty:
                    pass

            # Get new responses
            ready = select.select([cxn], [], [], 0.001)
            if not ready[0]:
                continue
            first_time = False

            data = cxn.recv(1024**3)
            partial = data.decode()

            # responses broken up into valid xml chunks and incomplete xml elements
            new_elements, rem = chunk_xml(partial)

            # if there is a partial chunk, assume large data incoming, and keep downloading.
            # This terminates when the chunks are complete or it times out.
            if rem:
                start = time.time()
                while rem:
                    if (time.time() - start) > Connection.timeout:
                        logger.error(
                            "Timeout on recieving, throwing away partial and continuing."
                        )
                        partial = ""
                        break
                    time.sleep(0.01)
                    data = cxn.recv(1024**3)
                    partial = partial + data.decode()
                    chunks, rem = chunk_xml(partial)
                    new_elements.extend(chunks)

            parsed_elements = []
            for raw_xml in new_elements:
                try:
                    parsed_elements.append(parse_chunk(raw_xml))
                except Exception as e:
                    logger.error(
                        "Failed to parse element: %s\n\n First 100 chars:\n %s",
                        e,
                        raw_xml[:100],
                    )

            for element in parsed_elements:
                if isinstance(element, DeleteProperty):
                    dev = element.device
                    name = element.name
                    logger.debug("DELETE %s / %s", dev, name)
                    if name is None and dev in state:
                        del state[dev]
                    elif dev in state and name in state[dev]:
                        del state[dev][name]
                elif isinstance(element, GenericVector):
                    dev = element.device
                    name = element.name
                    group = element.group
                    logger.debug("DEFINE VECTOR %s / %s", dev, name)
                    if dev not in state:
                        state[dev] = Device(name=dev)
                    state[dev][name] = element
                elif isinstance(element, SetValue):
                    dev = element.device
                    name = element.name
                    logger.debug("SET %s / %s", dev, name)
                    if dev in state and name in state[dev]:
                        state[dev][name].update_from_xml(element.xml_element)
                elif isinstance(element, Message):
                    logger.error("%s - %s", element.device, element.message)
                elif element is None:
                    # Either a bad element, or a NEW command
                    continue
                else:
                    logger.error("UNKNOWN COMMAND: %s", element)
        logger.error("Closing Connection!")
        cxn.close()

    @property
    def state(self) -> State:
        """
        Current state of all devices found.
        """
        if not self.is_connected:
            raise ValueError("Connection is closed.")
        self.task_queue.put("get state")
        state = self.response_queue.get(timeout=self.timeout)
        while True:
            try:
                state = self.response_queue.get_nowait()
            except Empty:
                return state

    @property
    def is_connected(self):
        return self.process.is_alive()

    def __repr__(self):
        conn = self.is_connected
        devices = "" if not conn else str(list(self.state.keys()))
        return f"Connection(devices={devices})"

    def __getitem__(self, key):
        state = self.state
        return state[key]

    def close(self):
        """
        Close the connection.
        """
        self.task_queue.put("stop")
        self.process.terminate()

    def __del__(self):
        self.close()

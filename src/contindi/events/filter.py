import kete
import tempfile
import os
import time
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from ..cache import Cache
from .base import Event, EventStatus
from ..system import Connection
from .dev_names import TELESCOPE

class SetFilter(Event):
    def __init__(self, filt, priority=0, name="Capture"):
        self.priority = priority
        self.filt = filt
        self.name = f"{name}(filt={filt}, priority={priority})"
        self._status = EventStatus.Ready
        self.slot_id = None

    def cancel(self, cxn: Connection, _cache: Cache) -> EventStatus:
        """Cancel the running event."""
        self._status = EventStatus.Failed
        return self._status, "Filter change cancelled"

    def status(self, cxn: Connection, cache: Cache) -> EventStatus:
        """Check the status of the event."""
        if self._status == EventStatus.Running:
            cur_state = cxn.state[WHEEL]["FILTER_SLOT"]
            if cur_state.value[0] == self.slot_id:
                self._status = EventStatus.Finished
        return self._status, f"Filter changed to {repr(self.filt)}"

    def trigger(self, cxn: Connection, _cache: Cache):
        """Trigger the beginning of the event."""
        lookup = {}
        for name, elem in cxn.state[WHEEL]["FILTER_NAME"].elements.items():
            idx = int(name.rsplit("_", maxsplit=1)[1])
            lookup[elem.value] = idx
        self.slot_id = lookup[self.filt]
        cxn.set_value(WHEEL, "FILTER_SLOT", self.slot_id, block=False)
        self._status = EventStatus.Running, f"Filter changing to {repr(self.filt)}"

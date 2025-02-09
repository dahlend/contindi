from ..cache import Cache
from .base import Event, EventStatus
from ..system import Connection
from ..config import CONFIG


class SetFilter(Event):
    def __init__(self, filt, priority=0):
        self.priority = priority
        self.filt = filt
        self.status = EventStatus.Ready
        self.slot_id = None

    def cancel(self, cxn: Connection, _cache: Cache):
        """Cancel the running event."""
        self.status = EventStatus.Failed
        self.msg = "Canceled"

    def update(self, cxn: Connection, cache: Cache):
        """Check the status of the event."""
        if self.status == EventStatus.Running:
            cur_state = cxn.state[CONFIG.wheel]["FILTER_SLOT"]
            if cur_state.value[0] == self.slot_id:
                self.status = EventStatus.Finished

    def trigger(self, cxn: Connection, _cache: Cache):
        """Trigger the beginning of the event."""
        lookup = {}
        for name, elem in cxn.state[CONFIG.wheel]["FILTER_NAME"].elements.items():
            idx = int(name.rsplit("_", maxsplit=1)[1])
            lookup[elem.value] = idx
        if self.filt not in lookup:
            self.status = EventStatus.Failed
            self.msg = f"Selected filter ({self.filt}) not in the available filter list: {list(lookup.values())}"
            return
        self.slot_id = lookup[self.filt]
        cxn.set_value(CONFIG.wheel, "FILTER_SLOT", self.slot_id, block=False)
        self.status = EventStatus.Running

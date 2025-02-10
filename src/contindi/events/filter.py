from .base import Event, EventStatus
from ..config import CONFIG


class SetFilter(Event):
    def __init__(self, job_id, filt, priority=0):
        self.priority = priority
        self.filt = filt
        self.status = EventStatus.Ready
        self.slot_id = None
        self.job_id = job_id

    def cancel(self, cxn, cache):
        """Cancel the running event."""
        self.status = EventStatus.Failed
        cache.update_job(
            job_id=self.job_id,
            log="Canceled",
        )

    def update(self, cxn, cache):
        """Check the status of the event."""
        if self.status == EventStatus.Running:
            cur_state = cxn.state[CONFIG.wheel]["FILTER_SLOT"]
            if cur_state.value[0] == self.slot_id:
                self.status = EventStatus.Finished
                cache.update_job(
                    job_id=self.job_id,
                    log=f"Filter changed to '{self.filt}'",
                )

    def trigger(self, cxn, cache):
        """Trigger the beginning of the event."""
        lookup = {}
        lookup_id_to_filt = {}
        for name, elem in cxn.state[CONFIG.wheel]["FILTER_NAME"].elements.items():
            idx = int(name.rsplit("_", maxsplit=1)[1])
            lookup[elem.value] = idx
            lookup_id_to_filt[idx] = elem.value

        if self.filt not in lookup:
            self.status = EventStatus.Failed
            cache.update_job(
                job_id=self.job_id,
                log=f"Selected filter '{self.filt}' not in the available filter list: {list(lookup.values())}",
            )
            return
        self.slot_id = lookup[self.filt]

        cur_state = cxn.state[CONFIG.wheel]["FILTER_SLOT"].value[0]
        diff = int((self.slot_id - cur_state) % len(lookup))
        cur_filter = lookup_id_to_filt[cur_state]

        cache.update_job(
            job_id=self.job_id,
            log=f"Changing filter - Moving {diff} positions - from '{cur_filter}' to '{self.filt}'",
        )
        self.status = EventStatus.Running

        if diff == 0:
            self.update(cxn, cache)
            return
        cxn.set_value(CONFIG.wheel, "FILTER_SLOT", self.slot_id, block=False)

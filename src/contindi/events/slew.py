import kete
from ..cache import Cache
from .base import Event, EventStatus
from ..system import Connection
from ..config import CONFIG


class Slew(Event):
    def __init__(self, ra, dec, priority=0):
        self.ra = ra
        self.dec = dec
        self.priority = priority
        self._status = EventStatus.Ready

    def cancel(self, cxn: Connection, _cache: Cache):
        """Cancel the running event."""
        cxn.set_value(CONFIG.mount, "TELESCOPE_ABORT_MOTION", "On", block=False)
        self._status = EventStatus.Failed
        return self._status, "Slew cancelled, motion aborted"

    def status(self, cxn: Connection, _cache: Cache):
        """Check the status of the event."""
        cur_dist = self._cur_dist(cxn)

        if self._status == EventStatus.Running and cur_dist < 3 / 60 / 60:
            self._status = EventStatus.Finished
        return self._status, None

    def _cur_dist(self, cxn):
        cur_ra, cur_dec = cxn[CONFIG.mount]["EQUATORIAL_EOD_COORD"].value
        cur_ra *= 360 / 24
        cur_vec = kete.Vector.from_ra_dec(cur_ra, cur_dec)
        target_vec = kete.Vector.from_ra_dec(self.ra, self.dec)

        return cur_vec.angle_between(target_vec)

    def trigger(self, cxn: Connection, _cache: Cache):
        """Trigger the beginning of the event."""
        if self._cur_dist(cxn) < 3 / 60 / 60:
            self._status = EventStatus.Finished
            return
        self._status = EventStatus.Running
        ra = self.ra / 360 * 24
        cxn.set_value(CONFIG.mount, "ON_COORD_SET", SLEW="On")
        cxn.set_value(
            CONFIG.mount,
            "EQUATORIAL_EOD_COORD",
            RA=ra,
            DEC=self.dec,
            block=False,
            timeout=90,
        )

    def __repr__(self):
        return f"Slew(ra={self.ra:0.3f}, dec={self.dec:0.3f}, priority={self.priority})"

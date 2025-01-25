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


class Slew(Event):
    def __init__(self, ra, dec, priority=0):
        self.ra = ra
        self.dec = dec
        self.priority = priority
        self.name = f"{name}(ra={ra:0.2f}, dec={dec:0.2f}, priority={priority})"
        self._status = EventStatus.Ready

    def cancel(self, cxn: Connection, _cache: Cache) -> EventStatus:
        """Cancel the running event."""
        cxn.set_value(TELESCOPE, "TELESCOPE_ABORT_MOTION", "On", block=False)
        self._status = EventStatus.Failed
        return self._status, "Slew cancelled, motion aborted"

    def status(self, cxn: Connection, _cache: Cache) -> EventStatus:
        """Check the status of the event."""
        ra = self.ra / 360 * 24
        cur_ra, cur_dec = cxn[TELESCOPE]["EQUATORIAL_EOD_COORD"].value
        cur_ra *= 360 / 24
        cur_vec = kete.Vector.from_ra_dec(cur_ra, cur_dec)
        target_vec = kete.Vector.from_ra_dec(self.ra, self.dec)

        if cur_vec.angle_between(target_vec) < 3 / 60 / 60:
            return EventStatus.Finished,  "Slew complete"
        return self._status, None

    def trigger(self, cxn: Connection, _cache: Cache):
        """Trigger the beginning of the event."""
        self._status = EventStatus.Running
        ra = self.ra / 360 * 24
        cxn.set_value(TELESCOPE, "ON_COORD_SET", SLEW="On")
        cxn.set_value(
            TELESCOPE,
            "EQUATORIAL_EOD_COORD",
            RA=ra,
            DEC=self.dec,
            block=False,
            timeout=90,
        )

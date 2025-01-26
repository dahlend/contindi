import kete
import time
from astropy.wcs import WCS
from ..cache import Cache
from .base import Event, EventStatus, SeriesEvent
from ..system import Connection
from ..config import CONFIG
from .capture import Capture


class _Sync(Event):
    def __init__(self, priority=0, name="Sync"):
        self.priority = priority
        self.name = name
        self._status = EventStatus.Ready
        self.attempts = 0

    def cancel(self, cxn: Connection, _cache: Cache) -> EventStatus:
        """Cancel the running event."""
        self._status = EventStatus.Failed
        return self._status, "Sync Failed"

    def status(self, cxn: Connection, cache: Cache) -> EventStatus:
        """Check the status of the event."""
        if self._status != EventStatus.Running:
            return self._status
        frame = cache.get_latest_frame(where=" where job='sync' ")
        self.attempts += 1
        if frame is None:
            if self.attempts == 10:
                self._status = EventStatus.Failed
                return self._status, "Sync failed after 10 attempts."
            if self.attempts < 5:
                time.sleep(0.5)
            else:
                time.sleep(2)
            return self._status, None

        if frame.solved == 0:
            # Solve not complete, dont delete frame
            return self._status, None
        elif frame.solved == 1:
            cache.delete_frame(frame)
            fit_frame = frame.frame
            center = fit_frame.header["NAXIS1"] / 2, fit_frame.header["NAXIS2"] / 2
            wcs = WCS(fit_frame.header)

            ra, dec = wcs.pixel_to_world_values(*center)
            vec = kete.Vector.from_ra_dec(ra, dec)

            obs_time = kete.Time.from_iso(fit_frame.header["DATE-OBS"] + "+00:00")
            vec = vec.jnow(obs_time.jd)
            ra = vec.ra / 360 * 24
            dec = vec.dec
            cxn.set_value(CONFIG.mount, "ON_COORD_SET", SYNC="On")
            cxn.set_value(CONFIG.mount, "EQUATORIAL_EOD_COORD", RA=ra, DEC=dec)
            return EventStatus.Finished, "Sync complete"
        elif frame.solved == 2:
            cache.delete_frame(frame)
            return EventStatus.Failed, "Solver failed to find solution"
        else:
            cache.delete_frame(frame)
            return (
                EventStatus.Failed,
                f"Solver returned solved state {frame.solved}, frame deleted.",
            )

    def trigger(self, cxn: Connection, cache: Cache, remaining_attempts=5):
        """Trigger the beginning of the event."""
        self._status = EventStatus.Running


def Sync(priority=0):
    return SeriesEvent("CaptureSolve", priority, [Capture("sync", 1), _Sync()])

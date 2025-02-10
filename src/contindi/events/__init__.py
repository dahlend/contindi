from .base import Event, EventStatus
from .capture import Capture
from .constraints import TimeConstrained
from .delay import Delay
from .filter import SetFilter
from .slew import Slew
from .sync import Sync
import kete
import numpy as np


__all__ = [
    "Event",
    "EventStatus",
    "Capture",
    "Delay",
    "SetFilter",
    "Slew",
    "Sync",
    "TimeConstrained",
]


def jnow(self, jd=None):
    """
    Convert a Vector into the Equinox of Date (EOD) equatorial frame.
    IE: The current equatorial axis of Earth.
    """
    if jd is None:
        jd = kete.Time.now().jd
    else:
        jd = kete.Time(jd).jd
    rot = np.transpose(kete.conversion.earth_precession_rotation(jd))
    return kete.Vector(rot @ self.as_equatorial, kete.Frames.Equatorial)


# monkey patch Vector to use this
kete.Vector.jnow = jnow


def parse_job(job):
    """
    Convert Job into an Event.
    """

    # Allowed cmd types:
    # "FOCUS"
    # "HOME"
    # "SYNC_INPLACE"
    # "STATIC ra(deg) dec(deg)"
    # "SSO_STATE desig jd x y z vx vy vz"

    utc_start = kete.Time(job.jd_start, scaling="utc").to_datetime()
    utc_end = kete.Time(job.jd_end, scaling="utc").to_datetime()
    cmd, *args = job.cmd.split()
    if cmd.upper() == "STATIC":
        ra, dec = args
        ra = float(ra)
        dec = float(dec)
        filters = list(job.filter)

        # slew to position, cycle through filters and capture
        event = Slew(job.id, ra, dec, job.priority)
        for filt in filters:
            filter = SetFilter(job.id, filt, job.priority)
            capture = Capture(job.id, job.duration, job.priority)
            event = event + filter + capture
        event = TimeConstrained(event, utc_start, utc_end)
        return event
    elif cmd.upper() == "SYNC_INPLACE":
        filter = SetFilter(job.id, job.filter, job.priority)
        sync = Sync(job.id, job.priority)
        event = filter + sync
        event = TimeConstrained(event, utc_start, utc_end)
        return event

    raise ValueError(f"Unknown command {cmd}")

from .base import Event, EventStatus
from .capture import Capture
from .filter import SetFilter
from .slew import Slew
from .sync import Sync
import kete
import numpy as np


__all__ = ["Event", "EventStatus", "Capture", "SetFilter", "Slew", "Sync"]


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

import kete
import tempfile
import os
import time
import numpy as np
from astropy.io import fits
import subprocess
from astropy.wcs import WCS
from contindi.cache import Cache
from contindi.scheduler import Event, EventStatus, SeriesEvent
from contindi.system import Connection

TELESCOPE = "iOptron CEM70"
CAMERA = "ZWO CCD ASI533MM Pro"
FOCUS = "ZWO EAF"
WHEEL = "ZWO EFW"


def jnow(self, jd=None):
    if jd is None:
        jd = kete.Time.now().jd
    else:
        jd = kete.Time(jd).jd
    rot = np.transpose(kete.conversion.earth_precession_rotation(jd))
    vec = self.as_equatorial
    return kete.Vector(rot @ vec, kete.Frames.Equatorial)


kete.Vector.jnow = jnow


class Init(Event):
    def __init__(self, priority=-1000000000, name="INIT"):
        self.name = name
        self.priority = priority
        self._status = EventStatus.Ready

    def cancel(self, cxn: Connection, _cache: Cache) -> EventStatus:
        """Cancel the running event."""
        self._status = EventStatus.Failed
        return self._status

    def status(self, cxn: Connection, _cache: Cache) -> EventStatus:
        """Check the status of the event."""
        return self._status

    def trigger(self, cxn: Connection, cache: Cache):
        """Trigger the beginning of the event."""
        cxn.set_camera_recv()
        frame = 1
        while frame is not None:
            frame = cache.get_latest_frame(where=" where job='sync' ")
            if frame is None:
                break
            cache.delete_frame(frame)
        self._status = EventStatus.Finished


class Slew(Event):
    def __init__(self, ra, dec, priority=0, name="slew"):
        self.ra = ra
        self.dec = dec
        self.priority = priority
        self.name = f"{name}(ra={ra:0.2f}, dec={dec:0.2f}, priority={priority})"
        self._status = EventStatus.Ready

    def cancel(self, cxn: Connection, _cache: Cache) -> EventStatus:
        """Cancel the running event."""
        cxn.set_value(TELESCOPE, "TELESCOPE_ABORT_MOTION", "On", block=False)
        self._status = EventStatus.Failed
        return self._status

    def status(self, cxn: Connection, _cache: Cache) -> EventStatus:
        """Check the status of the event."""
        ra = self.ra / 360 * 24
        cur_ra, cur_dec = cxn[TELESCOPE]["EQUATORIAL_EOD_COORD"].value
        cur_ra *= 360 / 24
        cur_vec = kete.Vector.from_ra_dec(cur_ra, cur_dec)
        target_vec = kete.Vector.from_ra_dec(self.ra, self.dec)

        if cur_vec.angle_between(target_vec) < 3 / 60 / 60:
            self._status = EventStatus.Finished
        return self._status

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
        return self._status

    def status(self, cxn: Connection, cache: Cache) -> EventStatus:
        """Check the status of the event."""
        if self._status == EventStatus.Running:
            cur_state = cxn.state[WHEEL]["FILTER_SLOT"]
            if cur_state.value[0] == self.slot_id:
                self._status = EventStatus.Finished
        return self._status

    def trigger(self, cxn: Connection, _cache: Cache):
        """Trigger the beginning of the event."""
        lookup = {}
        for name, elem in cxn.state[WHEEL]["FILTER_NAME"].elements.items():
            idx = int(name.rsplit("_", maxsplit=1)[1])
            lookup[elem.value] = idx
        self.slot_id = lookup[self.filt]
        cxn.set_value(WHEEL, "FILTER_SLOT", self.slot_id, block=False)
        self._status = EventStatus.Running


class Capture(Event):
    def __init__(self, job_name, duration, priority=0, keep=True, private=False):
        self.priority = priority
        self.duration = duration
        self.keep = keep
        self.private = private
        self.job_name = job_name
        self.name = f"Capture({job_name}, duration={duration}, priority={priority}, keep={keep}, private={private})"
        self._status = EventStatus.Ready
        self.timestamp = None

    def cancel(self, cxn: Connection, _cache: Cache) -> EventStatus:
        """Cancel the running event."""
        self._status = EventStatus.Failed
        return self._status

    def status(self, cxn: Connection, cache: Cache) -> EventStatus:
        """Check the status of the event."""
        if self._status == EventStatus.Running:
            cur_state = cxn[CAMERA]["CCD1"]
            if self.timestamp != cur_state.timestamp:
                self._status = EventStatus.Finished
                cache.add_frame(
                    self.job_name,
                    cur_state.elements["CCD1"].frame,
                    solved=False,
                    keep_frame=self.keep,
                    private=self.private,
                )
        return self._status

    def trigger(self, cxn: Connection, _cache: Cache):
        """Trigger the beginning of the event."""
        self.timestamp = cxn[CAMERA]["CCD1"].timestamp
        cxn.set_value(CAMERA, "CCD_EXPOSURE", self.duration, block=False)
        self._status = EventStatus.Running


class Sync(Event):
    def __init__(self, priority=0, name="Sync"):
        self.priority = priority
        self.name = name
        self._status = EventStatus.Ready
        self.attempts = 0

    def cancel(self, cxn: Connection, _cache: Cache) -> EventStatus:
        """Cancel the running event."""
        self._status = EventStatus.Failed
        return self._status

    def status(self, cxn: Connection, cache: Cache) -> EventStatus:
        """Check the status of the event."""
        if self._status != EventStatus.Running:
            return self._status
        frame = cache.get_latest_frame(where=" where job='sync' ")
        self.attempts += 1
        if frame is None:
            if self.attempts == 10:
                self._status = EventStatus.Failed
                return self._status
            if self.attempts < 5:
                time.sleep(0.5)
            else:
                time.sleep(2)
            return self._status

        if frame.solved == 0:
            # DONT DELETE
            return self._status
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
            cxn.set_value(TELESCOPE, "ON_COORD_SET", SYNC="On")
            cxn.set_value(TELESCOPE, "EQUATORIAL_EOD_COORD", RA=ra, DEC=dec)
            self._status = EventStatus.Finished
        elif frame.solved == 2:
            cache.delete_frame(frame)
            self._status = EventStatus.Failed
        return self._status

    def trigger(self, cxn: Connection, cache: Cache, remaining_attempts=5):
        """Trigger the beginning of the event."""
        self._status = EventStatus.Running


CaptureSync = lambda priority=0: SeriesEvent(
    "CaptureSolve", priority, [Capture("sync", 1), Sync()]
)

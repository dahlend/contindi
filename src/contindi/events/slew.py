import kete
from .base import Event, EventStatus
from ..config import CONFIG


class Slew(Event):
    def __init__(self, job_id, ra, dec, priority=0):
        self.job_id = job_id
        self.ra = ra
        self.dec = dec
        # The Telescope accepts RA/DEC in current equatorial frame.
        # Compute the rotation of the J2000 radec to the EOD radec.
        self.eod_vec = kete.Vector.from_ra_dec(ra, dec).jnow(kete.Time.now().jd)
        self.priority = priority
        self.status = EventStatus.Ready

    def cancel(self, cxn, cache):
        """Cancel the running event."""
        cxn.set_value(CONFIG.mount, "TELESCOPE_ABORT_MOTION", "On", block=False)
        self.status = EventStatus.Failed
        cache.update_job(self.job_id, log="Slew cancelled, motion aborted")

    def update(self, cxn, cache):
        """Check the status of the event."""
        if self.status == EventStatus.Running and self._cur_dist(cxn) < 5 / 60 / 60:
            self.status = EventStatus.Finished
            cache.update_job(
                self.job_id,
                log="Slew complete",
            )

    def _cur_dist(self, cxn):
        cur_ra, cur_dec = cxn[CONFIG.mount]["EQUATORIAL_EOD_COORD"].value
        cur_ra *= 360 / 24
        cur_vec = kete.Vector.from_ra_dec(cur_ra, cur_dec)
        angle = cur_vec.angle_between(self.eod_vec)
        return angle

    def trigger(self, cxn, cache):
        """Trigger the beginning of the event."""
        dist = self._cur_dist(cxn)
        if dist < 5 / 60 / 60:
            self.status = EventStatus.Finished
            cache.update_job(
                self.job_id,
                log="Slew not done, within 5 arcseconds of target.",
            )
            return
        self.status = EventStatus.Running
        deg_m_s = kete.conversion.dec_degrees_to_dms(dist)
        cache.update_job(self.job_id, log=f"Slewing {dist:0.4f} ({deg_m_s})")
        cxn.set_value(CONFIG.mount, "ON_COORD_SET", SLEW="On")
        cxn.set_value(
            CONFIG.mount,
            "EQUATORIAL_EOD_COORD",
            RA=self.eod_vec.ra / 360 * 24,
            DEC=self.eod_vec.dec,
            block=False,
            timeout=90,
        )

    def __repr__(self):
        return f"Slew(ra={self.ra:0.3f}, dec={self.dec:0.3f}, priority={self.priority})"

import kete
import time
from astropy.wcs import WCS
from .base import Event, EventStatus, SeriesEvent
from ..config import CONFIG
from ..cache import SolveStatus
from .capture import Capture
from pocketbase.client import ClientResponseError


class _Sync(Event):
    def __init__(self, job_id, priority=0):
        self.job_id = job_id
        self.priority = priority
        self.status = EventStatus.Ready
        self.attempts = 0

    def cancel(self, cxn, cache):
        """Cancel the running event."""
        self.status = EventStatus.Failed
        cache.update_job(self.job_id, log="Canceled")

    def update(self, cxn, cache):
        """Check the status of the event."""

        if self.status != EventStatus.Running:
            return

        self.attempts += 1
        try:
            job = cache.get_job(self.job_id)
        except ClientResponseError:
            self.status = EventStatus.Failed
            return

        if job.frame == "":
            if self.attempts == 10:
                self.status = EventStatus.Failed
                cache.update_job(
                    job_id=self.job_id, log="Sync failed after 10 attempts."
                )
                return
            if self.attempts < 5:
                time.sleep(0.5)
            else:
                time.sleep(2)

        if job.solve == SolveStatus.UNSOLVED:
            # Solve not complete, dont delete frame
            return
        elif job.solve == SolveStatus.SOLVED:
            fit_frame = job.get_frame()
            cache.update_job(
                job.id,
                frame=None,
                log="Solve succeeded and mount sync updated, frame deleted.",
            )
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
            self.status = EventStatus.Finished
        elif job.solve == SolveStatus.UNSOLVED:
            cache.update_job(job.jd, frame=None, log="Solver failed to find solution")
            self.status = EventStatus.Failed
        elif job.solve == SolveStatus.DONT_SOLVE:
            cache.update_job(
                job.jd,
                frame=None,
                log="Frame was marked as DONT_SOLVE, frame deleted.",
            )
            self.status = EventStatus.Failed

    def trigger(self, cxn, cache, remaining_attempts=5):
        """Trigger the beginning of the event."""
        self.status = EventStatus.Running


def Sync(job_id, priority=0):
    return SeriesEvent(
        "CaptureSolve", priority, [Capture(job_id, priority), _Sync(job_id, priority)]
    )

from astropy.io import fits
from enum import Enum
from dataclasses import dataclass, field, fields, asdict
from typing import Optional
import logging
import kete
from ..events import Capture, SetFilter, Slew, TimeConstrained, Sync


logger = logging.getLogger(__name__)


class SolveStatus(Enum):
    UNSOLVED = 0  # Unsolved, but intended to be solved
    SOLVED = 1
    SOLVE_FAILED = 2
    DONT_SOLVE = 3  # Temporary frame, may be deleted after a day (IE: focusing images)


class JobStatus(Enum):
    QUEUED = 0
    RUNNING = 1
    FAILED = 2
    FINISHED = 3


class PostProcessingStatus(Enum):
    QUEUED = 0
    RUNNING = 1
    FAILED = 2
    FINISHED = 3


@dataclass
class Job:
    id: str
    proposal_id: str
    cmd: str
    priority: int
    jd_end: Optional[float]
    jd_start: Optional[float]
    duration: float
    filter: str
    keep_frame: bool = field(default=True)
    log: str = field(default="")
    status: JobStatus = field(default=JobStatus.QUEUED)
    jd_obs: Optional[float] = field(default=None)
    private: bool = field(default=False)
    frame: Optional[str] = field(default=None)
    solve: Optional[SolveStatus] = field(default=None)
    post_processing: Optional[PostProcessingStatus] = field(default=None)

    @classmethod
    def from_record(cls, client, record):
        params = {k.name: getattr(record, k.name) for k in fields(cls)}

        url = client.files.get_url(record, record.frame)
        params["frame"] = url
        params["solve"] = SolveStatus[record.solve] if record.solve else None
        params["status"] = JobStatus[record.status]
        return cls(*params.values())

    def get_frame(self) -> fits.HDUList:
        return fits.open(self.frame)

    @staticmethod
    def new_static_exposure(
        job_id,
        proposal_id,
        priority,
        jd_start,
        jd_end,
        ra,
        dec,
        duration,
        filter,
        private=False,
    ):
        cmd = f"STATIC {ra} {dec}"
        return Job(
            id=job_id,
            proposal_id=proposal_id,
            priority=priority,
            jd_start=jd_start,
            jd_end=jd_end,
            duration=duration,
            cmd=cmd,
            filter=filter,
            private=private,
        )

    asdict = asdict

    def parse_job(self):
        """
        Convert Job into an Event.
        """

        # Allowed cmd types:
        # "FOCUS"
        # "HOME"
        # "SYNC_INPLACE"
        # "STATIC ra(deg) dec(deg)"
        # "SSO_STATE desig jd x y z vx vy vz"

        jd_start = kete.Time(self.jd_start).to_datetime()
        jd_end = kete.Time(self.jd_end).to_datetime()
        cmd, *args = self.cmd.split()
        if cmd.upper() == "STATIC":
            ra, dec = args
            ra = float(ra)
            dec = float(dec)
            filters = list(self.filter)

            # slew to position, cycle through filters and capture
            event = Slew(self.id, ra, dec, self.priority)
            for filt in filters:
                filter = SetFilter(self.id, filt, self.priority)
                capture = Capture(self.id, self.duration, self.priority)
                event = event + filter + capture
            event = TimeConstrained(event, jd_start, jd_end)
            return event
        elif cmd.upper() == "SYNC_INPLACE":
            filter = SetFilter(self.id, self.filter, self.priority)
            sync = Sync(self.id, self.priority)
            event = filter + sync
            event = TimeConstrained(event, jd_start, jd_end)
            return event

        raise ValueError(f"Unknown command {cmd}")

import io
import kete
from pocketbase import Client
from pocketbase.models import FileUpload
import gzip
import datetime
import threading
from enum import Enum

from astropy.io import fits
from dataclasses import dataclass, field, fields, asdict
from typing import Optional


class SolveStatus(Enum):
    """Has the frame in the database been WCS solved."""

    UNSOLVED = 0  # Unsolved, but intended to be solved
    SOLVED = 1
    SOLVE_FAILED = 2
    DONT_SOLVE = 3  # Temporary frame, may be deleted after a day (IE: focusing images)


class CaptureStatus(Enum):
    """Current status of image capture"""

    QUEUED = 0
    RUNNING = 1
    FAILED = 3
    FINISHED = 4
    EXPIRED = 5


class PostProcessingStatus(Enum):
    """
    Current status of post-processing of frames.
    """

    QUEUED = 0
    RUNNING = 1
    FAILED = 2
    FINISHED = 3


def fits_to_binary(frame):
    """Take a frame and compress it in memory."""
    byte_io = io.BytesIO()
    frame.writeto(gzip.GzipFile(fileobj=byte_io, mode="wb"))
    byte_io.seek(0)
    return byte_io


@dataclass
class Job:
    id: str
    proposal: str
    cmd: str
    priority: int
    duration: float
    filter: str
    jd_start: Optional[float]
    jd_end: Optional[float]
    jd_obs: Optional[float] = field(default=None)
    keep_frame: bool = field(default=True, repr=False)
    log: str = field(default="", repr=False)
    capture_status: CaptureStatus = field(default=CaptureStatus.QUEUED, repr=False)
    private: bool = field(default=False, repr=False)
    frame: Optional[str] = field(default=None, repr=False)
    solve: Optional[SolveStatus] = field(default=None, repr=False)
    post_processing: Optional[PostProcessingStatus] = field(default=None, repr=False)
    seeing: float = field(default=0, repr=False)
    mag_limit: float = field(default=0, repr=False)
    ra: float = field(default=0, repr=False)
    dec: float = field(default=0, repr=False)
    ra1: float = field(default=0, repr=False)
    dec1: float = field(default=0, repr=False)
    ra2: float = field(default=0, repr=False)
    dec2: float = field(default=0, repr=False)
    ra3: float = field(default=0, repr=False)
    dec3: float = field(default=0, repr=False)
    ra4: float = field(default=0, repr=False)
    dec4: float = field(default=0, repr=False)

    @classmethod
    def from_record(cls, client, record):
        params = {k.name: getattr(record, k.name) for k in fields(cls)}

        url = client.files.get_url(record, record.frame)
        params["frame"] = url
        params["solve"] = SolveStatus[record.solve] if record.solve else None
        params["capture_status"] = CaptureStatus[record.capture_status]
        return cls(*params.values())

    def get_frame(self) -> fits.HDUList:
        return fits.open(self.frame)

    @staticmethod
    def new_static_exposure(
        job_id,
        proposal,
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
            proposal=proposal,
            priority=priority,
            jd_start=jd_start,
            jd_end=jd_end,
            duration=duration,
            cmd=cmd,
            filter=filter,
            private=private,
        )

    asdict = asdict


class PBCache:
    def __init__(self, username, password, host="http://127.0.0.1:8090", admin=False):
        self.host = host
        self.con = Client(host)
        self.username = username
        self.password = password
        self.admin = admin
        self._auth()

    def _auth(self):
        if self.admin:
            self.token = self.con.admins.auth_with_password(
                self.username, self.password
            )
        else:
            self.token = self.con.collection("users").auth_with_password(
                self.username, self.password
            )

    @property
    def _jobs(self):
        try:
            return self.con.collection("jobs")
        except Exception:
            self.con = Client(self.host)
        return self.con.collection("jobs")

    def get_jobs(self, filter=None, sort="-priority"):
        records = self._jobs.get_full_list(
            query_params={"sort": sort, "filter": filter}
        )
        return [Job.from_record(self.con, r) for r in records]

    def get_latest(self, filter="capture_status='FINISHED'", sort="-jd_obs"):
        record = self._jobs.get_first_list_item(
            filter=filter, query_params={"sort": sort}
        )

        return Job.from_record(self.con, record)

    def get_job(self, job_id):
        record = self._jobs.get_one(job_id)
        return Job.from_record(self.con, record)

    def submit_job(self, job: Job):
        params = job.asdict()
        params["capture_status"] = params["capture_status"].name
        if params["solve"] is not None:
            params["solve"] = params["solve"].name
        self.con.collection("jobs").create(params)

    def update_job(self, job_id, log=None, **kwargs):
        if log is not None:
            cur_log = self.get_job(job_id).log
            iso = datetime.datetime.now(datetime.UTC).isoformat()
            jd = kete.Time.from_iso(iso).utc_jd
            kwargs["log"] = "\n".join([cur_log, f"{iso} - {jd:0.8f} - " + str(log)])
        if "capture_status" in kwargs:
            kwargs["capture_status"] = kwargs["capture_status"].name
        if "solve" in kwargs and kwargs["solve"] is not None:
            kwargs["solve"] = kwargs["solve"].name
        if "id" in kwargs:
            del kwargs["id"]
        self._jobs.update(job_id, kwargs)

    def add_frame(self, job_id, frame):
        """
        Add a frame to the specified job.
        """

        # Do this in a thread so that we are not blocked by waiting for the upload
        def _send(self, job_id, frame):
            jd_obs = kete.Time.from_iso(frame.header["DATE-OBS"] + "+00:00").utc_jd
            frame = fits_to_binary(frame)
            self._jobs.update(
                job_id,
                {"jd_obs": jd_obs, "frame": FileUpload("frame.fits.gz", frame)},
            )

        sender = threading.Thread(target=_send, args=(self, job_id, frame))
        sender.start()

import io
import kete
from pocketbase import Client
from pocketbase.models import FileUpload
import logging
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


class PostProcessingStatus(Enum):
    """
    Current status of post-processing of frames.
    """

    QUEUED = 0
    RUNNING = 1
    FAILED = 2
    FINISHED = 3


logger = logging.getLogger(__name__)


def fits_to_binary(frame):
    """Take a frame and compress it in memory."""
    byte_io = io.BytesIO()
    frame.writeto(gzip.GzipFile(fileobj=byte_io, mode="wb"))
    byte_io.seek(0)
    return byte_io


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
    capture_status: CaptureStatus = field(default=CaptureStatus.QUEUED)
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
        params["capture_status"] = CaptureStatus[record.capture_status]
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


class PBCache:
    def __init__(self, host="http://127.0.0.1:8090"):
        self.host = host
        self.con = Client(host)

    @property
    def _jobs(self):
        try:
            return self.con.collection("jobs")
        except Exception as e:
            logger.error("Failed to fetch collection: %s", e.data)
            self.con = Client(self.host)
        return self.con.collection("jobs")

    def get_jobs(self, filter="capture_status='QUEUED'", sort="-priority"):
        try:
            records = self._jobs.get_full_list(
                query_params={"sort": sort, "filter": filter}
            )
        except Exception as e:
            logger.error("Failed to fetch jobs: %s", e.data)
            raise
        return [Job.from_record(self.con, r) for r in records]

    def get_latest(self, filter="capture_status='FINISHED'", sort="-jd_obs"):
        try:
            record = self._jobs.get_first_list_item(
                filter=filter, query_params={"sort": sort}
            )
        except Exception as e:
            logger.error("Failed to fetch job: %s", e.data)
            raise
        return Job.from_record(self.con, record)

    def get_job(self, job_id):
        record = self._jobs.get_one(job_id)
        return Job.from_record(self.con, record)

    def submit_job(self, job: Job):
        params = job.asdict()
        params["capture_status"] = params["capture_status"].name
        if params["solve"] is not None:
            params["solve"] = params["solve"].name
        try:
            self.con.collection("jobs").create(params)
        except Exception as e:
            logger.error("Failed to submit job: %s", e.data)
            raise

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
        try:
            self._jobs.update(job_id, kwargs)
        except Exception as e:
            logger.error("Failed to submit job: %s", e.data)
            raise

    def add_frame(self, job_id, frame):
        """
        Add a frame to the specified job.
        """

        # Do this in a thread so that we are not blocked by waiting for the upload
        def _send(self, job_id, frame):
            jd_obs = kete.Time.from_iso(frame.header["DATE-OBS"] + "+00:00").utc_jd
            frame = fits_to_binary(frame)
            try:
                self._jobs.update(
                    job_id,
                    {"jd_obs": jd_obs, "frame": FileUpload("frame.fits.gz", frame)},
                )
            except Exception as e:
                logger.error("Failed to submit job: %s", e.data)
                raise

        sender = threading.Thread(target=_send, args=(self, job_id, frame))
        sender.start()

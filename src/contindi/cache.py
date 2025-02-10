import io
import kete
from astropy.io import fits
from enum import Enum
from pocketbase import Client
from pocketbase.models import FileUpload
from dataclasses import dataclass, field, fields, asdict
from typing import Optional
import logging
import gzip


logger = logging.getLogger(__name__)


class SolveStatus(Enum):
    UNSOVLED = 0  # Unsolved, but intended to be solved
    SOLVED = 1
    SOLVE_FAILED = 2
    DONT_SOLVE = 3  # Temporary frame, may be deleted after a day (IE: focusing images)


class JobStatus(Enum):
    QUEUED = 0
    RUNNING = 1
    FAILED = 2
    FINISHED = 3


"""
/*
Allowed cmd types:
"FOCUS"
"HOME"
"SYNC_INPLACE"
"STATIC ra(deg) dec(deg)"
"SSO_STATE desig jd x y z vx vy vz"
"""


@dataclass
class Job:
    id: str
    cmd: str
    priority: int
    jd_end: Optional[float]
    jd_start: Optional[float]
    duration: float
    filter: str
    keep_frame: bool = field(default=True)
    msg: str = field(default="")
    status: JobStatus = field(default=JobStatus.QUEUED)
    jd_obs: Optional[float] = field(default=None)
    private: bool = field(default=False)
    frame: Optional[str] = field(default=None)
    solve: Optional[SolveStatus] = field(default=None)

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
        job_id, priority, jd_start, jd_end, ra, dec, duration, filter, private=False
    ):
        cmd = f"STATIC {ra} {dec}"
        return Job(
            id=job_id,
            priority=priority,
            jd_start=jd_start,
            jd_end=jd_end,
            duration=duration,
            cmd=cmd,
            filter=filter,
            private=private,
        )

    asdict = asdict


def fits_to_binary(frame):
    b = io.BytesIO()
    f = gzip.GzipFile(fileobj=b, mode="wb")
    frame.writeto(f)
    b.seek(0)
    return b


class Cache:
    def __init__(self, host="http://127.0.0.1:8090"):
        self.con = Client(host)

    def get_jobs(self, filter="status='QUEUED'"):
        records = self.con.collection("jobs").get_full_list(
            query_params={"sort": "-priority", "filter": filter}
        )
        return [Job.from_record(self.con, r) for r in records]

    def get_job(self, job_id):
        record = self.con.collection("jobs").get_one(job_id)
        return Job.from_record(self.con, record)

    def submit_job(self, job: Job):
        params = job.asdict()
        params["status"] = params["status"].name
        if params["solve"] is not None:
            params["solve"] = params["solve"].name
        try:
            self.con.collection("jobs").create(params)
        except Exception as e:
            logger.error("Failed to submit job: %s", e.data)
            raise

    def update_job(self, job_id, **kwargs):
        if "status" in kwargs:
            kwargs["status"] = kwargs["status"].name
        if "solve" in kwargs and kwargs["solve"] is not None:
            kwargs["solve"] = kwargs["solve"].name
        if "id" in kwargs:
            del kwargs["id"]
        try:
            self.con.collection("jobs").update(job_id, kwargs)
        except Exception as e:
            logger.error("Failed to submit job: %s", e.data)
            raise

    def add_frame(self, job_id, frame):
        jd_obs = kete.Time.from_iso(frame.header["DATE-OBS"] + "+00:00").utc_jd
        frame = fits_to_binary(frame)
        try:
            self.con.collection("jobs").update(
                job_id,
                {"jd_obs": jd_obs, "frame": FileUpload("frame.fits.gz", frame)},
            )
        except Exception as e:
            logger.error("Failed to submit job: %s", e.data)
            raise

    # def delete_job(self, job: Job):
    #     try:
    #         with self.con:
    #             self.con.execute(f"delete from job_queue where id={job.id};")
    #     except sqlite3.OperationalError as e:
    #         logger.error(e)
    #         pass

    # def get_latest_frame(self, where=None):
    #     where = "" if where is None else where

    #     try:
    #         with self.con:
    #             res = self.con.execute(
    #                 f"Select * from frames {where} ORDER BY time desc LIMIT 1"
    #             ).fetchone()
    #             if res is None:
    #                 return None
    #             res = list(res)
    #         res[3] = fits.HDUList.fromstring(res[3])[0]
    #         res[8] = SolveStatus(res[8])
    #         return FrameMeta(*res)
    #     except sqlite3.OperationalError as e:
    #         logger.error(e)

    # def __del__(self):
    #     self.con.close()

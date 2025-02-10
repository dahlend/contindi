import io
import kete
from pocketbase import Client
from pocketbase.models import FileUpload
import logging
import gzip
import datetime
from .jobs import Job


logger = logging.getLogger(__name__)


def fits_to_binary(frame):
    """Take a frame and compress it in memory."""
    byte_io = io.BytesIO()
    frame.writeto(gzip.GzipFile(fileobj=byte_io, mode="wb"))
    byte_io.seek(0)
    return byte_io


class PBCache:
    def __init__(self, host="http://127.0.0.1:8090"):
        self.con = Client(host)

    def get_jobs(self, filter="status='QUEUED'", sort="-priority"):
        records = self.con.collection("jobs").get_full_list(
            query_params={"sort": sort, "filter": filter}
        )
        return [Job.from_record(self.con, r) for r in records]

    def get_latest(self, filter="status='FINISHED'", sort="-jd_obs"):
        record = self.con.collection("jobs").get_first_list_item(
            filter=filter, query_params={"sort": sort}
        )
        return Job.from_record(self.con, record)

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

    def update_job(self, job_id, log=None, **kwargs):
        if log is not None:
            cur_log = self.get_job(job_id).log
            iso = datetime.datetime.now(datetime.UTC).isoformat()
            jd = kete.Time.from_iso(iso).utc_jd
            kwargs["log"] = "\n".join([cur_log, f"{iso} - {jd:0.8f} - " + str(log)])
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

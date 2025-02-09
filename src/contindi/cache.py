import sqlite3
import kete
import io
import logging
from collections import namedtuple
from astropy.io import fits
from enum import Enum

logger = logging.getLogger(__name__)


class SolveStatus(Enum):
    Unsolved = 0  # Unsolved, but intended to be solved
    Solved = 1
    SolveFailed = 2
    DontSolve = 3  # Temporary frame, may be deleted after a day (IE: focusing images)


_CACHE_SQL = """
/* This defines the schema for the cache database. */

CREATE TABLE frames(
    id INTEGER PRIMARY KEY,
    job TEXT NOT NULL,
    time REAL UNIQUE NOT NULL,
    frame BLOB NOT NULL,
    private INTEGER NOT NULL,
    keep_frame BOOL NOT NULL,
    duration REAL NOT NULL,
    filter TEXT NOT NULL,
    solved int NOT NULL
);

CREATE INDEX obs_time ON frames (time);

CREATE TABLE job_queue(
    id INTEGER PRIMARY KEY,
    job TEXT NOT NULL,
    target TEXT NOT NULL,
    priority INTEGER NOT NULL,
    private INTEGER NOT NULL,
    duration REAL NOT NULL,
    filter TEXT NOT NULL,
    jd_start REAL NOT NULL,
    jd_end REAL NOT NULL,
    status TEXT NOT NULL DEFAULT "QUEUED",
    msg TEXT DEFAULT NULL
);

/*
Allowed target types:
"FOCUS"
"HOME"
"SYNC_INPLACE"
"STATIC ra(deg) dec(deg)"
"SSO_STATE desig jd x y z vx vy vz"


Allowed status:
"QUEUED"
"RUNNING"
"FAILED"
"FINISHED"
*/
"""


FrameMeta = namedtuple(
    "FrameMeta", "id, job, time, frame, private, keep_frame, duration, filter, solved"
)


Job = namedtuple(
    "Job",
    "id, job, target, priority, private, duration, filter, jd_start, jd_end, status, msg",
)


def fits_to_binary(frame):
    with io.BytesIO() as f:
        frame.writeto(f)
        f.seek(0)
        dat = f.read()
    return dat


class Cache:
    def __init__(self, db_file="local_cache.db", timeout=10):
        self.db_file = db_file
        self.con = sqlite3.connect(self.db_file, timeout=timeout)

    def initialize(self):
        try:
            with self.con:
                self.con.executescript(_CACHE_SQL)
        except sqlite3.OperationalError as e:
            logger.error(e)

    def add_static_exposure(
        self, priority, jd_start, jd_end, job, ra, dec, duration, filter, private=False
    ):
        target = f"STATIC {ra} {dec}"

        try:
            with self.con:
                self.con.execute(
                    """ INSERT INTO job_queue
                                  (job, target, priority, private, duration, filter, jd_start, jd_end)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        job,
                        target,
                        priority,
                        private,
                        duration,
                        filter,
                        jd_start,
                        jd_end,
                    ),
                )
        except sqlite3.OperationalError as e:
            logger.error(e)
            pass

    def add_focus(self, priority, jd_start, jd_end, duration=1, filter=""):
        try:
            with self.con:
                self.con.execute(
                    """ INSERT INTO job_queue
                                  (job, target, priority, private, duration, filter, jd_start, jd_end)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "FOCUS",
                        "FOCUS",
                        priority,
                        True,
                        duration,
                        filter,
                        jd_start,
                        jd_end,
                    ),
                )
        except sqlite3.OperationalError as e:
            logger.error(e)
            pass

    def add_sync(self, priority, jd_start, jd_end, duration=3, filter=""):
        try:
            with self.con:
                self.con.execute(
                    """ INSERT INTO job_queue
                                  (job, target, priority, private, duration, filter, jd_start, jd_end)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "SYNC_INPLACE",
                        "SYNC_INPLACE",
                        priority,
                        True,
                        duration,
                        filter,
                        jd_start,
                        jd_end,
                    ),
                )
        except sqlite3.OperationalError as e:
            logger.error(e)
            pass

    def add_home(self, priority, jd_start, jd_end):
        try:
            with self.con:
                self.con.execute(
                    """ INSERT INTO job_queue
                                  (job, target, priority, private, duration, filter, jd_start, jd_end)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "HOME",
                        "HOME",
                        priority,
                        True,
                        0,
                        "",
                        jd_start,
                        jd_end,
                    ),
                )
        except sqlite3.OperationalError as e:
            logger.error(e)
            pass

    def get_jobs(self, status="QUEUED"):
        args = ", ".join([x for x in Job._fields])
        try:
            with self.con:
                res = self.con.execute(
                    f"""Select {args}
                    from job_queue where status='{status}' ORDER BY priority asc"""
                ).fetchall()
                if res is None:
                    return None
            return [Job(*r) for r in res]
        except sqlite3.OperationalError as e:
            logger.error(e)

    def get_job(self, id):
        args = ", ".join([x for x in Job._fields])
        try:
            with self.con:
                res = self.con.execute(
                    f"""Select {args}
                    from job_queue where id='{id}' ORDER BY priority asc"""
                ).fetchone()
                if res is None:
                    return None
            return Job(*res)
        except sqlite3.OperationalError as e:
            logger.error(e)

    def update_job(self, job: Job):
        args = ", ".join([x + "=?" for x in Job._fields])

        try:
            with self.con:
                self.con.execute(
                    "UPDATE job_queue SET " + args + f" where id={job.id}", job
                )
        except sqlite3.OperationalError as e:
            logger.error(e)
            pass

    def delete_job(self, job: Job):
        try:
            with self.con:
                self.con.execute(f"delete from job_queue where id={job.id};")
        except sqlite3.OperationalError as e:
            logger.error(e)
            pass

    def add_frame(self, job, frame, solved, private=False, keep_frame=True):
        dat = fits_to_binary(frame)
        duration = frame.header["EXPTIME"]
        filt = frame.header["FILTER"]
        jd = kete.Time.from_iso(frame.header["DATE-OBS"] + "+00:00").utc_jd

        data = (job, jd, dat, private, keep_frame, duration, filt, solved)

        try:
            with self.con:
                self.con.execute(
                    """ INSERT INTO frames
                                  (job, time, frame, private, keep_frame, duration, filter, solved) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    data,
                )
        except sqlite3.OperationalError as e:
            logger.error(e)
            pass

    def get_latest_frame(self, where=None):
        where = "" if where is None else where

        try:
            with self.con:
                res = self.con.execute(
                    f"Select * from frames {where} ORDER BY time desc LIMIT 1"
                ).fetchone()
                if res is None:
                    return None
                res = list(res)
            res[3] = fits.HDUList.fromstring(res[3])[0]
            res[8] = SolveStatus(res[8])
            return FrameMeta(*res)
        except sqlite3.OperationalError as e:
            logger.error(e)

    def delete_frame(self, frame: FrameMeta):
        cmd = f"delete from frames where id={frame.id};"
        try:
            with self.con:
                self.con.execute(cmd)
        except sqlite3.OperationalError as e:
            logger.error(e)
            pass

    def update_frame(self, frame: FrameMeta):
        args = ", ".join([x + "=?" for x in FrameMeta._fields])
        frame = frame._replace(
            frame=fits_to_binary(frame.frame), solved=frame.solved.value
        )

        try:
            with self.con:
                self.con.execute(
                    "UPDATE frames SET " + args + f" where id={frame.id}", frame
                )
        except sqlite3.OperationalError as e:
            logger.error(e)
            pass

    def __del__(self):
        self.con.close()

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

PRAGMA foreign_keys = ON;

CREATE TABLE frames(
    id INTEGER PRIMARY KEY,
    job TEXT not null,
    time REAL UNIQUE not null,
    frame BLOB not null,
    private bool not null,
    keep_frame bool not null,
    duration REAL not null,
    filter TEXT not null,
    solved int not null,
);

CREATE INDEX obs_time ON frames (time);
"""

FrameMeta = namedtuple(
    "FrameMeta", "id, job, time, frame, private, keep_frame, duration, filter, solved"
)


def fits_to_binary(frame):
    with io.BytesIO() as f:
        frame.writeto(f)
        f.seek(0)
        dat = f.read()
    return dat


class Cache:
    def __init__(self, db_file="local_frames.db", timeout=10):
        self.db_file = db_file
        self.con = sqlite3.connect(self.db_file, timeout=timeout)

    def initialize(self):
        try:
            with self.con:
                self.con.executescript(_CACHE_SQL)
        except sqlite3.OperationalError as e:
            logger.error(e)

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

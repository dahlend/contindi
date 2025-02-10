import time
import kete
import click
from .system import Connection
from .cache import Cache, Job, JobStatus
from .events import EventStatus, Capture, SetFilter, Slew, TimeConstrained, Sync
from .config import CONFIG


@click.command()
@click.option("--mount", default="iOptron CEM70", help="INDI Name of the mount.")
@click.option("--camera", default="ZWO CCD ASI533MM Pro", help="Name of the camera.")
@click.option("--focus", default="iOptron CEM70", help="INDI Name of the focuser.")
@click.option("--wheel", default="iOptron CEM70", help="INDI Name of the filter wheel.")
@click.option("--host", default="localhost", help="Address of the INDI server.")
@click.option("--port", default=7624, help="Port of the INDI server.")
@click.option("--cache", default="http://127.0.0.1:8090", help="Cache pocketbase url")
def run_schedule(mount, camera, focus, wheel, host, port, cache):
    click.echo("Scheduler Running!")

    conf = dict(
        MOUNT=mount,
        CAMERA=camera,
        FOCUS=focus,
        WHEEL=wheel,
        HOST=(host, port),
        CACHE=cache,
    )
    CONFIG.update(conf)

    click.echo("Config set to:")
    for key, value in CONFIG.items():
        click.echo(f"\t{key:<10s} : {value}")

    cxn = Connection(host=host, port=port)

    state = cxn.state
    for dev in state.data.keys():
        if dev not in CONFIG.values():
            click.echo(f"\t{dev} not found in config")

    cache = Cache(cache)

    cxn.set_camera_recv(send_here="Also")

    event_map = {}

    running = None

    while True:
        time.sleep(0.05)
        jobs = cache.get_jobs()

        for job in jobs:
            if job.id in event_map:
                continue
            if job.status in [JobStatus.FINISHED, JobStatus.FAILED]:
                continue
            if job.status == JobStatus.RUNNING:
                cache.update_job(
                    job.id,
                    status=JobStatus.FAILED,
                    msg="Job was running, but no event found.",
                )
                continue
            try:
                event = parse_job(job)
            except Exception as e:
                click.echo(f"JOB FAILED TO PARSE {str(job)} - {str(e)}")
                cache.update_job(
                    job.id,
                    status=JobStatus.FAILED,
                    msg=f"Failed to parse job: {str(e)}",
                )
                continue
            event_map[job.id] = event
        event_map = {k: v for k, v in sorted(event_map.items(), key=lambda x: x[1])}

        trigger = None
        running = None
        delete = []
        for job_id, event in event_map.items():
            event._update(cxn, cache)
            status = event.status
            msg = event.msg
            job = cache.get_job(job_id)
            if job is None:
                event_map[job_id].cancel(cxn, cache)
                delete.append(job_id)
                continue

            if status == EventStatus.Running:
                running = event

            if status == EventStatus.Finished:
                delete.append(job_id)
                click.echo(f"Finished Job ID: {str(job_id)}")
                cache.update_job(job.id, status=JobStatus.FINISHED, msg=msg)
            elif status == EventStatus.Failed:
                delete.append(job_id)
                cache.update_job(job.id, status=JobStatus.FAILED, msg=msg)
            elif status == EventStatus.Running or status == EventStatus.Canceling:
                if job.status != JobStatus.RUNNING:
                    cache.update_job(job.id, status=JobStatus.RUNNING, msg=msg)
            elif status == EventStatus.NotReady:
                pass
            elif status == EventStatus.Ready and trigger is None:
                trigger = job_id
        for job_id in delete:
            del event_map[job_id]

        if running is None and trigger is not None:
            click.echo(f"Trigger Job ID: {str(trigger)}")
            job = cache.get_job(trigger)
            if job is None:
                event_map[trigger]._cancel(cxn, cache)
                del event_map[trigger]
                continue
            trigger = event_map[trigger]
            cache.update_job(job.id, status=JobStatus.RUNNING, msg=msg)
            trigger._trigger(cxn, cache)


def parse_job(job: Job):
    jd_start = kete.Time(job.jd_start).to_datetime()
    jd_end = kete.Time(job.jd_end).to_datetime()
    cmd, *args = job.cmd.split()
    if cmd.upper() == "STATIC":
        ra, dec = args
        ra = float(ra)
        dec = float(dec)
        filters = list(job.filter)

        # slew to position, cycle through filters and capture
        event = Slew(ra, dec, job.priority)
        for filt in filters:
            filter = SetFilter(filt, job.priority)
            capture = Capture(job.id, job.duration, job.priority)
            event = event + filter + capture
        event = TimeConstrained(event, jd_start, jd_end)
        return event
    elif cmd.upper() == "SYNC_INPLACE":
        filter = SetFilter(job.filter, job.priority)
        sync = Sync(job.priority)
        event = filter + sync
        event = TimeConstrained(event, jd_start, jd_end)
        return event

    raise ValueError(f"Unknown command {cmd}")


@click.command()
@click.option("--host", default="localhost", help="Address of the INDI server.")
@click.option("--port", default=7624, help="Port of the INDI server.")
def find_devices(host, port):
    click.echo("Looking for devices:")

    cxn = Connection(host=host, port=port)

    state = cxn.state

    for dev in state.data.keys():
        click.echo(f"\t{dev}")

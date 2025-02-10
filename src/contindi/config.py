import sys
from collections import UserDict


class Config(UserDict):
    @property
    def mount(self):
        return self["MOUNT"]

    @property
    def camera(self):
        return self["CAMERA"]

    @property
    def focus(self):
        return self["FOCUS"]

    @property
    def wheel(self):
        return self["WHEEL"]

    @property
    def host(self):
        return self["HOST"]

    @property
    def cache(self):
        return self["CACHE"]


this = sys.modules[__name__]
this.CONFIG = None

_DEFAULT_SETTINGS = dict(
    MOUNT="iOptron CEM70",
    CAMERA="ZWO CCD ASI533MM Pro",
    FOCUS="ZWO EAF",
    WHEEL="ZWO EFW",
    HOST=("localhost", 7624),
    CACHE="http://127.0.0.1:8090",
)


def initialize_config():
    if this.CONFIG is None:
        this.CONFIG = Config(**_DEFAULT_SETTINGS)
    else:
        msg = "CONFIG is already initialized."
        raise RuntimeError(msg.format(this.CONFIG))


initialize_config()

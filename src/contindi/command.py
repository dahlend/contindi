import dataclasses
import logging
from .base import INDI_VERSION, NamedInfo, timestamp_from_xml
from typing import Optional


logger = logging.getLogger(__name__)


@dataclasses.dataclass
class GetProperties:
    device: Optional[str] = None
    name: Optional[str] = None

    def to_xml(self):
        dev = f' device="{self.device}"' if self.device else ""
        name = f' name="{self.name}"' if self.name else ""
        return f"""<getProperties version="{INDI_VERSION}"{dev}{name}/>"""


@dataclasses.dataclass
class SetValue(NamedInfo):
    xml_element: None

    @classmethod
    def from_xml(cls, xml_element):
        attribs = super()._parse_xml_element(xml_element)
        attribs["timestamp"] = timestamp_from_xml(xml_element)
        attribs = {k: attribs[k] for k in ["device", "name", "timestamp"]}
        attribs["xml_element"] = xml_element
        return cls(**attribs)


@dataclasses.dataclass
class SetNumberVector(SetValue):
    pass


@dataclasses.dataclass
class SetTextVector(SetValue):
    pass


@dataclasses.dataclass
class SetSwitchVector(SetValue):
    pass


@dataclasses.dataclass
class SetBlobVector(SetValue):
    pass


@dataclasses.dataclass
class DeleteProperty(NamedInfo):
    device: str
    name: str

    @classmethod
    def from_xml(cls, xml_element):
        attribs = xml_element.attrib

        # Parse required values
        if "device" not in attribs:
            raise ValueError("Failed to parse command, 'device' not defined.")
        attribs["timestamp"] = timestamp_from_xml(xml_element)
        attribs["name"] = attribs.get("name", None)
        return cls(**attribs)

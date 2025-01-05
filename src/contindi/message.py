import dataclasses
import datetime
from .base import timestamp_from_xml


@dataclasses.dataclass
class Message:
    device: str
    timestamp: datetime.datetime
    message: str

    @classmethod
    def from_xml(cls, xml_element):
        attribs = xml_element.attrib

        # Parse required values
        for req in ["device", "message"]:
            if req not in attribs:
                raise ValueError(f"Failed to parse vector, '{req}' not defined.")
        attribs["timestamp"] = timestamp_from_xml(xml_element)
        return cls(**attribs)

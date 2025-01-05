from enum import Enum
import dataclasses
import datetime
import logging
from abc import ABC, abstractmethod


# INDI Version implemented
INDI_VERSION = 1.7

logger = logging.getLogger(__name__)


def timestamp_from_xml(xml_element):
    """
    Return a datetime element in UTC time from the provided xml element.
    If the xml does not contain a timestamp, return the current UTC time.
    """
    attribs = xml_element.attrib
    if "timestamp" not in attribs:
        return datetime.datetime.now(tz=datetime.UTC)
    else:
        if isinstance(attribs["timestamp"], datetime.datetime):
            return attribs["timestamp"]
        return datetime.datetime.fromisoformat(attribs["timestamp"].strip()).replace(
            tzinfo=datetime.UTC
        )


class PropertyState(Enum):
    Idle = "Idle"
    Ok = "Ok"
    Busy = "Busy"
    Alert = "Alert"

    @staticmethod
    def from_xml(xml_element):
        attribs = xml_element.attrib
        if attribs["state"] not in PropertyState:
            raise ValueError(
                f"{attribs['state']} not an allowed value for a PropertyState"
            )
        return PropertyState[attribs["state"]]

    def to_string(self):
        if self == PropertyState.Idle:
            return "Idle"
        elif self == PropertyState.Ok:
            return "Ok"
        elif self == PropertyState.Busy:
            return "Busy"
        elif self == PropertyState.Alert:
            return "Alert"


class PropertyPerm(Enum):
    ro = "ro"
    wo = "wo"
    rw = "rw"

    @staticmethod
    def from_xml(xml_element):
        attribs = xml_element.attrib
        if attribs["perm"] not in PropertyPerm:
            raise ValueError(
                f"{attribs['perm']} not an allowed value for a PropertyPerm"
            )
        return PropertyPerm[attribs["perm"]]


@dataclasses.dataclass
class NamedInfo:
    device: str
    name: str
    timestamp: datetime.datetime

    @staticmethod
    def _parse_xml_element(xml_element):
        """
        Return a dictionary of correctly parsed attributes for a vector.
        """
        attribs = xml_element.attrib

        # Parse required values
        for req in ["device", "name"]:
            if req not in attribs:
                raise ValueError(f"Failed to parse vector, '{req}' not defined.")

        attribs["timestamp"] = timestamp_from_xml(xml_element)
        return attribs


@dataclasses.dataclass
class GenericVector(NamedInfo, ABC):
    device: str
    name: str
    label: str
    group: str
    state: PropertyState
    perm: PropertyPerm
    timeout: int
    timestamp: datetime.datetime
    message: str
    elements: dict

    @classmethod
    def _parse_xml_element(cls, xml_element):
        """
        Return a dictionary of correctly parsed attributes for a vector.
        """
        attribs = super()._parse_xml_element(xml_element)

        # Parse required values
        for req in ["device", "name", "perm", "state"]:
            if req not in attribs:
                raise ValueError(f"Failed to parse vector, '{req}' not defined.")
        attribs["perm"] = PropertyPerm.from_xml(xml_element)
        attribs["state"] = PropertyState.from_xml(xml_element)

        attribs["label"] = attribs.get("label", attribs["name"])
        attribs["group"] = attribs.get("group", "")
        attribs["timeout"] = float(attribs.get("timeout", 0.0))
        attribs["message"] = attribs.get("message", None)
        if attribs["message"]:
            logger.warn(attribs["message"])
        return attribs

    @abstractmethod
    def update_from_xml(self, xml_element):
        raise NotImplementedError()

    def create_xml_command(self, *args, **kwargs):
        new_kwargs = {}
        elem_names = list(self.elements.keys())
        if len(elem_names) == len(args):
            new_kwargs = dict(zip(elem_names, args))
        elif len(args) != 0:
            raise ValueError(
                "If arg based setting is used, the number of args must exactly match the number of elements. %s",
                str(elem_names),
            )

        for name in kwargs.keys():
            if name not in self.elements:
                raise ValueError(
                    "Provided element name (%s) is not present in this parameter (%s).",
                    name,
                    str(elem_names),
                )
        new_kwargs.update(kwargs)
        return new_kwargs

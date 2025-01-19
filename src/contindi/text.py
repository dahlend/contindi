import dataclasses
import logging
import xml.etree.ElementTree as ET
from .base import GenericVector, NamedInfo, timestamp_from_xml

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class TextElement:
    name: str
    label: str
    value: str


@dataclasses.dataclass
class TextVector(GenericVector):
    elements: dict[TextElement]

    def create_xml_command(self, *args, **kwargs):
        kwargs = super().create_xml_command(*args, **kwargs)
        cmd = ET.Element("newTextVector", device=self.device, name=self.name)
        for elem_name, new_value in kwargs.items():
            element = self.elements[elem_name]
            elem = ET.SubElement(cmd, "oneText", name=elem_name)
            elem.text = str(new_value)
        return ET.tostring(cmd).decode()

    def is_set(self, *args, **kwargs):
        kwargs = super().create_xml_command(*args, **kwargs)
        for name, val in kwargs.items():
            if self.elements[name].value != val:
                return False
        return True

    @classmethod
    def from_xml(cls, xml_element):
        attribs = cls._parse_xml_element(xml_element)
        attribs["elements"] = {}
        for elem in xml_element.findall("*"):
            elem.attrib["value"] = elem.text.strip() if elem.text is not None else ""
            elem.attrib["label"] = elem.attrib.get("label", "")
            attribs["elements"][elem.attrib["name"]] = TextElement(**elem.attrib)
        return cls(**attribs)

    def update_from_xml(self, xml_element):
        attribs = NamedInfo._parse_xml_element(xml_element)
        if "message" in attribs:
            logger.warn(attribs["message"])

        for elem in xml_element.findall("*"):
            name = elem.attrib["name"]
            self.elements[name].value = elem.text
        self.timestamp = attribs["timestamp"]

    def to_string(self, prefix="", tab="    "):
        vals = [
            prefix
            + self.name
            + f"  ({self.label})   "
            + self.state.to_string()
            + "   "
            + self.timestamp.isoformat()
        ]
        for element in self.elements.values():
            vals.append(
                prefix
                + tab
                + element.name
                + " ("
                + element.label
                + ") : "
                + repr(element.value)
            )
        return "\n".join(vals)

    def __repr__(self):
        return self.to_string()

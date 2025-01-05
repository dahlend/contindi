import dataclasses
import logging
import xml.etree.ElementTree as ET
from .base import GenericVector, NamedInfo

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class NumberElement:
    name: str
    label: str
    format: str
    min: float
    max: float
    step: float
    value: float


@dataclasses.dataclass
class NumberVector(GenericVector):
    elements: dict[NumberElement]

    def create_xml_command(self, *args, **kwargs):
        kwargs = super().create_xml_command(*args, **kwargs)

        cmd = ET.Element("newNumberVector", device=self.device, name=self.name)
        for elem_name, new_value in kwargs.items():
            element = self.elements[elem_name]
            new_value = float(new_value)
            if new_value < element.min or new_value > element.max:
                raise ValueError(
                    "%s %s %s - Cannot set value outside of the range %s to %s ",
                    self.device,
                    self.name,
                    elem_name,
                    element.min,
                    element.max,
                )
            elem = ET.SubElement(cmd, "oneNumber", name=elem_name)
            elem.text = str(new_value)
        return ET.tostring(cmd).decode()

    @classmethod
    def from_xml(cls, xml_element):
        attribs = cls._parse_xml_element(xml_element)
        attribs["elements"] = {}
        for elem in xml_element.findall("*"):
            att = elem.attrib
            att["label"] = att.get("label", "")
            for req in ["name", "label", "format", "min", "max", "step"]:
                if req not in att:
                    raise ValueError(f"NumberElement missing required value '{req}'")
            for req in "min", "max", "step":
                att[req] = float(att[req])
            att["value"] = float(elem.text.strip())
            attribs["elements"][att["name"]] = NumberElement(**att)
        return cls(**attribs)

    def update_from_xml(self, xml_element):
        attribs = NamedInfo._parse_xml_element(xml_element)
        if "message" in attribs:
            logger.warn(attribs["message"])

        for elem in xml_element.findall("*"):
            name = elem.attrib["name"]
            value = float(elem.text)
            self.elements[name].value = value
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
            try:
                v_str = element.format % element.value
            except:
                v_str = str(element.value)
            vals.append(
                prefix + tab + element.name + " (" + element.label + ") : " + v_str
            )
        return "\n".join(vals)

    def __repr__(self):
        return self.to_string()

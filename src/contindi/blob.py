import dataclasses
import base64
import logging
from astropy.io import fits
import tempfile
from .base import GenericVector, NamedInfo

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class Blob:
    name: str
    label: str
    size: int
    value: str
    format: str

    def __repr__(self):
        return f"Blob(name='{self.name}', label='{self.label}', size={self.size}, format='{self.format}')"

    @property
    def frame(self):
        if "fit" in self.format:
            with tempfile.TemporaryFile() as tmp:
                tmp.write(self.value)
                frame = fits.open(tmp, mode=None, memmap=False, lazy_load_hdus=False)[0]
                frame.data
            return frame
        return self.value


@dataclasses.dataclass
class BlobVector(GenericVector):
    elements: dict[Blob]

    def create_xml_command(self, param_name, new_value):
        pass

    def is_set(self, *args, **kwargs):
        return True

    @classmethod
    def from_xml(cls, xml_element):
        attribs = cls._parse_xml_element(xml_element)
        attribs["elements"] = {}
        for elem in xml_element.findall("*"):
            att = elem.attrib
            for req in ["name", "label"]:
                if req not in att:
                    raise ValueError(f"BlobVector missing required value '{req}'")
            att["value"] = None
            att["format"] = None
            att["size"] = None
        attribs["elements"][att["name"]] = Blob(**att)
        return cls(**attribs)

    def update_from_xml(self, xml_element):
        attribs = NamedInfo._parse_xml_element(xml_element)
        if "message" in attribs:
            logger.error(attribs["message"])

        for elem in xml_element.findall("*"):
            name = elem.attrib["name"]
            value = elem.text
            data = base64.b64decode(value)

            self.elements[name].format = elem.attrib["format"]
            self.elements[name].size = int(elem.attrib["size"])
            self.elements[name].value = data
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
            if element.value:
                val = "len(" + str(len(element.value)) + ")"
            else:
                val = None
            vals.append(
                prefix
                + tab
                + element.name
                + "("
                + element.label
                + ")"
                + " : "
                + f"{val}"
            )
        return "\n".join(vals)

    def __repr__(self):
        return self.to_string()

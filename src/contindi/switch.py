import dataclasses
import logging
from enum import Enum
import xml.etree.ElementTree as ET
from .base import GenericVector, NamedInfo, timestamp_from_xml


logger = logging.getLogger(__name__)


class SwitchRule(Enum):
    OneOfMany = "OneOfMany"
    AtMostOne = "AtMostOne"
    AnyOfMany = "AnyOfMany"

    @staticmethod
    def from_str(val):
        if str(val).lower().strip() == "oneofmany":
            return SwitchRule.OneOfMany
        elif str(val).lower().strip() == "atmostone":
            return SwitchRule.AtMostOne
        elif str(val).lower().strip() == "anyofmany":
            return SwitchRule.AnyOfMany
        raise ValueError("Cannot convert string to SwitchRule.")


class SwitchState(Enum):
    On = "On"
    Off = "Off"

    @staticmethod
    def from_str(val):
        if str(val).lower().strip() == "on":
            return SwitchState.On
        elif str(val).lower().strip() == "off":
            return SwitchState.Off
        raise ValueError("Cannot convert string to SwitchState.")


@dataclasses.dataclass
class SwitchElement:
    name: str
    label: str
    value: SwitchState


@dataclasses.dataclass
class SwitchVector(GenericVector):
    rule: SwitchRule
    elements: dict[SwitchElement]

    def create_xml_command(self, *args, **kwargs):
        kwargs = super().create_xml_command(*args, **kwargs)
        if len(kwargs) == 1 and self.rule in [
            SwitchRule.OneOfMany,
            SwitchRule.AtMostOne,
        ]:
            new_val = next(iter(kwargs.values())).lower().capitalize()
            set_name = next(iter(kwargs.keys()))

            # Single command sent, lets make sure the rules are obeyed
            if new_val == "On":
                # if new value is On, everything else must be off
                for elem_name in self.elements.keys():
                    if elem_name not in kwargs:
                        kwargs[elem_name] = "Off"
            elif self.rule == SwitchRule.OneOfMany and len(self.elements) == 2:
                # if new value is Off, and there has to be one on, and there are only 2
                # then we can switch the other to on without ambiguity.
                other_name = set(self.elements.keys())
                other_name.discard(set_name)
                kwargs[next(iter(other_name))] = "On"
            elif self.rule == SwitchRule.AtMostOne:
                # its allowed to turn everything off in this case
                pass
            else:
                raise ValueError(
                    "Setting a single value (%s) Off is ambiguous in this case, as at least one (%s) must be On.",
                    set_name,
                    list(self.elements.keys()),
                )

        cmd = ET.Element("newSwitchVector", device=self.device, name=self.name)
        for elem_name, new_value in kwargs.items():
            element = self.elements[elem_name]
            new_value = str(new_value).lower().capitalize()
            if new_value not in ["On", "Off"]:
                raise ValueError("Switch states must either be On or Off")
            elem = ET.SubElement(cmd, "oneSwitch", name=elem_name)
            elem.text = new_value
        return ET.tostring(cmd).decode()

    def is_set(self, *args, **kwargs):
        kwargs = super().create_xml_command(*args, **kwargs)
        for name, val in kwargs.items():
            if self.elements[name].value != SwitchState.from_str(val):
                return False
        return True

    @classmethod
    def from_xml(cls, xml_element):
        attribs = cls._parse_xml_element(xml_element)
        if "rule" not in attribs:
            raise ValueError("SwitchVector missing required property 'rule'.")
        attribs["rule"] = SwitchRule[attribs["rule"]]

        attribs["elements"] = {}
        for elem in xml_element.findall("*"):
            elem.attrib["value"] = SwitchState[elem.text.strip()]
            attribs["elements"][elem.attrib["name"]] = SwitchElement(**elem.attrib)
        return cls(**attribs)

    def update_from_xml(self, xml_element):
        attribs = NamedInfo._parse_xml_element(xml_element)
        if "message" in attribs:
            logger.warn(attribs["message"])

        for elem in xml_element.findall("*"):
            name = elem.attrib["name"]
            new_state = SwitchState[elem.text.strip()]
            self.elements[name].value = new_state
            if new_state == SwitchState.On and self.rule in [
                SwitchRule.OneOfMany,
                SwitchRule.AtMostOne,
            ]:
                for elem_name in self.elements:
                    if name != elem_name:
                        self.elements[elem_name].value = SwitchState.Off
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
            if element.value == SwitchState.On:
                marker = "<<<"
            else:
                marker = ""
            vals.append(
                prefix + tab + element.name + " (" + element.label + ")    " + marker
            )
        return "\n".join(vals)

    def __repr__(self):
        return self.to_string()

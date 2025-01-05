from xml.etree import ElementTree
import logging
import time
from .switch import SwitchVector
from .text import TextVector
from .number import NumberVector
from .blob import BlobVector
from .message import Message
from .command import (
    DeleteProperty,
    SetNumberVector,
    SetSwitchVector,
    SetTextVector,
    SetBlobVector,
)

logger = logging.getLogger(__name__)


def chunk_xml(text):
    """
    Break text into xml elements <blah .../>

    Text does not have to contain a completely valid xml element.

    Infallable, best effort.

    Returns a list of found elements along with remaining text.
    ([a, b, c], rem_text)
    """

    chunk, text = _digest_chunk(text)
    chunks = []
    while chunk is not None:
        chunks.append(chunk)
        chunk, text = _digest_chunk(text)
    return chunks, text


def parse_chunk(chunk):

    try:
        elem = ElementTree.fromstring(chunk)
    except:
        logger.error("Failed to parse xml: ", chunk)
        return None
    tag = elem.tag.lower()

    # Start with definitions
    if tag == "defswitchvector":
        return SwitchVector.from_xml(elem)
    elif tag == "deftextvector":
        return TextVector.from_xml(elem)
    elif tag == "defnumbervector":
        return NumberVector.from_xml(elem)
    elif tag == "defblobvector":
        return BlobVector.from_xml(elem)
    # Now check for updates
    elif tag == "setnumbervector":
        return SetNumberVector.from_xml(elem)
    elif tag == "settextvector":
        return SetTextVector.from_xml(elem)
    elif tag == "setswitchvector":
        return SetSwitchVector.from_xml(elem)
    elif tag == "setblobvector":
        return SetBlobVector.from_xml(elem)
    # Now check for other
    elif tag == "delproperty":
        return DeleteProperty.from_xml(elem)
    elif tag == "message":
        return Message.from_xml(elem)
    elif tag[:3] == "new":
        # "new___" commands are sent from clients to devices, these are logged
        # here, but otherwise ignored.
        logger.debug("NEW: %s - %s", tag, elem.attrib)
        return None

    return elem


def _digest_chunk(text):
    """
    Given a chunk of xml elements,
    rip off the first one and return it along with the remaining text.
    """

    text = text.strip()
    if len(text) == 0:
        return None, text
    text_len = len(text)
    idx = 0
    if text[idx] != "<":
        logger.warn("Text does not begin with <, skipping ahead")
        while text[idx] != "<":
            idx += 1
            if idx == text_len:
                return None, ""
    text = text[idx:]

    if len(text) < 2:
        return None, text

    chunk = None
    elem_name = text.split(maxsplit=1)[0][1:]
    for idx in range(len(text) - 1):
        char = text[idx]
        chars = text[idx : idx + 2]
        if chars == "/>":
            chunk = text[: idx + 2].strip()
            if len(chunk) == 0:
                chunk = None
            text = text[idx + 2 :]
            return chunk, text
        elif char == ">":
            break

    end_str = "</" + elem_name + ">"
    if end_str not in text:
        # not a complete chunk
        return None, text

    idx = text.find(end_str) + len(end_str)

    chunk = text[:idx].strip()
    text = text[idx:]
    return chunk, text.strip()

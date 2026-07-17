"""Client-side triage for GNU `strings` output.

Extraction itself is done by the real GNU strings CLI in the analyzer container (see
core/analyzer/external_tools/strings_wrapper.py). What's left for the GUI is deciding which of
the returned runs are worth a human's attention - on compressed data most runs are coincidental
printable bytes, so this is the "| grep" half of the classic `strings file | grep ...` workflow.
"""
import re

# Markers worth flagging: CTF tokens, URLs/emails, PEM/key headers, common file magics,
# and long base64/hex blobs (often an encoded payload).
_INTERESTING = re.compile(
    r"flag\{|ctf\{|https?://|ftp://|-----BEGIN|BEGIN [A-Z ]*KEY|"
    r"[\w.+-]+@[\w-]+\.[\w.-]+|%PDF|PK\x03\x04|"
    r"[A-Za-z0-9+/]{24,}={0,2}|[0-9a-fA-F]{32,}",
    re.IGNORECASE,
)


def is_interesting(text: str) -> bool:
    return bool(_INTERESTING.search(text))

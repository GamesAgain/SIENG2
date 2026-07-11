import re

def extract_base64(text: str) -> list:
    pattern = re.compile(r'(?:[A-Za-z0-9+/]{4}){5,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?')
    return pattern.findall(text)

def extract_hex(text: str) -> list:
    pattern = re.compile(r'(?:[0-9A-Fa-f]{2}[\s:-]?){10,}')
    return pattern.findall(text)

def extract_binary(text: str) -> list:
    clean_text = text.replace(" ", "")
    pattern = re.compile(r'[01]{24,}')
    return pattern.findall(clean_text)
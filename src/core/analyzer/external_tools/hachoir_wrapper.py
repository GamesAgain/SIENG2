from typing import Dict, Any
from hachoir.parser import createParser
from hachoir.core.log import log

log.use_print = False

def _parse_field_recursive(field) -> Dict[str, Any]:
    chunk_info = {
        "name": field.name,
        "description": field.description,
        "size_bytes": field.size // 8
    }
    
    if field.display and not field.is_field_set:
        chunk_info["value"] = field.display

    if field.is_field_set:
        chunk_info["sub_chunks"] = []
        for child in field:
            chunk_info["sub_chunks"].append(_parse_field_recursive(child))
            
    return chunk_info

def extract_file_structure(file_path: str) -> Dict[str, Any]:
    results = {
        "parsed_size_bytes": 0,
        "structure": [],
        "error": None
    }

    try:
        parser = createParser(file_path)
        if not parser:
            results["error"] = "Hachoir does not support this file type."
            return results

        results["parsed_size_bytes"] = parser.size // 8

        for field in parser:
            results["structure"].append(_parse_field_recursive(field))

    except Exception as e:
        results["error"] = f"Hachoir extraction failed: {str(e)}"

    return results

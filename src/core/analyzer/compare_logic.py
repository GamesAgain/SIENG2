from typing import Dict, Any
from pathlib import Path
from src.core.analyzer.handle import FileAnalyzerDispatcher

def compare_results(res_original: Dict[str, Any], res_stego: Dict[str, Any], orig_path: str = None, stego_path: str = None) -> Dict[str, Any]:
    """
    Compares two analyzer result dictionaries and returns the differences.
    """
    diff = {
        "metadata_diff": compare_metadata(
            res_original.get("metadata_analysis", {}),
            res_stego.get("metadata_analysis", {})
        ),
        "structure_diff": compare_structure(
            res_original.get("structure_analysis", {}),
            res_stego.get("structure_analysis", {})
        ),
        "statistical_diff": compare_statistics(
            res_original.get("statistical_analysis", {}),
            res_stego.get("statistical_analysis", {})
        ),
        "basic_info": {
            "format_original": res_original.get("format"),
            "format_stego": res_stego.get("format"),
            "size_original": res_original.get("file_size", 0),
            "size_stego": res_stego.get("file_size", 0)
        }
    }
    
    return diff

def compare_metadata(meta_original: dict, meta_stego: dict) -> dict:
    raw_orig = meta_original.get("raw_data", {})
    raw_stego = meta_stego.get("raw_data", {})
    
    added = {}
    removed = {}
    changed = {}
    unchanged = {}
    
    keys_orig = set(raw_orig.keys())
    keys_stego = set(raw_stego.keys())
    
    # Ignore SourceFile and System:Directory as they will always be different
    keys_orig.discard("SourceFile")
    keys_stego.discard("SourceFile")
    keys_orig.discard("System:Directory")
    keys_stego.discard("System:Directory")
    
    for key in keys_stego - keys_orig:
        added[key] = raw_stego[key]
        
    for key in keys_orig - keys_stego:
        removed[key] = raw_orig[key]
        
    for key in keys_orig.intersection(keys_stego):
        if str(raw_orig[key]) != str(raw_stego[key]):
            changed[key] = {
                "original": raw_orig[key],
                "stego": raw_stego[key]
            }
        else:
            unchanged[key] = raw_stego[key]
            
    return {
        "unchanged": unchanged,
        "added": added,
        "removed": removed,
        "changed": changed
    }

def compare_structure(struct_orig: dict, struct_stego: dict) -> dict:
    return {
        "original": struct_orig,
        "stego": struct_stego
    }

def compare_statistics(stat_orig: dict, stat_stego: dict) -> dict:
    return {
        "original": stat_orig,
        "stego": stat_stego
    }

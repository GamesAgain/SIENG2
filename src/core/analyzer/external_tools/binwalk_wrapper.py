import subprocess
from typing import Dict, Any

def run_binwalk(file_path: str) -> Dict[str, Any]:

    results = {
        "signatures": [],
        "error": None
    }

    try:
        process = subprocess.run(['binwalk', file_path], capture_output=True, text=True)
        
        if process.returncode != 0 and not process.stdout:
            results["error"] = f"Binwalk error: {process.stderr}"
            return results
            
        for line in process.stdout.split('\n'):
            line = line.strip()
            if line and line[0].isdigit():
                parts = line.split(maxsplit=2)
                if len(parts) >= 3:
                    offset = int(parts[0])
                    description = parts[2]
                    results["signatures"].append({
                        "offset": offset,
                        "description": description
                    })
    except Exception as e:
        results["error"] = f"Failed to run binwalk CLI: {str(e)}"

    return results

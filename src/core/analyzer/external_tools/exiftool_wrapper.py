import exiftool

def extract_metadata(file_path: str):
    """
    Extracts deep metadata from a file using specific ExifTool options.
    """
    print(f"Reading deep metadata from: {file_path}\n{'-'*50}")
    
    try:
        with exiftool.ExifToolHelper() as et:

            metadata = et.execute_json(
                "-a",   # Allow Duplicates
                "-u",   # Unknown Tags
                "-ee",  # Extract Embedded
                "-G1",  # Detailed Grouping
                file_path
            )
                    
            if metadata and len(metadata) > 0:
                print(f"Data Type: {type(metadata[0])}")
                print(f"Total Tags Found: {len(metadata[0])}\n{'-'*50}")
                
                for key, value in metadata[0].items():
                    print(f"key: {key}")
                    print(f"value: {value}")
                    print("-" * 20)
                    
                return metadata[0]
            
            return {}
                    
    except Exception as e:
        if "not found" in str(e).lower() or "executable" in str(e).lower():
            print("ExifTool executable not found in the system.")
            print("Please ensure 'exiftool' is installed or in the System PATH.")
        else:
            print(f"ExifTool Error: {e}")
        return {}
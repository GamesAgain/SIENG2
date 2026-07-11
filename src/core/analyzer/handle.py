import os
from typing import Dict, Any

from src.core.analyzer.formats.png_handler import PNGHandler
from src.core.analyzer.formats.wav_handler import WAVHandler
from src.core.analyzer.formats.avi_handler import AVIHandler

class FileAnalyzerDispatcher:
    def __init__(self):
        self.handlers = {
            ".png": PNGHandler,
            ".wav": WAVHandler,
            ".avi": AVIHandler
        }

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}
            
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        
        handler_class = self.handlers.get(ext)
        
        if not handler_class:
            return {"error": f"Unsupported file format: {ext}"}
            
        print(f"[Dispatcher] Routing file {file_path} to {handler_class.__name__}")
        
        handler_instance = handler_class(file_path)
        results = handler_instance.analyze()
        
        return results
        
def analyze(file_path: str) -> Dict[str, Any]:
    dispatcher = FileAnalyzerDispatcher()
    return dispatcher.analyze_file(file_path)
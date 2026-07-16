from .compare_diff_base import CompareDiffTab

class MetaDiffTab(CompareDiffTab):
    def __init__(self):
        super().__init__(["PROPERTY", "ORIGINAL (COVER)", "SUSPICIOUS (STEGO)", "STATUS"])
        
    def load_data(self, meta_diff: dict):
        self.table.setRowCount(0)
        
        unchanged = meta_diff.get("unchanged", {})
        added = meta_diff.get("added", {})
        removed = meta_diff.get("removed", {})
        changed = meta_diff.get("changed", {})
        
        rows = []
        
        ignore_keys = {"directory", "sourcefile", "filename", "fileaccessdate", "filemodifydate", "filecreatedate", "file:directory", "file:filename"}
        
        for k, v in unchanged.items():
            if k.lower() in ignore_keys: continue
            rows.append((k, str(v), str(v), "", None)) # No highlight (white) and blank status
            
        for k, v in changed.items():
            if k.lower() in ignore_keys: continue
            rows.append((k, v.get("original", ""), v.get("stego", ""), "CHANGED", "#EAB308")) # Yellow
            
        for k, v in added.items():
            if k.lower() in ignore_keys: continue
            rows.append((k, "-", str(v), "ADDED", "#EF4444")) # Red
            
        for k, v in removed.items():
            if k.lower() in ignore_keys: continue
            rows.append((k, str(v), "-", "REMOVED", "#EF4444")) # Red
            
        rows.sort(key=lambda x: x[0])
        
        for r in rows:
            prop_name, orig_val, stego_val, status, color = r
            self.add_row([prop_name, orig_val, stego_val, status], color)


import json
import os
from pathlib import Path

class ProjectScanner:
    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root)
        self.reports_dir = self.repo_root / "security" / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
    def scan(self):
        # Gather basic directories
        dirs = [d.name for d in self.repo_root.iterdir() if d.is_dir() and not d.name.startswith(".")]
        
        inventory = {
            "project_structure": {
                "directories": dirs
            },
            "status": "Scanned successfully (Read-Only)"
        }
        
        # Save inventory
        inventory_path = self.reports_dir / "PROJECT_INVENTORY.json"
        with open(inventory_path, "w", encoding="utf-8") as f:
            json.dump(inventory, f, indent=2)
            
        print(f"Inventory saved to {inventory_path}")

if __name__ == "__main__":
    scanner = ProjectScanner(os.getcwd())
    scanner.scan()

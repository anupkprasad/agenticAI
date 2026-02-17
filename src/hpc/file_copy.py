"""
HPC File Copy Tool - Copy simulation files to HPC working directory
"""
import os
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool
def copy_simulation_files(
    source_dir: str,
    dest_dir: str,
    file_patterns: Optional[List[str]] = None,
    create_dest: bool = True
) -> Dict[str, Any]:
    """
    Copy simulation files from setup directory to HPC working directory.
    
    Args:
        source_dir: Source directory (e.g., working_dir/simsetup)
        dest_dir: Destination directory (e.g., working_dir/hpc)
        file_patterns: File patterns to copy (default: *.gro, *.top, *.mdp, *.itp)
        create_dest: Create destination directory if it doesn't exist
        
    Returns:
        Dict with success status and list of copied files
    """
    try:
        source_path = Path(source_dir)
        dest_path = Path(dest_dir)
        
        if not source_path.exists():
            return {
                "success": False,
                "error": f"Source directory does not exist: {source_dir}"
            }
        
        if create_dest:
            dest_path.mkdir(parents=True, exist_ok=True)
        
        if file_patterns is None:
            file_patterns = ["*.gro", "*.top", "*.mdp", "*.itp"]
        
        copied_files = []
        for pattern in file_patterns:
            for file_path in source_path.glob(pattern):
                dest_file = dest_path / file_path.name
                shutil.copy2(file_path, dest_file)
                copied_files.append({
                    "source": str(file_path),
                    "destination": str(dest_file),
                    "size": file_path.stat().st_size
                })
                logger.info(f"Copied: {file_path.name} -> {dest_dir}")
        
        if not copied_files:
            return {
                "success": False,
                "error": f"No files matching patterns {file_patterns} found in {source_dir}"
            }
        
        return {
            "success": True,
            "files_copied": len(copied_files),
            "copied_files": copied_files,
            "destination": str(dest_path),
            "message": f"Copied {len(copied_files)} files to {dest_dir}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"File copy failed: {e}"
        }

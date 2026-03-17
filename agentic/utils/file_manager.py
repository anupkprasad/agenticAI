"""
Secure File Manager for Workflow

Ensures all file operations:
1. Only happen within working_dir
2. Are tracked in file_registry
3. Prevent accidental writes to root or other directories
4. Agents only specify filenames, system manages full paths
"""
import os
import logging
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Union, List

logger = logging.getLogger(__name__)


class SecureFileManager:
    """
    Centralized file manager that enforces directory isolation and automatic tracking.
    
    All agents should use this manager for file operations to ensure:
    - Files only written/deleted within working_dir
    - All operations tracked in file_registry
    - LLM provides only filenames, not full paths
    """
    
    def __init__(
        self,
        working_dir: str,
        agent_name: str,
        file_registry: Dict[str, Dict[str, str]]
    ):
        """
        Initialize secure file manager for an agent.
        
        Args:
            working_dir: Base working directory (e.g., "working_dir")
            agent_name: Agent name (e.g., "analysis", "simsetup", "preprocess", "hpc")
            file_registry: Reference to state file_registry (modified in-place)
        """
        self.working_dir = str(Path(working_dir).resolve())
        self.agent_name = agent_name
        
        # Agent's designated subdirectory: working_dir/{agent_name}/
        self.agent_dir = str(Path(self.working_dir) / agent_name)
        os.makedirs(self.agent_dir, exist_ok=True)
        
        # Reference to state file_registry
        self.file_registry = file_registry
        
        logger.info(f"SecureFileManager initialized: {self.agent_name} -> {self.agent_dir}")
    
    def sanitize_filename(self, filename_or_path: str) -> str:
        """
        Extract only the filename from LLM output, removing any path components.
        
        This ensures LLM cannot specify directories, only filenames.
        
        Args:
            filename_or_path: Raw output from LLM (may contain path components)
            
        Returns:
            Clean filename without any directory separators
            
        Examples:
            >>> manager.sanitize_filename("output.csv")
            "output.csv"
            >>> manager.sanitize_filename("/some/path/output.csv")
            "output.csv"
            >>> manager.sanitize_filename("../../../etc/passwd")
            "passwd"        """
        clean_name = Path(filename_or_path).name
        
        if clean_name != filename_or_path:
            logger.warning(
                f"{self.agent_name}: Sanitized filename from '{filename_or_path}' to '{clean_name}'"
            )
        
        return clean_name
    
    def get_agent_path(self, filename: str) -> str:
        """
        Get full path for a file in the agent's directory.
        
        Args:
            filename: Just the filename (will be sanitized if contains path)
            
        Returns:
            Full absolute path: {working_dir}/{agent_name}/{filename}
        """
        clean_name = self.sanitize_filename(filename)
        full_path = str(Path(self.agent_dir) / clean_name)
        return full_path
    
    def validate_path(self, path: str) -> bool:
        """
        Validate that a path is within working_dir (security check).
        
        Args:
            path: Path to validate
            
        Returns:
            True if path is within working_dir, False otherwise
        """
        try:
            abs_path = Path(path).resolve()
            working_abs = Path(self.working_dir).resolve()
            
            # Check if path is within working_dir
            abs_path.relative_to(working_abs)
            return True
        except ValueError:
            logger.error(
                f"{self.agent_name}: SECURITY VIOLATION - Attempted access outside working_dir: "
                f"{path} (working_dir: {self.working_dir})"
            )
            return False
    
    def write_file(
        self,
        filename: str,
        content: Union[str, bytes],
        file_type: str = "output",
        description: str = "Generated file",
        mode: str = "w"
    ) -> Optional[str]:
        """
        Safely write a file to the agent's directory with automatic registry tracking.
        
        Args:
            filename: Just the filename (path components will be stripped)
            content: Content to write (str or bytes)
            file_type: Type classification for registry ("output", "topology", "coordinates", etc.)
            description: Description for registry
            mode: Write mode ("w" for text, "wb" for binary)
            
        Returns:
            Full path to written file, or None if failed
        """
        try:
            # Get sanitized path
            full_path = self.get_agent_path(filename)
            
            # Validate path is within working_dir
            if not self.validate_path(full_path):
                logger.error(f"Refusing to write file outside working_dir: {full_path}")
                return None
            
            # Write file
            with open(full_path, mode) as f:
                f.write(content)
            
            # Register in file_registry
            self._register_file(full_path, file_type, description)
            
            logger.info(f"{self.agent_name}: Wrote {file_type} file: {full_path}")
            return full_path
            
        except Exception as e:
            logger.error(f"{self.agent_name}: Failed to write {filename}: {e}")
            return None
    
    def delete_file(self, filename: str) -> bool:
        """
        Safely delete a file from the agent's directory.
        
        Args:
            filename: Filename to delete
            
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            full_path = self.get_agent_path(filename)
            
            # Validate path
            if not self.validate_path(full_path):
                logger.error(f"Refusing to delete file outside working_dir: {full_path}")
                return False
            
            if not Path(full_path).exists():
                logger.warning(f"{self.agent_name}: File doesn't exist: {full_path}")
                return False
            
            # Delete file
            os.remove(full_path)
            
            # Remove from registry
            if full_path in self.file_registry:
                del self.file_registry[full_path]
            
            logger.info(f"{self.agent_name}: Deleted file: {full_path}")
            return True
            
        except Exception as e:
            logger.error(f"{self.agent_name}: Failed to delete {filename}: {e}")
            return False
    
    def copy_file(
        self,
        source_path: str,
        dest_filename: str,
        file_type: str = "copy",
        description: str = "Copied file"
    ) -> Optional[str]:
        """
        Copy a file from another location to the agent's directory.
        
        Args:
            source_path: Source file path (can be from another agent's directory)
            dest_filename: Destination filename (not full path)
            file_type: Type classification for registry
            description: Description for registry
            
        Returns:
            Full path to copied file, or None if failed
        """
        try:
            # Sanitize destination filename
            dest_path = self.get_agent_path(dest_filename)
            
            # Validate destination is within working_dir
            if not self.validate_path(dest_path):
                logger.error(f"Refusing to copy to path outside working_dir: {dest_path}")
                return None
            
            # Validate source exists
            if not Path(source_path).exists():
                logger.error(f"{self.agent_name}: Source file doesn't exist: {source_path}")
                return None
            
            # Copy file
            shutil.copy2(source_path, dest_path)
            
            # Register in file_registry
            self._register_file(dest_path, file_type, description)
            
            logger.info(f"{self.agent_name}: Copied {source_path} -> {dest_path}")
            return dest_path
            
        except Exception as e:
            logger.error(f"{self.agent_name}: Failed to copy file: {e}")
            return None
    
    def register_external_file(
        self,
        file_path: str,
        file_type: str,
        description: str
    ) -> bool:
        """
        Register a file created by external tools (e.g., GROMACS) in the registry.
        
        Use this when tools create files directly and you need to track them.
        
        Args:
            file_path: Full path to the file
            file_type: Type classification
            description: Description for registry
            
        Returns:
            True if registered successfully
        """
        try:
            # Validate path exists and is within working_dir
            if not Path(file_path).exists():
                logger.warning(f"{self.agent_name}: Cannot register non-existent file: {file_path}")
                return False
            
            if not self.validate_path(file_path):
                logger.error(f"Refusing to register file outside working_dir: {file_path}")
                return False
            
            self._register_file(file_path, file_type, description)
            return True
            
        except Exception as e:
            logger.error(f"{self.agent_name}: Failed to register file: {e}")
            return False
    
    def _register_file(
        self,
        file_path: str,
        file_type: str,
        description: str
    ) -> None:
        """
        Internal method to register file in file_registry.
        
        Args:
            file_path: Full absolute path
            file_type: Type classification
            description: Description
        """
        abs_path = str(Path(file_path).resolve())
        
        self.file_registry[abs_path] = {
            "type": file_type,
            "description": description,
            "stage": self.agent_name,
            "filename": Path(abs_path).name
        }
        
        logger.debug(f"Registered in file_registry: {abs_path} ({file_type})")
    
    def resolve_input_file(
        self,
        file_reference: str,
        search_stages: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Resolve an input file reference to absolute path using file_registry.
        
        This enables cross-agent file access (e.g., analysis agent reading HPC outputs).
        
        Args:
            file_reference: Filename or path to resolve
            search_stages: List of workflow stages to search (e.g., ["hpc", "simsetup"])
            
        Returns:
            Absolute path if found, None otherwise
        """
        # Extract filename for comparison
        filename = Path(file_reference).name
        
        # Search file_registry
        for registered_path, metadata in self.file_registry.items():
            registered_filename = Path(registered_path).name
            
            # Check filename match
            if registered_filename == filename:
                # If search_stages specified, filter by stage
                if search_stages and metadata.get("stage") not in search_stages:
                    continue
                
                # Verify file exists
                if Path(registered_path).exists():
                    logger.debug(
                        f"{self.agent_name}: Resolved {file_reference} -> {registered_path} "
                        f"(from {metadata.get('stage', 'unknown')} stage)"
                    )
                    return registered_path
        
        # If not in registry, try as-is if it exists
        ref_path = Path(file_reference)
        if ref_path.exists():
            abs_path = str(ref_path.resolve())
            if self.validate_path(abs_path):
                return abs_path
        
        logger.warning(
            f"{self.agent_name}: Could not resolve file '{file_reference}' "
            f"(searched {len(self.file_registry)} registry entries)"
        )
        return None
    
    def get_files_by_type(self, file_type: str) -> List[str]:
        """
        Get all registered files of a specific type.
        
        Args:
            file_type: Type to filter by ("trajectory", "topology", etc.)
            
        Returns:
            List of absolute paths matching the type
        """
        matching_files = []
        for file_path, metadata in self.file_registry.items():
            if metadata.get("type") == file_type:
                matching_files.append(file_path)
        return matching_files
    
    def get_agent_files(self) -> List[str]:
        """
        Get all files created by this agent.
        
        Returns:
            List of absolute paths created by this agent
        """
        agent_files = []
        for file_path, metadata in self.file_registry.items():
            if metadata.get("stage") == self.agent_name:
                agent_files.append(file_path)
        return agent_files
    
    def list_agent_directory(self) -> List[str]:
        """
        List all files in the agent's directory.
        
        Returns:
            List of filenames (not full paths) in agent directory
        """
        try:
            agent_path = Path(self.agent_dir)
            return [f.name for f in agent_path.iterdir() if f.is_file()]
        except Exception as e:
            logger.error(f"{self.agent_name}: Failed to list directory: {e}")
            return []

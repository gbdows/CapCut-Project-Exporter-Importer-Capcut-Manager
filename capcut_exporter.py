#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CapCut Project Exporter
Export CapCut projects to portable ZIP files with relative media paths
"""

import json
import os
import shutil
import zipfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
import hashlib  

# Configure comprehensive logging
def setup_logging():
    """Setup detailed logging for debugging"""
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Setup file handler with detailed formatting
    log_file = os.path.join(log_dir, f'capcut_exporter_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()  # Also output to console
        ]
    )
    
    return logging.getLogger(__name__)

logger = setup_logging()

class CapCutExporter:
    """Main class for exporting CapCut projects to portable format"""
    
    def __init__(self):
        self.supported_extensions = {
            'video': ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm'],
            'audio': ['.mp3', '.wav', '.aac', '.ogg', '.flac', '.m4a'],
            'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
        }


    def _is_path_like_key(self, key: str) -> bool:
        if not isinstance(key, str):
            return False
        lower = key.lower()
        return lower.endswith('path') or lower.endswith('_path') or lower.endswith('filepath') or lower == 'file_path'

    def _looks_like_path_value(self, value: str) -> bool:
        if not isinstance(value, str):
            return False
        candidate = value.strip()
        if not candidate:
            return False
        normalized = candidate.replace('\\', '/')
        return (
            normalized.startswith(('./', '../', '/', '~/', '.\\', '..\\'))
            or (len(normalized) > 1 and normalized[1] == ':')
            or normalized.startswith('file:///')
        )

    def _abspath_norm(self, path_value: str) -> str:
        return os.path.abspath(path_value).replace('\\', '/')

    def _resolve_export_path(self, original: str, project_folder: str, medias_folder: str, key: str | None = None) -> str:
        """Convert any source path into a portable relative path inside the export bundle."""
        if not isinstance(original, str):
            return original

        stripped = original.strip()
        if not stripped:
            return stripped

        normalized = stripped.replace('\\', '/')

        structural = {
            'draft_root_path': './',
            'draft_fold_path': './project',
            'draft_cover': './project/draft_cover.jpg',
            'draft_removable_storage_device_path': '',
        }
        if key in structural:
            return structural[key]

        # Already portable.
        if normalized.startswith('./medias/') or normalized.startswith('medias/'):
            if normalized.startswith('./'):
                return normalized
            return './' + normalized

        if normalized.startswith('./project/') or normalized.startswith('project/'):
            if normalized.startswith('./'):
                return normalized
            return './' + normalized

        # Absolute path or path-like reference: try to map it inside the bundle.
        filename = os.path.basename(normalized)
        media_other = os.path.join(medias_folder, 'other', filename)
        media_main = os.path.join(medias_folder, filename)

        if os.path.exists(media_other):
            return './medias/other/' + os.path.basename(media_other)
        if os.path.exists(media_main):
            return './medias/' + os.path.basename(media_main)

        # Keep paths internal to the copied project tree relative to ./project.
        if os.path.exists(os.path.join(project_folder, filename)):
            return './project/' + filename

        if os.path.isabs(stripped) or (len(normalized) > 1 and normalized[1] == ':'):
            return './medias/' + filename

        if key is not None and self._is_path_like_key(key):
            return './project/' + normalized.lstrip('./').lstrip('.\\')

        return stripped

    def _rewrite_exported_project_jsons(self, project_folder: str, medias_folder: str) -> int:
        """Rewrite every JSON file under project/ to use portable relative paths."""
        rewritten_files = 0

        for root, _, files in os.walk(project_folder):
            for filename in files:
                if not filename.lower().endswith('.json'):
                    continue

                json_path = os.path.join(root, filename)
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except Exception as e:
                    logger.warning(f"Skipping unreadable JSON during export rewrite: {json_path} ({e})")
                    continue

                changed = 0

                def walk(obj):
                    nonlocal changed
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            if isinstance(value, str) and (self._is_path_like_key(key) or self._looks_like_path_value(value)):
                                new_value = self._resolve_export_path(value, project_folder, medias_folder, key)
                                if new_value != value:
                                    obj[key] = new_value
                                    changed += 1
                            else:
                                walk(value)
                    elif isinstance(obj, list):
                        for item in obj:
                            walk(item)

                walk(data)

                if changed:
                    try:
                        with open(json_path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                        rewritten_files += 1
                        logger.info(f"JSON export rewritten: {json_path} ({changed} path(s))")
                    except Exception as e:
                        logger.error(f"Failed to save rewritten JSON {json_path}: {e}")

        return rewritten_files
    
    def find_capcut_projects(self) -> List[str]:
        """Find all CapCut project folders in AppData with automatic user detection"""
        logger.debug("=== Starting CapCut project detection ===")
        
        # Get LOCALAPPDATA environment variable
        localappdata = os.environ.get('LOCALAPPDATA', '')
        logger.debug(f"LOCALAPPDATA environment variable: '{localappdata}'")
        
        if not localappdata:
            logger.error("LOCALAPPDATA environment variable not found")
            logger.error("Available environment variables: %s", [k for k in os.environ.keys() if 'APPDATA' in k or 'LOCAL' in k])
            return []
        
        # Construct CapCut projects path
        appdata_path = os.path.join(localappdata, 'CapCut', 'User Data', 'Projects')
        projects = []
        
        # Log user information for debugging
        username = os.environ.get('USERNAME', 'Unknown')
        logger.info(f"Searching for CapCut projects for user: {username}")
        logger.info(f"Looking in: {appdata_path}")
        logger.debug(f"Path exists: {os.path.exists(appdata_path)}")
        
        if not os.path.exists(appdata_path):
            logger.warning(f"CapCut projects folder not found: {appdata_path}")
            logger.debug("Searching alternative CapCut installation paths...")
            
            # Try alternative paths
            alt_paths = [
                os.path.join(os.environ.get('PROGRAMFILES', ''), 'CapCut', 'User Data', 'Projects'),
                os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'CapCut', 'User Data', 'Projects'),
                os.path.join(localappdata, 'Programs', 'CapCut', 'User Data', 'Projects'),
            ]
            
            for alt_path in alt_paths:
                logger.debug(f"Checking alternative path: {alt_path}")
                if os.path.exists(alt_path):
                    logger.info(f"Found CapCut at alternative path: {alt_path}")
                    appdata_path = alt_path
                    break
            else:
                logger.error("No CapCut installation found in any standard location")
                logger.info("Please ensure CapCut is installed and you have created at least one project")
                return projects
        
        for item in os.listdir(appdata_path):
            # Check for both patterns: "com.lveditor.draft" and "com.lveditor.draft.*"
            if item == 'com.lveditor.draft' or item.startswith('com.lveditor.draft.'):
                project_path = os.path.join(appdata_path, item)
                if os.path.isdir(project_path):
                    # If it's "com.lveditor.draft", explore subdirectories
                    if item == 'com.lveditor.draft':
                        logger.info(f"Exploring subdirectories in: {project_path}")
                        try:
                            subitems = os.listdir(project_path)
                            logger.debug(f"Found {len(subitems)} items in {project_path}")
                            
                            for subitem in subitems:
                                sub_path = os.path.join(project_path, subitem)
                                logger.debug(f"Checking subitem: {subitem} -> {sub_path}")
                                
                                if os.path.isdir(sub_path):
                                    # Check if this subdirectory contains draft_content.json
                                    draft_file = os.path.join(sub_path, 'draft_content.json')
                                    has_draft = os.path.exists(draft_file)
                                    logger.debug(f"Subdirectory {subitem} has draft_content.json: {has_draft}")
                                    
                                    if has_draft:
                                        projects.append(sub_path)
                                        logger.info(f"Found project in subdirectory: {sub_path}")
                                        
                                        # Log basic project info
                                        try:
                                            file_size = os.path.getsize(draft_file)
                                            logger.debug(f"draft_content.json size: {file_size} bytes")
                                        except Exception as size_e:
                                            logger.warning(f"Could not get file size for {draft_file}: {size_e}")
                                    else:
                                        logger.debug(f"No draft_content.json found in: {sub_path}")
                                else:
                                    logger.debug(f"Skipping non-directory: {sub_path}")
                        except PermissionError as pe:
                            logger.error(f"Permission denied accessing {project_path}: {pe}")
                        except Exception as e:
                            logger.error(f"Error exploring subdirectories in {project_path}: {e}")
                            logger.debug(f"Exception details:", exc_info=True)
                    else:
                        # For com.lveditor.draft.* patterns, add directly
                        projects.append(project_path)
                        logger.info(f"Found project folder: {project_path}")
                        logger.debug(f"Checking if {project_path} has draft_content.json: {os.path.exists(os.path.join(project_path, 'draft_content.json'))}")
        
        logger.info(f"Found {len(projects)} CapCut projects")
        return projects
    
    def diagnose_capcut_installation(self) -> Dict:
        """Diagnose CapCut installation and provide helpful information"""
        username = os.environ.get('USERNAME', 'Unknown')
        localappdata = os.environ.get('LOCALAPPDATA', '')
        appdata = os.environ.get('APPDATA', '')
        
        diagnostic_info = {
            'username': username,
            'localappdata': localappdata,
            'appdata': appdata,
            'capcut_paths': [],
            'issues': [],
            'recommendations': []
        }
        
        # Check common CapCut installation paths
        possible_paths = [
            os.path.join(localappdata, 'CapCut'),
            os.path.join(appdata, 'CapCut'),
            os.path.join(os.environ.get('PROGRAMFILES', ''), 'CapCut'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'CapCut'),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                diagnostic_info['capcut_paths'].append(path)
                logger.info(f"Found CapCut installation at: {path}")
            else:
                logger.debug(f"CapCut not found at: {path}")
        
        # Check for projects folder specifically
        projects_path = os.path.join(localappdata, 'CapCut', 'User Data', 'Projects')
        project_folders = []
        sub_projects = []

        if os.path.exists(projects_path):
            logger.info(f"Projects folder exists: {projects_path}")
            
            # Check for project folders inside
            if os.path.exists(projects_path):
                for item in os.listdir(projects_path):
                    if item == 'com.lveditor.draft' or item.startswith('com.lveditor.draft.'):
                        project_folders.append(item)
                        
                        # If it's com.lveditor.draft, explore subdirectories
                        if item == 'com.lveditor.draft':
                            draft_path = os.path.join(projects_path, item)
                            if os.path.isdir(draft_path):
                                try:
                                    for subitem in os.listdir(draft_path):
                                        sub_path = os.path.join(draft_path, subitem)
                                        if os.path.isdir(sub_path):
                                            draft_file = os.path.join(sub_path, 'draft_content.json')
                                            if os.path.exists(draft_file):
                                                sub_projects.append(f"{item}/{subitem}")
                                except Exception as e:
                                    logger.warning(f"Error exploring subdirectories in {draft_path}: {e}")
            
            if project_folders:
                logger.info(f"Found project folders: {project_folders}")
                diagnostic_info['project_folders'] = project_folders
                
                # Add sub-projects if found
                if sub_projects:
                    logger.info(f"Found sub-projects: {sub_projects}")
                    diagnostic_info['sub_projects'] = sub_projects
            else:
                diagnostic_info['issues'].append("No project folders found in Projects directory")
                diagnostic_info['recommendations'].append("Create at least one project in CapCut")
        else:
            diagnostic_info['issues'].append(f"Projects folder not found: {projects_path}")
            diagnostic_info['recommendations'].append("Install CapCut and create at least one project")
        
        # Check if CapCut executable exists (optional - not critical for project export)
        exe_paths = [
            os.path.join(os.environ.get('PROGRAMFILES', ''), 'CapCut', 'CapCut.exe'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'CapCut', 'CapCut.exe'),
            os.path.join(localappdata, 'CapCut', 'CapCut.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'CapCut', 'CapCut.exe'),
        ]
        
        capcut_exe_found = False
        for exe_path in exe_paths:
            if os.path.exists(exe_path):
                capcut_exe_found = True
                diagnostic_info['capcut_exe'] = exe_path
                break
        
        if not capcut_exe_found:
            # Only add as info, not as critical issue
            diagnostic_info['notes'] = diagnostic_info.get('notes', [])
            diagnostic_info['notes'].append("CapCut executable not found in standard locations (may be installed via Microsoft Store)")
        
        # Only recommend installation if no projects found AND no exe found
        if not project_folders and not capcut_exe_found:
            diagnostic_info['recommendations'].append("Install CapCut from official website or Microsoft Store")
        
        return diagnostic_info
    
    def get_project_info(self, project_path: str) -> Optional[Dict]:
        """Extract basic information from a CapCut project"""
        logger.debug(f"=== Getting project info for: {project_path} ===")
        
        draft_file = os.path.join(project_path, 'draft_content.json')
        logger.debug(f"Looking for draft_content.json at: {draft_file}")
        
        if not os.path.exists(draft_file):
            logger.warning(f"draft_content.json not found in {project_path}")
            logger.debug(f"Directory contents: {os.listdir(project_path) if os.path.exists(project_path) else 'Directory not found'}")
            return None
        
        try:
            logger.debug(f"Reading draft_content.json from {draft_file}")
            file_size = os.path.getsize(draft_file)
            logger.debug(f"draft_content.json size: {file_size} bytes")
            
            with open(draft_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.debug(f"Successfully parsed JSON with {len(data)} top-level keys")
            logger.debug(f"Top-level keys: {list(data.keys())}")
            
            # Extract basic project info
            project_name = data.get('name', '')
            logger.debug(f"Project name from JSON: '{project_name}'")
            
            if not project_name:
                project_name = os.path.basename(project_path)
                logger.debug(f"Using directory name as project name: '{project_name}'")
            
            # Duration is in microseconds, convert to seconds
            duration_us = data.get('duration', 0)
            duration_seconds = duration_us / 1000000 if duration_us else 0
            logger.debug(f"Duration: {duration_us} microseconds -> {duration_seconds:.2f} seconds")
            
            create_time = data.get('create_time', 0)
            logger.debug(f"Create time: {create_time}")
            
            # Count media files
            media_count = self._count_media_files(data)
            logger.debug(f"Media count: {media_count}")
            
            # Get folder size
            try:
                folder_size_bytes = self._get_folder_size(project_path)
                folder_size_mb = folder_size_bytes / (1024 * 1024)
                logger.debug(f"Folder size: {folder_size_bytes} bytes -> {folder_size_mb:.2f} MB")
            except Exception as size_e:
                logger.warning(f"Error calculating folder size: {size_e}")
                folder_size_mb = 0
            
            result = {
                'path': project_path,
                'name': project_name,
                'duration': duration_seconds,
                'create_time': create_time,
                'media_count': media_count,
                'size_mb': folder_size_mb
            }
            
            logger.debug(f"Project info result: {result}")
            return result
            
        except json.JSONDecodeError as je:
            logger.error(f"JSON decode error in {draft_file}: {je}")
            logger.debug(f"First 200 characters of file: {open(draft_file, 'r', encoding='utf-8').read(200) if os.path.exists(draft_file) else 'File not found'}")
            return None
        except UnicodeDecodeError as ue:
            logger.error(f"Unicode decode error in {draft_file}: {ue}")
            logger.debug(f"Trying alternative encodings...")
            try:
                with open(draft_file, 'r', encoding='latin-1') as f:
                    data = json.load(f)
                logger.info("Successfully read file with latin-1 encoding")
                # Continue with processing...
            except Exception as alt_e:
                logger.error(f"Alternative encoding also failed: {alt_e}")
                return None
        except PermissionError as pe:
            logger.error(f"Permission denied accessing {draft_file}: {pe}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading project info from {project_path}: {e}")
            logger.debug(f"Exception details:", exc_info=True)
            return None
    
    def _count_media_files(self, data: Dict) -> int:
        """Count total media files in the project"""
        count = 0
        materials = data.get('materials', {})
        
        # Check both singular and plural forms for media types
        media_types = [
            'video', 'videos',      # Video files
            'audio', 'audios',      # Audio files  
            'image', 'images',      # Image files
            'sticker', 'stickers',  # Stickers
            'effect', 'effects',    # Effects
            'transition', 'transitions',  # Transitions
            'text', 'texts',        # Text elements
            'canvas', 'canvases',   # Canvas elements
        ]
        
        for media_type in media_types:
            items = materials.get(media_type, [])
            # Only count items that have actual file paths
            for item in items:
                if isinstance(item, dict) and item.get('path') and item.get('path').strip():
                    count += 1
        
        return count
    
    def _get_folder_size(self, path: str) -> int:
        """Get total size of a folder in bytes"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
        return total_size
    
    def extract_media_files(self, project_path: str, output_folder: str, progress_callback=None) -> Tuple[List[str], Dict]:
        """Extract and copy all media files to output folder"""
        logger.debug(f"=== Starting media extraction from: {project_path} ===")
        logger.debug(f"Output folder: {output_folder}")
        
        draft_file = os.path.join(project_path, 'draft_content.json')
        media_folder = output_folder  # Use output_folder directly as it's already the medias folder
        
        logger.debug(f"Draft file path: {draft_file}")
        logger.debug(f"Media folder path: {media_folder}")
        
        if not os.path.exists(draft_file):
            error_msg = f"draft_content.json not found in {project_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        # Create media folder
        try:
            os.makedirs(media_folder, exist_ok=True)
            logger.debug(f"Created media folder: {media_folder}")
        except Exception as e:
            logger.error(f"Failed to create media folder {media_folder}: {e}")
            raise
        
        # Load draft content
        try:
            logger.debug(f"Loading draft content from {draft_file}")
            with open(draft_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.debug(f"Successfully loaded draft content")
        except Exception as e:
            logger.error(f"Failed to load draft content: {e}")
            raise
        
        copied_files = []
        materials = data.get('materials', {})
        logger.debug(f"Materials section keys: {list(materials.keys())}")
        
        # Track already copied files to avoid duplicates
        copied_original_paths = {}  # Maps original path to new filename
        
        # Calculate total files and size for progress tracking
        total_files = 0
        total_size = 0
        existing_files = 0
        
        for media_type in ['video', 'videos', 'audio', 'audios', 'image', 'images', 'sticker', 'stickers', 'effect', 'effects', 'transition', 'transitions', 'text', 'texts', 'canvas', 'canvases']:
            items = materials.get(media_type, [])
            logger.debug(f"Media type {media_type}: {len(items)} items")
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get('path') and item.get('path').strip():
                        total_files += 1
                        original_path = item['path']
                        logger.debug(f"  File {total_files}: {original_path}")
                        if os.path.exists(original_path):
                            total_size += os.path.getsize(original_path)
                            existing_files += 1
                            logger.debug(f"    EXISTS: {self.format_file_size(os.path.getsize(original_path))}")
                        else:
                            logger.debug(f"    MISSING: File not found")
        
        logger.info(f"Progress tracking: {total_files} total files, {existing_files} existing files, {self.format_file_size(total_size)} total size")
        
        # Force minimum progress tracking even if no files exist
        if total_files == 0:
            logger.warning("No media files found for progress tracking, using fallback")
            total_files = 1  # Prevent division by zero
        
        # Process all media types (both singular and plural)
        media_types = [
            'video', 'videos',      # Video files
            'audio', 'audios',      # Audio files  
            'image', 'images',      # Image files
            'sticker', 'stickers',  # Stickers
            'effect', 'effects',    # Effects
            'transition', 'transitions',  # Transitions
            'text', 'texts',        # Text elements
            'canvas', 'canvases',   # Canvas elements
        ]
        
        for media_type in media_types:
            media_list = materials.get(media_type, [])
            logger.debug(f"Processing {media_type}: {len(media_list)} items")
            
            for i, media_item in enumerate(media_list):
                path_value      = media_item.get('path', '').strip()
                file_path_value = media_item.get('file_Path', '').strip()

                # Choisir le meilleur chemin source disponible
                if path_value and os.path.exists(path_value):
                    original_path = path_value
                elif file_path_value and os.path.exists(file_path_value):
                    original_path = file_path_value
                    logger.debug(f"  Item {i+1}: path absent/introuvable, utilisation de file_Path: {file_path_value}")
                elif path_value or file_path_value:
                    logger.warning(f"Media file not found (path={path_value!r}, file_Path={file_path_value!r})")
                    continue
                else:
                    logger.debug(f"  Skipping item {i+1}: no path or file_Path")
                    continue

                logger.debug(f"  Item {i+1}: {original_path}")
                
                # Check if this file was already copied
                if original_path in copied_original_paths:
                    # Use the already copied file instead of creating a duplicate
                    existing_filename = copied_original_paths[original_path]
                    media_item['path'] = f"./medias/{existing_filename}"
                    # CORRECTION : mettre à jour file_Path également si présent
                    if 'file_Path' in media_item and media_item['file_Path']:
                        media_item['file_Path'] = f"./medias/{existing_filename}"
                    logger.debug(f"  Using existing copy: {original_path} -> {existing_filename}")
                    continue
                
                # Use original filename to avoid issues during import
                filename = os.path.basename(original_path)
                new_path = os.path.join(media_folder, filename)
                
                logger.debug(f"  Copying {original_path} -> {new_path}")
                
                try:
                    # Get original file size for logging
                    original_size = os.path.getsize(original_path)
                    logger.debug(f"  Original file size: {original_size} bytes")
                    
                    # Copy file
                    shutil.copy2(original_path, new_path)
                    copied_files.append(filename)
                    
                    # Track this original path to avoid future duplicates
                    copied_original_paths[original_path] = filename
                    
                    # Verify copy was successful
                    if os.path.exists(new_path):
                        copied_size = os.path.getsize(new_path)
                        logger.debug(f"  Copied file size: {copied_size} bytes")
                        if copied_size == original_size:
                            logger.debug(f"  Copy verified successful")
                        else:
                            logger.warning(f"  Copy size mismatch: {original_size} -> {copied_size}")
                    
                    # CORRECTION : mettre à jour 'path' ET 'file_Path' pour éviter que
                    # CapCut utilise file_Path comme fallback vers le fichier original.
                    media_item['path']      = f"./medias/{filename}"
                    media_item['file_Path'] = f"./medias/{filename}"
                    logger.debug(f"  Updated path in JSON: {media_item['path']}")
                    
                    logger.info(f"Copied: {original_path} -> {filename}")
                    
                    # Update progress if callback provided
                    if progress_callback and total_files > 0:
                        current_progress = len(copied_files)
                        progress_percent = 10 + (current_progress / total_files) * 20  # 10-30% range for media extraction
                        logger.debug(f"Progress update: {current_progress}/{total_files} files = {progress_percent:.1f}%")
                        # CORRECTION : utiliser 'filename' (défini), pas 'new_filename' (non défini → NameError)
                        continue_processing = progress_callback(
                            progress=progress_percent,
                            message=f"Extraction médias: {current_progress}/{total_files} fichiers",
                            stage="media_extraction",
                            files_processed=current_progress,
                            total_files=total_files,
                            current_file=filename,
                            bytes_processed=original_size,
                            total_bytes=total_size
                        )
                        # Check if callback returned False (cancellation signal)
                        if continue_processing is False:
                            logger.info("Media extraction cancelled by user")
                            return copied_files, data
                    
                except PermissionError as pe:
                    logger.error(f"Permission denied copying {original_path}: {pe}")
                except FileNotFoundError:
                    logger.error(f"Source file not found during copy: {original_path}")
                except Exception as e:
                    logger.error(f"Error copying {original_path}: {e}")
                    logger.debug(f"Exception details:", exc_info=True)
        
        return copied_files, data
    
    def _extract_effect_files(self, project_path: str, medias_folder: str, progress_callback=None) -> Tuple[List[str], Dict]:
        """Extract and copy effect files and other local files to medias/other/"""
        logger.debug(f"=== Starting effect files extraction from: {project_path} ===")
        
        draft_file = os.path.join(project_path, 'draft_content.json')
        other_folder = os.path.join(medias_folder, 'other')
        
        # Create other folder for effects and other files
        os.makedirs(other_folder, exist_ok=True)
        logger.debug(f"Created other folder: {other_folder}")
        
        if not os.path.exists(draft_file):
            logger.error(f"draft_content.json not found: {draft_file}")
            return [], {}
        
        try:
            with open(draft_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load draft content: {e}")
            return [], {}
        
        copied_files = []
        copied_original_paths = {}  # Maps original path to new filename
        paths_updated = 0
        
        def find_and_copy_local_files(obj, path_context="root"):
            nonlocal paths_updated
            
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in ['path', 'file_Path'] and isinstance(value, str) and value.strip():
                        original_path = value
                        
                        # Skip if already relative or media file
                        if original_path.startswith('./') or original_path.startswith('medias/'):
                            continue
                        
                        # Check if it's a local file that exists
                        if os.path.exists(original_path):
                            # Skip if it's already in medias folder
                            if 'medias' in original_path.lower():
                                continue
                            
                            # Check if it's an effect file or necessary asset
                            filename = os.path.basename(original_path).lower()
                            
                            # Only copy effect files and necessary assets
                            is_effect_file = (
                                # Beat files
                                filename.endswith('.beat') or
                                # Effect directories (usually contain effect files)
                                any(keyword in original_path.lower() for keyword in ['effect', 'cache']) or
                                # Common effect file patterns
                                any(pattern in filename for pattern in ['effect_', 'filter_', 'transition_', 'sticker_']) or
                                # Files in CapCut cache directories (usually effects)
                                'cache' in original_path.lower() or
                                # Small files that are likely effects (less than 10MB)
                                (os.path.getsize(original_path) < 10 * 1024 * 1024 and not any(
                                    filename.endswith(ext) for ext in ['.mp4', '.mov', '.avi', '.mkv', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.mp3', '.wav', '.aac', '.ogg', '.flac', '.m4a']
                                ))
                            )
                            
                            if not is_effect_file:
                                logger.debug(f"Skipping non-effect file: {original_path}")
                                continue
                            
                            # Check if already copied
                            if original_path in copied_original_paths:
                                new_filename = copied_original_paths[original_path]
                                obj[key] = f"./medias/other/{new_filename}"
                                paths_updated += 1
                                logger.debug(f"Using existing copy: {original_path} -> ./medias/other/{new_filename}")
                                continue
                            
                            # Generate unique filename
                            filename = os.path.basename(original_path)
                            name, ext = os.path.splitext(filename)
                            
                            # Add prefix to avoid conflicts
                            counter = 1
                            new_filename = f"effect_{counter}_{filename}"
                            while os.path.exists(os.path.join(other_folder, new_filename)):
                                counter += 1
                                new_filename = f"effect_{counter}_{filename}"
                            
                            source_path = original_path
                            dest_path = os.path.join(other_folder, new_filename)
                            
                            try:
                                # Copy file
                                shutil.copy2(source_path, dest_path)
                                copied_files.append(new_filename)
                                copied_original_paths[original_path] = new_filename
                                
                                # Update path in JSON
                                obj[key] = f"./medias/other/{new_filename}"
                                paths_updated += 1
                                
                                logger.info(f"Copied effect: {original_path} -> ./medias/other/{new_filename}")
                                
                            except Exception as e:
                                logger.error(f"Failed to copy effect {original_path}: {e}")
                    else:
                        find_and_copy_local_files(value, f"{path_context}.{key}")
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    find_and_copy_local_files(item, f"{path_context}[{i}]")
        
        # Process the entire JSON structure
        find_and_copy_local_files(data)
        
        logger.info(f"Extracted {len(copied_files)} effect files to ./medias/other/, updated {paths_updated} paths")
        return copied_files, data
    
    def _extract_effect_files_from_data(self, data: Dict, medias_folder: str, progress_callback=None) -> Tuple[List[str], Dict]:
        """Extract and copy effect files and other local files to medias/other/ from existing JSON data"""
        logger.debug(f"=== Starting effect files extraction from JSON data ===")
        
        other_folder = os.path.join(medias_folder, 'other')
        
        # Create other folder for effects and other files
        os.makedirs(other_folder, exist_ok=True)
        logger.debug(f"Created other folder: {other_folder}")
        
        copied_files = []
        copied_original_paths = {}  # Maps original path to new filename
        paths_updated = 0
        
        def find_and_copy_local_files(obj, path_context="root"):
            nonlocal paths_updated
            
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in ['path', 'file_Path'] and isinstance(value, str) and value.strip():
                        original_path = value
                        
                        # Skip if already relative or media file
                        if original_path.startswith('./') or original_path.startswith('medias/'):
                            continue
                        
                        # Check if it's a local file or directory that exists
                        if os.path.exists(original_path):
                            # Skip if it's already in medias folder
                            if 'medias' in original_path.lower():
                                continue
                            
                            # Check if it's an effect file or necessary asset
                            filename = os.path.basename(original_path).lower()
                            
                            # Only copy effect files and necessary assets
                            is_effect_file = (
                                # Beat files
                                filename.endswith('.beat') or
                                # Effect directories (usually contain effect files)
                                any(keyword in original_path.lower() for keyword in ['effect', 'cache']) or
                                # Common effect file patterns
                                any(pattern in filename for pattern in ['effect_', 'filter_', 'transition_', 'sticker_']) or
                                # Files in CapCut cache directories (usually effects)
                                'cache' in original_path.lower() or
                                # Small files that are likely effects (less than 10MB)
                                (os.path.isfile(original_path) and os.path.getsize(original_path) < 10 * 1024 * 1024 and not any(
                                    filename.endswith(ext) for ext in ['.mp4', '.mov', '.avi', '.mkv', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.mp3', '.wav', '.aac', '.ogg', '.flac', '.m4a']
                                ))
                            )
                            
                            if not is_effect_file:
                                logger.debug(f"Skipping non-effect file: {original_path}")
                                continue
                            
                            # Check if already copied
                            if original_path in copied_original_paths:
                                new_filename = copied_original_paths[original_path]
                                obj[key] = f"./medias/other/{new_filename}"
                                paths_updated += 1
                                logger.debug(f"Using existing copy: {original_path} -> ./medias/other/{new_filename}")
                                continue
                            
                            # Generate unique filename
                            filename = os.path.basename(original_path)
                            name, ext = os.path.splitext(filename)
                            
                            # Add prefix to avoid conflicts
                            counter = 1
                            new_filename = f"effect_{counter}_{filename if ext else filename + '_dir'}"
                            while os.path.exists(os.path.join(other_folder, new_filename)):
                                counter += 1
                                new_filename = f"effect_{counter}_{filename if ext else filename + '_dir'}"
                            
                            source_path = original_path
                            dest_path = os.path.join(other_folder, new_filename)
                            
                            try:
                                if os.path.isfile(original_path):
                                    # Copy file
                                    shutil.copy2(source_path, dest_path)
                                    copied_files.append(new_filename)
                                    copied_original_paths[original_path] = new_filename
                                    logger.info(f"Copied effect file: {original_path} -> ./medias/other/{new_filename}")
                                elif os.path.isdir(original_path):
                                    # Copy entire directory
                                    shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
                                    copied_files.append(new_filename)
                                    copied_original_paths[original_path] = new_filename
                                    logger.info(f"Copied effect directory: {original_path} -> ./medias/other/{new_filename}")
                                
                                # Update path in JSON
                                obj[key] = f"./medias/other/{new_filename}"
                                paths_updated += 1
                                
                            except Exception as e:
                                logger.error(f"Failed to copy effect {original_path}: {e}")
                    else:
                        find_and_copy_local_files(value, f"{path_context}.{key}")
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    find_and_copy_local_files(item, f"{path_context}[{i}]")
        
        # Process the entire JSON structure
        find_and_copy_local_files(data)
        
        logger.info(f"Extracted {len(copied_files)} effect files to ./medias/other/, updated {paths_updated} paths")
        return copied_files, data
    


    def _make_all_paths_relative(self, data: Dict, medias_folder: str) -> Dict:
        """
        Parcourt RÉCURSIVEMENT tout le JSON et remplace TOUS les chemins absolus
        par des chemins relatifs ./medias/... si le fichier existe dans medias_folder.

        Pour les chemins non résolus par nom, tente une correspondance par contenu
        (taille puis hash MD5) afin de retrouver les copies renommées.
        """
        remaining_absolute = []

        # ── Cache des fichiers présents dans medias/ et medias/other/ ────────────
        # Construit une fois, réutilisé pour chaque chemin non résolu.
        # Structure : { chemin_absolu_fichier: chemin_relatif_./medias/... }
        _media_index: dict[str, str] = {}
        for root, _, files in os.walk(medias_folder):
            for fname in files:
                full = os.path.join(root, fname)
                # Chemin relatif ./medias/... ou ./medias/other/...
                rel = './' + os.path.relpath(full, os.path.dirname(medias_folder)).replace('\\', '/')
                _media_index[full] = rel

        # ── Index par taille : { taille_octets: [chemins_absolus_dans_medias] } ──
        _size_index: dict[int, list[str]] = {}
        for full_path in _media_index:
            try:
                sz = os.path.getsize(full_path)
                _size_index.setdefault(sz, []).append(full_path)
            except OSError:
                pass

        def _md5(path: str) -> str | None:
            """Calcule le MD5 d'un fichier, retourne None si inaccessible."""
            try:
                h = hashlib.md5()
                with open(path, 'rb') as fh:
                    for chunk in iter(lambda: fh.read(65536), b''):
                        h.update(chunk)
                return h.hexdigest()
            except OSError:
                return None

        def _find_equivalent_in_medias(original_path: str) -> str | None:
            """
            Cherche dans medias_folder un fichier au contenu identique à original_path.
            Stratégie :
            1. Correspondance exacte par nom de fichier (déjà tentée avant d'appeler cette fn)
            2. Correspondance par taille → si unique : retourner directement
            3. Si plusieurs candidats de même taille : affiner par hash MD5
            Retourne le chemin relatif ./medias/... ou None si aucun équivalent trouvé.
            """
            if not os.path.isfile(original_path):
                return None  # Fichier source inaccessible, impossible de comparer

            try:
                orig_size = os.path.getsize(original_path)
            except OSError:
                return None

            candidates = _size_index.get(orig_size, [])

            if not candidates:
                return None  # Aucun fichier de même taille dans medias/

            if len(candidates) == 1:
                # Un seul candidat de même taille → très probable que ce soit le même
                logger.debug(
                    f"[_make_all_paths_relative] Correspondance par taille : "
                    f"{original_path} → {_media_index[candidates[0]]}"
                )
                return _media_index[candidates[0]]

            # Plusieurs candidats → départager par hash MD5
            orig_hash = _md5(original_path)
            if orig_hash is None:
                return None  # Impossible de lire l'original

            for candidate in candidates:
                if _md5(candidate) == orig_hash:
                    logger.debug(
                        f"[_make_all_paths_relative] Correspondance par hash MD5 : "
                        f"{original_path} → {_media_index[candidate]}"
                    )
                    return _media_index[candidate]

            return None  # Même taille mais contenu différent (collision improbable mais gérée)

        # ── Parcours récursif du JSON ─────────────────────────────────────────────
        def walk(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in ['path', 'file_Path'] and isinstance(value, str) and value.strip():
                        if value.startswith('./'):
                            continue  # Déjà relatif, rien à faire

                        filename = os.path.basename(value)

                        # 1. Correspondance exacte par nom dans medias/
                        media_path = os.path.join(medias_folder, filename)
                        if os.path.exists(media_path):
                            obj[key] = f"./medias/{filename}"
                            logger.debug(f"Made relative (nom exact): {value} -> ./medias/{filename}")
                            continue

                        # 2. Correspondance exacte par nom dans medias/other/
                        other_path = os.path.join(medias_folder, 'other', filename)
                        if os.path.exists(other_path):
                            obj[key] = f"./medias/other/{filename}"
                            logger.debug(f"Made relative (nom exact other): {value} -> ./medias/other/{filename}")
                            continue

                        # 3. Correspondance par contenu (copies renommées)
                        if len(value) > 1 and value[1] == ':':  # Chemin absolu Windows accessible
                            equiv = _find_equivalent_in_medias(value)
                            if equiv is not None:
                                obj[key] = equiv
                                logger.info(
                                    f"[_make_all_paths_relative] Équivalent trouvé par contenu : "
                                    f"{value!r} → {equiv!r}"
                                )
                                continue

                        # 4. Aucun équivalent trouvé : forcer quand même un chemin portable
                        #    pour éviter que CapCut utilise silencieusement le fichier original.
                        if len(value) > 1 and value[1] == ':':
                            fallback = f"./medias/{filename}"
                            remaining_absolute.append(f"{key}: {value} (→ fallback {fallback})")
                            logger.warning(
                                f"[_make_all_paths_relative] Aucun équivalent dans le paquet — "
                                f"chemin forcé vers portable (fichier sera manquant à l'import) : "
                                f"{key}: {value!r} → {fallback!r}"
                            )
                            obj[key] = fallback  # ← on écrase quand même, jamais de chemin original dans le ZIP
                    else:
                        walk(value)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(data)

        if remaining_absolute:
            logger.warning(
                f"{len(remaining_absolute)} chemin(s) sans équivalent dans le paquet portable. "
                f"Ces médias seront signalés comme manquants par CapCut à l'ouverture."
            )
        else:
            logger.info("Tous les chemins absolus ont été résolus (par nom ou par contenu).")

        return data

    def _process_meta_info_for_export(self, meta_info_path: str, project_folder: str, medias_folder: str):
        """Process draft_meta_info.json to update file paths for export"""
        logger.debug(f"Processing meta info for export: {meta_info_path}")
        
        try:
            with open(meta_info_path, 'r', encoding='utf-8') as f:
                meta_data = json.load(f)
            
            # Utiliser la même logique que _extract_effect_files pour traiter les chemins absolus
            other_folder = os.path.join(medias_folder, 'other')
            os.makedirs(other_folder, exist_ok=True)
            
            copied_original_paths = {}
            paths_updated = 0
            
            def find_and_copy_local_files(obj, path_context="root"):
                nonlocal paths_updated
                
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if key in ['path', 'file_Path'] and isinstance(value, str) and value.strip():
                            original_path = value
                            
                            # Skip if already relative
                            if original_path.startswith('./'):
                                continue
                            
                            # Check if it's a local file that exists
                            if os.path.exists(original_path):
                                # Skip if it's already in medias folder
                                if 'medias' in original_path.lower():
                                    continue
                                
                                # Check if it's an effect file or necessary asset
                                filename = os.path.basename(original_path).lower()
                                
                                # Only copy effect files and necessary assets
                                is_effect_file = (
                                    # Beat files
                                    filename.endswith('.beat') or
                                    # Effect directories (usually contain effect files)
                                    any(keyword in original_path.lower() for keyword in ['effect', 'cache']) or
                                    # Common effect file patterns
                                    any(pattern in filename for pattern in ['effect_', 'filter_', 'transition_', 'sticker_']) or
                                    # Files in CapCut cache directories (usually effects)
                                    'cache' in original_path.lower() or
                                    # Small files that are likely effects (less than 10MB)
                                    (os.path.isfile(original_path) and os.path.getsize(original_path) < 10 * 1024 * 1024 and not any(
                                        filename.endswith(ext) for ext in ['.mp4', '.mov', '.avi', '.mkv', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.mp3', '.wav', '.aac', '.ogg', '.flac', '.m4a']
                                    ))
                                )
                                
                                if not is_effect_file:
                                    logger.debug(f"Skipping non-effect file in meta: {original_path}")
                                    continue
                                
                                # Check if already copied
                                if original_path in copied_original_paths:
                                    new_filename = copied_original_paths[original_path]
                                    obj[key] = f"./medias/other/{new_filename}"
                                    paths_updated += 1
                                    logger.debug(f"Using existing copy: {original_path} -> ./medias/other/{new_filename}")
                                    continue
                                
                                # Generate unique filename
                                filename = os.path.basename(original_path)
                                name, ext = os.path.splitext(filename)
                                
                                # Add prefix to avoid conflicts
                                counter = 1
                                new_filename = f"meta_{counter}_{filename}"
                                while os.path.exists(os.path.join(other_folder, new_filename)):
                                    counter += 1
                                    new_filename = f"meta_{counter}_{filename}"
                                
                                source_path = original_path
                                dest_path = os.path.join(other_folder, new_filename)
                                
                                try:
                                    # Copy file
                                    shutil.copy2(source_path, dest_path)
                                    copied_original_paths[original_path] = new_filename
                                    
                                    # Update path in JSON
                                    obj[key] = f"./medias/other/{new_filename}"
                                    paths_updated += 1
                                    
                                    logger.info(f"Copied meta file: {original_path} -> ./medias/other/{new_filename}")
                                    
                                except Exception as e:
                                    logger.error(f"Failed to copy meta file {original_path}: {e}")
                        else:
                            find_and_copy_local_files(value, f"{path_context}.{key}")
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        find_and_copy_local_files(item, f"{path_context}[{i}]")
            
            # Process the entire JSON structure
            find_and_copy_local_files(meta_data)
            
            # Save processed meta info file
            output_meta_path = os.path.join(project_folder, 'draft_meta_info.json')
            with open(output_meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, ensure_ascii=False)
            
            logger.info(f"Processed and saved meta info file: {output_meta_path}, updated {paths_updated} paths")
        
        except Exception as e:
            logger.error(f"Error processing meta info file for export: {e}")
            raise
    
    def make_project_portable(self, project_path: str, output_folder: str, progress_callback=None) -> bool:
        """Make a CapCut project portable with project/ and medias/ folders"""
        logger.debug(f"=== Starting portable project creation ===")
        logger.debug(f"Source: {project_path}")
        logger.debug(f"Output: {output_folder}")
        
        try:
            logger.info(f"Making project portable: {project_path}")
            
            # Create output folder
            try:
                os.makedirs(output_folder, exist_ok=True)
                logger.debug(f"Created output folder: {output_folder}")
            except Exception as e:
                logger.error(f"Failed to create output folder {output_folder}: {e}")
                return False
            
            # Create subdirectories for new structure
            project_folder = os.path.join(output_folder, 'project')
            medias_folder = os.path.join(output_folder, 'medias')
            
            try:
                os.makedirs(project_folder, exist_ok=True)
                os.makedirs(medias_folder, exist_ok=True)
                logger.debug(f"Created subdirectories: project/ and medias/")
            except Exception as e:
                logger.error(f"Failed to create subdirectories: {e}")
                return False
            
            # Extract media files and get updated JSON data
            logger.debug("Starting media file extraction...")
            copied_files, updated_data = self.extract_media_files(project_path, medias_folder, progress_callback)
            logger.info(f"Extracted {len(copied_files)} media files")
            
            # Extract effect files and other local files from the already updated data
            logger.debug("Starting effect files extraction...")
            effect_files, updated_data = self._extract_effect_files_from_data(updated_data, medias_folder, progress_callback)
            logger.info(f"Extracted {len(effect_files)} effect files")
            
            # Make all paths relative (final cleanup pass)
            updated_data = self._make_all_paths_relative(updated_data, medias_folder)
            
            # Save updated draft_content.json in project folder
            output_draft = os.path.join(project_folder, 'draft_content.json')
            logger.debug(f"Saving updated draft to: {output_draft}")
            
            try:
                with open(output_draft, 'w', encoding='utf-8') as f:
                    json.dump(updated_data, f, indent=2, ensure_ascii=False)
                
                # Verify file was saved correctly
                if os.path.exists(output_draft):
                    saved_size = os.path.getsize(output_draft)
                    logger.debug(f"Saved draft_content.json: {saved_size} bytes")
                    
                    # Update progress for JSON saving completion
                    if progress_callback:
                        logger.debug("Progress update: JSON saved, moving to 25%")
                        progress_callback(
                            progress=25,
                            message="Fichier de projet sauvegardé",
                            stage="json_saved",
                            files_processed=len(copied_files),
                            total_files=len(copied_files),
                            current_file="draft_content.json",
                            bytes_processed=saved_size,
                            total_bytes=saved_size
                        )
                    
            except Exception as save_e:
                logger.error(f"Failed to save updated draft_content.json: {save_e}")
                return False
            
            # Process and copy draft_meta_info.json with path updates
            logger.debug("Processing draft_meta_info.json...")
            meta_info_path = os.path.join(project_path, 'draft_meta_info.json')
            if os.path.exists(meta_info_path):
                self._process_meta_info_for_export(meta_info_path, project_folder, medias_folder)
                
                # Also apply _make_all_paths_relative to ensure all paths are relative
                output_meta_path = os.path.join(project_folder, 'draft_meta_info.json')
                with open(output_meta_path, 'r', encoding='utf-8') as f:
                    meta_data = json.load(f)
                meta_data = self._make_all_paths_relative(meta_data, medias_folder)
                with open(output_meta_path, 'w', encoding='utf-8') as f:
                    json.dump(meta_data, f, indent=2, ensure_ascii=False)
                
                logger.info("Processed draft_meta_info.json with path updates")
            
            # Copy all other project files and folders
            logger.debug("Starting to copy all project files...")
            additional_files_copied = self.copy_all_project_files(project_path, project_folder, progress_callback, len(copied_files))
            logger.info(f"Copied {additional_files_copied} additional project files")

            # Final pass: make every JSON path inside the exported project portable
            rewritten_json_files = self._rewrite_exported_project_jsons(project_folder, medias_folder)
            logger.info(f"Rewritten portable paths in {rewritten_json_files} JSON file(s)")
            
            # Create export_info.json
            export_info_path = os.path.join(output_folder, 'export_info.json')
            project_name = os.path.basename(project_path)
            export_info = {
                "project_name": project_name,
                "version": 1,
                "portable": True
            }
            
            try:
                with open(export_info_path, 'w', encoding='utf-8') as f:
                    json.dump(export_info, f, indent=2, ensure_ascii=False)
                logger.info(f"Created export_info.json for project: {project_name}")
            except Exception as e:
                logger.error(f"Failed to create export_info.json: {e}")
            
            # Verify the output structure
            logger.debug("Verifying output structure...")
            media_folder = os.path.join(output_folder, 'medias')
            project_folder_check = os.path.join(output_folder, 'project')
            export_info_exists = os.path.exists(os.path.join(output_folder, 'export_info.json'))
            
            media_files_exist = os.path.exists(media_folder) and len(os.listdir(media_folder)) > 0
            draft_exists = os.path.exists(output_draft)
            project_folder_exists = os.path.exists(project_folder_check)
            
            logger.debug(f"Media folder exists and has files: {media_files_exist}")
            logger.debug(f"Project folder exists: {project_folder_exists}")
            logger.debug(f"Draft file exists: {draft_exists}")
            logger.debug(f"Export info exists: {export_info_exists}")
            
            if media_files_exist and draft_exists and project_folder_exists and export_info_exists:
                logger.info(f"Project exported successfully to {output_folder}")
                logger.info(f"Copied {len(copied_files)} media files")
                return True
            else:
                logger.error("Export verification failed - incomplete output structure")
                return False
            
        except Exception as e:
            logger.error(f"Error making project portable: {e}")
            logger.debug("Exception details:", exc_info=True)
            return False
    
    def create_zip_archive(self, project_folder: str, zip_path: str, progress_callback=None) -> bool:
        """Create a ZIP archive of the portable project with real-time progress tracking"""
        logger.debug(f"=== Starting ZIP creation ===")
        
        try:
            file_count = 0
            total_size = 0
            file_sizes = []
            
            # Get the project and medias subdirectories
            project_subdir = os.path.join(project_folder, 'project')
            medias_subdir = os.path.join(project_folder, 'medias')
            
            # Count files in both subdirectories
            for subdir in [project_subdir, medias_subdir]:
                if os.path.exists(subdir):
                    for root, dirs, files in os.walk(subdir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            if os.path.exists(file_path):
                                file_size = os.path.getsize(file_path)
                                file_sizes.append(file_size)
                                total_size += file_size
                                file_count += 1
            
            # Also include export_info.json if it exists
            export_info_file = os.path.join(project_folder, 'export_info.json')
            if os.path.exists(export_info_file):
                file_size = os.path.getsize(export_info_file)
                total_size += file_size
                file_count += 1
            
            logger.debug(f"Found {file_count} files to compress ({self.format_file_size(total_size)})")
            
            # Estimate ZIP size (typically 60-80% of original size depending on content)
            estimated_zip_size = int(total_size * 0.7)  # Conservative estimate
            logger.info(f"Estimated ZIP size: {self.format_file_size(estimated_zip_size)}")
            
            # Create ZIP with real-time progress
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
                files_processed = 0
                bytes_processed = 0
                
                # Add project/ directory contents (preserving project/ prefix)
                if os.path.exists(project_subdir):
                    for root, dirs, files in os.walk(project_subdir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            # Create relative path with project/ prefix
                            arcname = os.path.relpath(file_path, project_subdir)
                            arcname = os.path.join('project', arcname)
                            
                            try:
                                # Get file size before compression
                                file_size = os.path.getsize(file_path)
                                
                                # Add file to ZIP
                                zipf.write(file_path, arcname)
                                
                                files_processed += 1
                                bytes_processed += file_size
                                
                                # Calculate progress (60% for file processing, 40% for compression)
                                file_progress = (files_processed / file_count) * 60
                                
                                # Update progress every 5 files or for the last file
                                if files_processed % 5 == 0 or files_processed == file_count:
                                    progress = file_progress
                                    current_file = os.path.basename(file_path)
                                    
                                    # Log detailed progress
                                    logger.debug(f"Zipped {files_processed}/{file_count} files ({self.format_file_size(bytes_processed)}/{self.format_file_size(total_size)})")
                                    
                                    # Call progress callback if provided
                                    if progress_callback:
                                        continue_processing = progress_callback(
                                            progress=progress,
                                            message=f"Compression ZIP: {files_processed}/{file_count} fichiers",
                                            stage="zip_creation",
                                            files_processed=files_processed,
                                            total_files=file_count,
                                            current_file=current_file,
                                            bytes_processed=bytes_processed,
                                            total_bytes=total_size
                                        )
                                        # Check if callback returned False (cancellation signal)
                                        if continue_processing is False:
                                            logger.info("ZIP creation cancelled by user")
                                            return False
                                
                            except Exception as file_e:
                                logger.warning(f"Failed to add {file_path} to ZIP: {file_e}")
                
                # Add medias/ directory contents (preserving medias/ prefix)
                if os.path.exists(medias_subdir):
                    for root, dirs, files in os.walk(medias_subdir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            # Create relative path with medias/ prefix
                            arcname = os.path.relpath(file_path, medias_subdir)
                            arcname = os.path.join('medias', arcname)
                            
                            try:
                                # Get file size before compression
                                file_size = os.path.getsize(file_path)
                                
                                # Add file to ZIP
                                zipf.write(file_path, arcname)
                                
                                files_processed += 1
                                bytes_processed += file_size
                                
                                # Calculate progress (60% for file processing, 40% for compression)
                                file_progress = (files_processed / file_count) * 60
                                
                                # Update progress every 5 files or for the last file
                                if files_processed % 5 == 0 or files_processed == file_count:
                                    progress = file_progress
                                    current_file = os.path.basename(file_path)
                                    
                                    # Log detailed progress
                                    logger.debug(f"Zipped {files_processed}/{file_count} files ({self.format_file_size(bytes_processed)}/{self.format_file_size(total_size)})")
                                    
                                    # Call progress callback if provided
                                    if progress_callback:
                                        continue_processing = progress_callback(
                                            progress=progress,
                                            message=f"Compression ZIP: {files_processed}/{file_count} fichiers",
                                            stage="zip_creation",
                                            files_processed=files_processed,
                                            total_files=file_count,
                                            current_file=current_file,
                                            bytes_processed=bytes_processed,
                                            total_bytes=total_size
                                        )
                                        # Check if callback returned False (cancellation signal)
                                        if continue_processing is False:
                                            logger.info("ZIP creation cancelled by user")
                                            return False
                                
                            except Exception as file_e:
                                logger.warning(f"Failed to add {file_path} to ZIP: {file_e}")
                
                # Add export_info.json if it exists
                if os.path.exists(export_info_file):
                    try:
                        file_size = os.path.getsize(export_info_file)
                        zipf.write(export_info_file, 'export_info.json')
                        
                        files_processed += 1
                        bytes_processed += file_size
                        
                        logger.debug(f"Added export_info.json to ZIP")
                        
                    except Exception as file_e:
                        logger.warning(f"Failed to add export_info.json to ZIP: {file_e}")
            
            # Final compression stage (remaining 40%)
            if progress_callback:
                progress_callback(
                    progress=90,
                    message="Finalisation de l'archive ZIP...",
                    stage="zip_finalization",
                    files_processed=file_count,
                    total_files=file_count,
                    current_file="",
                    bytes_processed=total_size,
                    total_bytes=total_size
                )
            
            # Verify ZIP was created successfully
            if os.path.exists(zip_path):
                zip_size = os.path.getsize(zip_path)
                compression_ratio = (1 - zip_size/total_size) * 100 if total_size > 0 else 0
                
                logger.debug(f"Final ZIP file size: {self.format_file_size(zip_size)}")
                logger.info(f"ZIP archive created: {zip_path}")
                logger.info(f"Compressed {self.format_file_size(total_size)} to {self.format_file_size(zip_size)} ({compression_ratio:.1f}% compression)")
                
                # Final progress update
                if progress_callback:
                    progress_callback(
                        progress=100,
                        message=f"ZIP terminé: {self.format_file_size(zip_size)}",
                        stage="zip_complete",
                        files_processed=file_count,
                        total_files=file_count,
                        current_file="",
                        bytes_processed=total_size,
                        total_bytes=total_size
                    )
                
                return True
            else:
                logger.error("ZIP file was not created")
                return False
            
        except PermissionError as pe:
            logger.error(f"Permission denied creating ZIP {zip_path}: {pe}")
            return False
        except zipfile.BadZipFile as bze:
            logger.error(f"Bad ZIP file error: {bze}")
            return False
        except Exception as e:
            logger.error(f"Error creating ZIP archive: {e}")
            logger.debug("Exception details:", exc_info=True)
            return False
    
    def copy_all_project_files(self, project_path: str, output_folder: str, progress_callback=None, media_files_count: int = 0) -> int:
        """Copy all project files and folders except media files and draft_content.json (already handled)"""
        logger.debug(f"=== Copying all project files from {project_path} to {output_folder} ===")
        
        files_copied = 0
        total_size = 0
        
        # Files to skip (already handled or not needed)
        skip_files = {
            'draft_content.json',  # Already handled with media path updates
            'draft_content.json.bak',  # Backup file, not needed
            'draft_meta_info.json',  # Will be handled separately with path updates
        }
        
        # Folders to skip (already handled or not needed)
        skip_folders = {
            'medias',  # Will be created separately
        }
        
        try:
            # Get all items in project folder
            items = os.listdir(project_path)
            logger.debug(f"Found {len(items)} items in project folder")
            
            # Count total files for progress tracking
            total_files_to_copy = 0
            for item in items:
                item_path = os.path.join(project_path, item)
                if os.path.isfile(item_path) and item not in skip_files:
                    total_files_to_copy += 1
                elif os.path.isdir(item_path) and item not in skip_folders:
                    # Count files in subdirectory
                    for root, dirs, files in os.walk(item_path):
                        total_files_to_copy += len(files)
            
            logger.debug(f"Will copy {total_files_to_copy} additional files")
            
            # Copy each item
            for item in items:
                source_path = os.path.join(project_path, item)
                dest_path = os.path.join(output_folder, item)
                
                # Skip files and folders that should be ignored
                if item in skip_files or item in skip_folders:
                    logger.debug(f"Skipping: {item}")
                    continue
                
                try:
                    if os.path.isfile(source_path):
                        # Copy file
                        file_size = os.path.getsize(source_path)
                        total_size += file_size
                        
                        logger.debug(f"Copying file: {item} ({self.format_file_size(file_size)})")
                        shutil.copy2(source_path, dest_path)
                        files_copied += 1
                        
                        # Update progress
                        if progress_callback and total_files_to_copy > 0:
                            progress = 25 + (files_copied / total_files_to_copy) * 5  # 25-30% range for additional files
                            continue_processing = progress_callback(
                                progress=progress,
                                message=f"Copie des fichiers projet: {files_copied}/{total_files_to_copy}",
                                stage="copying_project_files",
                                files_processed=media_files_count + files_copied,
                                total_files=media_files_count + total_files_to_copy,
                                current_file=item,
                                bytes_processed=file_size,
                                total_bytes=total_size
                            )
                            # Check if callback returned False (cancellation signal)
                            if continue_processing is False:
                                logger.info("Project files copying cancelled by user")
                                return files_copied
                        
                    elif os.path.isdir(source_path):
                        # Copy directory recursively
                        logger.debug(f"Copying directory: {item}")
                        shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
                        
                        # Count files copied in this directory
                        dir_files_count = 0
                        for root, dirs, files in os.walk(source_path):
                            dir_files_count += len(files)
                        
                        files_copied += dir_files_count
                        logger.debug(f"Copied {dir_files_count} files from directory {item}")
                        
                        # Update progress
                        if progress_callback and total_files_to_copy > 0:
                            progress = 25 + (files_copied / total_files_to_copy) * 5  # 25-30% range for additional files
                            progress_callback(
                                progress=progress,
                                message=f"Copie des fichiers projet: {files_copied}/{total_files_to_copy}",
                                stage="copying_project_files",
                                files_processed=media_files_count + files_copied,
                                total_files=media_files_count + total_files_to_copy,
                                current_file=f"{item}/ ({dir_files_count} fichiers)",
                                bytes_processed=0,
                                total_bytes=total_size
                            )
                    
                except Exception as copy_e:
                    logger.error(f"Error copying {item}: {copy_e}")
                    # Continue with other files even if one fails
            
            logger.info(f"Successfully copied {files_copied} additional project files ({self.format_file_size(total_size)})")
            return files_copied
            
        except Exception as e:
            logger.error(f"Error copying project files: {e}")
            logger.debug("Exception details:", exc_info=True)
            return 0
    
    def format_file_size(self, size_bytes: int) -> str:
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        size = float(size_bytes)
        
        while size >= 1024.0 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1
        
        return f"{size:.1f} {size_names[i]}"
    
    def load_params(self):
        """Load parameters from params.json file"""
        params_file = os.path.join(os.path.dirname(__file__), 'params.json')
        try:
            if os.path.exists(params_file):
                with open(params_file, 'r', encoding='utf-8') as f:
                    params = json.load(f)
                logger.info(f"Parameters loaded from {params_file}")
                return params
            else:
                logger.info("params.json not found, using default parameters")
                return self.get_default_params()
        except Exception as e:
            logger.error(f"Error loading parameters: {e}")
            return self.get_default_params()
    
    def save_params(self, params):
        """Save parameters to params.json file"""
        params_file = os.path.join(os.path.dirname(__file__), 'params.json')
        try:
            with open(params_file, 'w', encoding='utf-8') as f:
                json.dump(params, f, indent=2, ensure_ascii=False)
            logger.info(f"Parameters saved to {params_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving parameters: {e}")
            return False
    
    def get_default_params(self):
        """Get default parameters"""
        return {
            "language": "fr",
            "theme": "dark",
            "default_save_path": "",
            "capcut_draft_path": "",
            "capcut_exe_path": "",
            "compression_format": "zip",
            "compression_level": "normal",
            "auto_cleanup": False,
            "include_templates": False,
            "process_timeout": 300,
            "max_file_size": 1024,
            "debug_mode": False,
            "auto_detect": True
        }

if __name__ == "__main__":
    # Test the exporter
    exporter = CapCutExporter()
    projects = exporter.find_capcut_projects()
    
    for project in projects:
        info = exporter.get_project_info(project)
        if info:
            print(f"Project: {info['name']}")
            print(f"Path: {info['path']}")
            print(f"Media files: {info['media_count']}")
            print(f"Size: {info['size_mb']:.2f} MB")
            print("-" * 50)

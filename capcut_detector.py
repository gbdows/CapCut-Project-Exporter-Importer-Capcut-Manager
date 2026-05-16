#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CapCut Draft Folder Detector
Automatically detects and validates CapCut draft folder location
"""

import os
import json
from pathlib import Path
import logging

# Setup logging
logger = logging.getLogger(__name__)

class CapCutDetector:
    """Handles automatic detection and validation of CapCut draft folders"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
    
    def detect_capcut_draft_folder(self) -> dict:
        """
        Automatically detect CapCut draft folder
        
        Returns:
            dict: {
                'found': bool,
                'path': str,
                'username': str,
                'error': str,
                'needs_manual_selection': bool
            }
        """
        result = {
            'found': False,
            'path': '',
            'username': '',
            'error': '',
            'needs_manual_selection': False
        }
        
        try:
            # Get username using multiple methods
            username = self._get_username()
            result['username'] = username
            
            if not username:
                result['error'] = 'Impossible de détecter le nom d\'utilisateur'
                result['needs_manual_selection'] = True
                return result
            
            # Construct expected CapCut draft path
            expected_path = self._construct_capcut_path(username)
            logger.info(f"Testing CapCut draft path: {expected_path}")
            
            # Validate the path
            validation_result = self._validate_capcut_path(expected_path)
            
            if validation_result['valid']:
                result['found'] = True
                result['path'] = expected_path
                logger.info(f"CapCut draft folder found: {expected_path}")
                
                # Auto-save to params.json if config manager available
                if self.config_manager:
                    self._save_to_config(expected_path)
                
            else:
                result['error'] = validation_result['error']
                result['needs_manual_selection'] = True
                logger.warning(f"CapCut draft folder not found: {validation_result['error']}")
        
        except Exception as e:
            logger.error(f"Error detecting CapCut draft folder: {e}")
            result['error'] = f'Erreur lors de la détection: {str(e)}'
            result['needs_manual_selection'] = True
        
        return result
    
    def _get_username(self) -> str:
        """Get current username using multiple methods"""
        username = ''
        
        try:
            # Method 1: os.getlogin()
            username = os.getlogin()
            logger.debug(f"Username from os.getlogin(): {username}")
        except (OSError, Exception) as e:
            logger.debug(f"os.getlogin() failed: {e}")
        
        if not username:
            try:
                # Method 2: Path.home()
                username = Path.home().name
                logger.debug(f"Username from Path.home(): {username}")
            except Exception as e:
                logger.debug(f"Path.home() failed: {e}")
        
        if not username:
            try:
                # Method 3: Environment variables
                username = os.environ.get('USERNAME') or os.environ.get('USER')
                logger.debug(f"Username from environment: {username}")
            except Exception as e:
                logger.debug(f"Environment variables failed: {e}")
        
        return username
    
    def _construct_capcut_path(self, username: str) -> str:
        """Construct the expected CapCut draft path"""
        return f"C:\\Users\\{username}\\AppData\\Local\\CapCut\\User Data\\Projects\\com.lveditor.draft"
    
    def _validate_capcut_path(self, path: str) -> dict:
        """
        Validate CapCut draft folder
        
        Returns:
            dict: {
                'valid': bool,
                'error': str,
                'has_projects': bool,
                'permissions_ok': bool
            }
        """
        result = {
            'valid': False,
            'error': '',
            'has_projects': False,
            'permissions_ok': False
        }
        
        # Check if folder exists
        if not os.path.exists(path):
            result['error'] = f'Le dossier n\'existe pas: {path}'
            return result
        
        # Check if it's a directory
        if not os.path.isdir(path):
            result['error'] = f'Le chemin n\'est pas un dossier: {path}'
            return result
        
        # Check read permissions
        if not os.access(path, os.R_OK):
            result['error'] = f'Pas de permission de lecture: {path}'
            return result
        
        # Check write permissions
        if not os.access(path, os.W_OK):
            result['error'] = f'Pas de permission d\'écriture: {path}'
            return result
        
        result['permissions_ok'] = True
        
        # Check if it contains CapCut projects
        try:
            items = os.listdir(path)
            has_draft_content = any(
                os.path.exists(os.path.join(path, item, 'draft_content.json'))
                for item in items if os.path.isdir(os.path.join(path, item))
            )
            result['has_projects'] = has_draft_content
            
            if not has_draft_content:
                result['error'] = 'Le dossier existe mais ne contient aucun projet CapCut valide'
                return result
        
        except PermissionError:
            result['error'] = 'Permission refusée lors de la lecture du dossier'
            return result
        except Exception as e:
            result['error'] = f'Erreur lors de la lecture du dossier: {str(e)}'
            return result
        
        result['valid'] = True
        return result
    
    def validate_manual_selection(self, selected_path: str) -> dict:
        """
        Validate manually selected CapCut draft folder
        
        Returns:
            dict: {
                'valid': bool,
                'error': str,
                'path': str
            }
        """
        result = {
            'valid': False,
            'error': '',
            'path': selected_path
        }
        
        # Normalize path
        selected_path = os.path.normpath(selected_path)
        
        # Check if folder name is correct
        folder_name = os.path.basename(selected_path)
        if folder_name != 'com.lveditor.draft':
            result['error'] = 'Veuillez sélectionner le dossier "com.lveditor.draft"'
            return result
        
        # Validate the path
        validation_result = self._validate_capcut_path(selected_path)
        
        if validation_result['valid']:
            result['valid'] = True
            # Auto-save to params.json if config manager available
            if self.config_manager:
                self._save_to_config(selected_path)
            logger.info(f"Manual selection validated and saved: {selected_path}")
        else:
            result['error'] = validation_result['error']
        
        return result
    
    def _save_to_config(self, path: str):
        """Save detected path to params.json"""
        try:
            if self.config_manager:
                self.config_manager.save_config({'capcut_draft_path': path})
                logger.info(f"Saved CapCut draft path to config: {path}")
        except Exception as e:
            logger.error(f"Failed to save path to config: {e}")
    
    def check_saved_path(self) -> dict:
        """
        Check if saved path in params.json is still valid
        
        Returns:
            dict: {
                'valid': bool,
                'path': str,
                'error': str
            }
        """
        result = {
            'valid': False,
            'path': '',
            'error': ''
        }
        
        try:
            if self.config_manager:
                config = self.config_manager.load_config()
                saved_path = config.get('capcut_draft_path', '')
                
                if saved_path:
                    result['path'] = saved_path
                    validation = self._validate_capcut_path(saved_path)
                    result['valid'] = validation['valid']
                    result['error'] = validation['error'] if not validation['valid'] else ''
                else:
                    result['error'] = 'Aucun chemin enregistré dans la configuration'
        
        except Exception as e:
            result['error'] = f'Erreur lors de la vérification du chemin enregistré: {str(e)}'
        
        return result

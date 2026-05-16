#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask Web Server for CapCut Project Exporter
Provides web interface for exporting CapCut projects
"""

from flask import Flask, render_template, request, jsonify, send_file, abort
import os
import shutil
import tempfile
import json
import time
import zipfile
import urllib.parse
from datetime import datetime
from capcut_exporter import CapCutExporter
from capcut_detector import CapCutDetector
from capcut_importer import CapCutImporter
import json
import threading
import uuid

class ConfigManager:
    """Simple config manager for CapCut detector"""
    
    def load_config(self):
        """Load configuration from params.json"""
        return load_config()
    
    def save_config(self, config_updates):
        """Save configuration updates to params.json"""
        current_config = self.load_config()
        current_config.update(config_updates)
        save_config(current_config)

app = Flask(__name__)
exporter = CapCutExporter()
importer = CapCutImporter()
config_manager = ConfigManager()
detector = CapCutDetector(config_manager=config_manager)

# Global progress tracking dictionary
progress_tracker = {}

# Configure upload folder
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/api/projects')
def get_projects():
    """Get list of all CapCut projects with automatic detection"""
    try:
        # First check if we have a valid saved path
        saved_check = detector.check_saved_path()
        
        if not saved_check['valid']:
            # Try automatic detection
            app.logger.info("No valid saved path, attempting automatic detection...")
            detection = detector.detect_capcut_draft_folder()
            
            if detection['found']:
                app.logger.info(f"Automatically detected CapCut draft folder: {detection['path']}")
            else:
                app.logger.warning(f"Automatic detection failed: {detection['error']}")
                # Return projects list with detection info
                return jsonify({
                    'success': True,
                    'projects': [],
                    'detection_needed': True,
                    'detection_result': detection
                })
        
        # Get projects using the exporter
        projects = exporter.find_capcut_projects()
        project_list = []
        
        for project_path in projects:
            info = exporter.get_project_info(project_path)
            if info:
                project_list.append(info)
        
        return jsonify({
            'success': True,
            'projects': project_list,
            'detection_needed': False
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/export', methods=['POST'])
def export_project():
    """Export a CapCut project to portable format"""
    try:
        data = request.get_json()
        project_path = data.get('project_path')
        create_zip = data.get('create_zip', True)
        save_location = data.get('save_location', '')
        
        # Log incoming request details
        app.logger.info("=== Export Request Received ===")
        app.logger.info(f"Raw project_path: {repr(project_path)}")
        app.logger.info(f"Project path type: {type(project_path)}")
        app.logger.info(f"Create ZIP: {create_zip}")
        app.logger.info(f"Save location: {save_location}")
        
        if not project_path:
            app.logger.error("No project path provided in request")
            return jsonify({
                'success': False,
                'error': 'Project path is required'
            }), 400
        
        # Validate save location
        if save_location and not os.path.exists(save_location):
            app.logger.error(f"Save location does not exist: {save_location}")
            return jsonify({
                'success': False,
                'error': f'Save location not found: {save_location}'
            }), 400
        
        # No path fixing - use the path as provided by the frontend
        # The frontend should provide the correct path from project detection
        
        # Verify path exists
        if not os.path.exists(project_path):
            app.logger.error(f"Project path does not exist: {project_path}")
            return jsonify({
                'success': False,
                'error': f'Project path not found: {project_path}'
            }), 404
        
        # Get project info for naming
        project_info = exporter.get_project_info(project_path)
        if not project_info:
            return jsonify({
                'success': False,
                'error': 'Invalid project path or project not found'
            }), 404
        
        # Determine output path
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        project_name = project_info['name'].replace(' ', '_').replace('/', '_')
        
        if save_location:
            # Use user-specified location
            output_dir = save_location
            zip_filename = f'{project_name}_portable_{timestamp}.zip'
            zip_path = os.path.join(output_dir, zip_filename)
            temp_dir = os.path.join(output_dir, f'temp_{project_name}_{timestamp}')
            app.logger.info(f"Using user-specified save location: {output_dir}")
        else:
            # Use temporary directory
            temp_dir = tempfile.mkdtemp(prefix=f'capcut_export_{project_name}_{timestamp}_')
            zip_filename = f'{project_name}_portable.zip'
            zip_path = os.path.join(temp_dir, zip_filename)
            app.logger.info(f"Using temporary directory: {temp_dir}")
        
        # Create output directory if using custom location
        if save_location:
            os.makedirs(temp_dir, exist_ok=True)
            app.logger.info(f"Created output directory: {temp_dir}")
        
        # Create progress tracking session
        import uuid
        import time
        export_id = str(uuid.uuid4())
        
        # Initialize progress tracking
        progress_tracker[export_id] = {
            'export_id': export_id,
            'status': 'processing',
            'progress': 0,
            'message': 'Démarrage de l\'export...',
            'start_time': time.time(),
            'details': {
                'stage': 'initialization',
                'files_processed': 0,
                'total_files': 0,
                'current_file': '',
                'bytes_processed': 0,
                'total_bytes': 0
            }
        }
        
        # Start async export in background thread
        app.logger.info(f"Starting async export {export_id} for {project_name}")
        
        # Update initial progress
        update_progress(export_id, 5, 'Démarrage de l\'export...', 'initialization', 0, 0, '', 0, 0)
        
        # Start export in background thread
        export_thread = threading.Thread(
            target=run_export_async,
            args=(export_id, project_path, temp_dir, zip_path, create_zip, save_location)
        )
        export_thread.daemon = True  # Allow thread to exit when main program exits
        export_thread.start()
        
        # Return immediately with export_id for tracking
        return jsonify({
            'success': True,
            'message': 'Export démarré en arrière-plan',
            'export_id': export_id,
            'project_name': project_name
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/download/<filename>')
def download_file(filename):
    """Download exported ZIP file"""
    try:
        # Find the file in temp directories
        temp_base = tempfile.gettempdir()
        for item in os.listdir(temp_base):
            if item.startswith('capcut_export_'):
                temp_path = os.path.join(temp_base, item)
                if os.path.isdir(temp_path):
                    file_path = os.path.join(temp_path, filename)
                    if os.path.exists(file_path):
                        return send_file(
                            file_path,
                            as_attachment=True,
                            download_name=filename,
                            mimetype='application/zip'
                        )
        
        abort(404)
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

import_tracker = {}

def run_export_async(export_id, project_path, temp_dir, zip_path, create_zip, save_location):
    """Run export in background thread"""
    try:
        app.logger.info(f"Starting async export {export_id} for {project_path}")
        
        # Define progress callback for project preparation
        def project_progress_callback(progress, message, stage, files_processed, total_files, current_file, bytes_processed, total_bytes):
            # Check if export was cancelled before updating progress
            if progress_tracker.get(export_id, {}).get('status') == 'cancelled':
                return False  # Signal to stop processing
            update_progress(export_id, progress, message, stage, files_processed, total_files, current_file, bytes_processed, total_bytes)
            return True  # Continue processing
        
        # Make project portable with progress tracking
        success = exporter.make_project_portable(project_path, temp_dir, project_progress_callback)
        
        # Check if export was cancelled during project preparation
        if progress_tracker.get(export_id, {}).get('status') == 'cancelled':
            app.logger.info(f"Export {export_id} was cancelled during project preparation")
            return
        
        if not success:
            progress_tracker[export_id]['status'] = 'failed'
            progress_tracker[export_id]['message'] = 'Échec de la préparation du projet'
            if save_location:
                shutil.rmtree(temp_dir, ignore_errors=True)
            app.logger.error(f"Async export {export_id} failed during project preparation")
            return
        
        # Update progress after project preparation
        update_progress(export_id, 30, 'Projet préparé avec succès', 'project_ready', 0, 0, '', 0, 0)
        
        # Create ZIP if requested with real-time progress tracking
        if create_zip:
            # Check if export was cancelled before starting ZIP
            if progress_tracker.get(export_id, {}).get('status') == 'cancelled':
                app.logger.info(f"Export {export_id} was cancelled before ZIP creation")
                return
                
            app.logger.info(f"Starting ZIP creation for {export_id}")
            
            # Update progress for ZIP initialization
            update_progress(export_id, 35, 'Démarrage de la compression ZIP...', 'zip_initialization', 0, 0, '', 0, 0)
            
            # Define progress callback for ZIP creation
            def zip_progress_callback(progress, message, stage, files_processed, total_files, current_file, bytes_processed, total_bytes):
                # Check if export was cancelled during ZIP creation
                if progress_tracker.get(export_id, {}).get('status') == 'cancelled':
                    return False  # Signal to stop ZIP processing
                update_progress(export_id, progress, message, stage, files_processed, total_files, current_file, bytes_processed, total_bytes)
                return True  # Continue ZIP processing
            
            # Create ZIP with progress tracking
            zip_success = exporter.create_zip_archive(temp_dir, zip_path, zip_progress_callback)
            
            # Check if export was cancelled during ZIP creation
            if progress_tracker.get(export_id, {}).get('status') == 'cancelled':
                app.logger.info(f"Export {export_id} was cancelled during ZIP creation")
                return
            
            if zip_success and os.path.exists(zip_path):
                zip_size = os.path.getsize(zip_path)
                app.logger.info(f"Async export {export_id} completed successfully: {zip_path} ({zip_size} bytes)")
                
                # Mark as complete
                progress_tracker[export_id]['status'] = 'completed'
                progress_tracker[export_id]['progress'] = 100
                progress_tracker[export_id]['message'] = 'Export terminé avec succès'
                progress_tracker[export_id]['zip_path'] = zip_path
                progress_tracker[export_id]['zip_size'] = zip_size
                
                if save_location:
                    progress_tracker[export_id]['location'] = save_location
                    progress_tracker[export_id]['filename'] = os.path.basename(zip_path)
            else:
                # Mark as failed
                progress_tracker[export_id]['status'] = 'failed'
                progress_tracker[export_id]['message'] = 'Échec de la création ZIP'
                app.logger.error(f"Async export {export_id} failed during ZIP creation")
        else:
            # No ZIP requested, mark as completed
            progress_tracker[export_id]['status'] = 'completed'
            progress_tracker[export_id]['progress'] = 100
            progress_tracker[export_id]['message'] = 'Projet exporté avec succès'
            progress_tracker[export_id]['temp_path'] = temp_dir
            
    except Exception as e:
        app.logger.error(f"Async export {export_id} failed with error: {str(e)}")
        progress_tracker[export_id]['status'] = 'failed'
        progress_tracker[export_id]['message'] = f'Erreur: {str(e)}'
        
        # Cleanup on error
        if save_location and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

def update_progress(export_id, progress, message, stage, files_processed=0, total_files=0, current_file='', bytes_processed=0, total_bytes=0):
    """Update progress tracking"""
    if export_id in progress_tracker:
        progress_tracker[export_id].update({
            'progress': progress,
            'message': message,
            'details': {
                'stage': stage,
                'files_processed': files_processed,
                'total_files': total_files,
                'current_file': current_file,
                'bytes_processed': bytes_processed,
                'total_bytes': total_bytes
            },
            'timestamp': time.time()
        })

def update_import_progress(import_id, progress, message, stage, files_processed=0, total_files=0, current_file='', bytes_processed=0, total_bytes=0):
    """Update import progress tracking"""
    if import_id in import_tracker:
        import_tracker[import_id].update({
            'progress': progress,
            'message': message,
            'details': {
                'stage': stage,
                'files_processed': files_processed,
                'total_files': total_files,
                'current_file': current_file,
                'bytes_processed': bytes_processed,
                'total_bytes': total_bytes
            },
            'timestamp': time.time()
        })

def run_import_async(import_id, source_path, project_name, media_location, capcut_draft_path):
    """Run import in background thread"""
    try:
        app.logger.info(f"Starting async import {import_id} for {project_name}")
        
        # Define progress callback
        def import_progress_callback(progress, message, stage, files_processed=0, total_files=0, current_file='', bytes_processed=0, total_bytes=0):
            if import_tracker.get(import_id, {}).get('status') == 'cancelled':
                return False
            update_import_progress(import_id, progress, message, stage, files_processed, total_files, current_file, bytes_processed, total_bytes)
            return True
        
        # Execute import
        result = importer.import_project(source_path, project_name, media_location, capcut_draft_path, import_progress_callback)
        
        # Check if import was cancelled
        if import_tracker.get(import_id, {}).get('status') == 'cancelled':
            app.logger.info(f"Import {import_id} was cancelled")
            return
        
        if result['success']:
            # Mark as completed
            import_tracker[import_id]['status'] = 'completed'
            import_tracker[import_id]['progress'] = 100
            import_tracker[import_id]['message'] = 'Import terminé avec succès'
            import_tracker[import_id]['project_path'] = result['project_path']
            import_tracker[import_id]['media_path'] = result['media_path']
            import_tracker[import_id]['files_copied'] = result['files_copied']
            
            app.logger.info(f"Async import {import_id} completed successfully: {result['project_path']}")
        else:
            # Mark as failed
            import_tracker[import_id]['status'] = 'failed'
            import_tracker[import_id]['message'] = f'Échec de l\'import: {result["error"]}'
            app.logger.error(f"Async import {import_id} failed: {result['error']}")
    
    except Exception as e:
        app.logger.error(f"Async import {import_id} failed with error: {str(e)}")
        import_tracker[import_id]['status'] = 'failed'
        import_tracker[import_id]['message'] = f'Erreur: {str(e)}'

@app.route('/api/progress/<export_id>')
def get_export_progress(export_id):
    """Get real-time export progress"""
    try:
        if export_id not in progress_tracker:
            return jsonify({
                'success': False,
                'error': 'Export session not found'
            }), 404
        
        progress_data = progress_tracker[export_id].copy()  # Create a copy to avoid modification issues
        
        # Calculate estimated time remaining
        if progress_data.get('start_time') and progress_data.get('progress', 0) > 0:
            elapsed = time.time() - progress_data['start_time']
            if progress_data['progress'] > 0:
                estimated_total = elapsed * 100 / progress_data['progress']
                remaining = estimated_total - elapsed
                progress_data['time_remaining'] = max(0, remaining)
        
        # If completed, include download information
        if progress_data.get('status') == 'completed':
            if progress_data.get('zip_path'):
                # ZIP export completed
                if progress_data.get('location'):
                    # Custom location
                    response_data = {
                        'success': True,
                        'progress': progress_data,
                        'download_info': {
                            'type': 'direct',
                            'filename': progress_data.get('filename'),
                            'file_path': progress_data.get('zip_path'),
                            'file_size': progress_data.get('zip_size'),
                            'location': progress_data.get('location')
                        }
                    }
                else:
                    # Temp location
                    response_data = {
                        'success': True,
                        'progress': progress_data,
                        'download_info': {
                            'type': 'temp',
                            'download_url': f'/api/download/{os.path.basename(progress_data.get("zip_path"))}',
                            'filename': os.path.basename(progress_data.get('zip_path')),
                            'temp_path': os.path.dirname(progress_data.get('zip_path')),
                            'file_size': progress_data.get('zip_size')
                        }
                    }
                return jsonify(response_data)
            elif progress_data.get('temp_path'):
                # Project export completed (no ZIP)
                response_data = {
                    'success': True,
                    'progress': progress_data,
                    'download_info': {
                        'type': 'project',
                        'temp_path': progress_data.get('temp_path')
                    }
                }
                return jsonify(response_data)
        
        return jsonify({
            'success': True,
            'progress': progress_data
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/browse-folders')
def browse_folders():
    """Browse and return available folders for save location"""
    try:
        # Get common save locations
        locations = []
        
        # User desktop
        desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
        if os.path.exists(desktop):
            locations.append({
                'name': 'Bureau',
                'path': desktop,
                'type': 'desktop'
            })
        
        # User documents
        documents = os.path.join(os.path.expanduser('~'), 'Documents')
        if os.path.exists(documents):
            locations.append({
                'name': 'Documents',
                'path': documents,
                'type': 'documents'
            })
        
        # User downloads
        downloads = os.path.join(os.path.expanduser('~'), 'Downloads')
        if os.path.exists(downloads):
            locations.append({
                'name': 'Téléchargements',
                'path': downloads,
                'type': 'downloads'
            })
        
        # Current directory
        current_dir = os.getcwd()
        locations.append({
            'name': 'Dossier actuel',
            'path': current_dir,
            'type': 'current'
        })
        
        return jsonify({
            'success': True,
            'locations': locations
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/prepare-export', methods=['POST'])
def prepare_export():
    """Prepare export with full diagnostic of the project"""
    try:
        data = request.get_json()
        project_path = data.get('project_path')
        
        if not project_path:
            return jsonify({
                'success': False,
                'error': 'Project path is required'
            }), 400
        
        # Use the path as provided by the frontend project detection
        # No path fixing needed - frontend should provide correct paths
        
        # Verify path exists
        if not os.path.exists(project_path):
            return jsonify({
                'success': False,
                'error': f'Project path not found: {project_path}'
            }), 404
        
        # Get project info
        project_info = exporter.get_project_info(project_path)
        if not project_info:
            return jsonify({
                'success': False,
                'error': 'Invalid project path or project not found'
            }), 404
        
        # Perform full diagnostic
        diagnostic = {
            'project_info': project_info,
            'file_checks': {},
            'media_analysis': {},
            'issues': [],
            'warnings': [],
            'ready': True
        }
        
        # Check project structure
        draft_content_path = os.path.join(project_path, 'draft_content.json')
        diagnostic['file_checks']['draft_content'] = {
            'exists': os.path.exists(draft_content_path),
            'path': draft_content_path,
            'size': os.path.getsize(draft_content_path) if os.path.exists(draft_content_path) else 0
        }
        
        if not diagnostic['file_checks']['draft_content']['exists']:
            diagnostic['issues'].append('draft_content.json manquant')
            diagnostic['ready'] = False
        
        # Analyze media files
        try:
            with open(draft_content_path, 'r', encoding='utf-8') as f:
                project_data = json.load(f)
            
            materials = project_data.get('materials', {})
            total_media = 0
            missing_files = []
            
            for media_type in ['videos', 'audios', 'images', 'stickers', 'effects', 'transitions', 'texts', 'canvases']:
                media_list = materials.get(media_type, [])
                if isinstance(media_list, list):
                    total_media += len(media_list)
                    
                    # Check each media file
                    for media_item in media_list:
                        if isinstance(media_item, dict) and 'path' in media_item:
                            media_path = media_item['path']
                            if not os.path.exists(media_path):
                                missing_files.append(media_path)
            
            diagnostic['media_analysis'] = {
                'total_media': total_media,
                'missing_files': missing_files,
                'media_types': {k: len(v) if isinstance(v, list) else 0 for k, v in materials.items()}
            }
            
            if missing_files:
                diagnostic['warnings'].append(f'{len(missing_files)} fichiers médias manquants')
            
        except Exception as e:
            diagnostic['issues'].append(f'Erreur analyse médias: {str(e)}')
            diagnostic['ready'] = False
        
        # Check output directory
        save_location = data.get('save_location', '')
        if save_location:
            if not os.path.exists(save_location):
                try:
                    os.makedirs(save_location, exist_ok=True)
                    app.logger.info(f"Created export directory: {save_location}")
                    diagnostic['output_location'] = {
                        'exists': True,
                        'path': save_location,
                        'writable': True,
                        'created': True
                    }
                except Exception as e:
                    diagnostic['issues'].append(f'Impossible de créer le dossier: {str(e)}')
                    diagnostic['ready'] = False
            else:
                diagnostic['output_location'] = {
                    'exists': True,
                    'path': save_location,
                    'writable': os.access(save_location, os.W_OK),
                    'created': False
                }
                if not diagnostic['output_location']['writable']:
                    diagnostic['issues'].append('Emplacement de sauvegarde non accessible en écriture')
                    diagnostic['ready'] = False
        
        return jsonify({
            'success': True,
            'diagnostic': diagnostic
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/import-missing-files', methods=['POST'])
def import_missing_files():
    """Handle missing files import or template creation"""
    try:
        data = request.get_json()
        project_path = data.get('project_path')
        missing_files = data.get('missing_files', [])
        action = data.get('action', 'import')  # 'import' or 'template'
        
        if not project_path:
            return jsonify({
                'success': False,
                'error': 'Project path is required'
            }), 400
        
        results = {
            'imported': [],
            'templates_created': [],
            'errors': []
        }
        
        for file_path in missing_files:
            try:
                if action == 'template':
                    # Create template file
                    template_content = create_template_file(file_path)
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    with open(file_path, 'w') as f:
                        f.write(template_content)
                    results['templates_created'].append(file_path)
                    app.logger.info(f"Created template file: {file_path}")
                else:
                    # For import, we'll just create a placeholder for now
                    # In a real implementation, you'd handle file upload
                    placeholder_content = create_placeholder_file(file_path)
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    with open(file_path, 'w') as f:
                        f.write(placeholder_content)
                    results['imported'].append(file_path)
                    app.logger.info(f"Created placeholder file: {file_path}")
                    
            except Exception as e:
                results['errors'].append(f'{file_path}: {str(e)}')
                app.logger.error(f"Error creating file {file_path}: {str(e)}")
        
        return jsonify({
            'success': True,
            'results': results
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def create_template_file(file_path):
    """Create a template file based on file type"""
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext in ['.mp4', '.mov', '.avi']:
        # Video template
        return '''# Template Video File
# This is a placeholder video file
# Replace this with your actual video content
'''
    
    elif ext in ['.mp3', '.wav', '.aac']:
        # Audio template
        return '''# Template Audio File
# This is a placeholder audio file
# Replace this with your actual audio content
'''
    
    elif ext in ['.jpg', '.jpeg', '.png', '.bmp']:
        # Image template
        return '''# Template Image File
# This is a placeholder image file
# Replace this with your actual image content
'''
    
    else:
        # Generic template
        return '''# Template File
# This is a placeholder file
# Replace this with your actual content
'''

def create_placeholder_file(file_path):
    """Create a placeholder file"""
    return f'''# Placeholder File
# Original path: {file_path}
# This file was created as a placeholder
# Please replace it with the actual file content
'''

@app.route('/api/cancel-export', methods=['POST'])
def cancel_export():
    """Cancel an ongoing export and clean up temporary files"""
    try:
        data = request.get_json()
        export_id = data.get('export_id')
        
        if not export_id:
            return jsonify({
                'success': False,
                'error': 'Export ID is required'
            }), 400
        
        if export_id not in progress_tracker:
            return jsonify({
                'success': False,
                'error': 'Export session not found'
            }), 404
        
        # Mark export as cancelled
        progress_tracker[export_id]['status'] = 'cancelled'
        progress_tracker[export_id]['message'] = 'Export annulé par l\'utilisateur'
        progress_tracker[export_id]['progress'] = 0
        
        # Clean up temporary files if they exist
        temp_path = progress_tracker[export_id].get('temp_path')
        if temp_path and os.path.exists(temp_path):
            app.logger.info(f"Cleaning up temp files: {temp_path}")
            shutil.rmtree(temp_path, ignore_errors=True)
            progress_tracker[export_id]['cleanup_performed'] = True
        
        # Also clean up any ZIP file if it was created
        zip_path = progress_tracker[export_id].get('zip_path')
        if zip_path and os.path.exists(zip_path):
            app.logger.info(f"Cleaning up ZIP file: {zip_path}")
            os.remove(zip_path)
            progress_tracker[export_id]['zip_cleanup_performed'] = True
        
        app.logger.info(f"Export {export_id} cancelled and cleaned up successfully")
        
        return jsonify({
            'success': True,
            'message': 'Export annulé avec succès',
            'cleanup_performed': progress_tracker[export_id].get('cleanup_performed', False),
            'zip_cleanup_performed': progress_tracker[export_id].get('zip_cleanup_performed', False)
        })
    
    except Exception as e:
        app.logger.error(f"Error cancelling export: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/config/capcut-path', methods=['GET'])
def get_capcut_path():
    """Get the stored CapCut draft path"""
    try:
        config = load_config()
        return jsonify({
            'success': True,
            'path': config.get('capcut_draft_path', '')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/config/capcut-path', methods=['POST'])
def set_capcut_path():
    """Set the CapCut draft path"""
    try:
        data = request.get_json()
        path = data.get('path', '')
        
        if not path:
            return jsonify({
                'success': False,
                'error': 'Path is required'
            }), 400
        
        config = load_config()
        config['capcut_draft_path'] = path
        save_config(config)
        
        return jsonify({
            'success': True,
            'message': 'CapCut draft path saved successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/config/validate-path', methods=['POST'])
def validate_capcut_path():
    """Validate a CapCut projects path"""
    try:
        data = request.get_json()
        path = data.get('path', '')
        
        if not path:
            return jsonify({
                'success': False,
                'valid': False,
                'message': 'Path is required'
            })
        
        # Check if path exists
        if not os.path.exists(path):
            return jsonify({
                'success': True,
                'valid': False,
                'message': 'Path does not exist'
            })
        
        # Check if it's a CapCut projects directory
        expected_subdirs = ['com.lveditor.draft']
        has_capcut_structure = any(
            os.path.exists(os.path.join(path, subdir)) 
            for subdir in expected_subdirs
        )
        
        if not has_capcut_structure:
            return jsonify({
                'success': True,
                'valid': False,
                'message': 'Not a valid CapCut projects directory'
            })
        
        return jsonify({
            'success': True,
            'valid': True,
            'message': 'Valid CapCut projects directory'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/capcut/detect', methods=['GET'])
def detect_capcut_draft_folder():
    """Automatically detect CapCut draft folder"""
    try:
        result = detector.detect_capcut_draft_folder()
        
        return jsonify({
            'success': True,
            'detection': result
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/capcut/validate-manual', methods=['POST'])
def validate_manual_capcut_selection():
    """Validate manually selected CapCut draft folder"""
    try:
        data = request.get_json()
        selected_path = data.get('path', '')
        
        if not selected_path:
            return jsonify({
                'success': False,
                'error': 'Path is required'
            }), 400
        
        result = detector.validate_manual_selection(selected_path)
        
        return jsonify({
            'success': True,
            'validation': result
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/capcut/check-saved', methods=['GET'])
def check_saved_capcut_path():
    """Check if saved CapCut path is still valid"""
    try:
        result = detector.check_saved_path()
        
        return jsonify({
            'success': True,
            'check': result
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/import/analyze', methods=['POST'])
def analyze_import_source():
    """Analyze import source (ZIP file or directory)"""
    try:
        data = request.get_json()
        source_path = data.get('source_path', '')
        
        if not source_path:
            return jsonify({
                'success': False,
                'error': 'Source path is required'
            }), 400
        
        if not os.path.exists(source_path):
            return jsonify({
                'success': False,
                'error': 'Source path does not exist'
            }), 404
        
        # Analyze the source
        import_info = importer.get_import_info(source_path)
        
        return jsonify({
            'success': True,
            'import_info': import_info
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/import/media-options', methods=['POST'])
def get_media_location_options():
    """Get available media location options"""
    try:
        data = request.get_json()
        project_name = data.get('project_name', '')
        capcut_draft_path = data.get('capcut_draft_path', '')
        
        if not project_name or not capcut_draft_path:
            return jsonify({
                'success': False,
                'error': 'Project name and CapCut draft path are required'
            }), 400
        
        options = importer.get_media_location_options(capcut_draft_path, project_name)
        
        return jsonify({
            'success': True,
            'options': options
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/import/execute', methods=['POST'])
def execute_import():
    """Execute the import process"""
    try:
        data = request.get_json()
        source_path = data.get('source_path', '')
        project_name = data.get('project_name', '')
        media_location = data.get('media_location', '')
        capcut_draft_path = data.get('capcut_draft_path', '')
        
        if not all([source_path, project_name, media_location, capcut_draft_path]):
            return jsonify({
                'success': False,
                'error': 'All parameters are required: source_path, project_name, media_location, capcut_draft_path'
            }), 400
        
        # Validate CapCut draft path
        if not os.path.exists(capcut_draft_path):
            return jsonify({
                'success': False,
                'error': 'CapCut draft path does not exist'
            }), 404
        
        # Create progress tracking
        import_id = str(uuid.uuid4())
        import_tracker[import_id] = {
            'import_id': import_id,
            'status': 'processing',
            'progress': 0,
            'message': 'Démarrage de l\'import...',
            'start_time': time.time(),
            'details': {
                'stage': 'initialization',
                'files_processed': 0,
                'total_files': 0,
                'current_file': '',
                'bytes_processed': 0,
                'total_bytes': 0
            }
        }
        
        # Start import in background thread
        def import_progress_callback(progress, message, stage, files_processed=0, total_files=0, current_file='', bytes_processed=0, total_bytes=0):
            if import_tracker.get(import_id, {}).get('status') == 'cancelled':
                return False
            update_import_progress(import_id, progress, message, stage, files_processed, total_files, current_file, bytes_processed, total_bytes)
            return True
        
        import_thread = threading.Thread(
            target=run_import_async,
            args=(import_id, source_path, project_name, media_location, capcut_draft_path)
        )
        import_thread.daemon = True
        import_thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Import démarré en arrière-plan',
            'import_id': import_id,
            'project_name': project_name
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/import/cancel', methods=['POST'])
def cancel_import():
    """Cancel an ongoing import"""
    try:
        data = request.get_json()
        import_id = data.get('import_id')
        
        if not import_id:
            return jsonify({
                'success': False,
                'error': 'Import ID is required'
            }), 400
        
        if import_id not in import_tracker:
            return jsonify({
                'success': False,
                'error': 'Import session not found'
            }), 404
        
        # Mark import as cancelled
        import_tracker[import_id]['status'] = 'cancelled'
        import_tracker[import_id]['message'] = 'Import annulé par l\'utilisateur'
        import_tracker[import_id]['progress'] = 0
        
        app.logger.info(f"Import {import_id} cancelled successfully")
        
        return jsonify({
            'success': True,
            'message': 'Import annulé avec succès'
        })
    
    except Exception as e:
        app.logger.error(f"Error cancelling import: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def load_config():
    """Load configuration from params.json with fallback to defaults"""
    # Default configuration with minimal required structure
    default_config = {
        "capcut_draft_path": ""
    }
    
    try:
        if os.path.exists('params.json'):
            with open('params.json', 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
                # Handle empty file
                if not content:
                    app.logger.warning("params.json is empty, using default configuration")
                    save_config(default_config)
                    return default_config
                
                # Try to parse JSON
                try:
                    config = json.loads(content)
                    
                    # Ensure required fields exist with fallback to defaults
                    if "capcut_draft_path" not in config:
                        config["capcut_draft_path"] = default_config["capcut_draft_path"]
                    
                    return config
                    
                except json.JSONDecodeError as je:
                    app.logger.error(f"Invalid JSON in params.json: {je}")
                    app.logger.warning("Using default configuration due to corrupted JSON")
                    save_config(default_config)
                    return default_config
                    
        else:
            # File doesn't exist, create it with default config
            app.logger.info("params.json not found, creating with default configuration")
            save_config(default_config)
            return default_config
            
    except Exception as e:
        app.logger.error(f"Unexpected error loading config: {e}")
        app.logger.warning("Using default configuration due to error")
        return default_config

def save_config(config):
    """Save configuration to params.json"""
    try:
        with open('params.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        app.logger.error(f"Error saving config: {e}")
        raise

@app.route('/api/import/upload', methods=['POST'])
def import_zip_upload():
    """Handle ZIP file upload for import"""
    try:
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file uploaded'
            }), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400
        
        if not file.filename.endswith('.zip'):
            return jsonify({
                'success': False,
                'error': 'File must be a ZIP archive'
            }), 400
        
        # Create temporary directory for upload
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_dir = os.path.join(tempfile.gettempdir(), f'capcut_import_{timestamp}')
        os.makedirs(temp_dir, exist_ok=True)
        
        # Save uploaded file
        zip_path = os.path.join(temp_dir, file.filename)
        file.save(zip_path)
        
        # Extract ZIP to analyze
        extract_dir = os.path.join(temp_dir, 'extracted')
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            zipf.extractall(extract_dir)
        
        # Analyze extracted project
        project_info = analyze_import_project(extract_dir)
        
        return jsonify({
            'success': True,
            'project_info': project_info,
            'temp_dir': temp_dir,
            'zip_path': zip_path
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def analyze_import_project(extract_dir):
    """Analyze extracted project for import"""
    project_info = {
        'name': 'Unknown Project',
        'duration': 0,
        'media_count': 0,
        'media_files': [],
        'has_draft_content': False,
        'structure_valid': False
    }
    
    try:
        # Check for draft_content.json
        draft_file = os.path.join(extract_dir, 'draft_content.json')
        if os.path.exists(draft_file):
            project_info['has_draft_content'] = True
            
            with open(draft_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            project_info['name'] = data.get('name', 'Unknown Project')
            duration_us = data.get('duration', 0)
            project_info['duration'] = duration_us / 1000000 if duration_us else 0
            
            # Count media files
            materials = data.get('materials', {})
            for media_type in ['videos', 'audios', 'images', 'stickers', 'effects', 'transitions', 'texts', 'canvases']:
                media_list = materials.get(media_type, [])
                if isinstance(media_list, list):
                    project_info['media_count'] += len(media_list)
                    for item in media_list:
                        if isinstance(item, dict) and 'path' in item:
                            project_info['media_files'].append(item['path'])
        
        # Check for medias folder
        medias_dir = os.path.join(extract_dir, 'medias')
        if os.path.exists(medias_dir):
            media_files = os.listdir(medias_dir)
            project_info['copied_media_count'] = len(media_files)
        
        project_info['structure_valid'] = project_info['has_draft_content']
        
    except Exception as e:
        app.logger.error(f"Error analyzing import project: {e}")
    
    return project_info



@app.route('/api/import/progress/<import_id>')
def get_import_progress(import_id):
    """Get real-time import progress"""
    try:
        if import_id not in import_tracker:
            return jsonify({
                'success': False,
                'error': 'Import session not found'
            }), 404
        
        progress_data = import_tracker[import_id].copy()
        
        # Calculate estimated time remaining
        if progress_data.get('start_time') and progress_data.get('progress', 0) > 0:
            elapsed = time.time() - progress_data['start_time']
            if progress_data['progress'] > 0:
                estimated_total = elapsed * 100 / progress_data['progress']
                remaining = estimated_total - elapsed
                progress_data['time_remaining'] = max(0, remaining)
        
        # If completed, include project information
        if progress_data.get('status') == 'completed':
            response_data = {
                'success': True,
                'progress': progress_data,
                'project_info': {
                    'folder': progress_data.get('project_folder'),
                    'name': progress_data.get('project_name')
                }
            }
            return jsonify(response_data)
        
        return jsonify({
            'success': True,
            'progress': progress_data
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/cleanup', methods=['POST'])
def cleanup_temp_files():
    """Clean up temporary files"""
    try:
        data = request.get_json()
        temp_path = data.get('temp_path')
        
        if temp_path and os.path.exists(temp_path):
            shutil.rmtree(temp_path, ignore_errors=True)
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/load-params', methods=['GET'])
def load_params():
    """Load parameters from params.json"""
    try:
        config = config_manager.load_config()
        return jsonify({
            'success': True,
            'settings': config
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/save-params', methods=['POST'])
def save_params():
    """Save parameters to params.json"""
    try:
        settings = request.get_json()
        if not settings:
            return jsonify({
                'success': False,
                'error': 'No settings provided'
            }), 400
        
        config_manager.save_config(settings)
        return jsonify({
            'success': True,
            'message': 'Settings saved successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/test-paths', methods=['POST'])
def test_paths():
    """Test if configured paths are valid"""
    try:
        data = request.get_json()
        results = {}
        
        if 'draft_path' in data and data['draft_path']:
            results['draft_path'] = os.path.exists(data['draft_path'])
        
        if 'exe_path' in data and data['exe_path']:
            results['exe_path'] = os.path.exists(data['exe_path'])
        
        if 'save_path' in data and data['save_path']:
            results['save_path'] = os.path.exists(data['save_path'])
        
        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/cover/<path:project_path>')
def get_project_cover(project_path):
    """Serve project cover image"""
    try:
        # Decode the project path
        import urllib.parse
        decoded_path = urllib.parse.unquote(project_path)
        
        # Construct cover image path
        cover_path = os.path.join(decoded_path, 'draft_cover.jpg')
        
        if os.path.exists(cover_path):
            return send_file(cover_path, mimetype='image/jpeg')
        else:
            # Return a default placeholder or 404
            return jsonify({'success': False, 'error': 'Cover not found'}), 404
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/duplicate-project', methods=['POST'])
def duplicate_project():
    """Duplicate a CapCut project"""
    try:
        data = request.get_json()
        if not data or 'path' not in data:
            return jsonify({'success': False, 'error': 'Project path required'}), 400
        
        source_path = data['path']
        project_name = data.get('name', 'Project')
        
        # Generate new project name
        import shutil
        from pathlib import Path
        
        source_dir = Path(source_path)
        parent_dir = source_dir.parent
        
        # Find a unique name for the duplicate
        base_name = project_name + '_copie'
        counter = 1
        new_name = base_name
        while (parent_dir / new_name).exists():
            new_name = f"{base_name}_{counter}"
            counter += 1
        
        new_path = parent_dir / new_name
        
        # Copy the entire project directory
        shutil.copytree(source_path, new_path, dirs_exist_ok=False)
        
        return jsonify({
            'success': True,
            'message': f'Projet dupliqué vers {new_name}',
            'new_path': str(new_path)
        })
    
    except Exception as e:
        logger.error(f"Error duplicating project: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete-project', methods=['POST'])
def delete_project():
    """Delete a CapCut project"""
    try:
        data = request.get_json()
        if not data or 'path' not in data:
            return jsonify({'success': False, 'error': 'Project path required'}), 400
        
        project_path = data['path']
        
        # Delete the project directory
        import shutil
        shutil.rmtree(project_path, ignore_errors=True)
        
        return jsonify({
            'success': True,
            'message': 'Projet supprimé avec succès'
        })
    
    except Exception as e:
        logger.error(f"Error deleting project: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/open-folder', methods=['POST'])
def open_folder():
    """Open a folder in the system file explorer"""
    try:
        data = request.get_json()
        if not data or 'path' not in data:
            return jsonify({'success': False, 'error': 'Folder path required'}), 400
        
        folder_path = data['path']
        
        # Open folder using system command
        import subprocess
        import platform
        
        if platform.system() == 'Windows':
            subprocess.run(['explorer', folder_path], check=True)
        elif platform.system() == 'Darwin':  # macOS
            subprocess.run(['open', folder_path], check=True)
        else:  # Linux
            subprocess.run(['xdg-open', folder_path], check=True)
        
        return jsonify({
            'success': True,
            'message': 'Dossier ouvert avec succès'
        })
    
    except Exception as e:
        logger.error(f"Error opening folder: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/diagnose')
def diagnose_capcut():
    """Diagnose CapCut installation and provide helpful information"""
    try:
        diagnostic = exporter.diagnose_capcut_installation()
        return jsonify({
            'success': True,
            'diagnostic': diagnostic
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'File not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    # Create static directory if it doesn't exist
    if not os.path.exists('static'):
        os.makedirs('static')
    
    print("Starting CapCut Exporter Web Server...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CapCut Project Importer
Import portable CapCut projects back to CapCut format
"""

import json
import logging
import os
import shutil
import tempfile
import zipfile
from typing import Dict, List, Optional, Tuple

# Configure logging
logger = logging.getLogger(__name__)


class CapCutImporter:
    """Main class for importing portable CapCut projects to CapCut format"""

    def __init__(self):
        self.supported_extensions = {
            'video': ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm'],
            'audio': ['.mp3', '.wav', '.aac', '.ogg', '.flac', '.m4a'],
            'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
        }
        self._media_extensions = {
            ext
            for exts in self.supported_extensions.values()
            for ext in exts
        }


    def _is_path_like_key(self, key: str) -> bool:
        """Return True for JSON keys that are likely to contain file paths."""
        if not isinstance(key, str):
            return False

        lower = key.lower()
        if key in self._PATH_KEYS or key in self._STRUCTURAL_KEYS:
            return True
        return lower.endswith('path') or lower.endswith('_path') or lower.endswith('filepath') or lower == 'file_path'

    def _looks_like_path_value(self, value: str) -> bool:
        """Heuristic used to catch path strings even when the key name is unusual."""
        if not isinstance(value, str):
            return False

        candidate = value.strip()
        if not candidate:
            return False

        normalized = candidate.replace('\\', '/')
        if normalized.startswith(('./', '../', '/', '~/', '.\\', '..\\')):
            return True
        if len(normalized) > 1 and normalized[1] == ':':
            return True
        if normalized.startswith('file:///'):
            return True
        return False

    def _abspath_norm(self, path_value: str) -> str:
        return os.path.abspath(path_value).replace('\\', '/')

    def _is_under_dir(self, path_value: str, base_dir: str) -> bool:
        abs_path = self._abspath_norm(path_value)
        abs_base = self._abspath_norm(base_dir)
        return abs_path == abs_base or abs_path.startswith(abs_base + '/')

    def _resolve_imported_path(
        self,
        original: str,
        media_dir: str,
        project_root: str,
        capcut_draft_path: str,
        key: Optional[str] = None,
    ) -> str:
        """Convert a portable/export path into a local absolute path for CapCut."""
        if not isinstance(original, str):
            return original

        stripped = original.strip()
        if not stripped:
            return stripped

        normalized = stripped.replace('\\', '/')

        # Structural keys are handled separately by _fix_structural_paths.
        if key in self._STRUCTURAL_KEYS:
            return stripped

        # Portable bundle paths -> local absolute paths.
        if normalized.startswith('./medias/other/') or normalized.startswith('medias/other/'):
            filename = os.path.basename(normalized)
            return self._abspath_norm(os.path.join(media_dir, 'other', filename))

        if normalized.startswith('./medias/') or normalized.startswith('medias/'):
            filename = os.path.basename(normalized)
            return self._abspath_norm(os.path.join(media_dir, filename))

        if normalized.startswith('./project/') or normalized.startswith('project/'):
            rel = normalized[2:] if normalized.startswith('./') else normalized
            return self._abspath_norm(os.path.join(capcut_draft_path, rel))

        if normalized.startswith('./') or normalized.startswith('../') or normalized.startswith('.\\') or normalized.startswith('..\\'):
            return self._abspath_norm(os.path.join(project_root, normalized.lstrip('./').lstrip('.\\')))

        # Absolute Windows / POSIX path from the original machine.
        if len(normalized) > 1 and normalized[1] == ':':
            filename = os.path.basename(normalized)
            portable_other = os.path.join(media_dir, 'other', filename)
            portable_main = os.path.join(media_dir, filename)

            if os.path.exists(portable_other):
                return self._abspath_norm(portable_other)
            if os.path.exists(portable_main):
                return self._abspath_norm(portable_main)
            return self._abspath_norm(portable_main)

        if os.path.isabs(stripped):
            filename = os.path.basename(stripped)
            portable_other = os.path.join(media_dir, 'other', filename)
            portable_main = os.path.join(media_dir, filename)

            if os.path.exists(portable_other):
                return self._abspath_norm(portable_other)
            if os.path.exists(portable_main):
                return self._abspath_norm(portable_main)
            return self._abspath_norm(portable_main)

        # Last resort for relative path-like strings under a path-like key.
        if key is not None and self._is_path_like_key(key):
            return self._abspath_norm(os.path.join(project_root, normalized))

        return stripped

    def _rewrite_imported_json_paths(self, project_dir: str, media_dir: str, capcut_draft_path: str) -> int:
        """Rewrite every JSON file in the imported project so paths become local absolutes."""
        rewritten_files = 0

        for root, _, files in os.walk(project_dir):
            for filename in files:
                if not filename.lower().endswith('.json'):
                    continue

                json_path = os.path.join(root, filename)

                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except Exception as e:
                    logger.warning(f"Skipping unreadable JSON during import rewrite: {json_path} ({e})")
                    continue

                changed = 0

                def walk(obj):
                    nonlocal changed
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            if key in self._STRUCTURAL_KEYS and isinstance(value, str):
                                new_value = {
                                    'draft_fold_path': self._abspath_norm(project_dir),
                                    'draft_root_path': self._abspath_norm(capcut_draft_path),
                                    'draft_cover': self._abspath_norm(os.path.join(project_dir, 'draft_cover.jpg')),
                                    'draft_removable_storage_device_path': '',
                                }[key]
                                if obj[key] != new_value:
                                    obj[key] = new_value
                                    changed += 1
                            elif isinstance(value, str) and (
                                self._is_path_like_key(key) or self._looks_like_path_value(value)
                            ):
                                new_value = self._resolve_imported_path(
                                    value,
                                    media_dir=media_dir,
                                    project_root=project_dir,
                                    capcut_draft_path=capcut_draft_path,
                                    key=key,
                                )
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
                        logger.info(f"JSON import rewritten: {json_path} ({changed} path(s))")
                    except Exception as e:
                        logger.error(f"Failed to save rewritten JSON {json_path}: {e}")

        return rewritten_files

    def extract_zip_file(self, zip_path: str, extract_to: str) -> bool:
        """Extract ZIP file to specified directory"""
        logger.debug(f"Extracting ZIP: {zip_path} -> {extract_to}")

        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)

            # Verify extraction structure
            expected_folders = ['project', 'medias']
            for folder in expected_folders:
                folder_path = os.path.join(extract_to, folder)
                if not os.path.exists(folder_path):
                    logger.error(f"Expected folder not found after extraction: {folder}")
                    return False

            logger.info(f"ZIP extracted successfully to: {extract_to}")
            return True

        except zipfile.BadZipFile:
            logger.error(f"Invalid ZIP file: {zip_path}")
            return False
        except Exception as e:
            logger.error(f"Error extracting ZIP: {e}")
            return False

    def get_import_info(self, source_path: str) -> Dict:
        """Get information about the import source"""
        logger.debug(f"Getting import info for: {source_path}")

        result = {
            'valid': False,
            'type': '',  # 'folder' or 'zip'
            'project_name': '',
            'export_info': {},
            'draft_info': {},
            'media_count': 0,
            'error': ''
        }

        try:
            if os.path.isfile(source_path) and source_path.lower().endswith('.zip'):
                result['type'] = 'zip'
                with tempfile.TemporaryDirectory() as temp_dir:
                    if not self.extract_zip_file(source_path, temp_dir):
                        result['error'] = 'Failed to extract ZIP file'
                        return result

                    analysis = self._analyze_extracted_project(temp_dir)
                    result.update(analysis)
                    result['valid'] = True

            elif os.path.isdir(source_path):
                result['type'] = 'folder'
                analysis = self._analyze_extracted_project(source_path)
                result.update(analysis)
                result['valid'] = True

            else:
                result['error'] = 'Source must be a ZIP file or project directory'

        except Exception as e:
            logger.error(f"Error getting import info: {e}")
            result['error'] = str(e)

        return result

    def _analyze_extracted_project(self, project_dir: str) -> Dict:
        """Analyze extracted project directory"""
        analysis = {
            'project_name': '',
            'export_info': {},
            'draft_info': {},
            'media_count': 0
        }

        project_folder = os.path.join(project_dir, 'project')
        medias_folder = os.path.join(project_dir, 'medias')
        export_info_file = os.path.join(project_dir, 'export_info.json')

        if not os.path.exists(project_folder):
            raise FileNotFoundError('project folder not found')

        if not os.path.exists(medias_folder):
            raise FileNotFoundError('medias folder not found')

        if os.path.exists(export_info_file):
            try:
                with open(export_info_file, 'r', encoding='utf-8') as f:
                    analysis['export_info'] = json.load(f)
                    analysis['project_name'] = analysis['export_info'].get('project_name', 'ImportedProject')
            except Exception as e:
                logger.warning(f"Error reading export_info.json: {e}")
                analysis['project_name'] = 'ImportedProject'

        draft_file = os.path.join(project_folder, 'draft_content.json')
        if os.path.exists(draft_file):
            try:
                with open(draft_file, 'r', encoding='utf-8') as f:
                    draft_data = json.load(f)
                    analysis['draft_info'] = {
                        'name': draft_data.get('name', analysis['project_name']),
                        'duration': draft_data.get('duration', 0) / 1000000,
                        'create_time': draft_data.get('create_time', 0)
                    }
                    analysis['project_name'] = analysis['draft_info']['name']
            except Exception as e:
                logger.warning(f"Error reading draft_content.json: {e}")

        if os.path.exists(medias_folder):
            media_files = [
                f for f in os.listdir(medias_folder)
                if os.path.isfile(os.path.join(medias_folder, f))
            ]
            analysis['media_count'] = len(media_files)

        return analysis

    def import_project(self, source_path: str, project_name: str, media_location: str,
                       capcut_draft_path: str, progress_callback=None) -> Dict:
        """
        Import portable project to CapCut format

        Args:
            source_path: Path to ZIP file or project directory
            project_name: Name for the imported project
            media_location: Where to place media files ('project' or custom path)
            capcut_draft_path: CapCut draft folder path
            progress_callback: Progress callback function

        Returns:
            dict: Import result with status and details
        """
        logger.info(f"Starting import: {source_path} -> {project_name}")

        result = {
            'success': False,
            'project_path': '',
            'media_path': '',
            'error': '',
            'files_copied': 0
        }

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                logger.debug(f"Using temporary directory: {temp_dir}")

                if os.path.isfile(source_path) and source_path.lower().endswith('.zip'):
                    if not self.extract_zip_file(source_path, temp_dir):
                        result['error'] = 'Failed to extract ZIP file'
                        return result
                    project_dir = temp_dir
                elif os.path.isdir(source_path):
                    project_dir = source_path
                else:
                    result['error'] = 'Invalid source path'
                    return result

                if progress_callback:
                    progress_callback(10, "Préparation de l'import...", "preparation")

                target_project_dir = os.path.join(capcut_draft_path, project_name)
                os.makedirs(target_project_dir, exist_ok=True)
                logger.info(f"Created target directory: {target_project_dir}")

                if media_location == 'project':
                    target_media_dir = os.path.join(target_project_dir, 'medias')
                else:
                    target_media_dir = media_location

                os.makedirs(target_media_dir, exist_ok=True)
                logger.info(f"Media files will be placed in: {target_media_dir}")

                if progress_callback:
                    progress_callback(20, "Copie des fichiers médias...", "copying_media")

                media_source = os.path.join(project_dir, 'medias')
                media_files_copied = self._copy_media_files(
                    media_source,
                    target_media_dir,
                    progress_callback
                )

                if progress_callback:
                    progress_callback(45, "Copie des fichiers du projet...", "copying_project")

                project_source = os.path.join(project_dir, 'project')
                files_copied = self._copy_project_files(
                    project_source,
                    target_project_dir,
                    target_media_dir,
                    target_project_dir,
                    progress_callback
                )

                if progress_callback:
                    progress_callback(90, "Finalisation de l'import...", "finalization")

                rewritten_json_files = self._rewrite_imported_json_paths(
                    target_project_dir,
                    target_media_dir,
                    capcut_draft_path,
                )
                logger.info(f"JSON local paths rewritten in {rewritten_json_files} file(s)")

                if self._verify_import(target_project_dir, target_media_dir):
                    result['success'] = True
                    result['project_path'] = target_project_dir
                    result['media_path'] = target_media_dir
                    result['files_copied'] = files_copied + media_files_copied
                    logger.info(f"Import completed successfully: {target_project_dir}")
                else:
                    result['error'] = 'Import verification failed'

                if progress_callback:
                    progress_callback(100, "Import terminé", "completed")

        except Exception as e:
            logger.error(f"Import failed: {e}")
            result['error'] = str(e)

        return result

    def _copy_project_files(self, source_dir: str, target_dir: str, media_dir: str,
                            project_root: str, progress_callback=None) -> int:
        """Copy project files and update media paths"""
        logger.debug(f"Copying project files: {source_dir} -> {target_dir}")

        files_copied = 0

        try:
            if not os.path.exists(source_dir):
                raise FileNotFoundError(f"Project source directory not found: {source_dir}")

            for item in os.listdir(source_dir):
                source_path = os.path.join(source_dir, item)
                target_path = os.path.join(target_dir, item)

                if os.path.isfile(source_path):
                    if item == 'draft_content.json':
                        self._process_draft_file(source_path, target_path, media_dir, project_root)
                    elif item == 'draft_meta_info.json':
                        self._process_meta_file(source_path, target_path, media_dir, project_root)
                    else:
                        shutil.copy2(source_path, target_path)

                    files_copied += 1
                    logger.debug(f"Copied project file: {item}")

                elif os.path.isdir(source_path):
                    shutil.copytree(source_path, target_path, dirs_exist_ok=True)
                    files_copied += 1
                    logger.debug(f"Copied project directory: {item}")

            if progress_callback:
                progress_callback(60, f"Fichiers projet copiés: {files_copied}", "project_copied")

        except Exception as e:
            logger.error(f"Error copying project files: {e}")
            raise

        return files_copied

    def _is_media_file(self, filename: str) -> bool:
        ext = os.path.splitext(filename)[1].lower()
        return ext in self._media_extensions

    def _list_media_files(self, media_dir: str) -> List[str]:
        if not os.path.exists(media_dir):
            return []
        return [
            f for f in os.listdir(media_dir)
            if os.path.isfile(os.path.join(media_dir, f)) and self._is_media_file(f)
        ]

    # Champs JSON contenant des chemins de fichiers MÉDIAS (à rediriger vers media_dir)
    _PATH_KEYS = frozenset({
        'path', 'file_Path',
    })

    # Champs JSON contenant des chemins STRUCTURELS du projet CapCut (traitement séparé)
    _STRUCTURAL_KEYS = frozenset({
        'draft_root_path', 'draft_fold_path', 'draft_cover',
        'draft_removable_storage_device_path'
    })

    def _replace_all_media_paths(self, data, media_dir: str):
        """
        Remplace TOUS les chemins (relatifs ET absolus) par des chemins ABSOLUS vers media_dir.

        RÈGLE FONDAMENTALE : un chemin absolu d'origine (C:/..., D:/...) ne doit JAMAIS
        rester dans le JSON après import. Il est TOUJOURS remplacé par le chemin portable,
        que le fichier y existe ou non. Cela garantit que CapCut n'utilise jamais les
        fichiers originaux à la place des fichiers portables.

        Gère :
          - Chemins relatifs ./medias/  →  media_dir/filename  (absolu local)
          - Chemins relatifs ./medias/other/  →  media_dir/other/filename
          - Chemins absolus Windows (X:/)  →  media_dir/filename  (toujours remplacé)
        """
        paths_updated = 0
        paths_not_found = 0   # remplacés mais fichier absent du paquet portable
        paths_skipped = 0     # chemins vides ou non reconnus (ni relatif ./ ni absolu X:/)

        abs_media_dir = os.path.abspath(media_dir).replace('\\', '/')
        abs_other_dir = os.path.abspath(os.path.join(media_dir, 'other')).replace('\\', '/')

        def walk(obj):
            nonlocal paths_updated, paths_not_found, paths_skipped

            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in self._PATH_KEYS and isinstance(value, str) and value.strip():
                        original = value
                        new_path = None

                        # ── Cas 1 : chemin relatif ./ (produit par l'exporteur) ──────────────
                        if original.startswith('./'):
                            relative_path = original[2:]  # Enlever ./

                            if relative_path.startswith('medias/other/'):
                                filename = os.path.basename(relative_path)
                                new_path = os.path.abspath(
                                    os.path.join(media_dir, 'other', filename)
                                ).replace('\\', '/')
                            elif relative_path.startswith('medias/'):
                                filename = os.path.basename(relative_path)
                                new_path = os.path.abspath(
                                    os.path.join(media_dir, filename)
                                ).replace('\\', '/')
                            else:
                                # ./autre/chemin → media_dir/autre/chemin
                                new_path = os.path.abspath(
                                    os.path.join(media_dir, relative_path)
                                ).replace('\\', '/')

                        # ── Cas 2 : chemin absolu Windows (X:/) ──────────────────────────────
                        # TOUJOURS remplacé — jamais de fallback vers le fichier original.
                        elif len(original) > 1 and original[1] == ':':
                            filename = os.path.basename(original)
                            portable_other = os.path.abspath(
                                os.path.join(media_dir, 'other', filename)
                            ).replace('\\', '/')
                            portable_main = os.path.abspath(
                                os.path.join(media_dir, filename)
                            ).replace('\\', '/')

                            if os.path.exists(portable_other):
                                # Présent dans other/ (effet exporté)
                                new_path = portable_other
                            elif os.path.exists(portable_main):
                                # Présent dans media_dir/ (média exporté)
                                new_path = portable_main
                            else:
                                # Fichier absent du paquet portable (oubli d'export ou
                                # ressource interne CapCut non portable). On pointe quand même
                                # vers le répertoire portable : CapCut signalera le média
                                # manquant plutôt que d'utiliser silencieusement l'original.
                                new_path = portable_main
                                paths_not_found += 1
                                logger.warning(
                                    f"[{key}] Fichier absent du paquet portable, "
                                    f"chemin prévu : {portable_main}  "
                                    f"(original ignoré : {original})"
                                )

                        else:
                            # Chemin non reconnu (vide après strip, ou format inconnu)
                            paths_skipped += 1
                            logger.debug(f"[{key}] chemin non traité (format inconnu) : {original}")

                        # Appliquer le nouveau chemin
                        if new_path is not None:
                            obj[key] = new_path
                            paths_updated += 1
                            logger.debug(f"[{key}] remplacé : {original!r}  →  {new_path!r}")
                    else:
                        walk(value)

            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(data)
        logger.info(
            f"Remplacement chemins terminé : {paths_updated} mis à jour, "
            f"{paths_not_found} absents du portable (mis à jour quand même), "
            f"{paths_skipped} ignorés"
        )
        return paths_updated, paths_not_found

    def _fix_structural_paths(self, data, target_project_dir: str, capcut_draft_path: str):
        """
        Second passage après _replace_all_media_paths :
        met à jour les clés STRUCTURELLES de CapCut avec les vrais chemins locaux.

        Ces clés ne sont PAS des chemins de médias — elles indiquent à CapCut
        où se trouve le dossier projet sur cette machine.

        draft_fold_path  → dossier du projet importé  (target_project_dir)
        draft_root_path  → dossier racine des drafts   (capcut_draft_path)
        draft_cover      → image de couverture dans le dossier projet
        draft_removable_storage_device_path → vide (n'a plus de sens après import)
        """
        abs_project_dir = os.path.abspath(target_project_dir).replace('\\', '/')
        abs_draft_root  = os.path.abspath(capcut_draft_path).replace('\\', '/')
        abs_cover       = os.path.join(abs_project_dir, 'draft_cover.jpg').replace('\\', '/')

        fixed_values = {
            'draft_fold_path':                    abs_project_dir,
            'draft_root_path':                    abs_draft_root,
            'draft_cover':                        abs_cover,
            'draft_removable_storage_device_path': '',
        }

        keys_updated = 0

        def walk(obj):
            nonlocal keys_updated
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in self._STRUCTURAL_KEYS:
                        new_val = fixed_values[key]
                        if obj[key] != new_val:
                            logger.debug(f"[structural] {key}: {value!r}  →  {new_val!r}")
                            obj[key] = new_val
                            keys_updated += 1
                    else:
                        walk(value)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(data)
        logger.info(f"Chemins structurels corrigés : {keys_updated} clé(s) mise(s) à jour")

    def _process_draft_file(self, source_path: str, target_path: str, media_dir: str, project_root: str):
        """Traite draft_content.json — remplace TOUS les chemins (path + file_Path) par l'absolu local."""
        logger.debug(f"Traitement du fichier draft : {source_path}")
        logger.debug(f"Répertoire médias : {media_dir}")

        try:
            with open(source_path, 'r', encoding='utf-8') as f:
                draft_data = json.load(f)

            # 1. Remplacer les chemins médias (./medias/... → absolu local)
            updated, not_found = self._replace_all_media_paths(draft_data, media_dir)

            # 2. Corriger les chemins structurels (draft_fold_path, draft_root_path…)
            #    project_root est target_project_dir ; on remonte d'un niveau pour capcut_draft_path
            capcut_draft_path = os.path.dirname(project_root)
            self._fix_structural_paths(draft_data, project_root, capcut_draft_path)

            with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(draft_data, f, indent=2, ensure_ascii=False)

            logger.info(
                f"draft_content.json traité : {updated} chemins mis à jour, "
                f"{not_found} fichiers absents du portable"
            )

        except Exception as e:
            logger.error(f"Erreur lors du traitement du fichier draft : {e}")
            raise

    def _process_meta_file(self, source_path: str, target_path: str, media_dir: str, project_root: str):
        """Traite draft_meta_info.json — remplace TOUS les chemins (path + file_Path) par l'absolu local."""
        logger.debug(f"Traitement du fichier meta : {source_path}")

        try:
            with open(source_path, 'r', encoding='utf-8') as f:
                meta_data = json.load(f)

            # 1. Remplacer les chemins médias
            updated, not_found = self._replace_all_media_paths(meta_data, media_dir)

            # 2. Corriger les chemins structurels — c'est surtout dans meta_info qu'ils apparaissent
            capcut_draft_path = os.path.dirname(project_root)
            self._fix_structural_paths(meta_data, project_root, capcut_draft_path)

            with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, indent=2, ensure_ascii=False)

            logger.info(
                f"draft_meta_info.json traité : {updated} chemins mis à jour, "
                f"{not_found} fichiers absents du portable"
            )

        except Exception as e:
            logger.error(f"Erreur lors du traitement du fichier meta : {e}")
            raise

    def _copy_media_files(self, source_dir: str, target_dir: str, progress_callback=None) -> int:
        """Copy media files to target location"""
        logger.debug(f"Copying media files: {source_dir} -> {target_dir}")

        files_copied = 0

        try:
            if not os.path.exists(source_dir):
                logger.warning("Media source directory not found")
                return 0

            # Copy files and directories
            for item in os.listdir(source_dir):
                source_path = os.path.join(source_dir, item)
                target_path = os.path.join(target_dir, item)

                if os.path.isfile(source_path):
                    shutil.copy2(source_path, target_path)
                    files_copied += 1
                    logger.debug(f"Copied media file: {item}")
                elif os.path.isdir(source_path):
                    # Copy subdirectories (like 'other/')
                    shutil.copytree(source_path, target_path, dirs_exist_ok=True)
                    # Count files in subdirectory
                    for root, dirs, files in os.walk(source_path):
                        files_copied += len(files)
                    logger.debug(f"Copied media directory: {item}")

            if progress_callback:
                progress_callback(35, f"Fichiers médias copiés: {files_copied}", "media_copied")

        except Exception as e:
            logger.error(f"Error copying media files: {e}")
            raise

        return files_copied

    def _verify_import(self, project_dir: str, media_dir: Optional[str] = None) -> bool:
        logger.debug(f"🔍 Début vérification de l'import : {project_dir}")

        # ✅ Fichiers JSON à IGNORER (non critiques ou souvent vides/corrompus)
        IGNORE_JSON_FILES = {
            'draft_biz_config.json',          # ← PROBLÈME PRINCIPAL : souvent vide
            'draft_cache_config.json',
            'draft_temp_config.json',
            'draft_removable_storage_device_path.json',
            'template.tmp',                   # Fichiers temporaires CapCut
            'template-2.tmp',
            'performance_opt_info.json',      # Non critique
            'key_value.json',                 # Non critique
        }

        # ✅ Fichiers JSON CRITIQUES à vérifier absolument
        CRITICAL_JSON_FILES = {'draft_content.json', 'draft_meta_info.json'}

        abs_project_dir = self._abspath_norm(project_dir)
        abs_media_dir = self._abspath_norm(media_dir) if media_dir else None
        abs_other_dir = self._abspath_norm(os.path.join(media_dir, 'other')) if media_dir else None
        abs_draft_root = self._abspath_norm(os.path.dirname(project_dir))

        def _value_is_local(value: str, key: str) -> bool:
            if not isinstance(value, str) or not value.strip():
                return True

            normalized = value.strip().replace('\\', '/')

            # Chemins structurels
            if key == 'draft_root_path':
                return self._is_under_dir(normalized, abs_draft_root)
            if key == 'draft_fold_path':
                return self._is_under_dir(normalized, abs_project_dir)
            if key == 'draft_cover':
                return self._is_under_dir(normalized, abs_project_dir)
            if key == 'draft_removable_storage_device_path':
                return value == ''

            # Rejeter les chemins relatifs non résolus
            if normalized.startswith(('./', '../', 'medias/', '.\\', '..\\')):
                return False

            # Accepter les chemins sous les répertoires médias
            if abs_media_dir is not None:
                if self._is_under_dir(normalized, abs_media_dir):
                    return True
                if abs_other_dir is not None and self._is_under_dir(normalized, abs_other_dir):
                    return True

            # Vérification des chemins absolus
            if self._looks_like_path_value(normalized) or self._is_path_like_key(key):
                return os.path.isabs(normalized) and (
                    self._is_under_dir(normalized, abs_project_dir)
                    or (abs_media_dir is not None and self._is_under_dir(normalized, abs_media_dir))
                    or (abs_other_dir is not None and self._is_under_dir(normalized, abs_other_dir))
                    or self._is_under_dir(normalized, abs_draft_root)
                )
            return True

        def _collect_bad_paths(data, ctx="root") -> List[str]:
            bad: List[str] = []
            def walk(obj, current_ctx="root"):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if isinstance(value, str) and (self._is_path_like_key(key) or self._looks_like_path_value(value)):
                            if not _value_is_local(value, key):
                                bad.append(f"{current_ctx}.{key}: {value}")
                        else:
                            walk(value, f"{current_ctx}.{key}")
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        walk(item, f"{current_ctx}[{i}]")
            walk(data, ctx)
            return bad

        try:
            # 1. Lister tous les fichiers JSON du projet
            json_files = []
            for root, _, files in os.walk(project_dir):
                for filename in files:
                    if filename.lower().endswith('.json'):
                        json_files.append(os.path.join(root, filename))

            if not json_files:
                logger.error("❌ Aucun fichier JSON trouvé après import")
                return False

            # 2. Vérifier que les fichiers critiques existent
            critical_files_found = any(
                os.path.exists(os.path.join(project_dir, fname))
                for fname in CRITICAL_JSON_FILES
            )
            if not critical_files_found:
                logger.error(f"❌ Fichiers critiques manquants: {CRITICAL_JSON_FILES}")
                return False

            # 3. Vérifier chaque fichier JSON
            any_invalid = False
            critical_files_verified = set()

            for json_path in json_files:
                filename = os.path.basename(json_path)
                logger.debug(f"📄 Vérification de: {filename}")

                # ✅ IGNORER les fichiers non critiques
                if filename in IGNORE_JSON_FILES:
                    logger.debug(f"⏭️  Fichier ignoré (non critique): {filename}")
                    continue

                # ✅ Marquer les fichiers critiques comme vérifiés
                if filename in CRITICAL_JSON_FILES:
                    critical_files_verified.add(filename)

                try:
                    # Lire le contenu du fichier
                    with open(json_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()

                    # Ignorer les fichiers vides
                    if not content:
                        logger.warning(f"⚠️  Fichier JSON vide ignoré: {filename}")
                        continue

                    # Tenter de parser le JSON
                    try:
                        data = json.loads(content)
                    except json.JSONDecodeError as je:
                        logger.warning(f"⚠️  Fichier JSON invalide ignoré: {filename} - {je}")
                        continue

                except Exception as e:
                    logger.warning(f"⚠️  Erreur lecture de {filename} ignorée: {e}")
                    continue

                # Vérifier les chemins dans les fichiers valides
                bad_paths = _collect_bad_paths(data, os.path.relpath(json_path, project_dir))
                if bad_paths:
                    any_invalid = True
                    logger.error(f"❌ Chemins non locaux dans {filename}:")
                    for path in bad_paths:
                        logger.error(f"   - {path}")

            # 4. Vérifier que tous les fichiers critiques ont été vérifiés
            if not critical_files_verified:
                missing = CRITICAL_JSON_FILES - critical_files_verified
                logger.error(f"❌ Fichiers critiques non vérifiés: {missing}")
                return False

            if any_invalid:
                logger.error("❌ Des chemins non locaux ont été détectés")
                return False

            # 5. Vérification optionnelle du dossier médias (non bloquante)
            if media_dir and os.path.exists(media_dir):
                media_files = self._list_media_files(media_dir)
                if not media_files:
                    logger.warning("⚠️  Répertoire médias vide (non bloquant)")

            logger.info("✅ Vérification réussie - tous les chemins critiques sont valides")
            return True

        except Exception as e:
            logger.error(f"❌ Échec inattendu de la vérification: {e}", exc_info=True)
            return False

    def get_media_location_options(self, capcut_draft_path: str, project_name: str) -> List[Dict]:
        """Get available media location options"""
        options = []

        project_media_path = os.path.join(capcut_draft_path, project_name, 'medias')
        options.append({
            'id': 'project',
            'name': 'Dans le dossier du projet',
            'path': project_media_path,
            'description': 'Les médias seront placés dans le dossier du projet CapCut'
        })

        common_locations = [
            ('Bureau', os.path.join(os.path.expanduser('~'), 'Desktop')),
            ('Documents', os.path.join(os.path.expanduser('~'), 'Documents')),
            ('Vidéos', os.path.join(os.path.expanduser('~'), 'Videos')),
            ('Téléchargements', os.path.join(os.path.expanduser('~'), 'Downloads'))
        ]

        for name, path in common_locations:
            if os.path.exists(path):
                media_path = os.path.join(path, 'CapCut_Medias')
                options.append({
                    'id': f'custom_{name.lower()}',
                    'name': f'Dossier {name}',
                    'path': media_path,
                    'description': f'Les médias seront placés dans {name}/CapCut_Medias'
                })

        options.append({
            'id': 'custom',
            'name': 'Emplacement personnalisé',
            'path': '',
            'description': 'Choisissez un emplacement personnalisé pour les médias'
        })

        return options
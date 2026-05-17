# CapCut Project Exporter & Importer: Capcut Manager

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![CapCut Version](https://img.shields.io/badge/CapCut-8.5.0-green.svg)](https://www.capcut.com/)

**A powerful, open-source tool for exporting and importing CapCut projects to/from portable ZIP archives, with automatic path conversion between absolute and relative paths.**

> ⚠️ **Important Warning**: This tool is **not affiliated with CapCut** or Bytedance. Always verify that imported projects work correctly in CapCut **before** deleting your original project files. The tool may fail in some cases, and data loss can occur if you delete originals without verification.

Last version: B v1.0.1
---

## 🌟 Features

### ✅ **Fully Implemented & Tested**

#### Export Features
- **Automatic project detection**: Automatically locates all CapCut projects in `%LOCALAPPDATA%\CapCut\User Data\Projects\`
- **Portable ZIP export**: Creates self-contained ZIP archives with all media files and relative paths
- **Comprehensive media support**: Handles videos, audio, images, stickers, effects, transitions, text, and canvas elements
- **Smart duplicate handling**: Detects and prevents duplicate media files in exports
- **Real-time progress tracking**: Live updates during export via web interface
- **Detailed logging**: Comprehensive logs saved to `logs/` directory for debugging
- **Pre-export diagnostics**: Checks project integrity before export
- **Path conversion**: Automatically converts absolute paths to relative paths (`./medias/...`)

#### Import Features
- **ZIP import**: Import projects from portable ZIP archives
- **Folder import**: Import from extracted project directories
- **Path restoration**: Converts relative paths back to absolute local paths
- **Structural path handling**: Correctly updates CapCut structural paths (`draft_fold_path`, `draft_root_path`, `draft_cover`)
- **Flexible media locations**: Choose where to place media files (project folder or custom path)
- **Import verification**: Validates that all paths are local and absolute after import
- **Progress tracking**: Real-time updates during import operations

#### Web Interface
- **Modern, responsive UI**: Built with vanilla HTML/CSS/JS (no external framework dependencies)
- **Multi-language support**: English, French, Spanish, Japanese, Simplified Chinese (fully functional)
- **Theme support**: Dark and light modes (fully functional)
- **Project browser**: View all detected projects with metadata
- **Search functionality**: Filter projects by name
- **Export/import wizards**: Step-by-step guided processes
- **Cancel operations**: Ability to cancel ongoing exports/imports

### ⚠️ **Partially Implemented / UI-Only Features**

The following features **appear in the UI** but are **not fully connected to the backend** or **not fully tested**:

| Feature | Status | Details |
|---------|--------|---------|
| Compression format settings | UI only | ZIP/7Z/TAR selection exists but only ZIP is implemented |
| Compression level | UI only | Fast/Normal/Maximum selection exists but not used |
| Auto-cleanup of temp files | Not implemented | Feature exists in UI but not in code |
| Include templates in export | Not implemented | Feature exists in UI but not in code |
| Processing timeout | UI only | Setting exists but not enforced |
| Max file size limit | UI only | Setting exists but not enforced |
| Debug mode | UI only | Setting exists but logging is always detailed |
| Auto-detect on startup | Partially implemented | Detection works but may need manual refresh |
| Test paths functionality | Not implemented | Button exists but no backend implementation |
| Export/import configuration | Not implemented | Buttons exist but no functionality |
| Missing files handling | Partially implemented | Placeholder creation exists but not fully integrated |

---

## 📋 Requirements

- **Operating System**: Windows 10/11 (tested)
- **CapCut Version**: 8.5.0 (tested and confirmed working)
- **Python**: 3.7 or higher
- **Web Browser**: Modern browser (Chrome, Firefox, Edge, etc.)
- **Disk Space**: Sufficient space for temporary files during export/import

### Python Dependencies

```bash
Flask==2.3.3
Werkzeug==2.3.7
```

---

## 🚀 Installation

### Quick Start

1. **Clone or download this repository**

2. **Install Python dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Ensure CapCut is installed** on your computer with at least one saved project

4. **Start the web server**:

   ```bash
   python web_server.py
   ```

   Or use the provided batch file (Windows):

   ```batch
   start.bat
   ```

5. **Open your browser** and navigate to `http://localhost:5000`

---

## 📖 Usage

### Web Interface (Recommended)

#### Exporting a Project

1. The dashboard automatically detects your CapCut projects
2. Browse the list of detected projects with their metadata (name, duration, media count, size)
3. Use the search bar to filter projects by name
4. Click on a project card to view details
5. Click **"Préparer l'export"** (Prepare Export) to run pre-export diagnostics
6. Choose a save location or use the temporary directory
7. Click **"Démarrer"** (Start) to begin the export
8. Monitor real-time progress
9. Once complete, **download the ZIP file** and **verify it imports correctly in CapCut** before deleting originals

#### Importing a Project

1. Navigate to the Import section (click "Import" in the sidebar)
2. Select a ZIP file or folder containing your portable project
3. Click **"Analyser la source"** (Analyze Source) to detect project information
4. Configure import settings:
   - Project name
   - Media location (in project folder or custom path)
5. Click **"Démarrer l'import"** (Start Import)
6. Monitor real-time progress
7. Once complete, the project will be available in your CapCut drafts folder

#### Settings

- **Language**: Change the interface language (fully functional)
- **Theme**: Switch between dark and light modes (fully functional)
- **CapCut Paths**: Manually configure CapCut draft and installation paths
- **Export Settings**: Configure compression and other options (UI only, not fully implemented)

---

## 📁 Project Structure

### Exported Project Format

```text
portable_capcut_project/
├── project/                      # Project files with relative paths
│   ├── draft_content.json        # Main project file (paths converted)
│   ├── draft_meta_info.json      # Project metadata (paths converted)
│   ├── draft_cover.jpg           # Project thumbnail
│   └── ...                       # Other project JSON files
├── medias/                       # All media files
│   ├── video_file1.mp4           # Video files
│   ├── audio_file1.mp3           # Audio files
│   ├── image_file1.png           # Image files
│   └── other/                    # Special files (effects, cache, etc.)
│       ├── effect1.beat
│       └── ...
└── export_info.json             # Optional export metadata
```

### Source Code Structure

```text
.
├── capcut_exporter.py
├── capcut_importer.py
├── capcut_detector.py
├── web_server.py
├── templates/
│   └── index.html
├── params.json
├── translations.jsonl
├── requirements.txt
├── start.bat
└── README.md
```

---

## 🔧 Configuration

The tool uses `params.json` for configuration. Currently, only these settings are **fully functional**:

```json
{
  "language": "en",              // Interface language (en, fr, es, ja, zh_CN)
  "theme": "dark",               // UI theme (dark, light)
  "capcut_draft_path": "",        // Custom CapCut drafts path (auto-detected if empty)
  "capcut_exe_path": ""          // CapCut executable path (not used currently)
}
```

> ⚠️ **Note**: Other settings in the UI (compression format, timeout, file size limits, etc.) are **not functional** in the current version.

---

## 🌍 Supported Languages

The web interface supports the following languages:

| Language | Code | Status |
|----------|------|--------|
| English | `en` | ✅ translated |
| French | `fr` | ✅ Fully translated |
| Spanish | `es` | ✅ translated |
| Japanese | `ja` | ✅ translated |
| Simplified Chinese | `zh_CN` | ✅ translated |

Language can be changed in the Settings panel.

---

## 🎬 Supported Media Formats

### Video
`.mp4`, `.mov`, `.avi`, `.mkv`, `.wmv`, `.flv`, `.webm`

### Audio
`.mp3`, `.wav`, `.aac`, `.ogg`, `.flac`, `.m4a`

### Images
`.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.tiff`, `.webp`

### Other
Effect files (`.beat`), cache files, and other CapCut-specific assets are placed in `medias/other/`

---

## 🔌 REST API

The web server provides the following API endpoints:

### Export Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/projects` | List all detected CapCut projects |
| POST | `/api/export` | Start a project export (returns `export_id`) |
| GET | `/api/progress/<export_id>` | Get real-time export progress |
| POST | `/api/prepare-export` | Run pre-export diagnostics |
| POST | `/api/cancel-export` | Cancel an ongoing export |
| GET | `/api/browse-folders` | Get available save locations |
| GET | `/api/download/<filename>` | Download exported ZIP file |

### Import Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/import/analyze` | Analyze import source (ZIP or folder) |
| POST | `/api/import/media-options` | Get available media location options |
| POST | `/api/import/execute` | Start an import process (returns `import_id`) |
| GET | `/api/import/progress/<import_id>` | Get real-time import progress |
| POST | `/api/import/cancel` | Cancel an ongoing import |
| POST | `/api/import/upload` | Upload ZIP file for import |

### Configuration Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config/capcut-path` | Get stored CapCut draft path |
| POST | `/api/config/capcut-path` | Set CapCut draft path |
| POST | `/api/config/validate-path` | Validate a CapCut projects path |
| GET | `/api/capcut/detect` | Auto-detect CapCut draft folder |
| POST | `/api/capcut/validate-manual` | Validate manually selected path |
| GET | `/api/capcut/check-saved` | Check if saved path is still valid |

---

## ⚠️ Important Warnings & Limitations

### Critical Warnings

1. **⚠️ ALWAYS VERIFY IMPORTS BEFORE DELETING ORIGINALS**
   - The tool may fail in some cases
   - Some projects may not import correctly
   - **Never delete your original CapCut projects until you've confirmed the import works**

2. **⚠️ Not Officially Supported**
   - This is a community tool, not affiliated with CapCut
   - CapCut may change its project format in future versions
   - No guarantee of compatibility with future CapCut versions

3. **⚠️ Encrypted Projects**
   - Recent CapCut versions may encrypt project files
   - This tool **cannot** export/import encrypted projects

### Known Limitations

| Limitation | Details |
|------------|---------|
| Windows only | Uses Windows-specific paths (`%LOCALAPPDATA%`) |
| Single-user | Designed for single-user systems |
| No encryption | Projects are exported as plain ZIP files |
| No cloud sync | Local tool only, no cloud integration |
| Partial settings | Only language and theme settings are functional |
| No update system | Manual updates required |
| No error recovery | If export/import fails, you may need to restart |

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| No projects detected | CapCut not installed or no projects created | Install CapCut and create a project |
| Export fails | Missing media files | Check that all media files still exist at their original paths |
| Import fails | Incompatible CapCut version | Use the same CapCut version for export and import |
| ZIP won't open in CapCut | Corrupted project file | Check logs and try again |
| Missing media after import | Files weren't in the export | Re-export with all media files included |

---

## 🛠️ Troubleshooting

### Export Problems

#### "No projects found"
- **Solution 1**: Ensure CapCut is installed correctly
- **Solution 2**: Create at least one project in CapCut and save it
- **Solution 3**: Manually specify the CapCut draft path in Settings
- **Solution 4**: Check the logs in the `logs/` directory for detailed error messages

#### "Error while copying media"
- **Cause**: Source media files may have been moved or deleted
- **Solution**: Ensure all media files exist at their original paths before exporting

#### "ZIP does not open in CapCut"
- **Solution 1**: Verify that `draft_content.json` is not corrupted
- **Solution 2**: Check that all media files were successfully copied to the `medias/` folder
- **Solution 3**: Try importing on the same CapCut version used for export

### Import Problems

#### "Import verification failed"
- **Cause**: ZIP file structure is incorrect or missing required files
- **Solution**: Ensure the ZIP contains both `project/` and `medias/` folders with a valid `draft_content.json`

#### "Missing media files after import"
- **Cause**: Some media files were not present in the original export
- **Solution**: CapCut will show missing media indicators; you can replace them manually

#### "Project not showing in CapCut"
- **Solution 1**: Verify that the import path matches your CapCut installation
- **Solution 2**: Check that structural paths (`draft_fold_path`, `draft_root_path`) are correct
- **Solution 3**: Restart CapCut to refresh the project list

### General Troubleshooting

1. **Check the logs**: All operations are logged to `logs/capcut_exporter_YYYYMMDD_HHMMSS.log`
2. **Enable debug mode**: Set `"debug_mode": true` in `params.json` for more detailed logs
3. **Verify paths**: Ensure CapCut is installed in the default location or update the path in Settings
4. **Try a different project**: Some projects may have issues; try exporting a different one

---

## 🎯 Use Cases

✅ **Transfer between computers**: Export projects on one PC and import on another
✅ **Backup**: Create self-contained backup archives of your projects
✅ **Sharing**: Easily share complete projects with collaborators
✅ **Organization**: Archive old projects without losing media files
✅ **Version control**: Store project snapshots for version history
✅ **Disaster recovery**: Protect against accidental project deletion

---

## 📝 Technical Notes

### How Export Works

1. **Project Detection**: Scans `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft*` for project folders
2. **Path Analysis**: Reads `draft_content.json` to find all media file references
3. **Media Collection**: Copies all referenced media files to a temporary `medias/` folder
4. **Path Conversion**: Updates all file paths in JSON files to use relative paths (`./medias/filename.ext`)
5. **Structural Paths**: Updates CapCut-specific paths (`draft_fold_path`, `draft_root_path`, etc.)
6. **Effect Files**: Copies effect files and special assets to `medias/other/`
7. **ZIP Creation**: Creates a portable ZIP archive containing the `project/` and `medias/` folders

### How Import Works

1. **Source Analysis**: Extracts ZIP or reads folder structure to detect project info
2. **Path Resolution**: Converts relative paths (`./medias/...`) to absolute local paths
3. **Media Copying**: Copies media files to the specified location
4. **Project Copying**: Copies project files to the CapCut drafts folder
5. **Path Rewriting**: Updates all JSON files to use absolute local paths
6. **Structural Updates**: Sets correct CapCut structural paths for the target system
7. **Verification**: Ensures no relative or external paths remain in the project files

### Path Handling

The tool handles three types of paths:

1. **Media Paths** (`path`, `file_Path`): Point to media files (videos, audio, images)
   - Export: Absolute → Relative (`./medias/filename.ext`)
   - Import: Relative → Absolute (local system path)

2. **Structural Paths** (`draft_fold_path`, `draft_root_path`, `draft_cover`):
   - Export: Absolute → Relative (`./`, `./project`, `./project/draft_cover.jpg`)
   - Import: Relative → Absolute (target system paths)

3. **Effect Paths**: Special files (`.beat`, cache, etc.)
   - Copied to `medias/other/` during export
   - Paths updated accordingly

---

## 🤝 Contributing

Contributions are welcome! Feel free to:

- **Report bugs**: Open an issue with details about the problem
- **Suggest features**: Share your ideas for improvements
- **Submit pull requests**: Fix bugs or add new features
- **Improve translations**: Help translate to more languages
- **Fork the project**: Use it as a base for your own tools

### How to Contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Areas Needing Work

- [ ] Implement compression format options (7Z, TAR)
- [ ] Implement compression level settings
- [ ] Add auto-cleanup of temporary files
- [ ] Add template inclusion in exports
- [ ] Implement processing timeout enforcement
- [ ] Add max file size limit enforcement
- [ ] Complete debug mode implementation
- [ ] Implement auto-detection on startup
- [ ] Add path testing functionality
- [ ] Implement export/import configuration save/load
- [ ] Improve missing files handling
- [ ] Add support for encrypted projects
- [ ] Add Linux/macOS support
- [ ] Add unit tests
- [ ] Improve error handling and recovery

---

## 📄 License

This project is **open source** and available under the **[MIT License](https://opensource.org/licenses/MIT)**.

You are free to:
- ✅ Use the software for any purpose
- ✅ Modify the source code
- ✅ Distribute the software
- ✅ Use it commercially
- ✅ Fork and create derivative works

**No attribution is required**, though a link back to the original project is appreciated.

---

## 🙏 Acknowledgments

- **CapCut**: For creating an amazing video editing tool
- **Flask**: For the lightweight web framework
- **Font Awesome**: For the icons used in the web interface
- **Google Fonts**: For the Plus Jakarta Sans font
- **All contributors**: For their valuable feedback and contributions

---

## 📞 Support

For support, questions, or bug reports:

1. **Check the README**: Most common issues are documented here
2. **Check the logs**: Detailed error information is in `logs/`
3. **Open an issue**: On the GitHub repository
4. **Fork and fix**: Feel free to submit a pull request

---

**Enjoy using CapCut Project Exporter & Importer!** 🎬

> **Remember**: Always verify imports before deleting originals. The tool is provided as-is with no guarantees. Use at your own risk.

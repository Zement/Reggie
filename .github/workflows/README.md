# GitHub Actions Workflows

## Build Workflow (`build.yml`)

Automatically builds Reggie! Next for Windows, macOS, and Linux on every push to `master` or `develop` branches.

### Triggers
- **Push** to `master` or `develop` branches
- **Pull requests** to `master` or `develop`
- **Tags** starting with `v` (e.g., `v4.9.1`)
- **Manual trigger** via GitHub Actions UI

### Build Platforms
- **Windows** (windows-latest)
- **macOS** (macos-latest)
- **Linux** (ubuntu-latest)

### Artifacts
Build artifacts are uploaded for each platform and retained for 30 days:
- `reggie-next-vX.X.X-windows`
- `reggie-next-vX.X.X-macos`
- `reggie-next-vX.X.X-linux`

### Releases
When you push a tag (e.g., `git tag v4.9.1 && git push origin v4.9.1`), the workflow automatically:
1. Builds for all platforms
2. Creates a GitHub Release
3. Uploads all build artifacts to the release

### Local Testing
To test the build locally before pushing:
```bash
# Windows
.\build_reggie.bat

# macOS/Linux
python -OO build_reggie.py
```

### Requirements
- Python 3.10+
- PyQt6
- nsmblib
- PyInstaller

All dependencies are automatically installed by the workflow.

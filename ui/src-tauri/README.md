# RaceLab Garage Desktop Shell

This is a minimal Tauri 2 desktop shell for RaceLab Garage.

Normal development launch from the project root:

```powershell
.\scripts\start_desktop.ps1
```

The Tauri dev workflow may use the local Vite server internally at `127.0.0.1`, but users should launch the desktop app instead of opening a browser URL.

Production builds load bundled local assets from `ui/dist`:

```powershell
.\scripts\build_desktop.ps1
```

Tauri requires a Windows `.ico` file at `ui/src-tauri/icons/icon.ico`. The current icon is a local placeholder and can be replaced later with final branding.

Native file dialogs and app settings are still future work. Cloud sync, remote analytics, updater wiring, and external runtime services are intentionally not enabled.

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            app.manage(BackendProcess::start(app.path().resource_dir().ok()));
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                window.app_handle().state::<BackendProcess>().stop();
            }
        })
        .run(tauri::generate_context!())
        .expect("failed to run RacerZLab Tauri shell");
}

use std::{
    fs,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
};
use tauri::Manager;

const BACKEND_EXE: &str = "racerzlab-backend.exe";
const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_PORT: &str = "8010";

struct BackendProcess {
    child: Mutex<Option<Child>>,
}

impl BackendProcess {
    fn start(resource_dir: Option<PathBuf>) -> Self {
        let child = match find_backend_sidecar(resource_dir) {
            Some(path) => start_backend_sidecar(path),
            None => {
                eprintln!("RacerZLab backend sidecar was not found.");
                None
            }
        };
        Self {
            child: Mutex::new(child),
        }
    }

    fn stop(&self) {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(mut child) = guard.take() {
                terminate_backend_process(&mut child);
            }
        }
    }
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        self.stop();
    }
}

fn start_backend_sidecar(path: PathBuf) -> Option<Child> {
    let mut command = Command::new(path);
    command
        .arg("--host")
        .arg(BACKEND_HOST)
        .arg("--port")
        .arg(BACKEND_PORT)
        .env("RACERZLAB_BACKEND_HOST", BACKEND_HOST)
        .env("RACERZLAB_BACKEND_PORT", BACKEND_PORT)
        .env("RACERZLAB_BACKEND_LOG", backend_log_path())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    match command.spawn() {
        Ok(child) => Some(child),
        Err(error) => {
            eprintln!("RacerZLab backend sidecar failed to start: {error}");
            None
        }
    }
}

#[cfg(windows)]
fn terminate_backend_process(child: &mut Child) {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x08000000;

    let pid = child.id().to_string();
    let _ = Command::new("taskkill")
        .arg("/PID")
        .arg(pid)
        .arg("/T")
        .arg("/F")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .creation_flags(CREATE_NO_WINDOW)
        .status();
    let _ = child.kill();
    let _ = child.wait();
}

#[cfg(not(windows))]
fn terminate_backend_process(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}

fn find_backend_sidecar(resource_dir: Option<PathBuf>) -> Option<PathBuf> {
    backend_sidecar_candidates(resource_dir)
        .into_iter()
        .find(|path| path.is_file())
}

fn backend_sidecar_candidates(resource_dir: Option<PathBuf>) -> Vec<PathBuf> {
    let mut candidates = Vec::new();

    if let Some(resource_dir) = resource_dir {
        candidates.push(resource_dir.join(BACKEND_EXE));
        candidates.push(resource_dir.join("bin").join(BACKEND_EXE));
    }

    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            candidates.push(exe_dir.join(BACKEND_EXE));
            candidates.push(exe_dir.join("bin").join(BACKEND_EXE));
            candidates.push(exe_dir.join("resources").join("bin").join(BACKEND_EXE));
            candidates.push(exe_dir.join("..").join("Resources").join("bin").join(BACKEND_EXE));
        }
    }

    candidates.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("bin").join(BACKEND_EXE));
    candidates
}

fn backend_log_path() -> PathBuf {
    let base = std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let dir = base.join("RacerZLab").join("logs");
    let _ = fs::create_dir_all(&dir);
    dir.join("backend.log")
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default();

    // This must be the first desktop plugin. A second launch focuses the
    // existing window and never reaches setup, so it cannot spawn or attach to
    // an ambiguous fixed-port backend process.
    #[cfg(desktop)]
    {
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.show();
                let _ = window.set_focus();
            }
        }));
    }

    builder
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            backend_capability_token,
            backend_instance_token,
            ensure_backend_running,
        ])
        .setup(|app| {
            let storage_paths = BackendStoragePaths::prepare(
                app.path().app_local_data_dir()?,
            )?;
            let backend_process = BackendProcess::start(
                app.path().resource_dir().ok(),
                storage_paths,
            )?;
            app.manage(backend_process);
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
    io,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
    time::{SystemTime, UNIX_EPOCH},
};
use tauri::Manager;

const BACKEND_EXE: &str = "racerzlab-backend.exe";
const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_PORT: &str = "8010";

#[derive(Clone, Debug, Eq, PartialEq)]
struct BackendStoragePaths {
    root: PathBuf,
    database: PathBuf,
    data: PathBuf,
    log: PathBuf,
}

impl BackendStoragePaths {
    fn prepare(root: PathBuf) -> io::Result<Self> {
        if !root.is_absolute() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "backend storage root must be absolute",
            ));
        }

        let data = root.join("data");
        let log_directory = root.join("logs");
        fs::create_dir_all(&data)?;
        fs::create_dir_all(&log_directory)?;

        Ok(Self {
            database: root.join("racelab.sqlite"),
            log: log_directory.join("backend.log"),
            data,
            root,
        })
    }
}

struct BackendProcess {
    child: Mutex<Option<Child>>,
    capability_token: String,
    instance_token: String,
    resource_dir: Option<PathBuf>,
    storage_paths: BackendStoragePaths,
}

impl BackendProcess {
    fn start(
        resource_dir: Option<PathBuf>,
        storage_paths: BackendStoragePaths,
    ) -> io::Result<Self> {
        let capability_token = backend_capability_token_value()?;
        let instance_token = backend_instance_token_value();
        let child = match find_backend_sidecar(resource_dir.clone()) {
            Some(path) => start_backend_sidecar(
                path,
                &instance_token,
                &capability_token,
                &storage_paths,
            ),
            None => {
                eprintln!("RacerZLab backend sidecar was not found.");
                None
            }
        };
        Ok(Self {
            child: Mutex::new(child),
            capability_token,
            instance_token,
            resource_dir,
            storage_paths,
        })
    }

    fn stop(&self) {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(mut child) = guard.take() {
                terminate_backend_process(&mut child);
            }
        }
    }

    fn ensure_running(&self) -> bool {
        let Ok(mut guard) = self.child.lock() else {
            return false;
        };
        if let Some(child) = guard.as_mut() {
            match child.try_wait() {
                Ok(None) => return true,
                Ok(Some(_)) | Err(_) => {
                    *guard = None;
                }
            }
        }
        let Some(path) = find_backend_sidecar(self.resource_dir.clone()) else {
            return false;
        };
        *guard = start_backend_sidecar(
            path,
            &self.instance_token,
            &self.capability_token,
            &self.storage_paths,
        );
        guard.is_some()
    }
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        self.stop();
    }
}

fn backend_instance_token_value() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default();
    format!("{}-{nanos:x}", std::process::id())
}

fn backend_capability_token_value() -> io::Result<String> {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut bytes = [0_u8; 32];
    getrandom::fill(&mut bytes)
        .map_err(|_| io::Error::other("failed to generate backend capability token"))?;

    let mut token = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        token.push(HEX[(byte >> 4) as usize] as char);
        token.push(HEX[(byte & 0x0f) as usize] as char);
    }
    Ok(token)
}

#[tauri::command]
fn backend_capability_token(process: tauri::State<'_, BackendProcess>) -> String {
    process.capability_token.clone()
}

#[tauri::command]
fn backend_instance_token(process: tauri::State<'_, BackendProcess>) -> String {
    process.instance_token.clone()
}

#[tauri::command]
fn ensure_backend_running(process: tauri::State<'_, BackendProcess>) -> bool {
    process.ensure_running()
}

fn backend_sidecar_command(
    path: PathBuf,
    instance_token: &str,
    capability_token: &str,
    storage_paths: &BackendStoragePaths,
) -> Command {
    let mut command = Command::new(path);
    command
        .arg("--host")
        .arg(BACKEND_HOST)
        .arg("--port")
        .arg(BACKEND_PORT)
        .env("RACERZLAB_BACKEND_HOST", BACKEND_HOST)
        .env("RACERZLAB_BACKEND_PORT", BACKEND_PORT)
        .env("RACERZLAB_BACKEND_INSTANCE_TOKEN", instance_token)
        .env("RACERZLAB_BACKEND_CAPABILITY_TOKEN", capability_token)
        .env("RACELAB_DB_PATH", &storage_paths.database)
        .env("RACELAB_DATA_DIR", &storage_paths.data)
        .env("RACERZLAB_BACKEND_LOG", &storage_paths.log)
        .current_dir(&storage_paths.root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    command
}

fn start_backend_sidecar(
    path: PathBuf,
    instance_token: &str,
    capability_token: &str,
    storage_paths: &BackendStoragePaths,
) -> Option<Child> {
    let mut command = backend_sidecar_command(
        path,
        instance_token,
        capability_token,
        storage_paths,
    );

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

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::OsStr;

    fn test_storage_root(label: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_nanos())
            .unwrap_or_default();
        std::env::temp_dir().join(format!(
            "racerzlab-{label}-{}-{nanos:x}",
            std::process::id()
        ))
    }

    fn command_env_path(command: &Command, name: &str) -> PathBuf {
        command
            .get_envs()
            .find(|(key, _)| *key == OsStr::new(name))
            .and_then(|(_, value)| value)
            .map(PathBuf::from)
            .unwrap_or_else(|| panic!("missing {name} from backend command"))
    }

    #[test]
    fn storage_paths_share_one_absolute_root_and_survive_prepare_again() {
        let root = test_storage_root("persistent-paths");
        let initial = BackendStoragePaths::prepare(root.clone()).expect("prepare storage root");
        let marker = initial.data.join("restart-marker");
        fs::write(&marker, b"preserved").expect("write restart marker");

        let restarted = BackendStoragePaths::prepare(root).expect("prepare storage after restart");

        assert_eq!(restarted, initial);
        assert!(restarted.root.is_absolute());
        assert!(restarted.database.is_absolute());
        assert!(restarted.data.is_absolute());
        assert!(restarted.log.is_absolute());
        assert_eq!(restarted.database, restarted.root.join("racelab.sqlite"));
        assert_eq!(restarted.data, restarted.root.join("data"));
        assert_eq!(
            restarted.log,
            restarted.root.join("logs").join("backend.log")
        );
        assert_eq!(
            fs::read(marker).expect("read restart marker"),
            b"preserved"
        );

        fs::remove_dir_all(&restarted.root).expect("remove test storage root");
    }

    #[test]
    fn backend_initial_start_and_restart_use_the_same_storage_contract() {
        let root = test_storage_root("command-contract");
        let storage_paths = BackendStoragePaths::prepare(root).expect("prepare storage root");
        let capability_token = backend_capability_token_value().expect("generate capability token");
        let initial = backend_sidecar_command(
            PathBuf::from(BACKEND_EXE),
            "owned-instance",
            &capability_token,
            &storage_paths,
        );
        let restarted = backend_sidecar_command(
            PathBuf::from(BACKEND_EXE),
            "owned-instance",
            &capability_token,
            &storage_paths,
        );

        for command in [&initial, &restarted] {
            assert_eq!(command.get_current_dir(), Some(storage_paths.root.as_path()));
            assert_eq!(
                command_env_path(command, "RACELAB_DB_PATH"),
                storage_paths.database
            );
            assert_eq!(
                command_env_path(command, "RACELAB_DATA_DIR"),
                storage_paths.data
            );
            assert_eq!(
                command_env_path(command, "RACERZLAB_BACKEND_LOG"),
                storage_paths.log
            );
            assert_eq!(
                command_env_path(command, "RACERZLAB_BACKEND_CAPABILITY_TOKEN"),
                PathBuf::from(&capability_token)
            );
        }

        fs::remove_dir_all(&storage_paths.root).expect("remove test storage root");
    }

    #[test]
    fn relative_storage_root_is_rejected() {
        let error = BackendStoragePaths::prepare(PathBuf::from("relative-storage"))
            .expect_err("relative root must fail");

        assert_eq!(error.kind(), io::ErrorKind::InvalidInput);
    }

    #[test]
    fn capability_token_is_32_random_bytes_encoded_as_lowercase_hex() {
        let first = backend_capability_token_value().expect("generate first capability token");
        let second = backend_capability_token_value().expect("generate second capability token");

        assert_eq!(first.len(), 64);
        assert!(first
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)));
        assert_ne!(first, second);
        assert_ne!(first, backend_instance_token_value());
    }
}

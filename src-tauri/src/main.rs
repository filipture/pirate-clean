#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Command, Stdio, Child};
use std::fs;
use std::path::PathBuf;
use std::io::{BufRead, BufReader};
use serde_json::{Value, json};
use tauri::{Manager, Window};
use tauri::Emitter;
use std::sync::{Mutex, Arc};
use include_dir::{include_dir, Dir};
use dirs::config_dir;
use std::env;

static RESOURCES: Dir = include_dir!("$CARGO_MANIFEST_DIR/resources");
static mut BOT_PROCESS: Option<Arc<Mutex<Child>>> = None;

// 🔧 Ścieżka do pliku konfiguracyjnego użytkownika
fn config_path() -> PathBuf {
    config_dir()
        .expect("❌ Can't get config dir")
        .join("redi")
        .join("config.json")
}

// 🔧 Gwarantuje, że config.json istnieje na dysku
fn ensure_config_file_exists() {
    let path = config_path();
    println!("🧾 używany config.json: {}", path.display());
    if !path.exists() {
        println!("📂 Config not found, creating from embedded");

        if let Some(file) = RESOURCES.get_file("config.json") {
            let content = file.contents();
            let parent = path.parent().unwrap();
            fs::create_dir_all(parent).expect("❌ Failed to create config dir");
            fs::write(&path, content).expect("❌ Failed to write default config");
        } else {
            panic!("❌ Embedded config.json not found!");
        }
    }
}

fn pause_flag_path() -> PathBuf {
    config_path().with_file_name("pause.flag")
}

fn main_py_path() -> PathBuf {
    if cfg!(debug_assertions) {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("resources")
            .join("main.py")
    } else {
        let exe_path = env::current_exe().expect("❌ Can't get current_exe");
        exe_path
            .parent()
            .unwrap() // MacOS/
            .parent()
            .unwrap() // Contents/
            .join("Resources")
            .join("resources")
            .join("main.py")
    }
}

#[tauri::command]
fn save_login(email: String, password: String) -> Result<(), String> {
    ensure_config_file_exists();
    let path = config_path();

    let raw = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let mut json: Value = serde_json::from_str(&raw).map_err(|e| e.to_string())?;

    if let Some(config) = json.get_mut("CONFIG") {
        config["email"] = json!(email);
        config["password"] = json!(password);
    }

    fs::write(&path, serde_json::to_string_pretty(&json).unwrap()).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn get_config() -> Result<Value, String> {
    ensure_config_file_exists();
    let path = config_path();

    let raw = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let json: Value = serde_json::from_str(&raw).map_err(|e| e.to_string())?;

    let mut combined = json.get("CONFIG").cloned().unwrap_or(json!({}));
    if let Some(map) = json.get("REDDIT_TO_ADSPOWER") {
        combined["REDDIT_TO_ADSPOWER"] = map.clone();
    }

    Ok(combined)
}

#[tauri::command]
fn update_config(config: Value) -> Result<(), String> {
    ensure_config_file_exists();
    let path = config_path();

    let raw = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let mut json: Value = serde_json::from_str(&raw).map_err(|e| e.to_string())?;

    let mut new_config = config.clone();

    if let Some(current_ids) = json["CONFIG"].get("ads_power_user_ids") {
        if !new_config.get("ads_power_user_ids").is_some() {
            new_config["ads_power_user_ids"] = current_ids.clone();
        }
    }

    if let Some(current_url) = json["CONFIG"].get("adspower_api_url") {
        if !new_config.get("adspower_api_url").is_some() {
            new_config["adspower_api_url"] = current_url.clone();
        }
    }

    if let Some(map) = config.get("REDDIT_TO_ADSPOWER") {
        json["REDDIT_TO_ADSPOWER"] = map.clone();
        new_config.as_object_mut().unwrap().remove("REDDIT_TO_ADSPOWER");
    }

    if let Some(ids) = config.get("ads_power_user_ids") {
        new_config["ads_power_user_ids"] = ids.clone();
    }

    json["CONFIG"] = new_config;
    fs::write(&path, serde_json::to_string_pretty(&json).unwrap()).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn start_bot(window: Window) {
    println!("🔥 start_bot wywołany");
    ensure_config_file_exists();

    let pause_flag_path = pause_flag_path();
    if pause_flag_path.exists() {
        let _ = fs::remove_file(&pause_flag_path);
    }

    let main_py = main_py_path();
    if !main_py.exists() {
        panic!("❌ Bot script not found at {:?}", main_py);
    }

    let resource_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources");
    let python_path = resource_dir.join("myenv").join("bin").join("python3");

    println!("🔥 python_path: {:?}", python_path);

    let mut child = Command::new(python_path)
        .arg(main_py.to_string_lossy().to_string())
        .arg(config_path().to_string_lossy().to_string())   
        .current_dir(&resource_dir)
        .env("PYTHONPATH", resource_dir.join("myenv").join("lib").join("python3.10").join("site-packages"))
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("❌ Failed to start bot");

    let stdout = child.stdout.take().unwrap();
    let stderr = child.stderr.take().unwrap();

    let bot_handle = Arc::new(Mutex::new(child));
    unsafe {
        BOT_PROCESS = Some(bot_handle.clone());
    }

    let window_stdout = window.clone();
    std::thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines().flatten() {
            let _ = window_stdout.emit("bot-log", line);
        }
    });

    let window_stderr = window.clone();
    std::thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines().flatten() {
            let _ = window_stderr.emit("bot-log", line);
        }
    });
}

#[tauri::command]
fn pause_bot() -> Result<(), String> {
    let path = pause_flag_path();
    fs::write(path, "pause").map_err(|e| e.to_string())
}

#[tauri::command]
fn resume_bot() -> Result<(), String> {
    let path = pause_flag_path();
    fs::remove_file(path).map_err(|e| e.to_string())
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            save_login,
            start_bot,
            pause_bot,
            resume_bot,
            get_config,
            update_config
        ])
        .on_window_event(|_app_handle, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                unsafe {
                    if let Some(child_arc) = BOT_PROCESS.take() {
                        if let Ok(mut child) = child_arc.lock() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("❌ Error while running Tauri app");
}

slint::include_modules!();

use std::fs;
use std::time::Duration;

fn read_file(path: &str) -> String {
    fs::read_to_string(path).unwrap_or_default()
}

/// Board uptime formatted as HH:MM:SS (from /proc/uptime).
fn fmt_uptime() -> String {
    let s = read_file("/proc/uptime");
    let secs: f64 = s
        .split_whitespace()
        .next()
        .and_then(|x| x.parse().ok())
        .unwrap_or(0.0);
    let total = secs as u64;
    format!("{:02}:{:02}:{:02}", total / 3600, (total % 3600) / 60, total % 60)
}

/// Used / total memory in MB (from /proc/meminfo).
fn fmt_mem() -> String {
    let s = read_file("/proc/meminfo");
    let mut total = 0u64;
    let mut avail = 0u64;
    for line in s.lines() {
        let mut it = line.split_whitespace();
        match it.next() {
            Some("MemTotal:") => total = it.next().and_then(|v| v.parse().ok()).unwrap_or(0),
            Some("MemAvailable:") => avail = it.next().and_then(|v| v.parse().ok()).unwrap_or(0),
            _ => {}
        }
    }
    let used = total.saturating_sub(avail);
    format!("{} / {} MB", used / 1024, total / 1024)
}

/// 1/5/15-minute load average (from /proc/loadavg).
fn fmt_load() -> String {
    let s = read_file("/proc/loadavg");
    s.split_whitespace().take(3).collect::<Vec<_>>().join("  ")
}

fn main() -> Result<(), slint::PlatformError> {
    let ui = MainWindow::new()?;

    ui.on_inc({
        let w = ui.as_weak();
        move || {
            if let Some(ui) = w.upgrade() {
                ui.set_counter(ui.get_counter() + 1);
            }
        }
    });

    let refresh = {
        let w = ui.as_weak();
        move || {
            if let Some(ui) = w.upgrade() {
                ui.set_uptime(fmt_uptime().into());
                ui.set_mem(fmt_mem().into());
                ui.set_load(fmt_load().into());
            }
        }
    };
    refresh(); // initial fill

    let timer = slint::Timer::default();
    let w = ui.as_weak();
    timer.start(slint::TimerMode::Repeated, Duration::from_secs(1), move || {
        if let Some(ui) = w.upgrade() {
            ui.set_elapsed(ui.get_elapsed() + 1);
        }
        refresh();
    });

    ui.run()
}

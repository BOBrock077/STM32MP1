slint::include_modules!();

use std::fs;
use std::io::{Read, Write};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

/// Command sent to the SGX sensor board; reply is CR-terminated ASCII.
const SENSOR_CMD: &[u8] = b"SC RE\r";

/// Latest data parsed from the USB-serial device, shared with the UI thread.
#[derive(Default)]
struct DevData {
    result: String, // the meaningful reply line, e.g. "Sensor board:SXT2SGXECE010010"
    raw: String,    // full raw reply (for debugging)
    connected: bool,
}

/// Pull the measurement line out of an `SC RE` reply and format it for display.
/// The reply looks like "nT1:23.500000 C,nH1:75.599998 %,nF1:306.000000 sml/min".
/// Returns "" if no measurement line is present (e.g. the board-id reply), so
/// the GUI keeps showing the last good reading instead of flickering.
fn parse_reply(text: &str) -> String {
    for line in text.lines() {
        let l = line.trim();
        if l.contains("nT1") || l.contains("nH1") || l.contains("nF1") {
            return format_measurements(l);
        }
    }
    String::new()
}

/// Turn "nT1:23.500000 C,nH1:75.599998 %,nF1:306.000000 sml/min," into
/// "Temp: 23.5 C\nHumidity: 75.6 %\nFlow: 306.0 sml/min".
fn format_measurements(line: &str) -> String {
    let mut out = Vec::new();
    for field in line.split(',') {
        let f = field.trim();
        if let Some((key, rest)) = f.split_once(':') {
            let label = match key.trim() {
                "nT1" => "Temp",
                "nH1" => "Humidity",
                "nF1" => "Flow",
                other => other,
            };
            let rest = rest.trim();
            let (num, unit) = rest.split_once(' ').unwrap_or((rest, ""));
            let num = num
                .parse::<f64>()
                .map(|x| format!("{:.1}", x))
                .unwrap_or_else(|_| num.to_string());
            out.push(format!("{}: {} {}", label, num, unit).trim_end().to_string());
        }
    }
    out.join("\n")
}

/// Background thread: open the serial port @115200 8N1, then poll the sensor
/// once a second with `SC RE`, capture the reply, and publish it. Auto-recovers
/// from unplug / not-yet-present so the GUI never dies on hot-plug.
fn spawn_serial(shared: Arc<Mutex<DevData>>) {
    // FT232 (FTDI) enumerates as /dev/ttyUSB0; native USB-CDC as /dev/ttyACM0.
    const PORTS: [&str; 2] = ["/dev/ttyUSB0", "/dev/ttyACM0"];
    thread::spawn(move || loop {
        let port_path = match PORTS.iter().find(|p| std::path::Path::new(p).exists()) {
            Some(p) => *p,
            None => {
                shared.lock().unwrap().connected = false;
                thread::sleep(Duration::from_secs(1));
                continue;
            }
        };
        let opened = serialport::new(port_path, 115200)
            .data_bits(serialport::DataBits::Eight)
            .parity(serialport::Parity::None)
            .stop_bits(serialport::StopBits::One)
            .timeout(Duration::from_millis(300))
            .open();
        let mut port = match opened {
            Ok(p) => p,
            Err(_) => {
                shared.lock().unwrap().connected = false;
                thread::sleep(Duration::from_secs(1));
                continue;
            }
        };
        shared.lock().unwrap().connected = true;

        // Some devices only talk when DTR/RTS are asserted.
        let _ = port.write_data_terminal_ready(true);
        let _ = port.write_request_to_send(true);

        loop {
            // Drop stale bytes, send the query, then collect the reply. Wait up
            // to ~2s for it to START arriving (device latency can exceed one
            // read timeout), then finish once the line goes idle.
            let _ = port.clear(serialport::ClearBuffer::Input);
            if port.write_all(SENSOR_CMD).is_err() || port.flush().is_err() {
                break; // device went away
            }
            let mut buf = Vec::new();
            let mut chunk = [0u8; 256];
            let start = Instant::now();
            loop {
                match port.read(&mut chunk) {
                    Ok(0) => {}
                    Ok(n) => buf.extend_from_slice(&chunk[..n]),
                    Err(ref e) if e.kind() == std::io::ErrorKind::TimedOut => {
                        if !buf.is_empty() {
                            break; // got the reply, line now idle
                        }
                    }
                    Err(_) => break,
                }
                if start.elapsed() > Duration::from_millis(2000) {
                    break;
                }
            }
            let text = String::from_utf8_lossy(&buf).into_owned();
            let result = parse_reply(&text);
            eprintln!("[serial] {} bytes; result={:?}", buf.len(), result);
            {
                let mut g = shared.lock().unwrap();
                g.raw = text.trim().to_string();
                if !result.is_empty() {
                    g.result = result;
                }
            }
            thread::sleep(Duration::from_secs(1));
        }
        shared.lock().unwrap().connected = false;
    });
}

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

    // Start reading the USB-serial device in the background.
    let dev = Arc::new(Mutex::new(DevData::default()));
    spawn_serial(dev.clone());

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
        let dev = dev.clone();
        move || {
            if let Some(ui) = w.upgrade() {
                ui.set_uptime(fmt_uptime().into());
                ui.set_mem(fmt_mem().into());
                ui.set_load(fmt_load().into());
                let g = dev.lock().unwrap();
                ui.set_dev_value(g.result.clone().into());
                ui.set_dev_raw(g.raw.clone().into());
                ui.set_dev_connected(g.connected);
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

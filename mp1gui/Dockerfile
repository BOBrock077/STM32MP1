# Native armhf build matching the board (Yocto thud == glibc 2.28).
# Debian buster == glibc 2.28, so the binary links an ABI the board provides.
# Built under QEMU arm emulation on the PC (slow but correct).
FROM arm32v7/debian:buster

# buster is archived -> point apt at archive.debian.org and skip date checks.
RUN printf 'deb http://archive.debian.org/debian buster main\n' > /etc/apt/sources.list \
 && printf 'deb http://archive.debian.org/debian-security buster/updates main\n' >> /etc/apt/sources.list \
 && printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99no

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates gcc libc6-dev pkg-config make \
      libwayland-dev libxkbcommon-dev libfontconfig1-dev libfreetype6-dev \
      libdrm-dev libinput-dev libudev-dev \
 && rm -rf /var/lib/apt/lists/*

# buster's CA store (GnuTLS curl) is too old to verify rustup/crates.io.
# Use a current Mozilla bundle and point all TLS tooling at it.
RUN curl -k -sS https://curl.se/ca/cacert.pem -o /opt/cacert.pem
ENV CURL_CA_BUNDLE=/opt/cacert.pem SSL_CERT_FILE=/opt/cacert.pem

# Modern rustc via rustup (buster's packaged rust is too old for Slint).
ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo PATH=/opt/cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
      | sh -s -- -y --profile minimal --default-toolchain stable

WORKDIR /src

# --- Dependency cache layer ---------------------------------------------
# Build a stub crate from just the manifests so the heavy slint/winit/...
# dependency tree (hundreds of crates) compiles ONCE and stays cached.
# This layer is invalidated only when Cargo.toml / Cargo.lock change, so
# editing src/ or ui/ no longer triggers a full rebuild -- cuts QEMU rebuilds
# from ~30 min down to ~1-2 min.
COPY Cargo.toml Cargo.lock ./
RUN mkdir src \
 && echo "fn main() {}" > src/main.rs \
 && echo "fn main() {}" > build.rs \
 && cargo build --release \
 && rm -rf src build.rs

# --- Application layer ---------------------------------------------------
# Real sources; only the mp1gui crate itself recompiles, deps come from cache.
COPY . .
RUN cargo build --release && ls -l /src/target/release/mp1gui

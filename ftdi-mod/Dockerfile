# Cross-build ftdi_sio.ko + usbserial.ko for the STM32MP1 board's stock kernel.
# Board kernel: Linux 4.19.94 armv7l, MODVERSIONS=y, MODULE_SIG not set,
# MODULE_FORCE_LOAD=y -> we force-load past the CRC/vermagic mismatch.
# Build on x86 with an armhf cross-toolchain (fast; no QEMU needed).
FROM debian:bullseye

RUN apt-get update && apt-get install -y --no-install-recommends \
      bc bison flex libssl-dev libelf-dev make cpio kmod \
      gcc gcc-arm-linux-gnueabihf libc6-dev xz-utils ca-certificates wget \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
# Stable 4.19.94 from kernel.org. ftdi_sio/usbserial are generic upstream
# drivers, so the vanilla stable tree matches the board's ST kernel ABI well
# enough (and force-load covers any CRC gaps).
RUN wget -q https://cdn.kernel.org/pub/linux/kernel/v4.x/linux-4.19.94.tar.xz \
 && tar xf linux-4.19.94.tar.xz && rm linux-4.19.94.tar.xz

# Board's own kernel config drives the module's vermagic/options.
COPY board.config /build/linux-4.19.94/.config

WORKDIR /build/linux-4.19.94
ARG CROSS=arm-linux-gnueabihf-
# gcc 10+ defaults to -fno-common, which breaks 4.19's bundled host tools
# (dtc: "multiple definition of yylloc"). Force -fcommon for HOST builds.
ARG HOSTFLAGS="-O2 -fcommon"
# Enable the two drivers as modules, reconcile config, prepare the tree, then
# build ONLY drivers/usb/serial (usbserial.ko + ftdi_sio.ko).
RUN ./scripts/config --module CONFIG_USB_SERIAL \
 && ./scripts/config --module CONFIG_USB_SERIAL_FTDI_SIO \
 && make ARCH=arm CROSS_COMPILE=$CROSS HOSTCFLAGS="$HOSTFLAGS" olddefconfig \
 && make ARCH=arm CROSS_COMPILE=$CROSS HOSTCFLAGS="$HOSTFLAGS" modules_prepare \
 && make ARCH=arm CROSS_COMPILE=$CROSS HOSTCFLAGS="$HOSTFLAGS" M=drivers/usb/serial \
 && ls -l drivers/usb/serial/usbserial.ko drivers/usb/serial/ftdi_sio.ko

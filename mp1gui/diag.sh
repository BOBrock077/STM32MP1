#!/bin/sh
echo 'deb http://archive.debian.org/debian buster main' > /etc/apt/sources.list
echo 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99no
apt-get update -qq 2>/dev/null
apt-get install -y -qq --no-install-recommends ca-certificates curl wget >/dev/null 2>&1

echo "=curl backend="; curl -V | head -1
curl -k -sS https://curl.se/ca/cacert.pem -o /opt/cacert.pem
echo "downloaded size=$(wc -c < /opt/cacert.pem)"

echo "=A: curl --cacert="
curl --cacert /opt/cacert.pem -sS https://sh.rustup.rs -o /tmp/r.sh; echo "exit=$?"
echo "=B: CURL_CA_BUNDLE env="
CURL_CA_BUNDLE=/opt/cacert.pem curl -sS https://sh.rustup.rs -o /tmp/r2.sh; echo "exit=$?"
echo "=C: SSL_CERT_FILE env="
SSL_CERT_FILE=/opt/cacert.pem curl -sS https://sh.rustup.rs -o /tmp/r3.sh; echo "exit=$?"
echo "=D: wget --no-check (fallback)="
wget --no-check-certificate -q https://sh.rustup.rs -O /tmp/r4.sh; echo "exit=$?"
ls -l /tmp/r*.sh 2>/dev/null

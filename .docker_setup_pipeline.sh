#!/usr/bin/env bash
set -euo pipefail

MARKER="/opt/pole_setup_done"
if [[ -f "${MARKER}" ]]; then
  echo "[docker_setup] Provisioning already completed. Skipping."
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive

apt update
apt install -y --no-install-recommends build-essential wget curl pkg-config cmake lsof \
  libproj-dev libgeos-dev libtiff5-dev libjpeg8-dev libpng-dev \
  libnetcdf-dev libcurl4-openssl-dev libsqlite3-dev libzstd-dev \
  libopenjp2-7 libopenjp2-7-dev libwebp-dev libwebpmux3 libwebpdemux2 \
  libcharls-dev libspatialite-dev libxerces-c-dev libpoppler-dev \
  libhdf5-dev libkml-dev libcfitsio-dev libpq-dev liblzma-dev \
  swig python3-dev git ca-certificates xz-utils >/dev/null

cd /tmp
rm -rf gdal-3.8.4 gdal-3.8.4.tar.gz
wget -q https://github.com/OSGeo/gdal/releases/download/v3.8.4/gdal-3.8.4.tar.gz
tar xf gdal-3.8.4.tar.gz
cd gdal-3.8.4
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local >/dev/null
make -j"$(nproc)" >/dev/null
make install >/dev/null
ldconfig

export CPLUS_INCLUDE_PATH=/usr/local/include/gdal
export C_INCLUDE_PATH=/usr/local/include/gdal
export GDAL_CONFIG=/usr/local/bin/gdal-config

cd /workspace

pip install --no-cache-dir --upgrade pip >/dev/null
pip install --no-cache-dir --force-reinstall "numpy<2" "pandas<2.2.3" "pyarrow<15" >/dev/null
pip uninstall -y opencv opencv-python opencv-python-headless opencv-contrib-python >/dev/null 2>&1 || true
pip install --no-cache-dir opencv-contrib-python-headless==4.10.0.84 >/dev/null
PIP_NO_BUILD_ISOLATION=1 pip install --no-cache-dir --no-binary=:all: gdal==3.8.4 >/dev/null

FILTERED_REQ=$(mktemp)
grep -vE '^(torch|torchvision|gdal|numpy|pandas)' requirements.txt > "$FILTERED_REQ"
pip install --no-cache-dir -r "$FILTERED_REQ" >/dev/null
rm "$FILTERED_REQ"

if [[ -f backend/requirements.txt ]]; then
  FILTERED_BACKEND=$(mktemp)
  grep -vE '^(torch|torchvision|gdal|numpy|pandas)' backend/requirements.txt > "$FILTERED_BACKEND"
  pip install --no-cache-dir -r "$FILTERED_BACKEND" >/dev/null
  rm "$FILTERED_BACKEND"
fi

pip install --no-cache-dir --force-reinstall "numpy<2" "pandas<2.2.3" "pyarrow<15" >/dev/null
pip uninstall -y opencv opencv-python opencv-python-headless opencv-contrib-python >/dev/null 2>&1 || true
pip install --no-cache-dir opencv-contrib-python-headless==4.10.0.84 >/dev/null

# Install Node.js (only if missing)
NODE_VERSION="v20.18.1"
NODE_DIR="/opt/node"
if [[ ! -x "${NODE_DIR}/bin/node" ]]; then
  mkdir -p "${NODE_DIR}"
  curl -fsSLo /tmp/node.tar.xz "https://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-linux-arm64.tar.xz"
  tar -xJf /tmp/node.tar.xz --strip-components=1 -C "${NODE_DIR}"
  rm /tmp/node.tar.xz
fi

echo 'export PATH=/opt/node/bin:$PATH' > /etc/profile.d/node_path.sh
chmod +x /etc/profile.d/node_path.sh

touch "${MARKER}"

python - <<'PY'
import subprocess
import torch
import rasterio

cuda_available = torch.cuda.is_available()
print('CUDA available inside container:', cuda_available)
print('Torch version:', torch.__version__)
print('Device:', torch.cuda.get_device_name(0) if cuda_available else 'None')
print('rasterio version:', rasterio.__version__)
try:
    gdal_info = subprocess.check_output(['gdalinfo', '--version'], text=True).strip()
except Exception as exc:
    gdal_info = f'Unavailable ({exc})'
print('gdalinfo --version:', gdal_info)
PY

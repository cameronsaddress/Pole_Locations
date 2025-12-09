#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt update
apt install -y build-essential wget curl pkg-config cmake \
  libproj-dev libgeos-dev libtiff5-dev libjpeg8-dev libpng-dev \
  libnetcdf-dev libcurl4-openssl-dev libsqlite3-dev libzstd-dev \
  libopenjp2-7 libopenjp2-7-dev libwebp-dev libwebpmux3 libwebpdemux2 \
  libcharls-dev libspatialite-dev libxerces-c-dev libpoppler-dev \
  libhdf5-dev libkml-dev libcfitsio-dev libpq-dev liblzma-dev \
  swig python3-dev

cd /tmp
rm -rf gdal-3.8.4 gdal-3.8.4.tar.gz
wget -q https://github.com/OSGeo/gdal/releases/download/v3.8.4/gdal-3.8.4.tar.gz
tar xf gdal-3.8.4.tar.gz
cd gdal-3.8.4
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local
make -j"$(nproc)"
make install
ldconfig

export CPLUS_INCLUDE_PATH=/usr/local/include/gdal
export C_INCLUDE_PATH=/usr/local/include/gdal
export GDAL_CONFIG=/usr/local/bin/gdal-config

cd /workspace

pip install --no-cache-dir --upgrade pip
pip install --no-cache-dir gdal==3.8.4
pip install --no-cache-dir -r requirements.txt
pip install --no-cache-dir -r backend/requirements.txt

python - <<'PY'
import torch
import rasterio
print('CUDA available inside container:', torch.cuda.is_available())
print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')
print('rasterio version:', rasterio.__version__)
print('GDAL version:', rasterio.get_gdal_version())
PY

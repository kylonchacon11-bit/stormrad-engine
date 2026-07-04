import os
import boto3
import pyart
import geojson
import numpy as np
from datetime import datetime, timedelta
from botocore import UNSIGNED
from botocore.config import Config

def fetch_and_compile():
    print("Connecting to NOAA S3 (Forced Anonymous)...")
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
    bucket = 'noaa-nexrad-level2'
    station = 'KHGX'
    
    # Target 15-20 minutes ago to ensure files exist
    now = datetime.utcnow() - timedelta(minutes=20)
    prefix = now.strftime('%Y/%m/%d') + f'/{station}/{station}'
    
    print(f"Searching prefix: {prefix}")
    try:
        objects = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    if 'Contents' not in objects:
        print("No files found. Exiting.")
        return

    # Grab the latest available file
    latest = sorted(objects['Contents'], key=lambda x: x['LastModified'])[-1]['Key']
    local_file = 'radar.bin'
    
    print(f"Downloading: {latest}")
    s3.download_file(bucket, latest, local_file)
    
    print("Decoding radar data...")
    radar = pyart.io.read_nexrad_archive(local_file)
    ref = radar.fields['reflectivity']['data'][0]
    lats = radar.gate_latitude['data'][0]
    lons = radar.gate_longitude['data'][0]
    
    features = []
    # Use 8x downsampling to keep file size ultra-low for the web
    for r in range(0, ref.shape[0], 8):
        for g in range(0, ref.shape[1], 8):
            val = ref[r, g]
            if not np.ma.is_masked(val) and val >= 20:
                p = (float(lons[r,g]), float(lats[r,g]))
                features.append(geojson.Feature(geometry=geojson.Point(p), properties={"dbz": int(val)}))
    
    with open('public/latest_radar.json', 'w') as f:
        geojson.dump(geojson.FeatureCollection(features), f)
        
    os.remove(local_file)
    print("Success. Radar data pushed to public/latest_radar.json")

if __name__ == "__main__":
    fetch_and_compile()

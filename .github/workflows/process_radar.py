import os
import boto3
import pyart
import geojson
import numpy as np
from datetime import datetime, timedelta
from botocore.config import Config
from botocore import UNSIGNED

def fetch_and_compile():
    print("Connecting to NOAA S3...")
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
    bucket = 'noaa-nexrad-level2'
    station = 'KHGX'
    
    # Get files for the last 15 mins
    now = datetime.utcnow() - timedelta(minutes=15)
    prefix = now.strftime('%Y/%m/%d') + f'/{station}/{station}'
    
    objects = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    if 'Contents' not in objects:
        return

    latest = sorted(objects['Contents'], key=lambda x: x['LastModified'])[-1]['Key']
    local_file = 'radar.bin'
    s3.download_file(bucket, latest, local_file)
    
    print("Processing file...")
    radar = pyart.io.read_nexrad_archive(local_file)
    ref = radar.fields['reflectivity']['data'][0]
    lats = radar.gate_latitude['data'][0]
    lons = radar.gate_longitude['data'][0]
    
    features = []
    # Downsample significantly to keep the file size tiny for the web browser
    for r in range(0, ref.shape[0], 5):
        for g in range(0, ref.shape[1], 5):
            val = ref[r, g]
            if not np.ma.is_masked(val) and val >= 20:
                p = (float(lons[r,g]), float(lats[r,g]))
                features.append(geojson.Feature(geometry=geojson.Point(p), properties={"dbz": int(val)}))
    
    with open('public/latest_radar.json', 'w') as f:
        geojson.dump(geojson.FeatureCollection(features), f)
        
    os.remove(local_file)
    print("Success.")

if __name__ == "__main__":
    fetch_and_compile()

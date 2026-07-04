import os
import boto3
import pyart
import geojson
import numpy as np
from datetime import datetime, timedelta
from botocore.config import Config
from botocore import UNSIGNED

def fetch_and_compile_latest_radar():
    print(">>> Connecting to NOAA AWS NEXRAD Live Bucket...")
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
    bucket_name = 'noaa-nexrad-level2'
    
    station = 'KHGX'
    
    now = datetime.utcnow() - timedelta(minutes=15)
    date_path = now.strftime('%Y/%m/%d')
    prefix = f"{date_path}/{station}/{station}"
    
    print(f">>> Scanning directory path: {prefix}")
    objects = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
    
    if 'Contents' not in objects:
        print("!!! Error: No active radar updates found in this timeframe slot. Standby...")
        return
        
    latest_file_key = sorted(objects['Contents'], key=lambda x: x['LastModified'])[-1]['Key']
    local_binary_filename = 'raw_radar.bin'
    
    print(f">>> Pulling raw file chunk down to container: {latest_file_key}")
    s3.download_file(bucket_name, latest_file_key, local_binary_filename)
    
    print(">>> Decoding NEXRAD Level II binary structures via PyArt...")
    radar = pyart.io.read_nexrad_archive(local_binary_filename)
    
    sweep_slice = radar.get_slice(0)
    ref_field = radar.fields['reflectivity']['data'][sweep_slice]
    gate_lat = radar.gate_latitude['data'][sweep_slice]
    gate_lon = radar.gate_longitude['data'][sweep_slice]
    
    features = []
    num_radials, num_gates = ref_field.shape
    print(f">>> Scanning array matrix size: {num_radials} radials x {num_gates} gates")
    
    for r in range(0, num_radials - 1, 2):
        for g in range(0, num_gates - 1, 2):
            val = ref_field[r, g]
            
            if np.ma.is_masked(val) or val < 20:
                continue
                
            p1 = (float(gate_lon[r, g]), float(gate_lat[r, g]))
            p2 = (float(gate_lon[r+1, g]), float(gate_lat[r+1, g]))
            p3 = (float(gate_lon[r+1, g+1]), float(gate_lat[r+1, g+1]))
            p4 = (float(gate_lon[r, g+1]), float(gate_lat[r, g+1]))
            
            poly = geojson.Polygon([[p1, p2, p3, p4, p1]])
            features.append(geojson.Feature(geometry=poly, properties={"dbz": int(val)}))
            
    print(f">>> Processing success! Compiled {len(features)} active storm polygons.")
    
    output_path = os.path.join('public', 'latest_radar.json')
    with open(output_path, 'w') as f:
        geojson.dump(geojson.FeatureCollection(features), f)
        
    if os.path.exists(local_binary_filename):
        os.remove(local_binary_filename)
    print(">>> Finished file write sequence. Memory cache cleared.")

if __name__ == "__main__":
    fetch_and_compile_latest_radar()

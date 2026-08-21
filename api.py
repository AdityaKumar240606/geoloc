from fastapi import FastAPI, HTTPException
import pandas as pd
import psycopg2
import numpy as np
from sklearn.cluster import DBSCAN
from contextlib import asynccontextmanager
from geopy.geocoders import Nominatim
from datetime import datetime, timezone
from typing import Optional

transition_matrix = pd.DataFrame()
fallback_matrix = pd.DataFrame()
place_names = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global transition_matrix
    global fallback_matrix
    global place_names

    conn = psycopg2.connect(host="localhost",database="tracker_db",user="postgres",password="aditya",port="5432")
    query = """ SELECT id, latitude, longitude, recorded_at
              FROM location_logs"""
    df = pd.read_sql_query(query, conn)
    conn.close()

    df['recorded_at'] = pd.to_datetime(df['recorded_at'], utc=True)
    df = df.sort_values(by='recorded_at').reset_index(drop=True)
    df['time_diff_mins'] = df['recorded_at'].diff().dt.total_seconds() / 60.0
    df['time_spent_mins'] = df['time_diff_mins'].shift(-1).fillna(0)
    stay_points = df[df['time_spent_mins'] >= 0.5].copy()
    
    try:
        if not stay_points.empty:
            coords = np.radians(stay_points[['latitude', 'longitude']])
            dbscan = DBSCAN(eps=40.0 / 6371000.0, min_samples=1, algorithm='ball_tree', metric='haversine')
            stay_points['place_id'] = dbscan.fit_predict(coords)
            
            cluster_centers = stay_points.groupby('place_id')[['latitude', 'longitude']].mean().reset_index()
            geolocator = Nominatim(user_agent="my_location_tracker_app")
            
            for _, row in cluster_centers.iterrows():
                pid = float(row['place_id'])
                if pid == -1:
                    place_names[pid] = "Unknown/Noise"
                    continue
                try:
                    location = geolocator.reverse(f"{row['latitude']}, {row['longitude']}", language="en")
                    if location and location.address:
                        address_parts = location.address.split(',')
                        short_name = ", ".join(address_parts[:2]).strip()
                        place_names[pid] = short_name
                    else:
                        place_names[pid] = f"Place {pid}"
                except Exception as e:
                    print(f"Geocoding failed for place {pid}: {e}")
                    place_names[pid] = f"Place {pid}"
            
            stay_points['next_place_id'] = stay_points['place_id'].shift(-1)
            transitions = stay_points.dropna(subset=['next_place_id']).copy()
            
            # General (time-agnostic) matrix
            fallback_counts = transitions.groupby(['place_id', 'next_place_id']).size().unstack(fill_value=0)
            fallback_matrix = fallback_counts.div(fallback_counts.sum(axis=1), axis=0) * 100
            
            # Time-conditioned matrix
            # Extract hour and create time_bin
            transitions['hour'] = transitions['recorded_at'].dt.hour
            bins = [-1, 5, 11, 17, 23]
            labels = ['Night', 'Morning', 'Afternoon', 'Evening']
            transitions['time_bin'] = pd.cut(transitions['hour'], bins=bins, labels=labels)
            
            transition_counts = transitions.groupby(['place_id', 'time_bin', 'next_place_id'], observed=False).size().unstack(fill_value=0)
            transition_probs = transition_counts.div(transition_counts.sum(axis=1), axis=0) * 100
            
            transition_matrix = transition_probs
            print("Model trained successfully")
        else:
            print("No stay points found")
    except Exception as e:
        print(f"Error training model: {e}")
        raise e
        
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/predict/{current_place_id}")
def get_prediction(current_place_id: float, time_bin: Optional[str] = None):
    """API Endpoint to get next location predictions."""
    
    if transition_matrix.empty or fallback_matrix.empty:
        raise HTTPException(status_code=503, detail="Model is not trained yet.")
        
    if time_bin is None:
        hour = datetime.now(timezone.utc).hour
        if hour < 6:
            time_bin = 'Night'
        elif hour < 12:
            time_bin = 'Morning'
        elif hour < 18:
            time_bin = 'Afternoon'
        else:
            time_bin = 'Evening'
            
    if time_bin not in ['Night', 'Morning', 'Afternoon', 'Evening']:
        raise HTTPException(status_code=400, detail="Invalid time_bin. Use Night, Morning, Afternoon, or Evening.")
        
    if current_place_id not in fallback_matrix.index:
        raise HTTPException(status_code=404, detail=f"Place ID {current_place_id} not recognized.")
        
    try:
        predictions = transition_matrix.loc[(current_place_id, time_bin)].sort_values(ascending=False)
        valid_predictions = predictions[predictions > 0].to_dict()
    except KeyError:
        # Fallback to general predictions if specific time context isn't available
        predictions = fallback_matrix.loc[current_place_id].sort_values(ascending=False)
        valid_predictions = predictions[predictions > 0].to_dict()
    
    labeled_predictions = {
        place_names.get(float(pid), f"Place {pid}"): prob 
        for pid, prob in valid_predictions.items()
    }
    
    current_name = place_names.get(float(current_place_id), f"Place {current_place_id}")
    
    return {
        "current_place_id": current_place_id,
        "current_place_name": current_name,
        "predictions": labeled_predictions
    }
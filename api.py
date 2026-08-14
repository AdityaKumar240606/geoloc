from fastapi import FastAPI,HTTPException
import pandas as pd
import psycopg2
import numpy as np
from sklearn.cluster import DBSCAN

app = FastAPI()
transition_matrix = pd.DataFrame()

@app.lifespan("startup")
def train_model():
    global transition_matrix

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

    if not stay_points.empty:

        coords = np.radians(stay_points[['latitude', 'longitude']])
        dbscan = DBSCAN(eps=40.0 / 6371000.0, min_samples=1, algorithm='ball_tree', metric='haversine')
        stay_points['place_id'] = dbscan.fit_predict(coords)
        transition_counts = stay_points.groupby(['place_id', 'next_place_id']).size().unstack(fill_value=0)
        transition_probs = transition_counts.div(transition_counts.sum(axis=1), axis=0) * 100
        
        # Save to our global variable
        transition_matrix = transition_probs
        print("Model trained successfully")
    else:
        print("No stay points found")

@app.get("/predict/{current_place_id}")
def get_prediction(current_place_id: float):
    """API Endpoint to get next location predictions."""
    
    if transition_matrix.empty:
        raise HTTPException(status_code=503, detail="Model is not trained yet.")
        
    if current_place_id not in transition_matrix.index:
        raise HTTPException(status_code=404, detail=f"Place ID {current_place_id} not recognized.")
        
    predictions = transition_matrix.loc[current_place_id].sort_values(ascending=False)
    
    valid_predictions = predictions[predictions > 0].to_dict()
    
    return {
        "current_place": current_place_id,
        "predictions": valid_predictions
    }



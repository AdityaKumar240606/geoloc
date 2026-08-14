import pandas as pd
import psycopg2 

from sklearn.cluster import DBSCAN

conn = psycopg2.connect(
    host="localhost",
    database="tracker_db",
    user="postgres",
    password="aditya",
    port="5432"
)

query = """ SELECT id, latitude, longitude, recorded_at
          FROM location_logs
          ORDER BY recorded_at DESC
          """

df = pd.read_sql_query(query, conn)

conn.close()

print("DataFrame created successfully!")
print(df.head())

import numpy as np

df['recorded_at'] = pd.to_datetime(df['recorded_at'],utc=True)
df = df.sort_values(by='recorded_at').reset_index(drop=True)

df['time_diff_mins'] = df['recorded_at'].diff().dt.total_seconds() / 60.0
df['time_diff_mins'] = df['time_diff_mins'].fillna(0)
df['time_spent_mins'] = df['time_diff_mins'].shift(-1).fillna(0)

stay_points = df[df['time_spent_mins'] >=15].copy()

if stay_points.empty:
    print("No stay points found.")
else:

    coords = np.radians(stay_points[['latitude', 'longitude']])
    epsilon = 40.0 / 6371000.0

    dbscan = DBSCAN(eps=epsilon, min_samples=1, algorithm='ball_tree', metric='haversine')
    stay_points['place_id'] = dbscan.fit_predict(coords)

    place_centers = stay_points.groupby('place_id')[['latitude', 'longitude']].mean()
    place_stats = stay_points.groupby('place_id').agg(
        total_visits=('id', 'count'),
        avg_duration_mins=('time_spent_mins', 'mean')
    )
    summary = pd.concat([place_centers, place_stats], axis=1)

    print("Summary of identified places:")
    print(summary)


stay_points['next_place_id'] = stay_points['place_id'].shift(-1)

transitions = stay_points.dropna(subset = ['next_place_id']).copy()
transitions['next_place_id'] = transitions['next_place_id'].astype(int)
transition_counts = transitions.groupby(['place_id', 'next_place_id']).size().reset_index(name='count')
transition_probs = transition_counts.div(transition_counts.sum(axis=1), axis=0) * 100
print(transition_probs.round(1))



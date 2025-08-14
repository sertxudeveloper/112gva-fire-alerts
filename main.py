import threading
import os
import psycopg

from utils import search_for_incidents_on_bbox, get_incident_information, send_incident_to_telegram

DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_DATABASE = os.getenv('DB_DATABASE')
DB_USERNAME = os.getenv('DB_USERNAME')
DB_PASSWORD = os.getenv('DB_PASSWORD')

BBOX_XATIVA = (-81954.0082793884, 4696976.047300361, -32613.90652130714, 4737029.0501217935)
BBOX_ENGUERA = (-120349.2871603583, 4691880.838453397, -71009.18540227704, 4731933.84127483)

DEBUG = False

def search_for_new_incidents():
    incidents = []

    for sha256, bbox in search_for_incidents_on_bbox(BBOX_XATIVA):
        incidents.append((sha256, bbox))

    for sha256, bbox in search_for_incidents_on_bbox(BBOX_ENGUERA):
        incidents.append((sha256, bbox))

    with psycopg.connect(f"host='{DB_HOST}' post='{DB_PORT}' dbname='{DB_DATABASE}' user='{DB_USERNAME}' password='{DB_PASSWORD}'") as conn:
        # Open a cursor to perform database operations
        with conn.cursor() as cur:
            # Create table if it doesn't exist
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fire_incidents (
                    id SERIAL PRIMARY KEY NOT NULL,
                    sha256 TEXT UNIQUE NOT NULL,
                    casefolderid UNSIGNED INTEGER NOT NULL,
                    city VARCHAR(100) NOT NULL,
                    address VARCHAR(255) NOT NULL,
                    description VARCHAR(255) NOT NULL,
                    calls UNSIGNED SMALLINT NOT NULL,
                    bbox GEOMETRY(POLYGON, 4326) NOT NULL
                );
            """)

            for sha256, bbox in incidents:
                if DEBUG:
                    print(f"Processing incident with SHA256: {sha256} and BBOX: {bbox}")

                # Check if the incident already exists in the database
                cur.execute("SELECT EXISTS(SELECT 1 FROM fire_incidents WHERE sha256 = %s)", (sha256,))

                if cur.fetchone()[0]:
                    print(f"Incident {sha256} already exists in the database. Skipping.")
                    continue

                incident = get_incident_information(bbox)

                send_incident_to_telegram(incident)

                cur.execute("""
                    INSERT INTO fire_incidents (sha256, bbox)
                    VALUES (%s, ST_MakeEnvelope(%s, %s, %s, %s, 4326), %s, %s, %s, %s)
                """, (sha256, bbox[0], bbox[1], bbox[2], bbox[3]), incident[0], incident[1], incident[2], incident[3], incident[4]))

                conn.commit()

                print(f"Incident {sha256} added to the database.")

        print("All incidents processed and sent to Telegram.")

def main():
    thread = threading.Timer(60.0, search_for_new_incidents) # 60 seconds = 1 minute
    thread.start()
    search_for_new_incidents()

main()

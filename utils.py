import os
import requests

import matplotlib.pyplot as plt
import matplotlib.image as mpimg

import cv2
import numpy as np
import hashlib

BASE_URL = "https://www.112cv.gva.es/geoserver/cv112/wms"

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def search_for_incidents_on_bbox(bbox):
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "FORMAT": "image/png",
        "TRANSPARENT": "true",
        "LAYERS": "gis112cv:V_INCIDENTES_CURSO",
        "SRS": "EPSG:3857",
        "EXCEPTIONS": "application/vnd.ogc.se_inimage",
        "TILED": "false",
        "STYLES": "",
        "WIDTH": 1024,
        "HEIGHT": 1024,
        "BBOX": ",".join(map(str, bbox)),
    }

    try:
        # Get the map image
        r = requests.get(BASE_URL, params=params, timeout=10)
    except requests.RequestException as e:
        print(f"Error fetching map image: {e}")
        return None

    if r.status_code != 200 or not r.content:
        print("Failed to fetch map image")
        return None

    # Save the map image to a file
    with open("image.png", "wb") as f:
        f.write(r.content)

    if DEBUG:
      # Display image
      img = mpimg.imread('image.png')
      plt.imshow(img)
      plt.axis('off')
      plt.show()

    detected_incidents = find_fire_incidents_on_image(image_path="image.png", BBOX=bbox, WIDTH=params["WIDTH"], HEIGHT=params["HEIGHT"])

    return detected_incidents

def find_fire_incidents_on_image(image_path, BBOX, WIDTH, HEIGHT):
    # Load image
    im = cv2.imread('image.png')

    # Convert the image to HSV
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)

    # Define the range of orange color in HSV
    # These values might need tuning based on the specific shade of orange in the image
    lower_orange = np.array([0, 100, 100])
    upper_orange = np.array([20, 255, 255])

    # Create a mask for the orange color
    mask = cv2.inRange(hsv, lower_orange, upper_orange)

    # Find contours in the mask
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Iterate through the contours and find circles
    detected_circles = []
    for contour in contours:
        # Approximate the contour to a circle
        (x, y), radius = cv2.minEnclosingCircle(contour)
        center = (int(x), int(y))
        radius = int(radius)

        # Filter for contours that are somewhat circular
        area = cv2.contourArea(contour)
        if area > 0:
            circularity = 4 * np.pi * area / (cv2.arcLength(contour, True)**2)
            # You might need to adjust this threshold based on how "circular" the icons are
            if 0.6 < circularity < 1.4:
                detected_circles.append((center, radius))

    # Draw the detected circles on the original image
    output_im = im.copy()
    for center, radius in detected_circles:
        cv2.circle(output_im, center, radius, (255, 0, 0), 2) # Draw a blue circle

    if DEBUG:
      # Save the output image with marked circles
      cv2.imwrite('output_image.png', output_im)

      # Display image
      img = mpimg.imread('output_image.png')
      plt.imshow(img)
      plt.axis('off')
      plt.show()

    # Convert pixel coordinates to geographic coordinates (BBOX)
    image_width = WIDTH
    image_height = HEIGHT

    minx, miny, maxx, maxy = BBOX

    # Calculate the resolution of the image in geographic units per pixel
    x_res = (maxx - minx) / image_width
    y_res = (maxy - miny) / image_height

    # Convert pixel coordinates to geographic coordinates
    incidents_bboxes = []
    for (x_pixel, y_pixel), radius_pixel in detected_circles:
        # Calculate the geographic coordinates of the center of the circle
        x_geo = minx + x_pixel * x_res
        # In image coordinates, the origin is at the top-left, while in geographic coordinates, the origin is at the bottom-left.
        # So, we need to subtract the pixel y from the image height to get the correct geographic y coordinate.
        y_geo = maxy - y_pixel * y_res

        # You can also estimate the radius in geographic units if needed
        radius_geo_x = radius_pixel * x_res
        radius_geo_y = radius_pixel * y_res

        if DEBUG:
          print(f"Circle at ({x_geo}, {y_geo}) with radius ({radius_geo_x}, {radius_geo_y})")

        incidents_bboxes.append((
            hashlib.sha256((f"X:{x_geo}, Y:{y_geo}").encode("utf-8")).hexdigest(),
            (
              x_geo - radius_geo_x,
              y_geo - radius_geo_y,
              x_geo + radius_geo_x,
              y_geo + radius_geo_y
            )
        ))

    return incidents_bboxes

def get_incident_information(bbox):
    params = {
      "SERVICE": "WMS",
      "VERSION": "1.1.1",
      "REQUEST": "GetFeatureInfo",
      "LAYERS": "gis112cv:V_INCIDENTES_CURSO",
      "QUERY_LAYERS": "gis112cv:V_INCIDENTES_CURSO",
      "BBOX": ",".join(map(str, bbox)),
      "SRS": "EPSG:3857",
      "WIDTH": 256,
      "HEIGHT": 256,
      "X": 128,
      "Y": 128,
      "INFO_FORMAT": "text/plain",
    }

    response = requests.get(BASE_URL, params=params, timeout=10)

    print(response.text)

    # Extract incident data
    id = response.text.split("CASEFOLDERID = ")[1].split("\n")[0]
    city = response.text.split("MUNICIPIO = ")[1].split("\n")[0]
    address = response.text.split("DIRECCION = ")[1].split("\n")[0]
    description = response.text.split("DESCRIPCION_ES = ")[1].split("\n")[0]
    calls = response.text.split("ASOCIADAS = ")[1].split("\n")[0]

    return (id, city, address, description, calls)

def send_incident_to_telegram(incident_info):
    id, city, address, description, calls = incident_info

    # Check if the Telegram bot token and chat ID are set
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram bot token or chat ID is not set.")
        return False

    # Escape special characters in the message
    description = parse_telegram_text(description)
    city = parse_telegram_text(city)
    address = parse_telegram_text(address)

    # Format the message to send to Telegram
    message = f"""
*🔥 Aviso de incendio 🚒*

*{description}*

\- Ciudad: {city}
\- Dirección: {address}
\- Llamadas relacionadas: {calls}
"""

    # Send the message to Telegram
    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "MarkdownV2"
        }
    )

    if response.status_code != 200:
        print(f"Failed to send message: {response.text}")
    else:
        print("Incident information sent to Telegram successfully.")
        return True

def parse_telegram_text(text):
    # Escape special characters in the text
    text = textreplace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("]", "\\]").replace("`", "\\`").replace("~", "\\~").replace(">", "\\>").replace("#", "\\#").replace("+", "\\+").replace("-", "\\-").replace("=", "\\=").replace("|", "\\|")
    return text

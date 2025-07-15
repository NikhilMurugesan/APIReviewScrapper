import os
import subprocess
import requests
import pandas as pd
import time
from deep_translator import GoogleTranslator
from google.cloud import storage
from flask import Flask, request, jsonify

# Replace with your actual Google Maps API Key
GOOGLE_MAPS_API_KEY = "AIzaSyAnXxA8ybIkTOym3FYo3-8pw3lfcfeXN44"

# Initialize Flask app
app = Flask(__name__)

# Set your Google Cloud Storage bucket name
BUCKET_NAME = "mera_storage"  # Your bucket name

# Function to upload CSV to Google Cloud Storage
def upload_to_gcs(local_file_path, bucket_name, destination_blob):
    try:
        # Run the gsutil cp command to upload the file
        subprocess.run(
            ["gsutil", "cp", local_file_path, f"gs://{bucket_name}/{destination_blob}"],
            check=True
        )
        print(f"✅ File {local_file_path} uploaded to gs://{bucket_name}/{destination_blob}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error uploading file to Google Cloud Storage: {e}")
        raise

# Function to fetch nearby courier services
def find_courier_services_near_location(pincode):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    # Use the pincode directly in the search query
    params = {
        "query": f"courier services in {pincode}",
        "key": GOOGLE_MAPS_API_KEY
    }
    
    response = requests.get(url, params=params).json()
    
    # Return the results (list of nearby courier services)
    print(f"Resopns {response}")
    return response.get("results", [])

# Function to fetch reviews for a particular place
def get_reviews_for_place(place_id):
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,rating,reviews",
        "key": GOOGLE_MAPS_API_KEY
    }

    all_reviews = []
    while True:
        # Making the request to the Google Places API
        response = requests.get(url, params=params).json()

        # Check if the response status is OK
        if response.get("status") == "OK":
            # Extract and return reviews if available
            reviews = response.get("result", {}).get("reviews", [])
            all_reviews.extend(reviews)  # Add reviews to the list

            # Check if there is a next_page_token to fetch more reviews
            next_page_token = response.get("next_page_token")
            if next_page_token:
                print(f"Fetching more reviews...")
                params["pagetoken"] = next_page_token  # Use the next_page_token to get the next set of reviews
                time.sleep(2)  # Wait a few seconds before making the next request (Google recommends a delay)
            else:
                break  # No more pages, exit the loop
        else:
            # If the status is not OK, print the error and return an empty list
            print(f"Error fetching reviews for Place ID {place_id}: {response.get('status')}")
            break  # Exit the loop if there's an error

    return all_reviews

# Function to translate text to English (if not already in English)
def translate_if_needed(text):
    try:
        cleaned = ''.join(e for e in text if e.isalpha())
        if cleaned and all(char.isalpha() and char.isascii() for char in cleaned):
            return text
        return GoogleTranslator(source='auto', target='en').translate(text)
    except Exception as e:
        print(f"Translation error: {e}")
        return text

# Main function to scrape and store reviews
def scrape_google_maps_reviews(pincode):
    print(f"Attempting to get reviews for pincode: {pincode}")
    
    # Step 1: Get courier services near the pincode
    courier_services = find_courier_services_near_location(pincode)
    if not courier_services:
        print(f"No courier services found near pincode {pincode}.")
        return

    all_reviews = []
    for service in courier_services:
        place_name = service.get('name')
        place_address = service.get('formatted_address')  # Use formatted address from the response
        place_id = service.get('place_id')
        
        if place_id:
            print(f"\nFetching reviews for: {place_name} (ID: {place_id})")
            reviews = get_reviews_for_place(place_id)
            if reviews:
                for review in reviews:
                    author = review.get('author_name', 'Anonymous')
                    rating = review.get('rating', 'N/A')
                    text = review.get('text', 'No review text.')
                    relative_time = review.get('relative_time_description', 'No time info')
                    
                    all_reviews.append({
                        "Courier Name": place_name,
                        "Address": place_address,
                        "Pincode": pincode,
                        "Overall Rating": rating,
                        "Review": text,
                        "Time": relative_time
                    })

    # Step 2: Save the reviews to a CSV file
    output_dir = "Extract"
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"courier_reviews_{pincode}.csv")
    df = pd.DataFrame(all_reviews)
    df.to_csv(file_path, index=False)
    
    # Step 3: Upload the CSV to Google Cloud Storage
    upload_to_gcs(file_path, BUCKET_NAME, f"Extract/courier_reviews_{pincode}.csv")

# API Endpoint to trigger scraping
@app.route('/scrape_reviews', methods=['GET'])
def scrape_reviews():
    pincode = request.args.get('pincode')
    if not pincode:
        return jsonify({"error": "Pincode is required!"}), 400
    try:
        scrape_google_maps_reviews(pincode)
        return jsonify({"message": f"Reviews for pincode {pincode} scraped and uploaded to Google Cloud Storage."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Health Check API to ensure the service is running
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "Service is up and running!"}), 200

# Run the Flask app
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)

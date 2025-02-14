def generate_google_maps_html(lat, lon, radius_km, api_key, output_file='map_with_circle.html'):
    """
    Generates an HTML file with an embedded Google Map showing a circle around a given point.

    Parameters:
        lat (float): Latitude of the center point.
        lon (float): Longitude of the center point.
        radius_km (float): Radius of the circle in kilometers.
        api_key (str): Your Google Maps JavaScript API key.
        output_file (str): Path to save the resulting HTML file.
    """
    # HTML template for embedding Google Maps
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Google Map with Circle</title>
        <script src="https://maps.googleapis.com/maps/api/js?key={api_key}"></script>
        <script>
            function initMap() {{
                // Center of the map
                var center = {{ lat: {lat}, lng: {lon} }};

                // Map options
                var map = new google.maps.Map(document.getElementById('map'), {{
                    zoom: 14,  // Adjust zoom level for better centering
                    center: center
                }});

                // Draw a circle
                var circle = new google.maps.Circle({{
                    strokeColor: '#FF0000',
                    strokeOpacity: 0.8,
                    strokeWeight: 2,
                    fillColor: '#FF0000',
                    fillOpacity: 0.35,
                    map: map,
                    center: center,
                    radius: {radius_km * 1000} // Radius in meters
                }});

                // Add a marker at the center
                new google.maps.Marker({{
                    position: center,
                    map: map,
                    title: "Lycée Guy de Maupassant"
                }});
            }}
        </script>
    </head>
    <body onload="initMap()">
        <h3>Google Map with a {radius_km} km Circle</h3>
        <div id="map" style="height: 600px; width: 100%;"></div>
    </body>
    </html>
    """

    # Save the HTML to a file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"HTML map saved to {output_file}")


# Correct coordinates for Lycée Guy de Maupassant
latitude = 33.509887021438914  # Adjusted latitude
longitude = -7.683197401134136  # Adjusted longitude
radius = 10  # Radius in kilometers
api_key = "AIzaSyBt3BhFQYyWsBbu_TKhgxANjt-7fSrN6H4"  # Your API key

generate_google_maps_html(latitude, longitude, radius, api_key)

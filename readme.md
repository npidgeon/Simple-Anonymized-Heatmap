# Anonymous US Density Heatmap

This is a professional Python Streamlit application that uses a CSV file of coordinates in conjunction with US national shapefile data to generate a density heatmap. Coordinates are jittered using a given random offset (in meters), adding anonymity while preserving the general geographic distribution.

The output is a real-time interactive mapping dashboard using `folium` and `streamlit`.

**Features:**
- Real-time manipulation of Anonymization radius.
- File uploads directly in the browser (or from a secure AWS S3 bucket).
- Toggles to include/exclude Hawaii, Alaska, and US territories.

## Prerequisites

You must have Python installed. You can install all project dependencies via `pip`:

```bash
pip install -r requirements.txt
```

*(Note: The `data/cb_2018_us_nation_5m.shp` boundary file must stay in the `/data` directory for the program to determine inland coordinate validity).*

## Usage

You no longer need to edit script files! Everything runs through the Streamlit web dashboard.

1. Navigate to the repository directory.
2. Launch the Streamlit application:

```bash
streamlit run src/app.py
```

3. Your default web browser will open (typically at `http://localhost:8501`).
4. **Local Data**: Look at the sidebar on the left and select "Upload Local CSV". You will be prompted to insert your CSV file. Ensure you define the exact names of your target columns (e.g. `lat` and `long`).
5. **AWS S3 Data**: Select "Fetch from AWS S3". Enter your secure credentials; they are *not* saved or logged to disk anywhere.


## Example

Eastern US using a standard 500m anonymity jitter radius:

<img width="1317" height="1010" alt="Image" src="https://github.com/user-attachments/assets/22def057-d6b3-4a51-bf61-24a40338c3e0" />


## License
MIT License

Copyright (c) 2026 Nicholas Pidgeon

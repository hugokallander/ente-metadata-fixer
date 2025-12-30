# Ente Metadata Fixer

This Python script updates the metadata of images and videos exported from [Ente](https://ente.io/). It uses the accompanying JSON sidecar files to restore the correct creation timestamps.

## Features

-   **Images**: Updates EXIF `DateTimeOriginal` using `piexif`.
-   **Videos**: Updates `creation_time` metadata using `ffmpeg`.
-   **Recursive Scanning**: Processes all files in the target directory and subdirectories.
-   **Smart Fallback**: Checks for `file.ext.json` and `file.json` naming conventions.

## Prerequisites

-   Python 3.x
-   `ffmpeg` (required for video processing)

### Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

Run the script pointing to your Ente export folder:

```bash
python -m ente_metadata_fixer /path/to/your/ente_photos
```

If no path is provided, it defaults to `~/Downloads/ente_photos`.

## How it Works

The script scans the specified directory for image and video files. For each file, it looks for a corresponding JSON file containing metadata. It parses the timestamp from the JSON and updates the media file's internal metadata to match.

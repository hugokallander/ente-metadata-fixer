"""Module for updating metadata of images and videos exported from Ente."""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys

# Check for piexif dependency
try:
    import piexif
except ImportError:
    print("Error: 'piexif' library is not installed.")
    print("Please install it using: pip install piexif")
    sys.exit(1)


def get_metadata_file(file_path) -> str | None:
    """Attempt to find the corresponding JSON metadata file.

    Checks for file.ext.json and file.json
    """
    # Strategy 1: file.jpg -> file.jpg.json
    json_path_1 = str(file_path) + ".json"
    if os.path.exists(json_path_1):
        return json_path_1

    # Strategy 2: file.jpg -> file.json
    json_path_2 = os.path.splitext(file_path)[0] + ".json"
    if os.path.exists(json_path_2):
        return json_path_2

    return None


def parse_timestamp(json_data) -> datetime.datetime | None:
    """Extract the timestamp from Ente JSON data.

    Returns a datetime object or None.
    """
    # Common fields in Ente exports or Google Takeout style JSONs
    possible_keys = ["creationTime", "photoTakenTime", "dateTaken", "timestamp"]

    timestamp = None

    for key in possible_keys:
        if key in json_data:
            val = json_data[key]
            # Handle nested objects like {"timestamp": "123456"}
            if isinstance(val, dict) and "timestamp" in val:
                val = val["timestamp"]

            # Handle string timestamps
            if isinstance(val, str):
                try:
                    # Try parsing integer string
                    timestamp = int(val)
                except ValueError:
                    # Try parsing ISO string (simplified)
                    try:
                        # 2023-01-01T12:00:00Z
                        dt = datetime.datetime.fromisoformat(val.replace("Z", "+00:00"))
                        return dt
                    except ValueError:
                        pass
            elif isinstance(val, (int, float)):
                timestamp = val

            if timestamp:
                break

    if timestamp:
        # Check if timestamp is in milliseconds (common in Java/JS) or seconds
        # If year is > 3000, assume milliseconds
        if timestamp > 100000000000:
            timestamp = timestamp / 1000.0
        return datetime.datetime.fromtimestamp(timestamp)

    return None


def update_image_exif(file_path, dt):
    """Updates the EXIF DateTimeOriginal field for images using piexif."""
    try:
        # Format for EXIF: "YYYY:MM:DD HH:MM:SS"
        exif_date_str = dt.strftime("%Y:%m:%d %H:%M:%S")

        try:
            exif_dict = piexif.load(file_path)
        except Exception:
            # If no EXIF data exists, create empty
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = exif_date_str.encode(
            "utf-8",
        )
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = exif_date_str.encode(
            "utf-8",
        )
        exif_dict["0th"][piexif.ImageIFD.DateTime] = exif_date_str.encode("utf-8")

        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, file_path)
        print(f"Updated EXIF for image: {file_path}")
        return True
    except Exception as e:
        print(f"Failed to update image {file_path}: {e}")
        return False


def update_video_metadata(file_path, dt):
    """Updates the creation_time metadata for videos using ffmpeg."""
    try:
        # Format for FFmpeg: "YYYY-MM-DD HH:MM:SS"
        date_str = dt.strftime("%Y-%m-%d %H:%M:%S")

        temp_file = file_path + ".temp" + os.path.splitext(file_path)[1]

        # ffmpeg command to copy stream and update metadata
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-i",
            file_path,
            "-c",
            "copy",
            "-metadata",
            f"creation_time={date_str}",
            "-map_metadata",
            "0",  # Copy global metadata
            temp_file,
        ]

        # Run ffmpeg quietly
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
        )

        if result.returncode == 0:
            # Replace original file with temp file
            os.replace(temp_file, file_path)
            print(f"Updated metadata for video: {file_path}")
            return True
        print(f"FFmpeg failed for {file_path}: {result.stderr.decode()}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

    except Exception as e:
        print(f"Failed to update video {file_path}: {e}")
        return False


def process_directory(directory):
    print(f"Scanning directory: {directory}")

    image_exts = {
        ".jpg",
        ".jpeg",
        ".tiff",
        ".webp",
    }  # PNG often doesn't support standard EXIF in same way or piexif issues
    video_exts = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}

    stats = {
        "processed": 0,
        "updated": 0,
        "failed": 0,
        "skipped_no_json": 0,
        "skipped_no_timestamp": 0,
    }
    failed_files = []

    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            ext = os.path.splitext(file)[1].lower()

            if ext in image_exts or ext in video_exts:
                stats["processed"] += 1
                json_path = get_metadata_file(file_path)

                if json_path:
                    try:
                        with open(json_path, encoding="utf-8") as f:
                            data = json.load(f)

                        dt = parse_timestamp(data)

                        if dt:
                            success = False
                            if ext in image_exts:
                                success = update_image_exif(file_path, dt)
                            elif ext in video_exts:
                                success = update_video_metadata(file_path, dt)

                            if success:
                                stats["updated"] += 1
                            else:
                                stats["failed"] += 1
                                failed_files.append(
                                    (file_path, "Update failed (check logs)"),
                                )
                        else:
                            stats["skipped_no_timestamp"] += 1
                            # print(f"No valid timestamp found in JSON for: {file}")

                    except Exception as e:
                        stats["failed"] += 1
                        failed_files.append((file_path, str(e)))
                        print(f"Error processing {file}: {e}")
                else:
                    stats["skipped_no_json"] += 1
                    # print(f"No JSON found for: {file}")

    print("\n" + "=" * 40)
    print("PROCESSING SUMMARY")
    print("=" * 40)
    print(f"Total files scanned: {stats['processed']}")
    print(f"Successfully updated: {stats['updated']}")
    print(f"Failed: {stats['failed']}")
    print(f"Skipped (no JSON found): {stats['skipped_no_json']}")
    print(f"Skipped (no timestamp in JSON): {stats['skipped_no_timestamp']}")

    if failed_files:
        print("\n" + "=" * 40)
        print("FAILED FILES LIST")
        print("=" * 40)
        for fpath, reason in failed_files:
            print(f"[FAILED] {os.path.basename(fpath)}")
            print(f"  Path: {fpath}")
            print(f"  Reason: {reason}")
            print("-" * 20)
    print("\nDone.")


if __name__ == "__main__":
    # Check for ffmpeg
    if shutil.which("ffmpeg") is None:
        print("Error: 'ffmpeg' is not installed or not found in PATH.")
        print("Videos cannot be processed without ffmpeg.")
        print("To install on macOS: brew install ffmpeg")
        sys.exit(1)

    # Default path from request
    target_dir = os.path.expanduser("~/Downloads/ente_photos")

    if not os.path.exists(target_dir):
        print(f"Directory not found: {target_dir}")
        print(
            "Please edit the script to set the correct 'target_dir' or ensure the folder exists.",
        )
    else:
        process_directory(target_dir)

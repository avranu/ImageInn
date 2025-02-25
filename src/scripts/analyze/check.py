"""*********************************************************************************************************************
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    METADATA:                                                                                                         *
*                                                                                                                      *
*        File:    check.py                                                                                             *
*        Project: imageinn                                                                                             *
*        Version: 0.1.0                                                                                                *
*        Created: 2025-02-21                                                                                           *
*        Author:  Jess Mann                                                                                            *
*        Email:   jess.a.mann@gmail.com                                                                                *
*        Copyright (c) 2025 Jess Mann                                                                                  *
*                                                                                                                      *
* -------------------------------------------------------------------------------------------------------------------- *
*                                                                                                                      *
*    LAST MODIFIED:                                                                                                    *
*                                                                                                                      *
*        2025-02-21     By Jess Mann                                                                                   *
*                                                                                                                      *
*********************************************************************************************************************"""
import rawpy
import numpy as np
from pathlib import Path

def analyze_image_brightness(image_path: Path):
    """
    Analyzes the brightness of a RAW image (NEF).
    
    Args:
        image_path (Path): Path to the image file.
        
    Returns:
        dict: Dictionary containing the brightest pixel, darkest pixel, and average brightness.
    """
    # Load RAW image
    with rawpy.imread(str(image_path)) as raw:
        raw_image = raw.raw_image_visible.astype(np.uint16)  # Extract visible RAW data

    # Compute brightness statistics
    brightest_pixel = np.max(raw_image)
    darkest_pixel = np.min(raw_image)
    average_brightness = np.mean(raw_image)

    return {
        "brightest_pixel": int(brightest_pixel),
        "darkest_pixel": int(darkest_pixel),
        "average_brightness": float(average_brightness),
    }

if __name__ == "__main__":
    image_path = Path(r"P:\2023\2023-02-20\LQ\JAM_5339.NEF")
    
    if not image_path.exists():
        print(f"Error: File not found - {image_path}")
    else:
        results = analyze_image_brightness(image_path)
        print(f"Brightest Pixel: {results['brightest_pixel']}")
        print(f"Darkest Pixel: {results['darkest_pixel']}")
        print(f"Average Brightness: {results['average_brightness']:.2f}")

"""
	
	Metadata:
	
		File: merge.py
		Project: hdr
		Created Date: 18 Aug 2023
		Author: Jess Mann
		Email: jess.a.mann@gmail.com
	
		-----
	
		Last Modified: Sat Aug 19 2023
		Modified By: Jess Mann
	
		-----
	
		Copyright (c) 2023 Jess Mann
"""
import cv2
import numpy as np
import rawpy
import imageio
import subprocess

class HDRProcessor:
    def __init__(self, image_paths):
        self.image_paths = image_paths
        self.images = []
        self.load_images()

    def load_images(self):
        for path in self.image_paths:
            with rawpy.imread(path) as raw:
                self.images.append(raw.postprocess())

    def align_images(self):
        alignMTB = cv2.createAlignMTB()
        alignMTB.process(self.images, self.images)

    def create_hdr_image_with_deghosting(self, output_path):
        command = ['hdrmerge', '-o', output_path] + self.image_paths
        subprocess.run(command, check=True)

    def save_image(self, path):
        res_8bit = np.clip(self.res_debvec*255, 0, 255).astype('uint8')
        imageio.imsave(path, res_8bit)

    def process(self, output_path):
        self.align_images()
        self.create_hdr_image_with_deghosting(output_path)

if __name__ == "__main__":
    image_paths = ['path_to_image1', 'path_to_image2', 'path_to_image3']  # Add paths to your images here
    hdr_processor = HDRProcessor(image_paths)
    hdr_processor.process('output_path')  # Add your output path here

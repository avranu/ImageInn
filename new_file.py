import cv2
import numpy as np
import rawpy
import imageio

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

    def create_hdr_image(self):
        merge_debvec = cv2.createMergeDebevec()
        self.hdr_debvec = merge_debvec.process(self.images)

    def tone_map(self):
        tonemap1 = cv2.createTonemapDurand(gamma=2.2)
        self.res_debvec = tonemap1.process(self.hdr_debvec.copy())

    def save_image(self, path):
        res_8bit = np.clip(self.res_debvec*255, 0, 255).astype('uint8')
        imageio.imsave(path, res_8bit)

    def process(self, output_path):
        self.align_images()
        self.create_hdr_image()
        self.tone_map()
        self.save_image(output_path)

if __name__ == "__main__":
    image_paths = ['path_to_image1', 'path_to_image2', 'path_to_image3']  # Add paths to your images here
    hdr_processor = HDRProcessor(image_paths)
    hdr_processor.process('output_path')  # Add your output path here

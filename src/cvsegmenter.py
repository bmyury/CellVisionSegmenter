# cvsegmenter.py
# ---------------------------
# Contains the logic for cropping and segmentation.  See class doc for details.

import os
import numpy as np
import warnings
import imageio
import skimage
import src.cvmodel as modellib
import random
import tensorflow as tf
import matplotlib.pyplot as plt

from keras import backend as K
from src.cvmodelconfig import CVSegmentationConfig

AUTOSIZE_MAX_SIZE = 800
# Maps image height, width to nrows, ncols to slice into for inference.
IMAGE_GRID = {
    (1440,1344):(2,2),
    (1440,1920):(2,2),
    (1008,1344):(1,2),
    (1008,1920):(1,2),
    (504, 672):(1,1)
}
class CVSegmenter:
    """
    Crops, runs CellVision segmentation, and stitches masks together. Assumes that all images are the same size, 
    have the same channels, and are being segmented on the same channel.  segment() returns a dictionary containing 
    all masks.  Currently does not return scores, class ids, or boxes, but can be modified to do so.
    """
    def __init__(self, shape, model_path, overlap, increase_factor):
        self.overlap = overlap
        self.shape = shape
        self.nrows = 0
        self.ncols = 0
        self.model = self.get_model(model_path, increase_factor)
    
    def get_model(self, model_path, increase_factor):
        print('Initializing model with weights located at', model_path)
        if self.shape[1:3] not in IMAGE_GRID:
            print('Using autosizing for image shape')
            self.nrows, self.ncols = int(np.ceil(self.shape[1] / AUTOSIZE_MAX_SIZE)), int(np.ceil(self.shape[2] / AUTOSIZE_MAX_SIZE))
        else:
            self.nrows, self.ncols = IMAGE_GRID[self.shape[1:3]]

        smallest_side = min(self.shape[1] // self.nrows, self.shape[2] // self.ncols) + self.overlap
        inference_config = CVSegmentationConfig(smallest_side, increase_factor)
        model = modellib.MaskRCNN(mode="inference", 
                          config=inference_config)
        model.load_weights(model_path, by_name=True)

        return model
    
    def get_overlap_coordinates(self, rows, cols, i, j, x1, x2, y1, y2):
        half = self.overlap // 2
        if i != 0:
            y1 -= half
        if i != rows - 1:
            y2 += half
        if j != 0:
            x1 -= half
        if j != cols - 1:
            x2 += half
        return (x1, x2, y1, y2)
    
    def crop_with_overlap(self, arr):
        crop_height, crop_width, channels = arr.shape[0]//self.nrows, arr.shape[1]//self.ncols, arr.shape[2] 
        
        crops = []
        for row in range(self.nrows):
            for col in range(self.ncols):
                x1, y1, x2, y2 = col*crop_width, row*crop_height, (col+1)*crop_width, (row+1)*crop_height
                x1, x2, y1, y2 = self.get_overlap_coordinates(self.nrows, self.ncols, row, col, x1, x2, y1, y2)
                crops.append(arr[y1:y2, x1:x2, :])

        return crops, self.nrows, self.ncols
    
    def segment_image(self, nuclear_image):
        crops, self.rows, self.cols = self.crop_with_overlap(nuclear_image)

        masks = []
        for crop in crops:
            results = self.model.detect([crop], verbose=0)[0]
            mask = results['masks']
            if mask.shape[2] == 0:
                print('Warning: no cell instances were detected for a crop.')
            masks.append(mask)
        return masks, self.rows, self.cols
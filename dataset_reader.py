import numpy as np
import os
from os import listdir
from os.path import isfile, join
import cv2
import scipy
import itertools
import pickle
import matplotlib.pyplot as plt
import time
import copy
import shutil
import random

import sys



class DataLoader:
    images = None  # (?,256,256,3)
    heatmaps = None  # (?,256,256,18) (also known as "poses")
    morphologicals = None  # (?,256,256)
    pairs = []
    groupsofIndices = []


    def __init__(self):
        print("Initializing DeepFashion Dataset Loader...")
        random.seed(5331)    # for repeatability, so that if the model is trained,saved,loaded,trained again, the train-validation split remains the same
        self.index2dir = {}
        self.groupsofIndices = []
        self.pairs = []
        self.numofphotos = 0
        self.extract()
        # Generate pairs
        for group in self.groupsofIndices:
            self.pairs.append(list(itertools.permutations(group, 2)))
        self.pairs = list(itertools.chain.from_iterable(self.pairs))
        random.shuffle(self.pairs)
        cutoff = int(len(self.pairs) * 0.9)
        self.trainingPairs = self.pairs[:cutoff]
        self.validationPairs = self.pairs[cutoff:]

    def process_oneimg(self, fulldir):

        if not "flat" in fulldir:
            img = cv2.imread(fulldir)
            if img is not None:
                img = np.expand_dims(img, axis=0)
                # process the keypoint thing
                heatmap = np.zeros([256, 256, 18])  # (of original image)
                mapofAllPoints = np.zeros([256, 256])

                # process the stored keypoints
                keypointfileDir = fulldir + 'keypoints'
                with open(keypointfileDir, 'rb') as kpfile:
                    keypoints = pickle.load(kpfile)
                    availablePoints = []
                    
                    print("keypoints",keypoints)
                    
                    
                    for i in range(len(keypoints)):
                        keypoint = keypoints[i]

                        # draw circles
                        if len(keypoint) != 0:  # a non-empty keypoint is a
                            # list consists of one and only one tuple.
                            availablePoints.append(i)
                            heatmap[:, :, i] = cv2.circle(np.zeros([256, 256]),
                                                          (keypoint[0][0], keypoint[0][1]), 4, 255, -1)
                            cv2.circle(mapofAllPoints, (keypoint[0][0], keypoint[0][1]), 4, 255, -1)
                            
                            # link the lines
                    cv2.imwrite("keypoints/kps.jpg",mapofAllPoints)
                    sys.exit()
                    links = [(16, 14), (14, 15), (15, 17), (16, 1), (14, 0),
                             (15, 0), (17, 1), (0, 1), (1, 2),
                             (2, 3), (3, 4), (1, 5), (5, 6), (6, 7), (2, 8), (1, 8), (1, 11), (5, 11),
                             (8, 9), (9, 10), (8, 11), (11, 12), (12, 13)]
                    for link in links:
                        if link[0] in availablePoints and link[1] in availablePoints:
                            point1 = (keypoints[link[0]][0][0], keypoints[link[0]][0][1])
                            point2 = (keypoints[link[1]][0][0], keypoints[link[1]][0][1])
                            cv2.line(mapofAllPoints, point1, point2, 255, 10)

                kernel = np.asarray([[1, 1, 1], [1, 1, 1], [1, 1, 1]], dtype=np.uint8)
                dilatedMapofAllPoints = cv2.dilate(mapofAllPoints, kernel, iterations=6)
                dilatedMapofAllPoints[dilatedMapofAllPoints == 0] = 1
                dilatedMapofAllPoints[dilatedMapofAllPoints == 255] = 2

                heatmap = np.expand_dims(heatmap, axis=0)
                dilatedMapofAllPoints = np.expand_dims(dilatedMapofAllPoints, axis=0)
                img = img/127.5 - 1.0
                
                #print("img_shape",img.shape)
                img = np.reshape(img, (img.shape[1], img.shape[2],3))
                if img.shape[0] != 256:
                    img2 = cv2.resize(img,(256,256))
                return img2, heatmap, dilatedMapofAllPoints

    def next_batch(self, batch_size, trainorval):
        conditional_image = np.zeros([batch_size, 256, 256, 3])
        target_pose = np.zeros([batch_size, 256, 256, 18])
        target_image = np.zeros([batch_size, 256, 256, 3])
        target_morphologicals = np.zeros([batch_size, 256, 256])

        pairstofeed = None
        if trainorval == 'TRAIN':
            pairstofeed = random.sample(self.trainingPairs, batch_size)
        elif trainorval=='VALIDATION':
            pairstofeed = random.sample(self.validationPairs, batch_size)
        else:
            raise ValueError("trainorval must be either TRAIN or VALIDATION")
        for i in range(batch_size):
            condimg_dir = self.index2dir[pairstofeed[i][0]]
            
            print("dataset_reader/condimg_dir",condimg_dir)
      
            
            conditional_image[i], _,_ = self.process_oneimg(condimg_dir)
            targetimg_dir = self.index2dir[pairstofeed[i][1]]
            target_image[i], target_pose[i], target_morphologicals[i] = self.process_oneimg(targetimg_dir)

        g1_feed = np.concatenate([conditional_image, target_pose], axis=3)  # the (batch,256,256,21) thing.
        target_morphologicals = np.expand_dims(target_morphologicals, axis=3)

        if (random.random() <= 0.5):
            g1_feed = np.flip(g1_feed,axis=2)
            conditional_image = np.flip(conditional_image,axis=2)
            target_image = np.flip(target_image,axis=2)
            target_morphologicals = np.flip(target_morphologicals,axis=2)
        return g1_feed, conditional_image, target_image, target_morphologicals

    def extract(self):
        root = os.path.join(os.getcwd(), 'dataset', 'Img')
        root = os.path.abspath(root)

        img_dir = os.path.join(root, 'img')
        keypoints_dir = os.path.join(root, 'img-keypoints')
        name = os.path.join(root, 'set')

        if os.path.exists(name):
            shutil.rmtree(name)
        if not os.path.exists(name):
            os.makedirs(name)

        for folder in os.listdir(keypoints_dir):

            curr_dir = os.path.join(img_dir, folder)
            key_dir = os.path.join(keypoints_dir, folder)

            for folder2 in os.listdir(key_dir):
                curr_dir1 = os.path.join(curr_dir, folder2)
                key_dir1 = os.path.join(key_dir, folder2)

                for folder3 in os.listdir(key_dir1):
                    curr_folder = os.path.join(name, folder3)  # the pointer to the 'set' pool
                    curr_dir2 = os.path.join(curr_dir1, folder3)
                    img_dir_base = copy.deepcopy(curr_dir2)
                    key_dir2 = os.path.join(key_dir1, folder3)

                    # this level is folder-level
                    if not os.path.exists(curr_folder):
                        code2index = {}
                        # if this id is new to 'set'
                        os.makedirs(curr_folder)
                        for file in os.listdir(key_dir2):
                            os.symlink(os.path.join(key_dir2, file), os.path.join(curr_folder, file))

                        for file_name in os.listdir(curr_dir2):
                            path_join = os.path.join(curr_dir2, file_name) # the ACTUAL path
                            if not 'keypoints' in file_name and not 'flat' in file_name:
                                self.index2dir[self.numofphotos] = os.path.join(curr_folder, file_name) # the symlinked path.
                                code = file_name[:2]
                                if not code in code2index:
                                    code2index[code] = [self.numofphotos]
                                else:
                                    code2index[code].append(self.numofphotos)
                                self.numofphotos += 1  # increment global counter
                                os.symlink(path_join, os.path.join(curr_folder, file_name))
                        for k, v in code2index.items():
                            self.groupsofIndices.append(v)


                    else:
                        # this id already exists in the 'set' collection
                        for img in os.listdir(img_dir_base):
                            if not os.path.exists(os.path.join(curr_folder, img)):
                                os.symlink(os.path.join(img_dir_base, img),
                                           os.path.join(curr_folder, img))  # symlink the images
                        for key in os.listdir(key_dir2):
                            if not os.path.exists(os.path.join(curr_folder, key)):
                                os.symlink(os.path.join(key_dir2, key), os.path.join(curr_folder, key))


if __name__ == '__main__':
    loader = DataLoader()
    g1, cond, target, morp  = loader.next_batch(4, trainorval='TRAIN')


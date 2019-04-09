# coding: utf-8
# from data_provider import *
from C3D_model import *
import torchvision
import torch
from torch.autograd import Variable
import torch.nn.functional as F
import argparse
import os 
from torch import save, load
import pickle
import time
import numpy as np
import PIL.Image as Image
import skimage.io as io
from skimage.transform import resize
import h5py
import cv2
import shutil
from PIL import Image
import sys
import Main
import anomalydetector


def feature_extractor(OUTPUT_DIR_TEXT,VIDEO_PATH,TEMP_PATH,EXTRACTED_LAYER = 6,RUN_GPU = True, BATCH_SIZE = 10):

	print(RUN_GPU)
	resize_w = 112

	resize_h = 171
	nb_frames = 16
	#trainloader = Train_Data_Loader( VIDEO_DIR, resize_w=128, resize_h=171, crop_w = 112, crop_h = 112, nb_frames=16)
	net = C3D(487)
	print('net', net)
	## Loading pretrained model from sports and finetune the last layer
	net.load_state_dict(torch.load('./c3d.pickle'))
	if RUN_GPU : 
		net.cuda(0)
		net.eval()
		print('net', net)
	feature_dim = 4096 if EXTRACTED_LAYER != 5 else 8192


	# read video list from the txt list
	'''
	video_list_file = args.video_list_file
	video_list = open(video_list_file).readlines()
	video_list = [item.strip() for item in video_list]
	print('video_list', video_list)
	'''
	gpu_id = 0

	'''
	if not os.path.isdir(OUTPUT_DIR):
		os.mkdir(OUTPUT_DIR)
	f = h5py.File(os.path.join(OUTPUT_DIR, OUTPUT_NAME), 'w')
	'''
	# current location
	temp_path = TEMP_PATH


	error_fid = open('error.txt', 'w')
	video_path = VIDEO_PATH
	video_name = os.path.basename(video_path)
	print('video_name', video_name)
	print('video_path', video_path)
	frame_path = os.path.join(temp_path, 'frames')
	if not os.path.exists(frame_path):
		os.mkdir(frame_path)


	print('Extracting video frames ...')
	# using ffmpeg to extract video frames into a temporary folder
	# example: ffmpeg -i video_validation_0000051.mp4 -q:v 2 -f image2 output/image%5d.jpg
	#os.system('ffmpeg -i ' + video_path + ' -q:v 2 -f image2 ' + frame_path + '/image_%5d.jpg')
	#os.system('ffmpeg -i {} {}/frames/image_%05d.jpg'.format(video_path, frame_path))
	cap = cv2.VideoCapture(video_path)
	count = 1
	while (cap.isOpened()):
		ret, frame =cap.read()
		if (ret!= True):
			break

		cv2.imwrite(os.path.join(frame_path,'image_{}.jpg').format(count),frame)
		count += 1



	print('Extracting features ...')
	total_frames = len(os.listdir(frame_path))
	if total_frames == 0:
		error_fid.write(video_name+'\n')
		print('Fail to extract frames for video: %s'%video_name)


	valid_frames = total_frames / nb_frames * nb_frames
	n_feat = valid_frames / nb_frames
	n_batch = n_feat / BATCH_SIZE
	if n_feat - n_batch*BATCH_SIZE > 0:
		n_batch = n_batch + 1
	print('n_frames: %d; n_feat: %d; n_batch: %d'%(total_frames, n_feat, n_batch))

	#print 'Total frames: %d'%total_frames
	#print 'Total validated frames: %d'%valid_frames
	#print 'NB features: %d' %(valid_frames/nb_frames)


	features = []

	for i in range((int)(n_batch)-1):
		input_blobs = []
		for j in range(BATCH_SIZE):
			clip = []
			clip = np.array([resize(io.imread(os.path.join(frame_path, 'image_{:01d}.jpg'.format(k))), output_shape=(resize_w, resize_h), preserve_range=True) for k in range((i*BATCH_SIZE+j) * nb_frames+1, min((i*BATCH_SIZE+j+1) * nb_frames+1, valid_frames+1))])
			#print('clip_shape', clip.shape)
			clip = clip[:, 8: 120, 30: 142, :]
			#print('clip_shape',clip.shape)
			#print('range', range((i*BATCH_SIZE+j) * nb_frames+1, min((i*BATCH_SIZE+j+1) * nb_frames+1, valid_frames+1)))
			input_blobs.append(clip)
		input_blobs = np.array(input_blobs, dtype='float32')
		print('input_blobs_shape', input_blobs.shape)
		input_blobs = torch.from_numpy(np.float32(input_blobs.transpose(0, 4, 1, 2, 3)))
		input_blobs = Variable(input_blobs).cuda() if RUN_GPU else Variable(input_blobs)
		_, batch_output = net(input_blobs, EXTRACTED_LAYER)
		batch_feature  = (batch_output.data).cpu()
		features.append(batch_feature)

	# The last batch
	input_blobs = []
	for j in range((int)(n_feat-(n_batch-1)*BATCH_SIZE)):
		clip = []
		clip = np.array([resize(io.imread(os.path.join(frame_path, 'image_{:01d}.jpg'.format(k))),
								output_shape=(resize_w, resize_h), preserve_range=True) for k in
						 range(int((((n_batch - 1) * BATCH_SIZE + j) * nb_frames + 1)),
							   min(int(((n_batch - 1) * BATCH_SIZE + j + 1) * nb_frames + 1), valid_frames + 1,
								   int((((n_batch - 1) * BATCH_SIZE + j) * nb_frames + 1) + 15)))])

		clip = clip[:, 8: 120, 30: 142, :]
		#print('range', range(((n_batch-1)*BATCH_SIZE+j) * nb_frames+1, min(((n_batch-1)*BATCH_SIZE+j+1) * nb_frames+1, valid_frames+1)))
		input_blobs.append(clip)
	input_blobs = np.array(input_blobs, dtype='float32')
	#print('input_blobs_shape', input_blobs.shape)
	input_blobs = torch.from_numpy(np.float32(input_blobs.transpose(0, 4, 1, 2, 3)))
	input_blobs = Variable(input_blobs).cuda() if RUN_GPU else Variable(input_blobs)
	_, batch_output = net(input_blobs, EXTRACTED_LAYER)
	batch_feature  = (batch_output.data).cpu()
	features.append(batch_feature)

	features = torch.cat(features, 0)
	features = features.numpy()
	Segments_Features = np.zeros((32, 4096))


	frameclips = np.size(features, 0)

	clipsegments = np.round(np.linspace(0, frameclips, 32))

	count = 0

	for segment in range(0, clipsegments.size - 1):

		clipstart = clipsegments[segment]
		clipend = clipsegments[segment + 1] - 1
		if segment == clipsegments.size:
			clipend = clipsegments[segment + 1]

		if (clipstart == clipend):

			try:
				temp_vect = features[int(clipstart), :]
			except:
				temp_vect = features[int(clipstart - 1), :]

		elif (clipend < clipstart):
			try:
				temp_vect = features[int(clipstart), :]
			except:
				temp_vect = features[int(clipstart - 1), :]

		else:
			temp_vect = np.mean(features[int(clipstart):int(clipend), :], axis=0)

		temp_vect = (temp_vect / np.linalg.norm(temp_vect))

		if np.linalg.norm(temp_vect) == 0:
			print('??')

		Segments_Features[count, :] = temp_vect
		count = count + 1

	result = np.matrix(Segments_Features)
	with open(OUTPUT_DIR_TEXT + '{}.txt'.format(video_name), 'wb') as f:
		for line in result:
			np.savetxt(f, line, fmt='%.6f')

	# clear temp frame folders
	try:
		shutil.rmtree(frame_path)
	except:
		pass



	sniplist = anomalydetector.anomalydetector(VIDEO_PATH,OUTPUT_DIR_TEXT,video_name)
	print(sniplist)
	Severity_High = 'Media/severity_high.png'
	Severity_Medium = 'Media/severity_medium.png'
	Severity_Low = 'Media/severity_low.png'
	DR = Main.DisplayRoot()

	for snip_vids in sniplist:
		print(snip_vids)
		severity = float(snip_vids[2])
		thumbnail_path = os.path.join(TEMP_PATH,snip_vids[1])
		print(thumbnail_path)
		if(severity >= 0.7 ):
			DR.add_widget(Main.Snippet(thumbnail_path,Severity_High,snip_vids[0]))
		elif severity >= 0.3 and severity < 0.7:
			DR.add_widget(Main.Snippet(thumbnail_path, Severity_Medium,snip_vids[0]))
		else:
			DR.add_widget(Main.Snippet(thumbnail_path, Severity_Low,snip_vids[0]))

	mainmenu = Main.App.get_running_app().root.get_screen("MainMenu")

	SS = mainmenu.SS
	SS.add_widget(DR)
	mainmenu.ids.Snippets.add_widget(SS)
	mainmenu.ids.videoplayer.source = ''
import numpy as np
import cv2
import onnxruntime
import torch
from skimage import transform as trans


arcface_dst = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
     [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=np.float32)

def estimate_norm(lmk, dst, image_size):
    assert lmk.shape == (5, 2)
    tform = trans.SimilarityTransform()
    #src = float(image_size) / 112 * dst
    tform.estimate(lmk, dst)
    M = tform.params[0:2, :]
    return M


def norm_crop(img, landmark, dst=arcface_dst, image_size=112):
    M = estimate_norm(landmark, dst, image_size)
    warped = cv2.warpAffine(img, M, (image_size, image_size), borderValue=0.0)
    return warped, M

def transform(data, center, output_size, scale, rotation=0):
    #scale_ratio = float(output_size)/scale
    scale_ratio = scale
    rot = float(rotation)*np.pi/180.0
    #translation = (output_size/2-center[0]*scale_ratio, output_size/2-center[1]*scale_ratio)
    t1 = trans.SimilarityTransform(scale=scale_ratio)
    cx = center[0]*scale_ratio
    cy = center[1]*scale_ratio
    t2 = trans.SimilarityTransform(translation=(-1*cx, -1*cy))
    t3 = trans.SimilarityTransform(rotation=rot)
    t4 = trans.SimilarityTransform(translation=(output_size/2, output_size/2))
    t = t1+t2+t3+t4
    M = t.params[0:2]
    #print('M', scale, rotation, trans)
    cropped = cv2.warpAffine(data,M,(output_size, output_size), borderValue = 0.0)
    return cropped, M

def trans_points2d(pts, M):
    new_pts = np.zeros(shape=pts.shape, dtype=np.float32)
    for i in range(pts.shape[0]):
        pt = pts[i]
        new_pt = np.array([pt[0], pt[1], 1.], dtype=np.float32)
        new_pt = np.dot(M, new_pt)
        #print('new_pt', new_pt.shape, new_pt)
        new_pts[i] = new_pt[0:2]

    return new_pts

def get_providers():
    #return ['TensorrtExecutionProvider', 'CUDAExecutionProvider']
    return ['CUDAExecutionProvider']


class Landmark:
    def __init__(self, path):
        self.lmk = onnxruntime.InferenceSession(path, providers=get_providers())
        input_cfg = self.lmk.get_inputs()[0]
        input_shape = input_cfg.shape
        input_name = input_cfg.name
        outputs = self.lmk.get_outputs()
        output_names = []
        for o in outputs:
            output_names.append(o.name)
        self.lmk_input_name = input_name
        self.lmk_output_names = output_names

    def get(self, img, bbox):
        center = (bbox[2]+bbox[0])/2, (bbox[3]+bbox[1])/2
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        face_size = max(w, h)
        imsize = 96
        _scale = imsize/(face_size*1.5)
        img96, M = transform(img, center, imsize, _scale)
        IM96 = cv2.invertAffineTransform(M)
        blob = cv2.dnn.blobFromImage(img96, 1.0, (imsize,imsize), (0.0, 0.0, 0.0), swapRB=True)
        pose_pred = self.lmk.run(self.lmk_output_names, {self.lmk_input_name : blob})[0][0]
        pose = pose_pred[0:3]*90
        blur = pose_pred[13:]
        pts5 = (pose_pred[3:13].reshape( (5,2) )+1.0)*(96/2)
        pts5 = trans_points2d(pts5, IM96)
        return pts5


class ArcFaceONNX:
    def __init__(self, path):
        self.session = None
        input_mean = 127.5
        input_std = 127.5
        self.input_mean = input_mean
        self.input_std = input_std
        self.session = onnxruntime.InferenceSession(path, providers=get_providers())
        input_cfg = self.session.get_inputs()[0]
        input_shape = input_cfg.shape
        input_name = input_cfg.name
        self.channel_in = input_shape[1]
        self.input_size = tuple(input_shape[2:4][::-1])
        self.input_shape = input_shape
        #print(self.input_shape, self.channel_in)
        outputs = self.session.get_outputs()
        output_names = []
        for out in outputs:
            output_names.append(out.name)
        self.input_name = input_name
        self.output_names = output_names
        assert len(self.output_names)==1
        self.output_shape = outputs[0].shape
        self.enable_flip = False
        self.blob_one = np.zeros( (int(self.enable_flip)+1, self.channel_in)+self.input_size, dtype=np.float32 )
        self.blob_pair = np.zeros( (int(self.enable_flip)*2+2, self.channel_in)+self.input_size, dtype=np.float32 )

    def forward(self, img):
        blob = img
        blob -= self.input_mean
        blob /= self.input_std
        #tb = datetime.datetime.now()
        #print('PRE', (tb-ta).total_seconds())
        #print(blob.shape)

        embs = self.session.run(self.output_names, {self.input_name: blob})[0]
        return embs

    def get(self, img_list, kps_list):
        #ta = datetime.datetime.now()
        num = len(img_list)
        assert num==1 or num==2
        assert len(img_list)==len(kps_list)
        if num==1:
            blob = self.blob_one
        else:
            blob = self.blob_pair
        index = 0
        for img, kps in zip(img_list, kps_list):
            aimg, _ = norm_crop(img, landmark=kps)
            if self.channel_in==1:
                aimg = cv2.cvtColor(aimg, cv2.COLOR_BGR2GRAY)
                aimg = aimg[:, :, np.newaxis]
            else:
                aimg = aimg[:,:,::-1]
            aimg = aimg.transpose( (2,0,1) ) #(c,h,w)
            blob[index] = aimg
            if self.enable_flip:
                blob[index+num] = aimg[:,:,::-1]
            index+=1
        blob -= self.input_mean
        blob /= self.input_std
        #tb = datetime.datetime.now()
        #print('PRE', (tb-ta).total_seconds())
        #print(blob.shape)

        embs = self.session.run(self.output_names, {self.input_name: blob})[0]
        ret = []
        for i in range(num):
            emb = embs[i]
            if self.enable_flip:
                emb += embs[i+num]
                emb /= 2.0
            ret.append(emb)
        #emb = emb.flatten()
        return ret

    def compute_sim(self, feat1, feat2):
        from numpy.linalg import norm
        feat1 = feat1.ravel()
        feat2 = feat2.ravel()
        sim = np.dot(feat1, feat2) / (norm(feat1) * norm(feat2))
        return sim

class InferONNX:
    def __init__(self, path, input_mean=0.0, input_std=255.0):
        self.session = onnxruntime.InferenceSession(path, providers=get_providers())
        self.input_mean = input_mean
        self.input_std = input_std
        #input_cfg = self.session.get_inputs()[0]
        #input_shape = input_cfg.shape
        #input_name = input_cfg.name
        #self.input_size = tuple(input_shape[2:4][::-1])
        #self.input_shape = input_shape
        inputs = self.session.get_inputs()
        self.input_names = []
        for inp in inputs:
            self.input_names.append(inp.name)
        outputs = self.session.get_outputs()
        output_names = []
        for out in outputs:
            output_names.append(out.name)
        self.output_names = output_names
        assert len(self.output_names)==1
        output_shape = outputs[0].shape


    def forward(self, img, latent):
        img = (img - self.input_mean) / self.input_std
        pred = self.session.run(self.output_names, {self.input_names[0]: img, self.input_names[1]: latent})[0]
        return pred

class InferScript:
    def __init__(self, path, input_mean=0.0, input_std=255.0):
        self.input_mean = input_mean
        self.input_std = input_std
        self.device = torch.device('cuda:0')
        self.net = torch.jit.load(path).to(self.device)
        self.net.eval()


    def forward(self, img, latent):
        img = (img - self.input_mean) / self.input_std
        img = torch.tensor(img).to(self.device)
        latent = torch.tensor(latent).to(self.device)
        with torch.no_grad():
            pred = self.net.forward(img, latent)
        pred = pred.cpu().numpy()
        return pred


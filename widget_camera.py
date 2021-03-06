# -*- coding: utf-8 -*-

"""
Author: mxy
Email: mxy493@qq.com
Date: 2020/11/3
Desc: 摄像头界面
"""
import os
from pathlib import Path
import numpy as np
import time
import cv2

from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QPainter, QColor, QPixmap, QImage, QFont, QBrush, QPen
from PyQt5.QtWidgets import QWidget
import msg_box
from gb import thread_runner, YOLOGGER
from yolo import YOLO5

class WidgetCamera(QWidget):
    def __init__(self):
        super(WidgetCamera, self).__init__()

        self.yolo = YOLO5()
        current_date = time.strftime('%d-%m-%Y_%H-%M', time.localtime())
        self.path = f'output/{current_date}'

        self.sh, self.sw = self.height(), self.width()
        self.opened = False                                 # Camera Opened
        self.detecting = False                              # Target detection thread active
        self.cap = cv2.VideoCapture()

        self.fourcc = cv2.VideoWriter_fourcc(*"XVID")  # XVID MPEG-4
        self.writer = cv2.VideoWriter()  # Record Vide, turn on camera then record

        self.pix_image = None   # QPixmap video frame
        self.image = None       # Current image
        self.scale = 1          # Scaling
        self.objects = []
        self.rec_src = None     # Video Recorder source
        self.ox, self.oy, self.ow, self.oh = 0,0,0,0

        self.fps = 0            # Frame rate

    def open_camera(self, use_camera, video):
        """Turn on camera (webcam), return true if success"""
        self.x = 1
        YOLOGGER.info('Turn on Camera')
        cam = 0                     # Default camera (/dev/video0)
        if not use_camera:
            cam = video             # If Source is video 
        flag = self.cap.open(cam)   # open camera
        if flag:
            self.opened = True      # Open Camera
            return True
        else:
            msg = msg_box.MsgWarning()
            msg.setText('Failed to start video！\n'
                        'Make sure camera or video file correct！')
            msg.exec()
            return False

    def close_camera(self):
        YOLOGGER.info('Turn off camera')
        self.opened = False         #  Close YOLO detection then camera
        self.stop_detect()          # Stop YOLO
        time.sleep(0.1)             # Wait for last frame to be detected
        self.cap.release()
        self.x = 1
        self.reset()                # Return to original state

    @thread_runner
    def show_camera(self, fps=0):
        """Pass frame information, camera is 0 while video is 30 or 60"""
        YOLOGGER.info('Display thread start')
        wait = 1 / fps if fps else 0
        while self.opened:
            self.read_image()       # read frame every 0.02 or 0.03s
            if fps:
                time.sleep(wait)    # wait for [wait] seconds before read and display frame
            self.update()
        self.update()
        YOLOGGER.info('Display thread ends')

    def read_image(self):
        ret, img = self.cap.read()
        if ret:
            if img.shape[2] == 4:
                img = img[:, :, :-1]
            self.image = img

    def cv_bounding_box(self):
        img = self.image
        for obj in self.objects:
            rgb = [round(c) for c in obj['color']]
            color = (rgb[0], rgb[1], rgb[2])
            point = (self.ox, self.oy)
            size = (self.ow, self.oh)
            img = cv2.rectangle(img, point, size, color, 1)
            img = cv2.putText(img, str(obj['class']) + str(round(obj['confidence'], 2)), (self.ox, self.oy-5), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 1, cv2.LINE_AA)
        self.rec_src = img

    @thread_runner
    def run_video_recorder(self, fps=30):
        self.record = True
        """Run video writer"""
        YOLOGGER.info('Video writer run')
        now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
        if not os.path.exists('output'):        # make sure output folder exist, if not create one
            os.mkdir('output')
        if not os.path.exists(self.path):
            os.mkdir(self.path)
        t0 = time.time()   
        while self.image is None:               # Wait for Image to be available
            time.sleep(0.01)
            if time.time() - t0 > 3:            # Avoid thread can't exist due to no screen
                YOLOGGER.warning('Frame was not acquired after timeout, video recording canceled')
                break

        # If image exist, start recording
        if self.image is not None: 
            # open video writer
            self.writer.open(
                filename=f'{self.path}/{now}_record.avi',
                fourcc=self.fourcc,
                fps=fps,
            frameSize=(self.sw, self.sh))           # Video Recording size
            wait = 1 / fps - 0.004                  # wait for writer to finish
            while self.opened:
                self.writer.write(self.rec_src)
                cv2.waitKey(1)
                self.cv_bounding_box()
        self.record = False
        YOLOGGER.info('video recording thread ends')

    def stop_video_recorder(self):
        # Stop video recording thread
        if self.writer.isOpened():
            self.writer.release()
            path = os.path.abspath('output')
            msg = msg_box.MsgSuccess()
            msg.setText(f'The recorded video has been saved to the following path:\n{path}')
            msg.exec()

    def image_capture(self):
        img_name = f"{self.path}/capture_{self.x}.png"
        img = QPixmap(self.grab(QRect(0,0, self.sw, self.sh)))
        QPixmap.save(img, img_name, "JPEG", 100)
        YOLOGGER.info("Image captured")
        self.x += 1

    @thread_runner
    def start_detect(self):
        # Initialized YOLO parameter
        YOLOGGER.info('Target detection thread starts')
        self.detecting = True
        while self.detecting:
            if self.image is None:      # If image is not exist, skip detection
                continue
            t0 = time.time()
            self.objects = self.yolo.obj_detect(self.image)
            t1 = time.time()
            self.fps = 1 / (t1 - t0)
            self.update()
        self.update()
        YOLOGGER.info('Target detection thread ends')

    def stop_detect(self):
        # YOLO detection thread ends
        self.detecting = False

    def reset(self):
        # Return to original state
        self.opened = False     # Camera closed
        self.pix_image = None   # Video frame pixmap None
        self.image = None       # Remove image from variable
        self.scale = 1          # Return proportion to 1
        self.objects = []       # Celar detection objects
        self.fps = 0            # FPS to 0

    def resizeEvent(self, event):   # Reize window event, rescale images
        self.update()

    def paintEvent(self, event):    # Paint event for displaying image and bounding box
        qp = QPainter()
        qp.begin(self)
        self.draw(qp)
        qp.end()


    def draw(self, qp):
        qp.setWindow(0, 0, self.width(), self.height())  # Set drawing window
        qp.setRenderHint(QPainter.SmoothPixmapTransform)
        qp.setPen(Qt.NoPen)
        rect = QRect(0, 0, self.width(), self.height())
        qp.drawRect(rect)
        sw, sh = self.width(), self.height()            # Image frame size

        if not self.opened:
            qp.drawPixmap((sw-1)/2-100, sh/2-100, 200, 200, QPixmap('img/video.svg'))

        # Draw Image to pixmap and displaying it
        if self.opened and self.image is not None:
            ih, iw, _ = self.image.shape
            self.scale = sw / iw if sw / iw < sh / ih else sh / ih  # scaling ratio
            px = round((sw - iw * self.scale) / 2)
            py = round((sh - ih * self.scale) / 2)
            qimage = QImage(self.image.data, iw, ih, 3 * iw, QImage.Format_BGR888)  # CV2 Image to QImage
            qpixmap = QPixmap.fromImage(qimage.scaled(sw, sh, Qt.KeepAspectRatio))  # QImage to Pixmap
            pw, ph = qpixmap.width(), qpixmap.height()                              # Get Pixmap's dimension
            qp.drawPixmap(px, py, qpixmap)
            
            # Bounding Box for objects
            font = QFont()
            font.setFamily('Microsoft YaHei')
            font.setPointSize(12)
            qp.setFont(font)
            brush1 = QBrush(Qt.NoBrush)  # Internal without filling
            qp.setBrush(brush1)
            pen = QPen()
            pen.setWidth(2)  # Bounding box line width
            for obj in self.objects:
                rgb = [round(c) for c in obj['color']]
                pen.setColor(QColor(rgb[0], rgb[1], rgb[2]))  # Set color from model color
                qp.setPen(pen)
                self.ox, self.oy = px + round(pw * obj['x']), py + round(ph * obj['y'])
                self.ow, self.oh = round(pw * obj['w']), round(ph * obj['h'])
                obj_rect = QRect(self.ox, self.oy, self.ow, self.oh)
                qp.drawRect(obj_rect)  # Draw rectangle 
                # Draw class and confidence
                qp.drawText(self.ox, self.oy - 5, str(obj['class']) + str(round(obj['confidence'], 2)))
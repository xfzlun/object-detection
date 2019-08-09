import os
import io
import cv2
import picamera
import numpy as np
from celery import Celery
from datetime import datetime, timedelta
from importlib import import_module
from picamera.array import PiRGBArray
from picamera import PiCamera
from backend.base_camera import BaseCamera
Detector = import_module('backend.' + os.environ['DETECTION_MODEL']).Detector
detector = Detector()

WIDTH = 640
HEIGHT = 480
IMAGE_FOLDER = "./imgs"

celery = Celery("app")
celery.conf.update(
        broker_url='redis://localhost:6379/0',
        result_backend='redis://localhost:6379/0',
        beat_schedule={
            "photos_SO": {
                "task": "backend.camera_pi.CaptureContinous",
                "schedule": timedelta(seconds=5),
                "args": []
                }
            }
)


class CameraPred(BaseCamera):
    @staticmethod
    def frames():
        with PiCamera() as camera:
            camera.rotation = 180

            stream = io.BytesIO()
            for _ in camera.capture_continuous(stream, 'jpeg',
                                                 use_video_port=True):
                # return current frame
                #stream.seek(0)
                #yield stream.read()

                #_stream = stream.getvalue()
                #data = np.fromstring(_stream, dtype=np.uint8)
                #img = cv2.imdecode(data, 1)
                #yield _stream

                _stream = stream.getvalue()
                data = np.fromstring(_stream, dtype=np.uint8)
                img = cv2.imdecode(data, 1)
                # Prediction
                output = detector.prediction(img)
                df = detector.filter_prediction(output, img)
                img = detector.draw_boxes(img, df)
                yield cv2.imencode('.jpg', img)[1].tobytes()

                # reset stream for next frame
                stream.seek(0)
                stream.truncate()


class Camera(BaseCamera):
    @staticmethod
    def frames():
        with PiCamera() as camera:
            camera.rotation = 180
            stream = io.BytesIO()
            for _ in camera.capture_continuous(stream, 'jpeg',
                                                 use_video_port=True):
                # return current frame
                stream.seek(0)
                yield stream.read()

                # reset stream for next frame
                stream.seek(0)
                stream.truncate()


@celery.task(bind=True)
def CaptureContinous(self):
    camera = PiCamera()
    camera.rotation = 180
    camera.resolution = (WIDTH, HEIGHT)
    camera.framerate = 10
    rawCapture = PiRGBArray(camera, size=(WIDTH, HEIGHT))
    rawCapture.truncate(0)
    for frame in camera.capture_continuous(
            rawCapture,
            format="bgr",
            use_video_port=True
            ):
        image = frame.array
        rawCapture.truncate(0)
        output = detector.prediction(image)
        df = detector.filter_prediction(output, image)
        if len(df) > 0:
            if (df['class_name']
                    .str
                    .contains('person|bird|cat|wine glass|cup|sandwich')
                    .any()):
                day = datetime.now().strftime("%Y%m%d")
                directory = os.path.join(IMAGE_FOLDER, 'pi', day)
                if not os.path.exists(directory):
                    os.makedirs(directory)
                image = detector.draw_boxes(image, df)
                classes = df['class_name'].unique().tolist()
                hour = datetime.now().strftime("%H%M%S")
                filename_output = os.path.join(
                        directory, "{}_{}_.jpg".format(hour, "-".join(classes))
                        )
                cv2.imwrite(filename_output, image)

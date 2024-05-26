import argparse
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer, RTCIceCandidate, RTCDataChannel,MediaStreamTrack
from aiortc.rtcrtpreceiver import RemoteStreamTrack
import socketio
import asyncio
import time
import pyaudio

#import fractions
from av import AudioFrame, VideoFrame
from av.frame import Frame
import fractions
import numpy as np
import threading

from aiortc.contrib.media import MediaPlayer,MediaRecorderContext #MediaRecorder

# Global Variables
#WEBSOCKET_ADDRESS = "localhost"  # all on the same machine, this is also the "ws-server.py"
WEBSOCKET_ADDRESS = "192.33.91.242"  # Noah's server


config = RTCConfiguration(
    iceServers=[
        RTCIceServer(
            urls=[
                "stun:stun.l.google.com:19302",
                "stun:stun1.l.google.com:19302",
                "stun:stun2.l.google.com:19302",
                "stun:stun3.l.google.com:19302",
                "stun:stun4.l.google.com:19302",
            ]
        ),
    ]
)

#Args parameters function
def parse_args():
    parser = argparse.ArgumentParser(
        description="Python client with audio",
        epilog="Examples: \n\npython rp_client_audio.py --id 123 --callee 345 \npython rp_client_audio.py --callerId 123 --calleeId 456 --callerBool False\n",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--id", help="Your ID")
    parser.add_argument("--callee", help="Callee ID if you are the caller")
    args = parser.parse_args()

    return args

from av import AudioFrame
import pyaudio
import av
import numpy as np

from threading import Thread, Event, Lock
from aiortc.mediastreams import MediaStreamTrack

def parser_candidate(candidate_dict):
    #candidate_dict={'candidate': 'candidate:955633931 1 tcp 1518283007 2001:67c:10ec:574c:8000::46c 63889 typ host tcptype passive generation 11 ufrag D98f network-id 2 network-cost 10', 'sdpMLineIndex': 0, 'sdpMid': '0'}
    # If candidate_dict is a string, parse it into a dictionary


    candidate_str = candidate_dict['candidate']
    sdpMid = candidate_dict['sdpMid']
    sdpMLineIndex = candidate_dict['sdpMLineIndex']

    # Split the candidate string into parts
    candidate_parts = candidate_str.split(' ')
    #print("candidate parts: ", candidate_parts)
    # Extract the necessary parts
    foundation = candidate_parts[0].split(':')[1]
    component = candidate_parts[1]
    protocol = candidate_parts[2]
    priority = candidate_parts[3]
    ip = candidate_parts[4]
    port = candidate_parts[5]
    type = candidate_parts[7]

    # Create the RTCIceCandidate object
    if type == "srflx":
        relatedAddress = candidate_parts[12]
        relatedPort = candidate_parts[14]
        rtc_ice_candidate = RTCIceCandidate(component=component, foundation=foundation, sdpMid=sdpMid, sdpMLineIndex=sdpMLineIndex, ip=ip, port=port, priority=priority, protocol=protocol, type=type, relatedAddress=relatedAddress, relatedPort=relatedPort)
    else:
        rtc_ice_candidate = RTCIceCandidate(component=component, foundation=foundation, sdpMid=sdpMid, sdpMLineIndex=sdpMLineIndex, ip=ip, port=port, priority=priority, protocol=protocol, type=type)

    return rtc_ice_candidate

import asyncio
import threading
import pyaudio
import numpy as np
import av


class MediaRecorderContext:
    def __init__(self, stream):
        self.stream = stream
        self.task = None
        self.started = False

class MediaRecorder:
    """
    A media sink that writes audio and/or video to a file.

    Examples:

    .. code-block:: python

        # Write to a video file.
        player = MediaRecorder('/path/to/file.mp4')

        # Write to a set of images.
        player = MediaRecorder('/path/to/file-%3d.png')

    :param file: The path to a file, or a file-like object.
    :param format: The format to use, defaults to autodetect.
    :param options: Additional options to pass to FFmpeg.
    """

    def __init__(self, file, format=None, options=None):
        self.__container = av.open(file=file, format=format, mode="w", options=options)
        self.__tracks = {}
        self.stream = pyaudio.PyAudio().open(
            format=pyaudio.paInt32,
            channels=1,
            rate=44100,
            output=True,
            frames_per_buffer=512,
            output_device_index=2
        )
        self.audio_buffer = []
        self.audio_buffer_lock = threading.Lock()
        self.audio_thread = threading.Thread(target=self._play_audio)
        self.audio_thread.start()

    def addTrack(self, track):
        """
        Add a track to be recorded.

        :param track: A :class:`aiortc.MediaStreamTrack`.
        """
        print("starting to add the external track")
        if track.kind == "audio":
            print("track is audio as intended")
            if self.__container.format.name in ("wav", "alsa", "pulse"):
                codec_name = "pcm_s16le"
            elif self.__container.format.name == "mp3":
                codec_name = "mp3"
            else:
                codec_name = "aac"
            stream = self.__container.add_stream(codec_name)
        else:
            if self.__container.format.name == "image2":
                stream = self.__container.add_stream("png", rate=30)
                stream.pix_fmt = "rgb24"
            else:
                stream = self.__container.add_stream("libx264", rate=30)
                stream.pix_fmt = "yuv420p"
        self.__tracks[track] = MediaRecorderContext(stream)

    async def start(self):
        """
        Start recording.
        """
        print("started correctly with this items: ", self.__tracks.items())
        for track, context in self.__tracks.items():
            print("got track")
            if context.task is None:
                print("task is none")
                context.task = asyncio.ensure_future(self.__run_track(track, context))

    async def stop(self):
        """
        Stop recording.
        """
        if self.__container:
            for track, context in self.__tracks.items():
                if context.task is not None:
                    context.task.cancel()
                    context.task = None
                    for packet in context.stream.encode(None):
                        self.__container.mux(packet)
            self.__tracks = {}

            if self.__container:
                self.__container.close()
                self.__container = None

        if self.audio_thread.is_alive():
            self.audio_thread.join()

    async def __run_track(self, track: MediaStreamTrack, context: MediaRecorderContext):
        while True:
            try:
                frame = await track.recv()
            except MediaStreamError:
                return

            '''if not context.started:
                # adjust the output size to match the first frame
                if isinstance(frame, VideoFrame):
                    context.stream.width = frame.width
                    context.stream.height = frame.height
                context.started = True'''

            # for packet in context.stream.encode(frame):
            print("doing stuff")
            # self.__container.mux(packet)
            audio_data = frame.to_ndarray().tobytes()
            with self.audio_buffer_lock:
                self.audio_buffer.append(audio_data)

    def _play_audio(self):
        while True:
            if self.audio_buffer:
                with self.audio_buffer_lock:
                    audio_data = self.audio_buffer.pop(0)
                self.stream.write(audio_data)
            else:
                time.sleep(0.001)  # Evita di occupare troppo la CPU


class SystemMic(MediaStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()

        self.kind = "audio"
        self.RATE = 44100
        self.AUDIO_PTIME = 0.020  # 20ms audio packetization
        self.SAMPLES = int(self.AUDIO_PTIME * self.RATE)
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.CHUNK = int(self.RATE * self.AUDIO_PTIME)
        self.INDEX = 1
        self.FORMATAF = 's16'  # 's32'                           # s32_le
        self.LAYOUT = 'mono'
        self.sampleCount = 0

        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(format=self.FORMAT, channels=self.CHANNELS, rate=self.RATE,
                                      input=True, input_device_index=self.INDEX,
                                      frames_per_buffer=self.CHUNK)
        # thread
        self.micData = None
        self.micDataLock = threading.Lock()
        self.newMicDataEvent = threading.Event()
        self.newMicDataEvent.clear()
        self.captureThread = threading.Thread(target=self.capture)
        self.captureThread.start()

    def capture(self):
        while True:
            data = np.fromstring(self.stream.read(self.CHUNK), dtype=np.int16)

            with self.micDataLock:
                self.micData = data
                self.newMicDataEvent.set()

    async def recv(self):
        newMicData = None

        self.newMicDataEvent.wait()

        with self.micDataLock:
            data = self.micData
            data = (data / 2).astype('int16')
            data = np.array([data])
            self.newMicDataEvent.clear()

        frame = av.AudioFrame.from_ndarray(data, self.FORMATAF, layout=self.LAYOUT)
        frame.pts = self.sampleCount
        frame.rate = self.RATE
        self.sampleCount += frame.samples

        return frame

    def stop(self):
        super.stop()
        self.stream.stop_stream()
        self.stream.close()
        self.audio.terminate()
        self.captureThread.join()

# asyncio socket client
sio = socketio.AsyncClient(logger=True)

pc = RTCPeerConnection(config)

# Global variable to keep the DataChannel reference
data_channel = None

# List to store ICE candidates
local_ice_candidates = []

@sio.event
async def connect():
    print('Connected')
    print('Socket ID:', sio.sid)

@sio.event
async def disconnect():
    print('Disconnected')

@sio.on('message')
async def on_message(message):
    await message_func(message)

#Probabilmente si può rimuovere
@pc.on('icecandidate')
async def on_icecandidate(event):
    if event.candidate:
        candidate_dict = {
            "candidate": event.candidate.candidate,
            "sdpMid": event.candidate.sdpMid,
            "sdpMLineIndex": event.candidate.sdpMLineIndex,
        }
        local_ice_candidates.append(candidate_dict)
    else:
        print("End of candidates")

@pc.on('connectionstatechange')
def on_connectionstatechange():
    print('Connection state:', pc.connectionState)
    if pc.connectionState == 'connected':
        print('Peers are connected!')

@pc.on('signalingstatechange')
def on_signalingstatechange():
    print('Signaling state:', pc.signalingState)

@pc.on('iceconnectionstatechange')
def on_iceconnectionstatechange():
    print('ICE connection state:', pc.iceConnectionState)

@pc.on('datachannel')
def on_datachannel(channel: RTCDataChannel):
    global data_channel
    data_channel = channel
    print('Data channel is created')

    @channel.on('open')
    def on_open():
        print('Data channel is open')
        channel.send("ping")

    @channel.on('message')
    def on_message(message):
        print('Received message:', message)
        if message == "ping":
            channel.send("pong")

@pc.on("track")
def on_track(track):
    print("Track %s received" % track.kind)
    if track.kind == "audio":
        p = pyaudio.PyAudio()
        print(track)
        recorder.addTrack(track)
        
        '''while True:
            mic=RemoteStreamTrack(track)
            frame=mic.recv()
            print(frame)
            # Extract sample rate from the frame
            if stream is None:
                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=frame.layout.channels,
                    rate=frame.sample_rate,
                    output=True,
                    output_device_index=0
                )
                print("stream opened")

            # Play the audio frame
            try:
                stream.write(frame.to_ndarray().tobytes())
            except Exception as e:
                print("Error writing audio frame to stream:", e)'''
   



async def message_func(message):
    if 'answer' in message:
        print("Received answer from", message['sender'])
        
        remote_description = RTCSessionDescription(**message['answer'])
        await pc.setRemoteDescription(remote_description)
        await recorder.start()

    if 'offer' in message:
        print("Received offer from", message['sender'])
        offer_description = RTCSessionDescription(**message['offer'])
        await pc.setRemoteDescription(offer_description)
        answer_description = await pc.createAnswer()
        await pc.setLocalDescription(answer_description)

        # Wait until ICE gathering is complete
        while pc.iceGatheringState != 'complete':
            print("ICE gathering state:", pc.iceGatheringState)
            await asyncio.sleep(0.2)

        answer_dict = {"type": answer_description.type, "sdp": pc.localDescription.sdp}
        await sio.emit('message', {'receiver': message['sender'], 'answer': answer_dict})

        print('Sent answer with ICE candidates')

    if 'iceCandidate' in message:
        await asyncio.sleep(1)
        print("adding new ice candidate")
        try:
            candidate_dict = message['iceCandidate']
            candidate = parser_candidate(candidate_dict)
            await pc.addIceCandidate(candidate) 
        except Exception as e:
            print('Error adding received ice candidate', e)

async def start_call(calleeId):
    global data_channel
    data_channel = pc.createDataChannel('chat')
    print('Data channel is created locally')

    @data_channel.on('open')
    def on_open():
        print('Data channel is open')
        data_channel.send("ping")

    @data_channel.on('message')
    def on_message(message):
        print('Received message:', message)
        if message == "ping":
            data_channel.send("pong")

    pc.addTransceiver("audio")
    mic_track = SystemMic()
    pc.addTrack(mic_track)

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    # Wait until ICE gathering is complete
    while pc.iceGatheringState != 'complete':
        print("ICE gathering state:", pc.iceGatheringState)
        await asyncio.sleep(0.2)

    offer_dict = {'type': offer.type, 'sdp': pc.localDescription.sdp}
    await sio.emit('message', {'receiver': calleeId, 'offer': offer_dict})
    print('Sent offer with ICE candidates')
    

async def main():
    await sio.connect(f'http://{WEBSOCKET_ADDRESS}:4000?callerId={id}', transports=['websocket'], socketio_path='socket.io')
    if callee is not None:
        await start_call(callee)
    
    await sio.wait()


args = parse_args()
id = args.id
callee = args.callee
recorder = MediaRecorder("./file.wav",format='wav')

if __name__ == '__main__':
    asyncio.run(main())
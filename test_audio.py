import scipy.io.wavfile as wav
import numpy as np
from moviepy.audio.AudioClip import AudioArrayClip

fps, data = wav.read("assets/music/soft_tick.wav")
# Normalize to -1.0 to 1.0 float if it's int16
if data.dtype == np.int16:
    data = data.astype(np.float32) / 32768.0

if len(data.shape) == 1:
    data = np.vstack((data, data)).T

clip = AudioArrayClip(data, fps=fps)
print("Duration:", clip.duration)
print("Max val:", np.max(data))

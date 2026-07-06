import os
import numpy as np
from scipy.io import wavfile
import scipy.signal

def save_wav(filename, audio, sample_rate=44100):
    audio_int = np.int16(audio * 32767)
    wavfile.write(filename, sample_rate, audio_int)
    print(f"Generated {filename}")

def generate_soft_swish(filename, sample_rate=44100):
    duration = 0.6
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    # White noise
    noise = np.random.normal(0, 1, len(t))
    # Bandpass filter (wind sound)
    b, a = scipy.signal.butter(4, [200, 2000], btype='bandpass', fs=sample_rate)
    filtered = scipy.signal.lfilter(b, a, noise)
    # Envelope: soft fade in and fade out
    envelope = np.sin(np.pi * t / duration) ** 2
    audio = filtered * envelope
    # Normalize to 0.5 peak
    audio = audio / np.max(np.abs(audio)) * 0.5
    save_wav(filename, audio, sample_rate)

def generate_glitch(filename, sample_rate=44100):
    duration = 0.15
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    audio = np.zeros_like(t)
    
    # Generate multiple short random bursts of sine waves with random frequencies
    num_bursts = 5
    for _ in range(num_bursts):
        start_idx = np.random.randint(0, len(t) - 500)
        dur_idx = np.random.randint(200, 1000)
        freq = np.random.uniform(500, 3000)
        idx_range = np.arange(dur_idx)
        burst = np.sin(2 * np.pi * freq * idx_range / sample_rate)
        
        # apply square distortion
        burst = np.sign(burst) * 0.5
        
        end_idx = min(start_idx + dur_idx, len(t))
        audio[start_idx:end_idx] += burst[:end_idx - start_idx]
        
    # Add random static noise
    noise = np.random.normal(0, 0.2, len(t))
    audio += noise
    
    # Envelope
    envelope = np.exp(-t * 15)
    audio = audio * envelope
    audio = audio / np.max(np.abs(audio)) * 0.4
    save_wav(filename, audio, sample_rate)

def generate_sub_drop(filename, sample_rate=44100):
    duration = 2.0
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    # Pitch drop from 60Hz down to 20Hz
    freq = np.linspace(60, 20, len(t))
    audio = np.sin(2 * np.pi * freq * t)
    # Add some harmonics for presence on small speakers
    audio += 0.2 * np.sin(2 * np.pi * (freq * 2) * t)
    # Envelope: fast attack, slow release
    envelope = np.exp(-t * 1.5)
    audio = audio * envelope
    audio = audio / np.max(np.abs(audio)) * 0.8
    save_wav(filename, audio, sample_rate)

def generate_heartbeat(filename, sample_rate=44100):
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    audio = np.zeros_like(t)
    
    def add_thump(start_sec):
        thump_dur = 0.2
        start_idx = int(start_sec * sample_rate)
        thump_t = np.linspace(0, thump_dur, int(sample_rate * thump_dur), False)
        freq = np.linspace(50, 30, len(thump_t))
        thump = np.sin(2 * np.pi * freq * thump_t)
        # Lowpass filter the thump to make it muffled
        b, a = scipy.signal.butter(2, 100, btype='lowpass', fs=sample_rate)
        thump = scipy.signal.lfilter(b, a, thump)
        envelope = np.sin(np.pi * thump_t / thump_dur)
        thump = thump * envelope
        end_idx = min(start_idx + len(thump), len(t))
        audio[start_idx:end_idx] += thump[:end_idx - start_idx]

    add_thump(0.1)
    add_thump(0.35) # lub-dub
    
    audio = audio / np.max(np.abs(audio)) * 0.6
    save_wav(filename, audio, sample_rate)

def generate_soft_tick(filename, sample_rate=44100):
    duration = 0.05
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    # Short click (broadband noise heavily lowpassed)
    noise = np.random.normal(0, 1, len(t))
    b, a = scipy.signal.butter(2, 5000, btype='lowpass', fs=sample_rate)
    tick = scipy.signal.lfilter(b, a, noise)
    
    # Very fast exponential decay
    envelope = np.exp(-t * 200)
    audio = tick * envelope
    audio = audio / np.max(np.abs(audio)) * 0.4
    save_wav(filename, audio, sample_rate)

def generate_rain_noise(filename, sample_rate=44100):
    duration = 5.0
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    # Rain is mostly pink/brown noise
    noise = np.random.normal(0, 1, len(t))
    # Lowpass filter to make it muffled
    b, a = scipy.signal.butter(1, 1500, btype='lowpass', fs=sample_rate)
    rain = scipy.signal.lfilter(b, a, noise)
    
    # Add slow volume modulation (wind gusts)
    modulation = 0.7 + 0.3 * np.sin(2 * np.pi * 0.2 * t)
    rain = rain * modulation
    
    rain = rain / np.max(np.abs(rain)) * 0.3
    save_wav(filename, rain, sample_rate)

if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "music")
    os.makedirs(out_dir, exist_ok=True)
    
    generate_soft_swish(os.path.join(out_dir, "soft_swish.wav"))
    generate_glitch(os.path.join(out_dir, "glitch.wav"))
    generate_sub_drop(os.path.join(out_dir, "sub_drop.wav"))
    generate_heartbeat(os.path.join(out_dir, "heartbeat.wav"))
    generate_soft_tick(os.path.join(out_dir, "soft_tick.wav"))
    generate_rain_noise(os.path.join(out_dir, "rain_noise.wav"))
    print("All advanced SFX generated successfully.")

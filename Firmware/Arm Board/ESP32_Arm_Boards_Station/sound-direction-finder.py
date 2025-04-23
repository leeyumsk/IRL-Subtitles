#!/usr/bin/env python3
import numpy as np
import requests
import struct
import time
import matplotlib.pyplot as plt
from scipy import signal
from scipy.io import wavfile
import sys
import matplotlib.animation as animation
from mpl_toolkits.mplot3d import Axes3D

# ESP32 settings
ESP32_IP = "192.168.4.1"  # Default IP for ESP32 in AP mode
AUDIO_ENDPOINT = f"http://{ESP32_IP}/ach1"
SAMPLE_RATE = 24000
BITS_PER_SAMPLE = 16
CHANNELS = 4

# Microphone array geometry (in meters) - assumed square configuration
# Adjust these values based on your actual microphone placement
MIC_POSITIONS = np.array([
    [-0.05, -0.05, 0],  # Mic 0 (I2S0 Left)
    [0.05, -0.05, 0],   # Mic 1 (I2S0 Right)
    [-0.05, 0.05, 0],   # Mic 2 (I2S1 Left)
    [0.05, 0.05, 0]     # Mic 3 (I2S1 Right)
])

# Speed of sound in air (m/s)
SOUND_SPEED = 343.0

# Buffer size for processing
PROCESS_SIZE = 8192  # Should match the ESP's buffer size

# Visualization settings
PLOT_UPDATE_INTERVAL = 100  # milliseconds


def read_audio_stream(chunk_size=PROCESS_SIZE*CHANNELS*2):
    """
    Generator function to read audio chunks from the ESP32 stream.
    Each chunk contains interleaved samples from all 4 microphones.
    """
    try:
        response = requests.get(AUDIO_ENDPOINT, stream=True)
        if response.status_code != 200:
            print(f"Error connecting to ESP32: {response.status_code}")
            return

        buffer = bytearray()
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                buffer.extend(chunk)
                while len(buffer) >= chunk_size:
                    yield buffer[:chunk_size]
                    buffer = buffer[chunk_size:]

    except requests.exceptions.RequestException as e:
        print(f"Connection error: {e}")
        return


def parse_audio_data(raw_data):
    """
    Parse raw audio data into 4 separate channels.
    The data is assumed to be interleaved 16-bit samples.
    """
    # Convert bytes to 16-bit integers
    samples = np.frombuffer(raw_data, dtype=np.int16)
    
    # Reshape to get interleaved channels
    # Format: [mic0, mic1, mic2, mic3, mic0, mic1, mic2, mic3, ...]
    samples = samples.reshape(-1, CHANNELS)
    
    # Extract individual channels
    channels = [samples[:, i] for i in range(CHANNELS)]
    
    return channels


def compute_cross_correlation(signal1, signal2):
    """
    Compute the cross-correlation between two signals to find the time delay.
    """
    correlation = signal.correlate(signal1, signal2, mode='full')
    lags = signal.correlation_lags(len(signal1), len(signal2), mode='full')
    lag = lags[np.argmax(correlation)]
    
    return lag


def estimate_tdoa(channels):
    """
    Estimate Time Difference of Arrival (TDOA) between microphone pairs.
    Returns the time delays in samples.
    """
    # Reference mic is mic0 (channels[0])
    time_delays = np.zeros(len(channels))
    
    for i in range(1, len(channels)):
        lag = compute_cross_correlation(channels[0], channels[i])
        time_delays[i] = lag
    
    return time_delays


def tdoa_to_direction(time_delays):
    """
    Convert time delays to a direction vector using multilateration.
    Returns a unit vector pointing toward the sound source.
    """
    # Convert time delays from samples to seconds
    time_delays_sec = time_delays / SAMPLE_RATE
    
    # Convert time delays to distance differences (meters)
    distance_diffs = time_delays_sec * SOUND_SPEED
    
    # Simple direction finding for 3D space
    # This is a simplified approach using the time differences directly
    
    # For a more accurate approach, we would use multilateration algorithms
    # like least squares minimization to find the source position
    
    # Weights based on the confidence in each measurement
    # (could be based on correlation strength, signal energy, etc.)
    weights = np.ones(len(time_delays))
    weights[0] = 0  # No delay for reference mic
    
    # Estimated direction vector using weighted microphone positions
    direction = np.zeros(3)
    for i in range(1, len(time_delays)):
        if abs(time_delays[i]) > 0:
            # Direction from mic0 to mici adjusted by the time delay
            vec = MIC_POSITIONS[i] - MIC_POSITIONS[0]
            # Adjust based on whether sound arrived earlier or later
            sign = -1 if time_delays[i] > 0 else 1
            direction += sign * vec * weights[i]
    
    # Normalize to get unit vector
    norm = np.linalg.norm(direction)
    if norm > 0:
        direction = direction / norm
    else:
        # Default direction if we can't determine
        direction = np.array([0, 0, 1])  # Pointing up
    
    return direction


def apply_bandpass_filter(channels, low_freq=300, high_freq=3000):
    """
    Apply a bandpass filter to focus on the frequency range of interest.
    """
    nyquist = 0.5 * SAMPLE_RATE
    low = low_freq / nyquist
    high = high_freq / nyquist
    
    # Design filter
    b, a = signal.butter(4, [low, high], btype='band')
    
    # Apply filter to each channel
    filtered_channels = [signal.lfilter(b, a, channel) for channel in channels]
    
    return filtered_channels


def setup_visualization():
    """
    Set up the 3D visualization for the direction vector.
    """
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    # Plot microphone positions
    ax.scatter(MIC_POSITIONS[:, 0], MIC_POSITIONS[:, 1], MIC_POSITIONS[:, 2], 
               color='blue', s=100, label='Microphones')
    
    # Initial vector (will be updated)
    vector = ax.quiver(0, 0, 0, 0, 0, 1, color='red', length=0.2, 
                       arrow_length_ratio=0.3, linewidth=3)
    
    # Set plot limits and labels
    ax.set_xlim(-0.3, 0.3)
    ax.set_ylim(-0.3, 0.3)
    ax.set_zlim(-0.1, 0.5)
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')
    ax.set_zlabel('Z (m)')
    ax.set_title('Sound Direction')
    ax.legend()
    
    return fig, ax, vector


def update_vector(vector, direction):
    """
    Update the 3D vector visualization.
    """
    vector.set_segments([[[0, 0, 0], direction * 0.2]])  # Scale for visibility
    return vector,


def save_to_wav(channels, filename="captured_audio.wav"):
    """
    Save the captured audio to a WAV file for debugging.
    """
    # Interleave channels
    interleaved = np.empty((len(channels[0]) * len(channels),), dtype=np.int16)
    for i in range(len(channels[0])):
        for j in range(len(channels)):
            interleaved[i * len(channels) + j] = channels[j][i]
    
    wavfile.write(filename, SAMPLE_RATE, interleaved)
    print(f"Saved audio to {filename}")


def main():
    """
    Main function to process audio stream and calculate direction.
    """
    print("Starting sound direction finder...")
    print(f"Connecting to ESP32 at {AUDIO_ENDPOINT}")
    print(f"Microphone positions:")
    for i, pos in enumerate(MIC_POSITIONS):
        print(f"  Mic {i}: ({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})")
    
    # Set up visualization
    fig, ax, vector = setup_visualization()
    
    # For animation
    directions_buffer = []
    buffer_size = 5  # Average over this many direction calculations
    
    def process_frame(frame_num):
        nonlocal directions_buffer
        
        try:
            # Get next chunk of audio data
            raw_data = next(audio_stream)
            
            # Parse into channels
            channels = parse_audio_data(raw_data)
            
            # Apply bandpass filter to focus on speech frequencies
            filtered_channels = apply_bandpass_filter(channels)
            
            # Estimate time delays
            time_delays = estimate_tdoa(filtered_channels)
            
            # Calculate direction vector
            direction = tdoa_to_direction(time_delays)
            
            # Smooth direction by averaging recent directions
            directions_buffer.append(direction)
            if len(directions_buffer) > buffer_size:
                directions_buffer.pop(0)
            
            avg_direction = np.mean(directions_buffer, axis=0)
            avg_direction = avg_direction / np.linalg.norm(avg_direction)
            
            # Display direction
            print(f"\rDirection: [{avg_direction[0]:.2f}, {avg_direction[1]:.2f}, {avg_direction[2]:.2f}]", end="")
            
            # Update visualization
            update_vector(vector, avg_direction)
            
            return vector,
            
        except StopIteration:
            print("\nAudio stream ended")
            plt.close()
            sys.exit(0)
        except Exception as e:
            print(f"\nError: {e}")
            return vector,
    
    # Start the audio stream
    audio_stream = read_audio_stream()
    
    # Set up animation
    ani = animation.FuncAnimation(fig, process_frame, interval=PLOT_UPDATE_INTERVAL, blit=True)
    
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()

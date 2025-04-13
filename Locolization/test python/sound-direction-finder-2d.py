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
import argparse
import threading
import queue
import socket
from matplotlib.patches import Circle

# ESP32 settings (configurable via command line args)
DEFAULT_ESP32_IP = "192.168.4.1"  # Default IP for ESP32 in AP mode
AUDIO_ENDPOINT = "/ach1"
SAMPLE_RATE = 24000
BITS_PER_SAMPLE = 16
CHANNELS = 4

# Microphone array geometry (in meters) - assumed square configuration
# Using only x and y coordinates for 2D representation
MIC_POSITIONS = np.array([
    [-0.075, -0.075, 0],  # Mic 0 (I2S0 Left)
    [-0.075, 0.075, 0],   # Mic 1 (I2S0 Right)
    [0.075, 0.075, 0],    # Mic 2 (I2S1 Left)
    [0.075, -0.075, 0]    # Mic 3 (I2S1 Right)
])

# Speed of sound in air (m/s)
SOUND_SPEED = 343.0

# Buffer size for processing
PROCESS_SIZE = 8192  # Should match the ESP's buffer size

# Visualization settings
PLOT_UPDATE_INTERVAL = 200  # milliseconds

# Queue for communication between threads
audio_queue = queue.Queue(maxsize=5)
direction_queue = queue.Queue(maxsize=5)
stop_event = threading.Event()


def read_audio_stream(ip_address, port=80, chunk_size=PROCESS_SIZE*CHANNELS*2):
    """
    Thread function to read audio chunks from the ESP32 stream.
    Each chunk contains interleaved samples from all 4 microphones.
    Puts data in audio_queue.
    """
    url = f"http://{ip_address}:{port}{AUDIO_ENDPOINT}"
    print(f"Connecting to ESP32 at {url}")
    
    retry_count = 0
    max_retries = 5
    retry_delay = 2  # seconds
    
    while not stop_event.is_set() and retry_count < max_retries:
        try:
            response = requests.get(url, stream=True, timeout=5)
            if response.status_code != 200:
                print(f"Error connecting to ESP32: {response.status_code}")
                retry_count += 1
                time.sleep(retry_delay)
                continue

            # Reset retry count on successful connection
            retry_count = 0
            print("Connected to audio stream")
            
            buffer = bytearray()
            for chunk in response.iter_content(chunk_size=chunk_size):
                if stop_event.is_set():
                    break
                    
                if chunk:
                    buffer.extend(chunk)
                    while len(buffer) >= chunk_size:
                        # Try to put data in queue - non-blocking
                        try:
                            audio_queue.put(buffer[:chunk_size], block=False)
                            buffer = buffer[chunk_size:]
                        except queue.Full:
                            # Queue is full, discard oldest data
                            try:
                                audio_queue.get_nowait()
                                audio_queue.put(buffer[:chunk_size], block=False)
                                buffer = buffer[chunk_size:]
                            except:
                                # If still having issues, just continue
                                pass

        except (requests.exceptions.RequestException, socket.error) as e:
            print(f"Connection error: {e}")
            retry_count += 1
            if retry_count < max_retries:
                print(f"Retrying in {retry_delay} seconds (attempt {retry_count}/{max_retries})...")
                time.sleep(retry_delay)
            else:
                print(f"Failed to connect after {max_retries} attempts")
                stop_event.set()
                
    print("Audio stream reader thread ending")


def parse_audio_data(raw_data):
    """
    Parse raw audio data into 4 separate channels.
    The data is assumed to be interleaved 16-bit samples.
    """
    try:
        # Convert bytes to 16-bit integers
        samples = np.frombuffer(raw_data, dtype=np.int16)
        
        # Check if we have enough samples
        if len(samples) < CHANNELS:
            return [np.zeros(1) for _ in range(CHANNELS)]
        
        # Reshape to get interleaved channels
        # Format: [mic0, mic1, mic2, mic3, mic0, mic1, mic2, mic3, ...]
        # Ensure sample count is divisible by CHANNELS
        usable_samples = (len(samples) // CHANNELS) * CHANNELS
        samples = samples[:usable_samples].reshape(-1, CHANNELS)
        
        # Extract individual channels
        channels = [samples[:, i] for i in range(CHANNELS)]
        
        return channels
    except Exception as e:
        print(f"Error parsing audio data: {e}")
        return [np.zeros(1) for _ in range(CHANNELS)]


def compute_cross_correlation(signal1, signal2):
    """
    Compute the cross-correlation between two signals to find the time delay.
    """
    try:
        # Ensure signals have data
        if len(signal1) < 10 or len(signal2) < 10:
            return 0
            
        correlation = signal.correlate(signal1, signal2, mode='full')
        lags = signal.correlation_lags(len(signal1), len(signal2), mode='full')
        lag = lags[np.argmax(correlation)]
        
        return lag
    except Exception as e:
        print(f"Error in cross-correlation: {e}")
        return 0


def estimate_tdoa(channels):
    """
    Estimate Time Difference of Arrival (TDOA) between microphone pairs.
    Returns the time delays in samples.
    """
    time_delays = np.zeros(len(channels))
    
    try:
        # Reference mic is mic0 (channels[0])
        for i in range(1, len(channels)):
            lag = compute_cross_correlation(channels[0], channels[i])
            time_delays[i] = lag
    except Exception as e:
        print(f"Error estimating TDOA: {e}")
    
    return time_delays


def tdoa_to_direction(time_delays):
    """
    Convert time delays to a 2D direction vector.
    Returns a unit vector pointing toward the sound source.
    """
    try:
        # Convert time delays from samples to seconds
        time_delays_sec = time_delays / SAMPLE_RATE
        
        # Convert time delays to distance differences (meters)
        distance_diffs = time_delays_sec * SOUND_SPEED
        
        # Simple direction finding for 2D space
        # Weights based on the confidence in each measurement
        weights = np.ones(len(time_delays))
        weights[0] = 0  # No delay for reference mic
        
        # Estimated 2D direction vector using weighted microphone positions
        direction = np.zeros(2)  # Just x and y
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
            direction = np.array([1, 0])  # Default to pointing right
        
        return direction
    except Exception as e:
        print(f"Error calculating direction: {e}")
        return np.array([1, 0])  # Default to pointing right


def apply_bandpass_filter(channels, low_freq=300, high_freq=3000):
    """
    Apply a bandpass filter to focus on the frequency range of interest.
    """
    try:
        nyquist = 0.5 * SAMPLE_RATE
        low = low_freq / nyquist
        high = high_freq / nyquist
        
        # Design filter
        b, a = signal.butter(4, [low, high], btype='band')
        
        # Apply filter to each channel
        filtered_channels = [signal.lfilter(b, a, channel) for channel in channels]
        
        return filtered_channels
    except Exception as e:
        print(f"Error applying bandpass filter: {e}")
        return channels


def setup_visualization():
    """
    Set up the 2D visualization for the direction vector and microphone positions.
    """
    fig, ax = plt.subplots(figsize=(10, 10))
    
    # Plot microphone positions
    ax.scatter(MIC_POSITIONS[:, 0], MIC_POSITIONS[:, 1], color='blue', s=100, label='Microphones')
    
    # Add microphone labels
    for i, pos in enumerate(MIC_POSITIONS):
        ax.text(pos[0], pos[1], f' Mic {i}', fontsize=9)
    
    # Add a circular boundary to represent detection range
    circle = Circle((0, 0), 0.2, fill=False, linestyle='--', color='gray', alpha=0.5)
    ax.add_patch(circle)
    
    # Initial vector (will be updated)
    vector = ax.quiver(0, 0, 1, 0, color='red', scale=2, scale_units='xy', angles='xy', width=0.008)
    
    # Set plot limits and labels
    ax.set_xlim(-0.25, 0.25)
    ax.set_ylim(-0.25, 0.25)
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')
    ax.set_title('Sound Direction (Top View)')
    ax.grid(True, linestyle='--', alpha=0.7)
    ax.set_aspect('equal')
    ax.legend(loc='upper right')
    
    # Text display for vector components and angle
    text = ax.text(0.02, 0.96, "", transform=ax.transAxes, 
                 bbox=dict(facecolor='white', alpha=0.7))
    
    return fig, ax, vector, text, circle


def calculate_angle(vector):
    """
    Calculate the angle in degrees from the unit vector.
    0 degrees is to the right (positive x), 90 degrees is up (positive y).
    """
    angle_rad = np.arctan2(vector[1], vector[0])
    angle_deg = np.degrees(angle_rad)
    if angle_deg < 0:
        angle_deg += 360
    return angle_deg


def audio_processor_thread():
    """
    Thread function to process audio data from the queue.
    Calculates direction vectors and puts them in the direction queue.
    """
    directions_buffer = []
    buffer_size = 3  # Average over this many direction calculations
    
    while not stop_event.is_set():
        try:
            # Get audio data from queue with timeout
            raw_data = audio_queue.get(timeout=1)
            
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
            
            # Put direction in queue - non-blocking
            try:
                direction_queue.put(avg_direction, block=False)
            except queue.Full:
                # If queue is full, remove oldest item
                try:
                    direction_queue.get_nowait()
                    direction_queue.put(avg_direction, block=False)
                except:
                    pass
                    
        except queue.Empty:
            # No data in queue, just continue
            continue
        except Exception as e:
            print(f"Error in audio processor: {e}")
            time.sleep(0.1)  # Short delay to prevent CPU hogging in error case
    
    print("Audio processor thread ending")


def update_visualization(frame_num, vector, text):
    """
    Update function for the animation.
    Gets direction from queue and updates the plot.
    """
    try:
        # Try to get a direction from the queue
        try:
            direction = direction_queue.get_nowait()
            
            # Update the vector
            vector.set_UVC(direction[0], direction[1])
            
            # Calculate angle
            angle = calculate_angle(direction)
            
            # Update text display
            text.set_text(f"Direction: [{direction[0]:.2f}, {direction[1]:.2f}]\nAngle: {angle:.1f}°")
            
            # Print to console as well
            print(f"\rDirection: [{direction[0]:.2f}, {direction[1]:.2f}] | Angle: {angle:.1f}°", end="")
            
        except queue.Empty:
            # No new direction available
            pass
            
        return vector, text
        
    except Exception as e:
        print(f"\nError updating visualization: {e}")
        return vector, text


def cleanup():
    """Clean up resources and threads."""
    stop_event.set()
    print("\nStopping all threads...")
    time.sleep(1)  # Give threads time to terminate


def main():
    """
    Main function to process audio stream and calculate direction.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Sound Direction Finder")
    parser.add_argument("-i", "--ip", default=DEFAULT_ESP32_IP, help=f"ESP32 IP address (default: {DEFAULT_ESP32_IP})")
    parser.add_argument("-p", "--port", type=int, default=80, help="ESP32 HTTP port (default: 80)")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()
    
    print("Starting sound direction finder...")
    print(f"Connecting to ESP32 at http://{args.ip}:{args.port}{AUDIO_ENDPOINT}")
    print(f"Microphone positions:")
    for i, pos in enumerate(MIC_POSITIONS):
        print(f"  Mic {i}: ({pos[0]:.2f}, {pos[1]:.2f})")
    
    try:
        # Start audio stream reader thread
        stream_thread = threading.Thread(target=read_audio_stream, args=(args.ip, args.port), daemon=True)
        stream_thread.start()
        
        # Start audio processor thread
        processor_thread = threading.Thread(target=audio_processor_thread, daemon=True)
        processor_thread.start()
        
        # Set up visualization
        fig, ax, vector, text, circle = setup_visualization()
        
        # Set up animation with explicit frame count to avoid warning
        ani = animation.FuncAnimation(
            fig, 
            update_visualization, 
            fargs=(vector, text),
            interval=PLOT_UPDATE_INTERVAL, 
            blit=True,
            save_count=100,  # Limit cached frames
            cache_frame_data=False  # Don't cache frame data
        )
        
        # Show the plot - this will block until the window is closed
        plt.tight_layout()
        plt.show()
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        cleanup()
        print("Sound direction finder stopped")


if __name__ == "__main__":
    main()

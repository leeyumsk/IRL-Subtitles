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
from matplotlib.widgets import TextBox

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

# Default microphone gains (adjustable via command line or UI)
DEFAULT_MIC_GAINS = [1.0, 1.0, 1.0, 1.0]  # Default gain of 1.0 for each mic
mic_gains = DEFAULT_MIC_GAINS.copy()  # Working copy that can be adjusted at runtime

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
        
        # Reshape to get channels
        usable_samples = (len(samples) // CHANNELS) * CHANNELS
        samples = samples[:usable_samples].reshape(-1, CHANNELS)
        
        # Extract individual channels and apply gains
        channels = []
        for i in range(CHANNELS):
            # Apply gain to each channel
            channels.append(samples[:, i] * mic_gains[i])
        
        return channels
    except Exception as e:
        print(f"Error parsing audio data: {e}")
        return [np.zeros(1) for _ in range(CHANNELS)]


def is_sound_active(channels, threshold=35):
    """
    Check if there is significant sound activity in the microphone inputs.
    Returns True if sound energy is above threshold.
    """
    try:
        # Calculate average energy across all channels
        energies = [np.sqrt(np.mean(np.square(channel))) for channel in channels]
        avg_energy = np.mean(energies)
        
        # Debug output to see energy levels
        print(f"\rEnergies: {[round(e, 2) for e in energies]}, Avg: {round(avg_energy, 2)}, Threshold: {threshold}", end="")
        
        return avg_energy > threshold
    except Exception as e:
        print(f"Error in sound activity detection: {e}")
        return False


def compute_cross_correlation(signal1, signal2):
    """
    Compute the cross-correlation between two signals to find the time delay.
    Uses GCC-PHAT algorithm for better performance in noisy environments.
    """
    try:
        # Ensure signals have data
        if len(signal1) < 10 or len(signal2) < 10:
            return 0
            
        # Apply window function to reduce edge effects
        window = signal.windows.hann(len(signal1))
        signal1 = signal1 * window
        signal2 = signal2[:len(window)] * window
        
        # GCC-PHAT method
        X1 = np.fft.rfft(signal1)
        X2 = np.fft.rfft(signal2)
        X1X2 = X1 * np.conj(X2)
        
        # Phase transform
        X1X2_abs = np.abs(X1X2) + 1e-10  # Avoid division by zero
        X1X2_normalized = X1X2 / X1X2_abs
        
        # Inverse FFT to get correlation
        correlation = np.fft.irfft(X1X2_normalized)
        
        # Find the peak
        max_index = np.argmax(correlation)
        
        # Convert to proper lag
        lag = max_index
        if max_index > len(correlation) // 2:
            lag = max_index - len(correlation)
            
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


def tdoa_to_direction(time_delays, sound_active=False):
    """
    Convert time delays to a 2D direction vector.
    Returns a unit vector pointing toward the sound source,
    or [0, 0] if no sound is active.
    """
    try:
        # If no sound is active, return zero vector (no direction)
        if not sound_active:
            return np.array([0, 0])
        
        # Convert time delays from samples to seconds
        time_delays_sec = time_delays / SAMPLE_RATE
        
        # Convert time delays to distance differences (meters)
        distance_diffs = time_delays_sec * SOUND_SPEED
        
        # Calculate confidence for each mic pair based on correlation strength
        confidences = np.abs(time_delays)
        confidences = confidences / (np.max(confidences) + 1e-10)
        
        # Estimated 2D direction vector
        direction = np.zeros(2)  # Just x and y
        total_weight = 0
        
        for i in range(1, len(time_delays)):
            if abs(time_delays[i]) > 1:  # Ignore very small delays
                # Direction from mic0 to mici
                vec = MIC_POSITIONS[i][:2] - MIC_POSITIONS[0][:2]  # Just x,y components
                
                # Weight by confidence and use appropriate sign
                sign = -1 if time_delays[i] > 0 else 1
                weight = confidences[i]
                
                direction += sign * vec[:2] * weight
                total_weight += weight
        
        # Normalize if we have any contribution
        if total_weight > 0 and np.linalg.norm(direction) > 0:
            direction = direction / np.linalg.norm(direction)
        else:
            # No significant direction detected
            direction = np.array([0, 0])
        
        return direction
    except Exception as e:
        print(f"Error calculating direction: {e}")
        return np.array([0, 0])  # Return zero vector on error


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
    Also adds numerical inputs for microphone gain control.
    """
    fig = plt.figure(figsize=(10, 10))
    
    # Create a grid layout: 3 rows (main plot + controls), 1 column
    gs = fig.add_gridspec(3, 1, height_ratios=[4, 0.5, 0.5])
    
    # Direction plot
    ax = fig.add_subplot(gs[0])
    
    # Plot microphone positions
    ax.scatter(MIC_POSITIONS[:, 0], MIC_POSITIONS[:, 1], color='blue', s=100, label='Microphones')
    
    # Add microphone labels
    for i, pos in enumerate(MIC_POSITIONS):
        ax.text(pos[0], pos[1], f' Mic {i}', fontsize=9)
    
    # Add a circular boundary to represent detection range
    circle = Circle((0, 0), 0.2, fill=False, linestyle='--', color='gray', alpha=0.5)
    ax.add_patch(circle)
    
    # Initial vector (will be updated)
    vector = ax.quiver(0, 0, 0, 0, color='red', scale=2, scale_units='xy', angles='xy', width=0.008)
    
    # Set plot limits and labels
    ax.set_xlim(-1, 1)
    ax.set_ylim(-1, 1)
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')
    ax.set_title('Sound Direction (Top View)')
    ax.grid(True, linestyle='--', alpha=0.7)
    ax.set_aspect('equal')
    ax.legend(loc='upper right')
    
    # Text display for vector components and angle
    text = ax.text(0.02, 0.96, "No sound detected", transform=ax.transAxes, 
                 bbox=dict(facecolor='white', alpha=0.7))
    
    # Add numerical text inputs for mic gain adjustment
    mic_gain_textboxes = []
    
    # Set up title for gain controls
    ax_input_title = fig.add_subplot(gs[1])
    ax_input_title.set_title("Microphone Gain Control")
    ax_input_title.axis('off')  # Hide axes, just show the title
    
    # First row of text inputs (Mic 0 and 1)
    mic0_label_ax = plt.axes([0.15, 0.65, 0.1, 0.03])
    mic0_label_ax.text(0.5, 0.5, 'Mic 0 Gain:', horizontalalignment='right', verticalalignment='center')
    mic0_label_ax.axis('off')
    
    mic0_textbox_ax = plt.axes([0.25, 0.65, 0.1, 0.03])
    mic0_textbox = TextBox(mic0_textbox_ax, '', initial=str(mic_gains[0]))
    
    mic1_label_ax = plt.axes([0.55, 0.65, 0.1, 0.03])
    mic1_label_ax.text(0.5, 0.5, 'Mic 1 Gain:', horizontalalignment='right', verticalalignment='center')
    mic1_label_ax.axis('off')
    
    mic1_textbox_ax = plt.axes([0.65, 0.65, 0.1, 0.03])
    mic1_textbox = TextBox(mic1_textbox_ax, '', initial=str(mic_gains[1]))
    
    # Second row of text inputs (Mic 2 and 3)
    mic2_label_ax = plt.axes([0.15, 0.55, 0.1, 0.03])
    mic2_label_ax.text(0.5, 0.5, 'Mic 2 Gain:', horizontalalignment='right', verticalalignment='center')
    mic2_label_ax.axis('off')
    
    mic2_textbox_ax = plt.axes([0.25, 0.55, 0.1, 0.03])
    mic2_textbox = TextBox(mic2_textbox_ax, '', initial=str(mic_gains[2]))
    
    mic3_label_ax = plt.axes([0.55, 0.55, 0.1, 0.03])
    mic3_label_ax.text(0.5, 0.5, 'Mic 3 Gain:', horizontalalignment='right', verticalalignment='center')
    mic3_label_ax.axis('off')
    
    mic3_textbox_ax = plt.axes([0.65, 0.55, 0.1, 0.03])
    mic3_textbox = TextBox(mic3_textbox_ax, '', initial=str(mic_gains[3]))
    
    # Apply button to update gains
    apply_button_ax = plt.axes([0.4, 0.5, 0.2, 0.04])
    apply_button = plt.Button(apply_button_ax, 'Apply Gains')
    
    # Status text to show current gains or input errors
    status_text_ax = plt.axes([0.3, 0.45, 0.4, 0.03])
    status_text = status_text_ax.text(0.5, 0.5, "Current gains: " + str(mic_gains), 
                                     horizontalalignment='center', verticalalignment='center')
    status_text_ax.axis('off')
    
    # Update function for text inputs
    def update_mic_gain(event):
        try:
            # Try to parse the input values as floats
            new_gains = [
                float(mic0_textbox.text),
                float(mic1_textbox.text),
                float(mic2_textbox.text),
                float(mic3_textbox.text)
            ]
            
            # Update the global mic_gains
            global mic_gains
            mic_gains = new_gains
            
            # Update status text
            status_text.set_text(f"Gains updated: {mic_gains}")
            print(f"Updated mic gains: {mic_gains}")
            
        except ValueError:
            # Display error if input cannot be converted to float
            status_text.set_text("Error: Enter valid numbers")
            print("Error: Invalid gain value entered")
    
    # Connect apply button to update function
    apply_button.on_clicked(update_mic_gain)
    
    mic_gain_textboxes.extend([mic0_textbox, mic1_textbox, mic2_textbox, mic3_textbox])
    
    plt.tight_layout()
    
    return fig, ax, vector, text, circle, mic_gain_textboxes, status_text


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
    buffer_size = 5  # Average over this many direction calculations
    energy_threshold = 35  # Adjust based on your microphone sensitivity
    
    while not stop_event.is_set():
        try:
            # Get audio data from queue with timeout
            raw_data = audio_queue.get(timeout=1)
            
            # Parse into channels
            channels = parse_audio_data(raw_data)
            
            # Check if sound is active
            sound_active = is_sound_active(channels, threshold=energy_threshold)
            
            # If no sound, put zero vector and continue
            if not sound_active:
                direction_queue.put(np.array([0, 0]), block=False)
                continue
                
            # Apply bandpass filter to focus on speech frequencies
            filtered_channels = apply_bandpass_filter(channels)
            
            # Estimate time delays
            time_delays = estimate_tdoa(filtered_channels)
            
            # Calculate direction vector
            direction = tdoa_to_direction(time_delays, sound_active)
            
            # Only add non-zero directions to the buffer
            if np.linalg.norm(direction) > 0:
                directions_buffer.append(direction)
                if len(directions_buffer) > buffer_size:
                    directions_buffer.pop(0)
                
                # Only average non-zero directions
                if len(directions_buffer) > 0:
                    avg_direction = np.mean(directions_buffer, axis=0)
                    # Only normalize if not zero
                    if np.linalg.norm(avg_direction) > 0:
                        avg_direction = avg_direction / np.linalg.norm(avg_direction)
                else:
                    avg_direction = np.array([0, 0])
            else:
                # Clear buffer if we detect no direction
                directions_buffer = []
                avg_direction = np.array([0, 0])
            
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
            time.sleep(0.1)  # Short delay to prevent CPU hogging
    
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
            
            # Check if direction is non-zero (sound detected)
            if np.linalg.norm(direction) > 0.01:
                # Update the vector
                vector.set_UVC(direction[0], direction[1])
                
                # Calculate angle
                angle = calculate_angle(direction)
                
                # Update text display
                text.set_text(f"Direction: [{direction[0]:.2f}, {direction[1]:.2f}]\nAngle: {angle:.1f}°")
                
                # Print to console as well
                print(f"\rSound detected! Direction: [{direction[0]:.2f}, {direction[1]:.2f}] | Angle: {angle:.1f}°", end="")
            else:
                # No sound, hide vector
                vector.set_UVC(0, 0)
                text.set_text("No sound detected")
                print("\rNo sound detected                                           ", end="")
            
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
    parser.add_argument("-t", "--threshold", type=int, default=500, help="Sound detection threshold (default: 500)")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug output")
    parser.add_argument("-g", "--gains", type=float, nargs=4, default=DEFAULT_MIC_GAINS, 
                        help="Initial microphone gains as 4 values (default: 1.0 1.0 1.0 1.0)")
    parser.add_argument("--low-freq", type=int, default=300, help="Low cutoff frequency for bandpass filter (default: 300Hz)")
    parser.add_argument("--high-freq", type=int, default=3000, help="High cutoff frequency for bandpass filter (default: 3000Hz)")
    args = parser.parse_args()
    
    # Set initial microphone gains
    global mic_gains
    mic_gains = args.gains
    
    print("Starting sound direction finder...")
    print(f"Connecting to ESP32 at http://{args.ip}:{args.port}{AUDIO_ENDPOINT}")
    print(f"Sound detection threshold: {args.threshold}")
    print(f"Initial microphone gains: {mic_gains}")
    print(f"Bandpass filter: {args.low_freq}Hz - {args.high_freq}Hz")
    print(f"Microphone positions:")
    for i, pos in enumerate(MIC_POSITIONS):
        print(f"  Mic {i}: ({pos[0]:.2f}, {pos[1]:.2f})")
    
    try:
        # Start audio stream reader thread
        stream_thread = threading.Thread(target=read_audio_stream, args=(args.ip, args.port), daemon=True)
        stream_thread.start()
        
        # Start audio processor thread with configurable threshold
        processor_thread = threading.Thread(
            target=audio_processor_thread,
            daemon=True
        )
        processor_thread.start()
        
        # Set up visualization
        fig, ax, vector, text, circle, textboxes, status_text = setup_visualization()
        
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
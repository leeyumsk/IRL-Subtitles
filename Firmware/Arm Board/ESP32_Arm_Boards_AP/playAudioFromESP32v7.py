# When connected to the ESP32-S3 wifi AP, this script can pull audio data from 4 microphones (4 channels)
# over WiFi from <ip>/ach1
# and save it as a WAV file

import numpy as np
import sounddevice as sd
import requests
import wave
import time
import datetime

# Audio configuration
SAMPLE_RATE = 24000
CHANNELS = 4
BYTES_PER_SAMPLE = 2
BUFFER_SIZE = 512  # We might need to adjust this
ESP32_IP = "192.168.4.1"  # IP address of the ESP32 (4-mic array)
AMPLIFICATION = 4  # Keep the working amplification

# Calculate expected data rates
BYTES_PER_SECOND = SAMPLE_RATE * BYTES_PER_SAMPLE * CHANNELS
EXPECTED_CHUNKS_PER_SECOND = BYTES_PER_SECOND / BUFFER_SIZE

def play_audio_chunk(chunk):
    """Play a chunk of audio data with amplitude adjustment."""
    if len(chunk) % 2 != 0:
        chunk = chunk[:-1]
    
    audio_samples = np.frombuffer(chunk, dtype=np.int16)
    audio_samples = audio_samples * AMPLIFICATION
    audio_samples = np.clip(audio_samples, -32768, 32767)
    
    # Do not uncomment this code unless testing
    # sd.play and sd.wait will cause the code to hang and you will not collect the audio well
    # sd.play(audio_samples, samplerate=SAMPLE_RATE)
    # sd.wait()

# allows for automatic unique filenames for recordings
def generate_filename():
    """Generate a filename using current date and time."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"audio_{timestamp}.wav"

def save_audio_to_wav(audio_buffer):
    """Save the audio data to a .wav file with amplitude adjustment and timestamped filename."""
    filename = generate_filename()
    
    audio_samples = np.frombuffer(audio_buffer, dtype=np.int16)
    audio_samples = audio_samples * AMPLIFICATION
    audio_samples = np.clip(audio_samples, -32768, 32767)
    audio_buffer = audio_samples.tobytes()
    
    with wave.open(filename, 'wb') as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(BYTES_PER_SAMPLE)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(audio_buffer)
    print(f"Audio data saved to {filename}")
    return filename

def main():
    try:
        url = f"http://{ESP32_IP}/ach1"
        print(f"Connecting to ESP32 at {url}")
        
        # Print expected rates
        print(f"\nExpected data rates:")
        print(f"Sample rate: {SAMPLE_RATE} Hz")
        print(f"Expected bytes per second: {BYTES_PER_SECOND}")
        print(f"Expected chunks per second: {EXPECTED_CHUNKS_PER_SECOND:.1f}")
        print(f"Buffer size: {BUFFER_SIZE} bytes")
        
        audio_buffer = bytearray()
        chunk_count = 0
        start_time = time.time()
        
        # Make request to audio endpoint
        response = requests.get(url, stream=True)
        
        if response.status_code != 200:
            print(f"Failed to connect to ESP32: {response.status_code}")
            return

        print("\nConnected to ESP32 audio stream")
        stream_start_time = time.time()
        last_stats_time = stream_start_time
        
        # Process the stream
        for chunk in response.iter_content(chunk_size=BUFFER_SIZE):
            if chunk:
                chunk_count += 1
                current_time = time.time()
                elapsed_time = current_time - stream_start_time
                
                # Print statistics every second
                # if current_time - last_stats_time >= 1.0:
                #     actual_data_rate = len(audio_buffer) / elapsed_time
                #     actual_chunks_per_sec = chunk_count / elapsed_time
                #     expected_data = BYTES_PER_SECOND * elapsed_time
                #     data_ratio = (len(audio_buffer) / expected_data) * 100
                    
                #     print(f"\nTiming Statistics:")
                #     print(f"Elapsed time: {elapsed_time:.1f} seconds")
                #     print(f"Expected data: {expected_data/1024:.1f} KB")
                #     print(f"Actual data: {len(audio_buffer)/1024:.1f} KB")
                #     print(f"Data ratio: {data_ratio:.1f}%")
                #     print(f"Chunks received: {chunk_count}")
                #     print(f"Chunks per second: {actual_chunks_per_sec:.1f}")
                #     print(f"Data rate: {actual_data_rate/1024:.1f} KB/s")
                    
                #     last_stats_time = current_time
                
                play_audio_chunk(chunk)
                audio_buffer.extend(chunk)
            else:
                print("No data received, continuing...")

    except KeyboardInterrupt:
        print("\nInterrupted by user. Saving recording...")
        if len(audio_buffer) > 0:
            elapsed_time = time.time() - stream_start_time
            expected_duration = len(audio_buffer) / BYTES_PER_SECOND
            actual_audio_duration = len(audio_buffer) / (SAMPLE_RATE * BYTES_PER_SAMPLE * CHANNELS)  # Duration of audio in buffer
            
            print(f"\nFinal Statistics:")
            print(f"Elapsed real time: {elapsed_time:.1f} seconds")
            print(f"Expected audio duration: {expected_duration:.1f} seconds")
            print(f"Actual audio duration: {actual_audio_duration:.1f} seconds")
            print(f"Ratio: {(expected_duration/actual_audio_duration)*100:.1f}%")
            # print(f"Average data rate: {len(audio_buffer)/elapsed_time/1024:.1f} KB/s")
            # print(f"Expected data rate: {BYTES_PER_SECOND/1024:.1f} KB/s")
            
            saved_filename = save_audio_to_wav(audio_buffer)
            print(f"Recording saved successfully as {saved_filename}.")
        print("Exiting...")
    except Exception as e:
        print(f"Error: {e}")
        if len(audio_buffer) > 0:
            saved_filename = save_audio_to_wav(audio_buffer)
            print(f"Recording saved successfully as {saved_filename}.")

if __name__ == "__main__":
    main()
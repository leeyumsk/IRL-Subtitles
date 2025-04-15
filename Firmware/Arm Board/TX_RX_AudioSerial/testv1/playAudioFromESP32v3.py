import serial
import numpy as np
import sounddevice as sd
import time

# Serial port configuration
BAUD_RATE = 115200
SERIAL_PORT = 'COM3'

# Audio configuration
SAMPLE_RATE = 24000  # Must match the sample rate from ESP32
CHANNELS = 1  # Mono audio
BYTES_PER_SAMPLE = 2  # 16-bit (2 bytes per sample)
SYNC_HEADER = b'\xAA\xBB\xCC\xDD'  # Sync header to detect
ENDING_FOOTER = b'\xDE\xAD\xBE\xEF'  # Ending footer to detect
HEADER_SIZE = len(SYNC_HEADER)
FOOTER_SIZE = len(ENDING_FOOTER)
BUFFER_SIZE = 1024  # Serial buffer read size

# Create a list to store audio data
audio_buffer = bytearray()

# Set up the serial port connection
ser = serial.Serial(
    port=SERIAL_PORT,
    baudrate=BAUD_RATE,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=5
)

def detect_sync_header(buffer):
    """Find the sync header in the incoming data."""
    sync_index = buffer.find(SYNC_HEADER)
    return sync_index

def detect_ending_footer(buffer):
    """Find the ending footer in the incoming data."""
    footer_index = buffer.find(ENDING_FOOTER)
    return footer_index

def play_audio_from_buffer(audio_buffer):
    """Play the audio from the buffer once data is collected."""
    # Convert the bytearray to numpy int16 array (assuming 16-bit audio samples)
    audio_samples = np.frombuffer(audio_buffer, dtype=np.int16)

    # Play the accumulated audio
    print(f"Playing {len(audio_samples)} samples.")
    sd.play(audio_samples, samplerate=SAMPLE_RATE)
    sd.wait()  # Wait for the playback to finish

try:
    print("Waiting for sync header...")
    sync_found = False
    footer_found = False

    while True:
        # Read data from the serial port
        data = ser.read(BUFFER_SIZE)

        if data:
            if not sync_found:
                # Look for sync header in the incoming data
                audio_buffer.extend(data)
                sync_index = detect_sync_header(audio_buffer)
                if sync_index != -1:
                    # Start recording after sync header is found
                    print("Sync header found. Starting to collect audio data...")
                    sync_found = True
                    audio_buffer = audio_buffer[sync_index + HEADER_SIZE:]  # Remove the sync header and preceding bytes
            else:
                # Append the data after the sync header is found
                audio_buffer.extend(data)

                # Check for the ending footer
                footer_index = detect_ending_footer(audio_buffer)
                if footer_index != -1:
                    # Stop recording when the footer is found
                    print("Ending footer found. Stopping audio collection.")
                    audio_buffer = audio_buffer[:footer_index]  # Remove the footer and anything after
                    footer_found = True

                # If footer is found, stop and play the audio
                if footer_found:
                    play_audio_from_buffer(audio_buffer)
                    break

        else:
            print("No data received, retrying...")

except KeyboardInterrupt:
    print("Interrupted by user. Exiting...")
finally:
    ser.close()
    print("Serial port closed.")

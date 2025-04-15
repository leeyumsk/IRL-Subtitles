import wave
import os

def convert_wav_to_c_array(wav_filename, output_filename):
    # Open the .wav file
    with wave.open(wav_filename, 'rb') as wav_file:
        # Extract audio file parameters
        params = wav_file.getparams()
        num_channels = params.nchannels
        sample_width = params.sampwidth
        frame_rate = params.framerate
        num_frames = params.nframes
        print(f"Channels: {num_channels}, Sample Width: {sample_width} bytes, Frame Rate: {frame_rate}, Frame Count: {num_frames}")

        # Read the frames of the .wav file
        audio_frames = wav_file.readframes(num_frames)

        # Convert raw audio data to byte array
        audio_data = bytearray(audio_frames)

        # Create a C array string
        c_array = ", ".join(f"0x{byte:02X}" for byte in audio_data)

        # Write to output header file
        with open(output_filename, 'w') as header_file:
            header_file.write(f"// Audio data converted from {wav_filename}\n\n")
            header_file.write("#ifndef AUDIO_DATA_H\n")
            header_file.write("#define AUDIO_DATA_H\n\n")
            header_file.write(f"#define audio_data_size {len(audio_data)}\n\n")
            header_file.write("const uint8_t audio_data[] = {\n")
            
            # Add the C array in chunks of 12 bytes per line for readability
            for i in range(0, len(audio_data), 12):
                header_file.write(", ".join(f"0x{byte:02X}" for byte in audio_data[i:i+12]))
                header_file.write(",\n")

            header_file.write("};\n\n")
            header_file.write("#endif // AUDIO_DATA_H\n")

        print(f"Audio data converted and saved to {output_filename}")

# Provide input and output file names
wav_filename = "testAudio.wav"  # Input WAV file
output_filename = "audio_data.h"  # Output C header file

convert_wav_to_c_array(wav_filename, output_filename)
